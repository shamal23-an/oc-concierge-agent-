from __future__ import annotations

import structlog
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis

from src.config.settings import get_settings

logger = structlog.get_logger()

# ── Client singletons (created once, reused across requests) ─────────────── #

_qdrant_client: AsyncQdrantClient | None = None
_redis_client: Redis | None = None


def get_qdrant_client() -> AsyncQdrantClient:
    """Get the Qdrant async client singleton."""
    if _qdrant_client is None:
        msg = "Qdrant client not initialised. Call init_clients() first."
        raise RuntimeError(msg)
    return _qdrant_client


def get_redis_client() -> Redis:
    """Get the Redis async client singleton."""
    if _redis_client is None:
        msg = "Redis client not initialised. Call init_clients() first."
        raise RuntimeError(msg)
    return _redis_client


async def init_clients() -> None:
    """Create async clients at application startup."""
    global _qdrant_client, _redis_client
    settings = get_settings()

    _qdrant_client = AsyncQdrantClient(
        host=settings.qdrant_host, port=settings.qdrant_port,
    )
    _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)

    logger.info("clients_initialised", qdrant=settings.qdrant_host, redis=settings.redis_url)


async def close_clients() -> None:
    """Gracefully close clients at application shutdown."""
    global _qdrant_client, _redis_client

    if _qdrant_client:
        await _qdrant_client.close()
        _qdrant_client = None

    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None

    logger.info("clients_closed")


async def check_qdrant_health() -> bool:
    """Check if Qdrant is reachable."""
    try:
        client = get_qdrant_client()
        await client.get_collections()
        return True
    except Exception:
        logger.warning("qdrant_health_check_failed")
        return False


async def check_redis_health() -> bool:
    """Check if Redis is reachable."""
    try:
        client = get_redis_client()
        return await client.ping()
    except Exception:
        logger.warning("redis_health_check_failed")
        return False
