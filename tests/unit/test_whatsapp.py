from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from src.channels.whatsapp import _WA_MAX_LENGTH, _process_message, init_whatsapp


def _make_msg(wa_id: str = "27821234567", text: str = "Hello") -> MagicMock:
    """Create a minimal pywa Message mock."""
    msg = MagicMock()
    msg.from_user.wa_id = wa_id
    msg.text = text
    return msg


# ── init_whatsapp ──────────────────────────────────────────────────── #


class TestInitWhatsApp:
    """Test WhatsApp client initialisation."""

    def test_returns_none_when_credentials_missing(self):
        app = MagicMock()
        with patch(
            "src.channels.whatsapp.get_settings",
            return_value=SimpleNamespace(whatsapp_enabled=False),
        ):
            result = init_whatsapp(app)

        assert result is None

    def test_returns_client_when_configured(self):
        app = MagicMock()
        settings = SimpleNamespace(
            whatsapp_enabled=True,
            whatsapp_phone_id="12345",
            whatsapp_token="tok",
            whatsapp_verify_token="verify",
            whatsapp_app_secret="secret",
            whatsapp_callback_url="",
        )
        with (
            patch("src.channels.whatsapp.get_settings", return_value=settings),
            patch("src.channels.whatsapp.WhatsApp") as mock_wa_cls,
        ):
            mock_client = MagicMock()
            mock_wa_cls.return_value = mock_client

            result = init_whatsapp(app)

        assert result is mock_client
        mock_wa_cls.assert_called_once()
        # Verify key constructor arguments
        call_kwargs = mock_wa_cls.call_args
        assert call_kwargs.kwargs["phone_id"] == "12345"
        assert call_kwargs.kwargs["server"] is app
        assert call_kwargs.kwargs["webhook_endpoint"] == "/webhook"

    def test_callback_url_none_when_empty(self):
        """Empty callback_url should pass None to pywa (skip auto-registration)."""
        app = MagicMock()
        settings = SimpleNamespace(
            whatsapp_enabled=True,
            whatsapp_phone_id="12345",
            whatsapp_token="tok",
            whatsapp_verify_token="verify",
            whatsapp_app_secret="secret",
            whatsapp_callback_url="",
        )
        with (
            patch("src.channels.whatsapp.get_settings", return_value=settings),
            patch("src.channels.whatsapp.WhatsApp") as mock_wa_cls,
        ):
            init_whatsapp(app)

        call_kwargs = mock_wa_cls.call_args
        assert call_kwargs.kwargs["callback_url"] is None

    def test_callback_url_passed_when_set(self):
        app = MagicMock()
        settings = SimpleNamespace(
            whatsapp_enabled=True,
            whatsapp_phone_id="12345",
            whatsapp_token="tok",
            whatsapp_verify_token="verify",
            whatsapp_app_secret="secret",
            whatsapp_callback_url="https://example.com",
        )
        with (
            patch("src.channels.whatsapp.get_settings", return_value=settings),
            patch("src.channels.whatsapp.WhatsApp") as mock_wa_cls,
        ):
            init_whatsapp(app)

        call_kwargs = mock_wa_cls.call_args
        assert call_kwargs.kwargs["callback_url"] == "https://example.com"


# ── _process_message ───────────────────────────────────────────────── #


