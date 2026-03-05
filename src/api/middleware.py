from __future__ import annotations

import time
from collections.abc import Callable

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.config.settings import get_settings

logger = structlog.get_logger()

# Paths that require API key auth (when API_KEY is set)
_PROTECTED_PATHS = {"/chat", "/debug/rag"}
# Paths that are always public
_PUBLIC_PATHS = {"/health", "/properties", "/docs", "/openapi.json", "/webhook"}


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Reject requests to protected endpoints without a valid X-API-Key header.

    If API_KEY is empty (dev mode), all requests are allowed through.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        settings = get_settings()

        # No key configured = dev mode, skip auth
        if not settings.api_key:
            return await call_next(request)

        path = request.url.path.rstrip("/")

        # Only protect specific paths
        if path in _PROTECTED_PATHS:
            provided = request.headers.get("X-API-Key", "")
            if provided != settings.api_key:
                logger.warning("auth_rejected", path=path, reason="invalid_api_key")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key."},
                )

        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log request method, path, status code, and duration."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        return response
