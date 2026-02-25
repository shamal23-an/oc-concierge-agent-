from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis

from src.config.settings import get_settings

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = structlog.get_logger()

# ── Client singletons (created once, reused across requests) ─────────────── #

async def init_clients(app: FastAPI) -> None:
    """Create async clients and store them on app.state."""
    settings = get_settings()

    app.state.qdrant_client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        timeout=settings.qdrant_timeout,
    )
    app.state.redis_client = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_timeout=settings.redis_timeout,
        socket_connect_timeout=settings.redis_timeout,
    )

    logger.info("clients_initialised", qdrant=settings.qdrant_host, redis=settings.redis_url)


async def close_clients(app: FastAPI) -> None:
    """Gracefully close clients at application shutdown."""
    qdrant: AsyncQdrantClient | None = getattr(app.state, "qdrant_client", None)
    redis: Redis | None = getattr(app.state, "redis_client", None)

    if qdrant:
        await qdrant.close()
    if redis:
        await redis.aclose()

    logger.info("clients_closed")


def get_qdrant_client(app: FastAPI) -> AsyncQdrantClient:
    """Get the Qdrant async client from app.state."""
    return app.state.qdrant_client


def get_redis_client(app: FastAPI) -> Redis:
    """Get the Redis async client from app.state."""
    return app.state.redis_client


async def check_qdrant_health(app: FastAPI) -> bool:
    """Check if Qdrant is reachable."""
    try:
        client: AsyncQdrantClient = app.state.qdrant_client
        await client.get_collections()
        return True
    except Exception as exc:
        logger.warning("qdrant_health_check_failed", error=str(exc))
        return False


async def check_redis_health(app: FastAPI) -> bool:
    """Check if Redis is reachable."""
    try:
        client: Redis = app.state.redis_client
        return await client.ping()
    except Exception as exc:
        logger.warning("redis_health_check_failed", error=str(exc))
        return False
