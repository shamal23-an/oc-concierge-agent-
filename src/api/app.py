from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.dependencies import close_clients, init_clients
from src.api.middleware import RequestLoggingMiddleware
from src.api.routes import chat, health, properties
from src.channels.whatsapp import init_whatsapp
from src.config.logging import setup_logging
from src.config.settings import get_settings

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Manage async client lifecycle: create on startup, close on shutdown."""
    import asyncio

    application.state.event_loop = asyncio.get_running_loop()
    await init_clients(application)
    logger.info("application_started")
    yield
    await close_clients(application)
    logger.info("application_stopped")


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()
    setup_logging()

    application = FastAPI(
        title="Oyster Collection AI Concierge",
        version="0.2.0",
        description="AI-powered concierge for The Oyster Collection properties",
        lifespan=lifespan,
    )

    # Middleware
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(RequestLoggingMiddleware)

    # Routes
    application.include_router(health.router, tags=["health"])
    application.include_router(properties.router, tags=["properties"])
    application.include_router(chat.router, tags=["chat"])

    # WhatsApp webhook (registers GET/POST /webhook if credentials present)
    init_whatsapp(application)

    # Global exception handler — safety net for any unhandled errors.
    # Ensures the client always gets structured JSON, never a raw 500.
    @application.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception,
    ) -> JSONResponse:
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "An internal error occurred. Please try again later.",
            },
        )

    return application


app = create_app()
