from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app():
    """Minimal FastAPI app with Twilio router."""
    from src.channels.twilio_whatsapp import router

    application = FastAPI()
    application.include_router(router)

    # Mock app.state clients
    application.state.qdrant_client = MagicMock()
    application.state.redis_client = AsyncMock()
    return application


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestTwilioWebhook:
    async def test_disabled_returns_200(self, client):
        """When Twilio is not configured, return empty 200."""
        with patch("src.channels.twilio_whatsapp.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(twilio_enabled=False)
            resp = await client.post(
                "/twilio/webhook",
                data={"From": "whatsapp:+27821234567", "Body": "Hello"},
            )
            assert resp.status_code == 200

    async def test_empty_body_returns_200(self, client):
        """Empty message body returns 200 without processing."""
        with patch("src.channels.twilio_whatsapp.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                twilio_enabled=True,
                twilio_account_sid="ACtest",
                twilio_auth_token="test",
                twilio_whatsapp_number="whatsapp:+14155238886",
            )
            resp = await client.post(
                "/twilio/webhook",
                data={"From": "whatsapp:+27821234567", "Body": ""},
            )
            assert resp.status_code == 200

    async def test_valid_message_calls_pipeline(self, client, app):
        """Valid message triggers the RAG pipeline and sends reply."""
        mock_twilio_client = MagicMock()
        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(
            return_value={
                "response": "Welcome to The Oyster Collection!",
                "sources": [],
                "scope": "group",
            }
        )

        with (
            patch("src.channels.twilio_whatsapp.get_settings") as mock_settings,
            patch("src.channels.twilio_whatsapp.create_agent", return_value=mock_agent),
            patch("src.channels.twilio_whatsapp.session_lock") as mock_lock,
            patch(
                "src.channels.twilio_whatsapp._get_twilio_client",
                return_value=mock_twilio_client,
            ),
            patch(
                "src.channels.twilio_whatsapp.get_qdrant_client",
                return_value=MagicMock(),
            ),
            patch(
                "src.channels.twilio_whatsapp.get_redis_client",
                return_value=AsyncMock(),
            ),
        ):
            mock_settings.return_value = MagicMock(
                twilio_enabled=True,
                twilio_account_sid="ACtest",
                twilio_auth_token="test",
                twilio_whatsapp_number="whatsapp:+14155238886",
            )
            mock_lock.return_value.__aenter__ = AsyncMock()
            mock_lock.return_value.__aexit__ = AsyncMock()

            resp = await client.post(
                "/twilio/webhook",
                data={"From": "whatsapp:+27821234567", "Body": "Hello"},
            )

            assert resp.status_code == 200
            mock_agent.ainvoke.assert_called_once()
            mock_twilio_client.messages.create.assert_called_once()

            call_kwargs = mock_twilio_client.messages.create.call_args.kwargs
            assert "Welcome to The Oyster Collection!" in call_kwargs["body"]
            assert call_kwargs["to"] == "whatsapp:+27821234567"

    async def test_session_lock_error_sends_wait_message(self, client, app):
        """Session lock contention sends a wait message."""
        from src.agent.session_lock import SessionLockError

        mock_twilio_client = MagicMock()

        with (
            patch("src.channels.twilio_whatsapp.get_settings") as mock_settings,
            patch("src.channels.twilio_whatsapp.session_lock") as mock_lock,
            patch(
                "src.channels.twilio_whatsapp._get_twilio_client",
                return_value=mock_twilio_client,
            ),
            patch(
                "src.channels.twilio_whatsapp.get_qdrant_client",
                return_value=MagicMock(),
            ),
            patch(
                "src.channels.twilio_whatsapp.get_redis_client",
                return_value=AsyncMock(),
            ),
            patch("src.channels.twilio_whatsapp.create_agent"),
        ):
            mock_settings.return_value = MagicMock(
                twilio_enabled=True,
                twilio_account_sid="ACtest",
                twilio_auth_token="test",
                twilio_whatsapp_number="whatsapp:+14155238886",
            )
            mock_lock.return_value.__aenter__ = AsyncMock(side_effect=SessionLockError("locked"))
            mock_lock.return_value.__aexit__ = AsyncMock()

            resp = await client.post(
                "/twilio/webhook",
                data={"From": "whatsapp:+27821234567", "Body": "Hello"},
            )

            assert resp.status_code == 200
            call_kwargs = mock_twilio_client.messages.create.call_args.kwargs
            assert "still working" in call_kwargs["body"]

    async def test_pipeline_error_sends_error_message(self, client, app):
        """Pipeline error sends a friendly error message."""
        mock_twilio_client = MagicMock()
        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(side_effect=RuntimeError("LLM down"))

        with (
            patch("src.channels.twilio_whatsapp.get_settings") as mock_settings,
            patch("src.channels.twilio_whatsapp.create_agent", return_value=mock_agent),
            patch("src.channels.twilio_whatsapp.session_lock") as mock_lock,
            patch(
                "src.channels.twilio_whatsapp._get_twilio_client",
                return_value=mock_twilio_client,
            ),
            patch(
                "src.channels.twilio_whatsapp.get_qdrant_client",
                return_value=MagicMock(),
            ),
            patch(
                "src.channels.twilio_whatsapp.get_redis_client",
                return_value=AsyncMock(),
            ),
        ):
            mock_settings.return_value = MagicMock(
                twilio_enabled=True,
                twilio_account_sid="ACtest",
                twilio_auth_token="test",
                twilio_whatsapp_number="whatsapp:+14155238886",
            )
            mock_lock.return_value.__aenter__ = AsyncMock()
            mock_lock.return_value.__aexit__ = AsyncMock()

            resp = await client.post(
                "/twilio/webhook",
                data={"From": "whatsapp:+27821234567", "Body": "Hello"},
            )

            assert resp.status_code == 200
            call_kwargs = mock_twilio_client.messages.create.call_args.kwargs
            assert "having trouble" in call_kwargs["body"]

    async def test_phone_extraction(self, client, app):
        """Phone number correctly stripped of whatsapp: prefix for session ID."""
        mock_twilio_client = MagicMock()
        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(
            return_value={"response": "Hi!", "sources": [], "scope": "group"}
        )

        with (
            patch("src.channels.twilio_whatsapp.get_settings") as mock_settings,
            patch("src.channels.twilio_whatsapp.create_agent", return_value=mock_agent),
            patch("src.channels.twilio_whatsapp.session_lock") as mock_lock,
            patch(
                "src.channels.twilio_whatsapp._get_twilio_client",
                return_value=mock_twilio_client,
            ),
            patch(
                "src.channels.twilio_whatsapp.get_qdrant_client",
                return_value=MagicMock(),
            ),
            patch(
                "src.channels.twilio_whatsapp.get_redis_client",
                return_value=AsyncMock(),
            ),
        ):
            mock_settings.return_value = MagicMock(
                twilio_enabled=True,
                twilio_account_sid="ACtest",
                twilio_auth_token="test",
                twilio_whatsapp_number="whatsapp:+14155238886",
            )
            mock_lock.return_value.__aenter__ = AsyncMock()
            mock_lock.return_value.__aexit__ = AsyncMock()

            await client.post(
                "/twilio/webhook",
                data={"From": "whatsapp:+27821234567", "Body": "Test"},
            )

            # Check the agent was called with correct session_id
            call_args = mock_agent.ainvoke.call_args[0][0]
            assert call_args["session_id"] == "tw_+27821234567"
