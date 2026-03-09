from __future__ import annotations

import json
import uuid

import structlog
from redis.asyncio import Redis

from src.config.constants import MAX_CONVERSATION_HISTORY
from src.config.settings import get_settings

logger = structlog.get_logger()


class SessionData:
    """Conversation session stored in Redis."""

    def __init__(
        self,
        session_id: str,
        *,
        active_property: str | None = None,
        active_region: str | None = None,
        booking_details: dict | None = None,
        conversation_history: list[dict] | None = None,
    ):
        self.session_id = session_id
        self.active_property = active_property
        self.active_region = active_region
        self.booking_details = booking_details
        self.conversation_history: list[dict] = conversation_history or []

    def add_message(self, role: str, content: str) -> None:
        """Add a message and trim to max history."""
        self.conversation_history.append({"role": role, "content": content})
        if len(self.conversation_history) > MAX_CONVERSATION_HISTORY:
            self.conversation_history = self.conversation_history[-MAX_CONVERSATION_HISTORY:]

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "active_property": self.active_property,
            "active_region": self.active_region,
            "booking_details": self.booking_details,
            "conversation_history": self.conversation_history,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SessionData:
        return cls(
            session_id=data["session_id"],
            active_property=data.get("active_property"),
            active_region=data.get("active_region"),
            booking_details=data.get("booking_details"),
            conversation_history=data.get("conversation_history", []),
        )


def _session_key(session_id: str) -> str:
    return f"session:{session_id}"


async def load_session(redis_client: Redis, session_id: str | None) -> SessionData:
    """Load session from Redis or create a new one."""
    if session_id:
        raw = await redis_client.get(_session_key(session_id))
        if raw:
            try:
                data = json.loads(raw)
                logger.debug("session_loaded", session_id=session_id)
                return SessionData.from_dict(data)
            except (json.JSONDecodeError, KeyError):
                logger.warning("session_load_failed", session_id=session_id)

    new_id = session_id or str(uuid.uuid4())
    logger.debug("session_created", session_id=new_id)
    return SessionData(session_id=new_id)


async def save_session(redis_client: Redis, session: SessionData) -> None:
    """Save session to Redis with TTL."""
    settings = get_settings()
    key = _session_key(session.session_id)
    try:
        await redis_client.setex(
            key,
            settings.session_ttl_seconds,
            json.dumps(session.to_dict()),
        )
        logger.debug("session_saved", session_id=session.session_id)
    except Exception as exc:
        logger.warning(
            "session_save_error",
            session_id=session.session_id,
            error=str(exc),
        )
