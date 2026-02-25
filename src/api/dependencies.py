from __future__ import annotations

from functools import lru_cache

import structlog
from qdrant_client import QdrantClient
from redis import Redis

from src.config.settings import get_settings

logger = structlog.get_logger()


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    """Get or create Qdrant client singleton."""
    settings = get_settings()
    return QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)


@lru_cache(maxsize=1)
def get_redis_client() -> Redis:
    """Get or create Redis client singleton."""
    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)


def check_qdrant_health() -> bool:
    """Check if Qdrant is reachable."""
    try:
        client = get_qdrant_client()
        client.get_collections()
        return True
    except Exception:
        logger.warning("qdrant_health_check_failed")
        return False


def check_redis_health() -> bool:
    """Check if Redis is reachable."""
    try:
        client = get_redis_client()
        return client.ping()
    except Exception:
        logger.warning("redis_health_check_failed")
        return False