class TestProcessMessage:
    """Test the async pipeline runner."""

    async def test_successful_pipeline_sends_reply(self):
        app = MagicMock()
        client = MagicMock()
        msg = _make_msg(text="What is breakfast time?")

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            "response": "Breakfast is served 7-10am.",
            "session_id": "wa_27821234567",
        }

        lock_cm = AsyncMock()
        lock_cm.__aenter__ = AsyncMock()
        lock_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.channels.whatsapp.get_qdrant_client"),
            patch("src.channels.whatsapp.get_redis_client"),
            patch(
                "src.channels.whatsapp.create_agent",
                return_value=mock_agent,
            ),
            patch(
                "src.channels.whatsapp.session_lock",
                return_value=lock_cm,
            ),
            patch("src.channels.whatsapp.asyncio") as mock_asyncio,
        ):
            mock_asyncio.to_thread = AsyncMock()
            await _process_message(app, client, msg)

            mock_asyncio.to_thread.assert_called_once_with(
                client.send_message,
                to="27821234567",
                text="Breakfast is served 7-10am.",
            )

    async def test_session_locked_sends_busy_reply(self):
        from src.agent.session_lock import SessionLockError

        app = MagicMock()
        client = MagicMock()
        msg = _make_msg()

        lock_cm = AsyncMock()
        lock_cm.__aenter__ = AsyncMock(side_effect=SessionLockError("locked"))
        lock_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.channels.whatsapp.get_qdrant_client"),
            patch("src.channels.whatsapp.get_redis_client"),
            patch("src.channels.whatsapp.create_agent"),
            patch(
                "src.channels.whatsapp.session_lock",
                return_value=lock_cm,
            ),
            patch("src.channels.whatsapp.asyncio") as mock_asyncio,
        ):
            mock_asyncio.to_thread = AsyncMock()
            await _process_message(app, client, msg)

            sent_text = mock_asyncio.to_thread.call_args.kwargs["text"]
            assert "still working" in sent_text

    async def test_pipeline_error_sends_friendly_message(self):
        app = MagicMock()
        client = MagicMock()
        msg = _make_msg()

        lock_cm = AsyncMock()
        lock_cm.__aenter__ = AsyncMock()
        lock_cm.__aexit__ = AsyncMock(return_value=False)

        mock_agent = AsyncMock()
        mock_agent.ainvoke.side_effect = RuntimeError("LLM down")

        with (
            patch("src.channels.whatsapp.get_qdrant_client"),
            patch("src.channels.whatsapp.get_redis_client"),
            patch(
                "src.channels.whatsapp.create_agent",
                return_value=mock_agent,
            ),
            patch(
                "src.channels.whatsapp.session_lock",
                return_value=lock_cm,
            ),
            patch("src.channels.whatsapp.asyncio") as mock_asyncio,
        ):
            mock_asyncio.to_thread = AsyncMock()
            await _process_message(app, client, msg)

            sent_text = mock_asyncio.to_thread.call_args.kwargs["text"]
            assert "having trouble" in sent_text

    async def test_long_response_truncated(self):
        app = MagicMock()
        client = MagicMock()
        msg = _make_msg()

        long_text = "x" * 5000
        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {"response": long_text}

        lock_cm = AsyncMock()
        lock_cm.__aenter__ = AsyncMock()
        lock_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.channels.whatsapp.get_qdrant_client"),
            patch("src.channels.whatsapp.get_redis_client"),
            patch(
                "src.channels.whatsapp.create_agent",
                return_value=mock_agent,
            ),
            patch(
                "src.channels.whatsapp.session_lock",
                return_value=lock_cm,
            ),
            patch("src.channels.whatsapp.asyncio") as mock_asyncio,
        ):
            mock_asyncio.to_thread = AsyncMock()
            await _process_message(app, client, msg)

            sent_text = mock_asyncio.to_thread.call_args.kwargs["text"]
            assert len(sent_text) == _WA_MAX_LENGTH
            assert sent_text.endswith("...")

    async def test_send_failure_logged_not_raised(self):
        """If send_message fails, we log but don't crash."""
        app = MagicMock()
        client = MagicMock()
        msg = _make_msg()

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {"response": "OK"}

        lock_cm = AsyncMock()
        lock_cm.__aenter__ = AsyncMock()
        lock_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.channels.whatsapp.get_qdrant_client"),
            patch("src.channels.whatsapp.get_redis_client"),
            patch(
                "src.channels.whatsapp.create_agent",
                return_value=mock_agent,
            ),
            patch(
                "src.channels.whatsapp.session_lock",
                return_value=lock_cm,
            ),
            patch("src.channels.whatsapp.asyncio") as mock_asyncio,
        ):
            mock_asyncio.to_thread = AsyncMock(
                side_effect=RuntimeError("network error"),
            )
            # Should not raise
            await _process_message(app, client, msg)

    async def test_session_id_format(self):
        """Session ID should be wa_{phone_number}."""
        app = MagicMock()
        client = MagicMock()
        msg = _make_msg(wa_id="27821234567")

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {"response": "Hi"}

        lock_cm = AsyncMock()
        lock_cm.__aenter__ = AsyncMock()
        lock_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.channels.whatsapp.get_qdrant_client"),
            patch("src.channels.whatsapp.get_redis_client"),
            patch(
                "src.channels.whatsapp.create_agent",
                return_value=mock_agent,
            ),
            patch(
                "src.channels.whatsapp.session_lock",
                return_value=lock_cm,
            ) as mock_lock,
            patch("src.channels.whatsapp.asyncio") as mock_asyncio,
        ):
            mock_asyncio.to_thread = AsyncMock()
            await _process_message(app, client, msg)

            # Verify session_lock was called with correct session_id
            mock_lock.assert_called_once()
            call_args = mock_lock.call_args
            assert call_args.args[1] == "wa_27821234567"

    async def test_property_id_is_none(self):
        """Property should be None — let context resolver detect it."""
        app = MagicMock()
        client = MagicMock()
        msg = _make_msg()

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {"response": "Hi"}

        lock_cm = AsyncMock()
        lock_cm.__aenter__ = AsyncMock()
        lock_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.channels.whatsapp.get_qdrant_client"),
            patch("src.channels.whatsapp.get_redis_client"),
            patch(
                "src.channels.whatsapp.create_agent",
                return_value=mock_agent,
            ),
            patch(
                "src.channels.whatsapp.session_lock",
                return_value=lock_cm,
            ),
            patch("src.channels.whatsapp.asyncio") as mock_asyncio,
        ):
            mock_asyncio.to_thread = AsyncMock()
            await _process_message(app, client, msg)

            invoke_state = mock_agent.ainvoke.call_args.args[0]
            assert invoke_state["property_id"] is None


# ── Constants ──────────────────────────────────────────────────────── #


class TestConstants:
    def test_wa_max_length(self):
        assert _WA_MAX_LENGTH == 4096
