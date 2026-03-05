"""Twilio WhatsApp Sandbox adapter.

Receives incoming WhatsApp messages via Twilio webhook (form-encoded),
runs the RAG pipeline, and replies via Twilio REST API.

Twilio sends POST to /twilio/webhook with:
  - From: whatsapp:+<phone>
  - Body: message text
  - MessageSid: unique message ID

We reply via the Twilio client (client.messages.create).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter, Request, Response
from twilio.rest import Client as TwilioClient

from src.agent.graph import create_agent
from src.agent.session_lock import SessionLockError, session_lock
from src.api.dependencies import get_qdrant_client, get_redis_client
from src.config.settings import get_settings
from src.domain.schemas import AgentState

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()

router = APIRouter()

_WA_MAX_LENGTH = 1600  # Twilio WhatsApp limit per message

# Module-level Twilio client (lazy init)
_twilio_client: TwilioClient | None = None


def _get_twilio_client() -> TwilioClient:
    """Return a cached Twilio client."""
    global _twilio_client
    if _twilio_client is None:
        settings = get_settings()
        _twilio_client = TwilioClient(
            settings.twilio_account_sid,
            settings.twilio_auth_token,
        )
    return _twilio_client


@router.post("/twilio/webhook")
async def twilio_webhook(request: Request) -> Response:
    """Handle incoming Twilio WhatsApp messages.

    Twilio sends form-encoded data with From, Body, MessageSid, etc.
    We parse the form manually to avoid ruff N803 (uppercase arg names).
    """
    settings = get_settings()

    if not settings.twilio_enabled:
        logger.warning("twilio_webhook_disabled")
        return Response(content="", media_type="text/xml", status_code=200)

    form = await request.form()
    sender = str(form.get("From", ""))
    body = str(form.get("Body", ""))

    # Extract phone number (strip whatsapp: prefix)
    phone = sender.replace("whatsapp:", "").strip()
    text = body.strip()
    session_id = f"tw_{phone}"

    log = logger.bind(phone=phone, session_id=session_id, channel="twilio")

    if not text:
        log.info("twilio_empty_message")
        return Response(content="", media_type="text/xml", status_code=200)

    log.info("twilio_message_received", text=text[:100])

    try:
        qdrant_client = get_qdrant_client(request.app)
        redis_client = get_redis_client(request.app)

        agent = create_agent(
            qdrant_client=qdrant_client,
            redis_client=redis_client,
        )

        initial_state: AgentState = {
            "message": text,
            "property_id": None,
            "session_id": session_id,
        }

        async with session_lock(redis_client, session_id):
            result = await agent.ainvoke(initial_state)

        response_text = result.get(
            "response",
            "I'm sorry, I couldn't process your request.",
        )

        # Interaction audit log
        log.info(
            "interaction",
            channel="twilio_whatsapp",
            message=text[:500],
            response=response_text[:500],
            scope=result.get("scope"),
            property_id=result.get("active_property"),
            sources=result.get("sources", []),
            cached=result.get("cache_hit", False),
        )

    except SessionLockError:
        log.warning("twilio_session_locked")
        response_text = (
            "I'm still working on your previous message — please give me a moment and try again."
        )
    except Exception:
        log.exception("twilio_pipeline_error")
        response_text = (
            "I'm sorry, I'm having trouble right now. "
            "Please try again in a moment, or contact "
            "our team directly for assistance."
        )

    # Truncate to WhatsApp limit
    if len(response_text) > _WA_MAX_LENGTH:
        response_text = response_text[: _WA_MAX_LENGTH - 3] + "..."

    # Send reply via Twilio API
    try:
        client = _get_twilio_client()
        client.messages.create(
            body=response_text,
            from_=settings.twilio_whatsapp_number,
            to=sender,
        )
        log.info("twilio_reply_sent", length=len(response_text))
    except Exception:
        log.exception("twilio_send_failed")

    # Return empty TwiML (Twilio expects 200 with text/xml)
    return Response(content="", media_type="text/xml", status_code=200)
