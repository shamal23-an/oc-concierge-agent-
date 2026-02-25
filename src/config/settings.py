from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenAI
    openai_api_key: str = Field(..., description="OpenAI API key")
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.1
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 1536

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "oyster_collection"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    session_ttl_seconds: int = 14400  # 4 hours

    # Retrieval
    confidence_threshold: float = 0.7
    chunk_size: int = 1024
    chunk_overlap: int = 128
    top_k: int = 5

    # WhatsApp (optional)
    whatsapp_token: str = ""
    whatsapp_phone_id: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""

    # Timeouts (seconds)
    openai_timeout: int = 30  # LLM generation
    embedding_timeout: int = 15  # Embedding API
    qdrant_timeout: int = 10  # Vector search
    redis_timeout: int = 5  # Cache/session ops

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = ["http://localhost:8501"]


_settings: Settings | None = None


def get_settings() -> Settings:
    """Cached settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
