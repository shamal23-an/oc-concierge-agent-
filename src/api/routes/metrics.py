"""Metrics endpoint for observability."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.observability.metrics import get_metrics

router = APIRouter()


@router.get("/metrics")
async def metrics() -> JSONResponse:
    """Return current application metrics."""
    return JSONResponse(content=get_metrics().snapshot())
