from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app


@pytest.fixture
def client():
    """Test client with mocked infrastructure clients."""
    app = create_app()

    # Mock the lifespan clients so we don't need real Redis/Qdrant
    app.state.qdrant_client = AsyncMock()
    app.state.redis_client = AsyncMock()

    # Patch settings so API_KEY from .env doesn't block test requests
    mock_settings = MagicMock()
    mock_settings.api_key = ""

    with patch("src.api.middleware.get_settings", return_value=mock_settings):
        yield TestClient(app, raise_server_exceptions=False)


class TestGlobalExceptionHandler:
    """Test the catch-all exception handler in app.py."""

    def test_unhandled_error_returns_500_json(self, client):
        """Routes that raise unexpected errors return structured JSON, not raw 500."""
        # Hit a route that doesn't exist won't trigger this —
        # we need to trigger an actual unhandled exception.
        # The health route accesses app.state, so if we break that
        # it'll throw. But easier: patch a route to raise.
        with (
            patch(
                "src.api.routes.health.check_qdrant_health",
                side_effect=RuntimeError("unexpected"),
            ),
            patch(
                "src.api.routes.health.check_redis_health",
                side_effect=RuntimeError("unexpected"),
            ),
        ):
            response = client.get("/health")

        assert response.status_code == 500
        body = response.json()
        assert "detail" in body
        assert "internal error" in body["detail"].lower()


class TestChatErrorHandling:
    """Test that chat endpoint returns friendly response on pipeline failure."""

    def test_pipeline_crash_returns_friendly_response(self, client):
        """If the agent pipeline throws, return a proper ChatResponse."""
        with patch(
            "src.api.routes.chat.session_lock",
        ) as mock_lock:
            # Make the context manager work but agent.ainvoke() raises
            mock_lock.return_value.__aenter__ = AsyncMock(return_value=None)
            mock_lock.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch(
                "src.api.routes.chat.create_agent",
            ) as mock_agent:
                mock_agent.return_value.ainvoke = AsyncMock(
                    side_effect=RuntimeError("LLM is down"),
                )
                response = client.post(
                    "/chat",
                    json={"message": "What are the rates?"},
                )

        # Should be 200 (not 500) — the error is handled gracefully
        assert response.status_code == 200
        body = response.json()
        assert "trouble processing" in body["response"].lower()
        assert body["sources"] == []

    def test_pipeline_crash_preserves_session_id(self, client):
        """Session ID from request should be in the fallback response."""
        with patch(
            "src.api.routes.chat.session_lock",
        ) as mock_lock:
            mock_lock.return_value.__aenter__ = AsyncMock(return_value=None)
            mock_lock.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch(
                "src.api.routes.chat.create_agent",
            ) as mock_agent:
                mock_agent.return_value.ainvoke = AsyncMock(
                    side_effect=ConnectionError("Redis gone"),
                )
                response = client.post(
                    "/chat",
                    json={
                        "message": "hello",
                        "session_id": "test-session-123",
                    },
                )

        assert response.status_code == 200
        body = response.json()
        assert body["session_id"] == "test-session-123"

    def test_pipeline_crash_preserves_property_id(self, client):
        """Property ID from request should be in the fallback response."""
        with patch(
            "src.api.routes.chat.session_lock",
        ) as mock_lock:
            mock_lock.return_value.__aenter__ = AsyncMock(return_value=None)
            mock_lock.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch(
                "src.api.routes.chat.create_agent",
            ) as mock_agent:
                mock_agent.return_value.ainvoke = AsyncMock(
                    side_effect=TimeoutError("timed out"),
                )
                response = client.post(
                    "/chat",
                    json={
                        "message": "rates?",
                        "property_id": "la_fontaine",
                    },
                )

        assert response.status_code == 200
        body = response.json()
        assert body["property_id"] == "la_fontaine"

    def test_session_lock_timeout_still_returns_429(self, client):
        """SessionLockError should still return 429, not be caught by generic handler."""
        from src.agent.session_lock import SessionLockError

        with patch(
            "src.api.routes.chat.session_lock",
        ) as mock_lock:
            mock_lock.return_value.__aenter__ = AsyncMock(
                side_effect=SessionLockError("locked"),
            )
            mock_lock.return_value.__aexit__ = AsyncMock(return_value=False)

            response = client.post(
                "/chat",
                json={"message": "hello"},
            )

        assert response.status_code == 429
