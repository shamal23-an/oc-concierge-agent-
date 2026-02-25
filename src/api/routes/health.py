from __future__ import annotations

from fastapi import APIRouter

from src.api.dependencies import check_qdrant_health, check_redis_health

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    """Check API, Qdrant, and Redis health."""
    qdrant_ok = check_qdrant_health()
    redis_ok = check_redis_health()
    all_healthy = qdrant_ok and redis_ok

    return {
        "status": "healthy" if all_healthy else "degraded",
        "qdrant": qdrant_ok,
        "redis": redis_ok,
    }
