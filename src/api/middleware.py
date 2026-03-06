from __future__ import annotations

import time
from collections.abc import MutableMapping
from typing import Any

import structlog
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from src.config.settings import get_settings

logger = structlog.get_logger()

# Paths that require API key auth (when API_KEY is set)
_PROTECTED_PATHS = {"/chat"}
# Paths that are always public
_PUBLIC_PATHS = {"/health", "/properties", "/docs", "/openapi.json", "/webhook", "/twilio/webhook"}


class ApiKeyMiddleware:
    """Pure ASGI middleware — reject requests without valid X-API-Key.

    Replaces BaseHTTPMiddleware to avoid the known Starlette bug where
    exceptions in the response body are swallowed into bare 500s.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = get_settings()

        # No key configured = dev mode, skip auth
        if not settings.api_key:
            await self.app(scope, receive, send)
            return

        path = scope["path"].rstrip("/")

        if path in _PROTECTED_PATHS:
            headers: dict[str, str] = {}
            for key, value in scope.get("headers", []):
                headers[key.decode("latin-1").lower()] = value.decode("latin-1")

            provided = headers.get("x-api-key", "")
            if provided != settings.api_key:
                logger.warning("auth_rejected", path=path, reason="invalid_api_key")
                response = JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key."},
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


class RequestLoggingMiddleware:
    """Pure ASGI middleware — log request method, path, status, and duration.

    Replaces BaseHTTPMiddleware to avoid swallowed exceptions.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 500  # default if we never see the response

        async def send_wrapper(message: MutableMapping[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info(
                "http_request",
                method=scope.get("method", "?"),
                path=scope.get("path", "?"),
                status=status_code,
                duration_ms=duration_ms,
            )
