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
    embedding_dimensions: int = 3072

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_url: str = ""  # Cloud URL (e.g. https://xxx.cloud.qdrant.io)
    qdrant_api_key: str = ""  # Cloud API key
    qdrant_collection: str = "oyster_collection"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    session_ttl_seconds: int = 14400  # 4 hours

    # Retrieval
    confidence_threshold: float = 0.7
    chunk_size: int = 512
    chunk_overlap: int = 64
    top_k: int = 5

    # Jina Reranker (optional — fallback to local ranking if empty)
    jina_api_key: str = ""
    jina_rerank_model: str = "jina-reranker-v2-base-multilingual"
    jina_rerank_timeout: int = 5  # seconds
    rerank_min_score: float = 0.25

    # WhatsApp — Meta direct (optional)
    whatsapp_token: str = ""
    whatsapp_phone_id: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_callback_url: str = ""

    @property
    def whatsapp_enabled(self) -> bool:
        """True when all required WhatsApp credentials are configured."""
        return all(
            [
                self.whatsapp_token,
                self.whatsapp_phone_id,
                self.whatsapp_verify_token,
                self.whatsapp_app_secret,
            ]
        )

    # Twilio WhatsApp Sandbox (optional)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_number: str = ""  # e.g. whatsapp:+14155238886

    @property
    def twilio_enabled(self) -> bool:
        """True when all required Twilio credentials are configured."""
        return all(
            [
                self.twilio_account_sid,
                self.twilio_auth_token,
                self.twilio_whatsapp_number,
            ]
        )

    # Timeouts (seconds)
    openai_timeout: int = 30  # LLM generation
    embedding_timeout: int = 15  # Embedding API
    qdrant_timeout: int = 10  # Vector search
    redis_timeout: int = 5  # Cache/session ops

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_key: str = ""  # X-API-Key header; empty = no auth (dev mode)
    cors_origins: list[str] = [
        "http://localhost:8501",
        "https://oc-concierge-agent-production.up.railway.app",
    ]


_settings: Settings | None = None


def get_settings() -> Settings:
    """Cached settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
