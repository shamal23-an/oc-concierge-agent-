from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.agent.session_lock import (
    SessionLockError,
    acquire_session_lock,
    release_session_lock,
    session_lock,
)


class TestAcquireSessionLock:
    """Test distributed lock acquisition."""

    async def test_acquires_on_first_try(self):
        redis = AsyncMock()
        redis.set.return_value = True  # NX succeeds

        token = await acquire_session_lock(redis, "sess-1")

        assert isinstance(token, str)
        assert len(token) == 36  # UUID format
        redis.set.assert_called_once()
        # Verify NX and EX params
        call_kwargs = redis.set.call_args
        assert call_kwargs.kwargs["nx"] is True
        assert call_kwargs.kwargs["ex"] == 10  # default TTL

    async def test_waits_and_acquires_on_second_try(self):
        redis = AsyncMock()
        # First call: lock held; second call: lock free
        redis.set.side_effect = [False, True]

        token = await acquire_session_lock(
            redis, "sess-1", wait_timeout=1.0,
        )

        assert isinstance(token, str)
        assert redis.set.call_count == 2

    async def test_raises_after_timeout(self):
        redis = AsyncMock()
        redis.set.return_value = False  # Lock always held

        with pytest.raises(SessionLockError, match="Could not acquire lock"):
            await acquire_session_lock(
                redis, "sess-1", wait_timeout=0.3,
            )

    async def test_custom_ttl_passed_to_redis(self):
        redis = AsyncMock()
        redis.set.return_value = True

        await acquire_session_lock(redis, "sess-1", ttl=30)

        call_kwargs = redis.set.call_args
        assert call_kwargs.kwargs["ex"] == 30


class TestReleaseSessionLock:
    """Test lock release with token ownership check."""

    async def test_releases_when_token_matches(self):
        redis = AsyncMock()
        redis.get.return_value = "my-token"

        await release_session_lock(redis, "sess-1", "my-token")

        redis.delete.assert_called_once_with("lock:session:sess-1")

    async def test_skips_release_when_token_mismatch(self):
        """If another request took the lock (ours expired), don't delete it."""
        redis = AsyncMock()
        redis.get.return_value = "other-token"

        await release_session_lock(redis, "sess-1", "my-token")

        redis.delete.assert_not_called()

    async def test_skips_release_when_lock_already_gone(self):
        """Lock expired before we tried to release — that's fine."""
        redis = AsyncMock()
        redis.get.return_value = None

        await release_session_lock(redis, "sess-1", "my-token")

        redis.delete.assert_not_called()


class TestSessionLockContextManager:
    """Test the async context manager wrapper."""

    async def test_acquires_and_releases(self):
        redis = AsyncMock()
        redis.set.return_value = True
        redis.get.return_value = None  # Already expired by release time

        executed = False
        async with session_lock(redis, "sess-1"):
            executed = True

        assert executed
        redis.set.assert_called_once()  # acquire

    async def test_releases_on_exception(self):
        """Lock must be released even if the wrapped code raises."""
        redis = AsyncMock()
        redis.set.return_value = True
        # Make get return the token so delete gets called
        redis.get.side_effect = lambda key: redis.set.call_args.args[1]

        with pytest.raises(ValueError, match="boom"):
            async with session_lock(redis, "sess-1"):
                raise ValueError("boom")

        # Release was still called despite the exception
        redis.delete.assert_called_once()

    async def test_concurrent_sessions_not_blocked(self):
        """Different session_ids should not block each other."""
        redis = AsyncMock()
        redis.set.return_value = True
        redis.get.return_value = None

        results = []

        async def process(sid: str) -> None:
            async with session_lock(redis, sid):
                results.append(sid)

        await asyncio.gather(process("sess-1"), process("sess-2"))

        assert "sess-1" in results
        assert "sess-2" in results
