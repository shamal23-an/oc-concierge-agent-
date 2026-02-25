from __future__ import annotations

import hashlib
import json

import structlog
from redis import Redis

from src.config.constants import RESPONSE_CACHE_TTL, RETRIEVAL_CACHE_TTL
from src.domain.schemas import RetrievedChunk

logger = structlog.get_logger()

# Redis key prefixes
_RESPONSE_PREFIX = "cache:response:"
_RETRIEVAL_PREFIX = "cache:retrieval:"


def _build_cache_key(message: str, property_id: str | None, scope: str) -> str:
    """Build a deterministic cache key from query parameters.

    Normalises the message (lowercase, stripped) so minor variations
    like trailing spaces or capitalisation still hit the same entry.
    """
    normalised = message.lower().strip()
    raw = f"{normalised}|{property_id or ''}|{scope}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ── Response cache ────────────────────────────────────────────────────────── #


def get_cached_response(
    redis: Redis,
    message: str,
    property_id: str | None,
    scope: str,
) -> dict | None:
    """Look up a cached full response. Returns None on miss."""
    key = _RESPONSE_PREFIX + _build_cache_key(message, property_id, scope)
    try:
        data = redis.get(key)
    except Exception:
        logger.warning("response_cache_read_error", key=key)
        return None

    if data is None:
        return None

    logger.debug("response_cache_hit", key=key)
    return json.loads(data)


def set_cached_response(
    redis: Redis,
    message: str,
    property_id: str | None,
    scope: str,
    *,
    response: str,
    sources: list[str],
) -> None:
    """Store a full response in Redis with TTL."""
    key = _RESPONSE_PREFIX + _build_cache_key(message, property_id, scope)
    payload = json.dumps({"response": response, "sources": sources})
    try:
        redis.setex(key, RESPONSE_CACHE_TTL, payload)
        logger.debug("response_cache_set", key=key, ttl=RESPONSE_CACHE_TTL)
    except Exception:
        logger.warning("response_cache_write_error", key=key)


# ── Retrieval cache ──────────────────────────────────────────────────────── #


def get_cached_retrieval(
    redis: Redis,
    message: str,
    property_id: str | None,
    scope: str,
) -> list[RetrievedChunk] | None:
    """Look up cached retrieval chunks. Returns None on miss."""
    key = _RETRIEVAL_PREFIX + _build_cache_key(message, property_id, scope)
    try:
        data = redis.get(key)
    except Exception:
        logger.warning("retrieval_cache_read_error", key=key)
        return None

    if data is None:
        return None

    logger.debug("retrieval_cache_hit", key=key)
    return json.loads(data)


def set_cached_retrieval(
    redis: Redis,
    message: str,
    property_id: str | None,
    scope: str,
    *,
    chunks: list[RetrievedChunk],
) -> None:
    """Store retrieval chunks in Redis with TTL."""
    key = _RETRIEVAL_PREFIX + _build_cache_key(message, property_id, scope)
    payload = json.dumps(chunks)
    try:
        redis.setex(key, RETRIEVAL_CACHE_TTL, payload)
        logger.debug("retrieval_cache_set", key=key, ttl=RETRIEVAL_CACHE_TTL)
    except Exception:
        logger.warning("retrieval_cache_write_error", key=key)
