from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog
from pywa import WhatsApp, filters, types

from src.agent.graph import create_agent
from src.agent.session_lock import SessionLockError, session_lock
from src.api.dependencies import get_qdrant_client, get_redis_client
from src.config.settings import get_settings
from src.domain.schemas import AgentState

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = structlog.get_logger()

# WhatsApp text messages are limited to 4096 characters.
_WA_MAX_LENGTH = 4096


def init_whatsapp(app: FastAPI) -> WhatsApp | None:
    """Register WhatsApp webhook routes on *app*.

    Returns the WhatsApp client if credentials are configured, else ``None``.
    pywa registers ``GET /webhook`` (verification) and ``POST /webhook``
    (incoming events) directly on the FastAPI application.
    """
    settings = get_settings()

    if not settings.whatsapp_enabled:
        logger.info("whatsapp_disabled", reason="missing credentials")
        return None

    wa = WhatsApp(
        phone_id=settings.whatsapp_phone_id,
        token=settings.whatsapp_token,
        server=app,
        verify_token=settings.whatsapp_verify_token,
        app_secret=settings.whatsapp_app_secret,
        callback_url=settings.whatsapp_callback_url or None,
        webhook_endpoint="/webhook",
        validate_updates=True,
    )

    # ── Text message handler ────────────────────────────────────────── #

    @wa.on_message(filters.text)
    def _handle_text(client: WhatsApp, msg: types.Message) -> None:
        """Schedule async pipeline processing for an incoming text message."""
        loop: asyncio.AbstractEventLoop | None = getattr(
            app.state,
            "event_loop",
            None,
        )
        if loop is None or loop.is_closed():
            logger.error("whatsapp_no_event_loop")
            return

        asyncio.run_coroutine_threadsafe(
            _process_message(app, client, msg),
            loop,
        )

    # ── Catch-all for unsupported types (images, audio, etc.) ─────── #

    @wa.on_message()
    def _handle_unsupported(client: WhatsApp, msg: types.Message) -> None:
        """Reply with a hint when the guest sends non-text media."""
        try:
            client.send_message(
                to=msg.from_user.wa_id,
                text=(
                    "I can only read text messages at the moment. "
                    "Please type your question and I'll do my best to help! 😊"
                ),
            )
        except Exception:
            logger.exception(
                "whatsapp_unsupported_reply_failed",
                wa_id=msg.from_user.wa_id,
            )

    logger.info("whatsapp_initialised", webhook_endpoint="/webhook")
    return wa


# ── Async pipeline runner ──────────────────────────────────────────── #


async def _process_message(
    app: FastAPI,
    client: WhatsApp,
    msg: types.Message,
) -> None:
    """Run the RAG pipeline and send the reply back via WhatsApp."""
    phone = msg.from_user.wa_id
    session_id = f"wa_{phone}"
    text = msg.text or ""

    log = logger.bind(wa_id=phone, session_id=session_id)
    log.info("whatsapp_message_received", text=text[:100])

    try:
        qdrant_client = get_qdrant_client(app)
        redis_client = get_redis_client(app)

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
            channel="whatsapp",
            message=text[:500],
            response=response_text[:500],
            scope=result.get("scope"),
            property_id=result.get("active_property"),
            sources=result.get("sources", []),
            cached=result.get("cache_hit", False),
        )

    except SessionLockError:
        log.warning("whatsapp_session_locked")
        response_text = (
            "I'm still working on your previous message — please give me a moment and try again."
        )
    except Exception:
        log.exception("whatsapp_pipeline_error")
        response_text = (
            "I'm sorry, I'm having trouble right now. "
            "Please try again in a moment, or contact "
            "our team directly for assistance."
        )

    # Truncate to WhatsApp limit
    if len(response_text) > _WA_MAX_LENGTH:
        response_text = response_text[: _WA_MAX_LENGTH - 3] + "..."

    try:
        await asyncio.to_thread(
            client.send_message,
            to=phone,
            text=response_text,
        )
        log.info("whatsapp_reply_sent", length=len(response_text))
    except Exception:
        log.exception("whatsapp_send_failed")
