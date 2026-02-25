from __future__ import annotations

from fastapi import APIRouter, Request

from src.api.dependencies import check_qdrant_health, check_redis_health

router = APIRouter()


@router.get("/health")
async def health_check(request: Request) -> dict:
    """Check API, Qdrant, and Redis health."""
    qdrant_ok = await check_qdrant_health(request.app)
    redis_ok = await check_redis_health(request.app)
    all_healthy = qdrant_ok and redis_ok

    return {
        "status": "healthy" if all_healthy else "degraded",
        "qdrant": qdrant_ok,
        "redis": redis_ok,
    }
