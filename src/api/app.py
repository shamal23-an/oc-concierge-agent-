from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.dependencies import close_clients, init_clients
from src.api.middleware import RequestLoggingMiddleware
from src.api.routes import chat, health, properties
from src.config.logging import setup_logging
from src.config.settings import get_settings

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Manage async client lifecycle: create on startup, close on shutdown."""
    await init_clients()
    logger.info("application_started")
    yield
    await close_clients()
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

    return application


app = create_app()
