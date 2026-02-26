from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from redis.asyncio import Redis

from src.config.constants import (
    SESSION_LOCK_POLL_INTERVAL,
    SESSION_LOCK_TTL,
    SESSION_LOCK_WAIT_TIMEOUT,
)

logger = structlog.get_logger()


class SessionLockError(Exception):
    """Raised when the session lock cannot be acquired within the timeout."""


def _lock_key(session_id: str) -> str:
    return f"lock:session:{session_id}"


async def acquire_session_lock(
    redis_client: Redis,
    session_id: str,
    *,
    ttl: int = SESSION_LOCK_TTL,
    wait_timeout: float = SESSION_LOCK_WAIT_TIMEOUT,
) -> str:
    """Acquire a distributed lock for a session.

    Uses Redis SET NX EX — atomic "set if not exists" with expiry.
    Returns a unique token needed to release the lock.

    Raises SessionLockError if the lock cannot be acquired within
    wait_timeout seconds.
    """
    key = _lock_key(session_id)
    token = str(uuid.uuid4())
    elapsed = 0.0

    while elapsed < wait_timeout:
        # SET key token NX EX ttl — atomic, returns True if set
        acquired = await redis_client.set(key, token, nx=True, ex=ttl)
        if acquired:
            logger.debug(
                "session_lock_acquired",
                session_id=session_id,
                wait_ms=round(elapsed * 1000),
            )
            return token

        await asyncio.sleep(SESSION_LOCK_POLL_INTERVAL)
        elapsed += SESSION_LOCK_POLL_INTERVAL

    logger.warning(
        "session_lock_timeout",
        session_id=session_id,
        wait_timeout=wait_timeout,
    )
    raise SessionLockError(
        f"Could not acquire lock for session {session_id} "
        f"within {wait_timeout}s"
    )


async def release_session_lock(
    redis_client: Redis,
    session_id: str,
    token: str,
) -> None:
    """Release a session lock, but only if we own it.

    Compares the stored token to prevent releasing a lock that
    was acquired by a different request (e.g. after our lock
    expired and someone else took it).
    """
    key = _lock_key(session_id)
    stored = await redis_client.get(key)

    if stored == token:
        await redis_client.delete(key)
        logger.debug("session_lock_released", session_id=session_id)
    else:
        # Lock was already expired or taken by another request —
        # this is normal under high contention, not an error.
        logger.debug(
            "session_lock_already_released",
            session_id=session_id,
        )


@asynccontextmanager
async def session_lock(
    redis_client: Redis,
    session_id: str,
) -> AsyncIterator[None]:
    """Context manager for session locking.

    Usage:
        async with session_lock(redis_client, session_id):
            # process the request — only one at a time per session
    """
    token = await acquire_session_lock(redis_client, session_id)
    try:
        yield
    finally:
        await release_session_lock(redis_client, session_id, token)
