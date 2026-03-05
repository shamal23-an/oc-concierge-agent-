from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError

from src.retrieval.embedder import _embed_with_retry


class TestEmbeddingRetry:
    """Test retry behavior for OpenAI embedding calls."""

    async def test_succeeds_on_first_try(self):
        mock_response = AsyncMock()
        mock_response.data = [AsyncMock(embedding=[0.1, 0.2, 0.3])]

        mock_client = AsyncMock()
        mock_client.embeddings.create.return_value = mock_response

        with patch("src.retrieval.embedder._get_openai_client", return_value=mock_client):
            result = await _embed_with_retry("hello")

        assert result == (0.1, 0.2, 0.3)
        assert mock_client.embeddings.create.call_count == 1

    async def test_retries_on_timeout(self):
        mock_response = AsyncMock()
        mock_response.data = [AsyncMock(embedding=[0.1, 0.2, 0.3])]

        mock_client = AsyncMock()
        mock_client.embeddings.create.side_effect = [
            APITimeoutError(request=None),
            mock_response,
        ]

        with patch("src.retrieval.embedder._get_openai_client", return_value=mock_client):
            result = await _embed_with_retry("hello")

        assert result == (0.1, 0.2, 0.3)
        assert mock_client.embeddings.create.call_count == 2

    async def test_retries_on_connection_error(self):
        mock_response = AsyncMock()
        mock_response.data = [AsyncMock(embedding=[0.1, 0.2])]

        mock_client = AsyncMock()
        mock_client.embeddings.create.side_effect = [
            APIConnectionError(request=None),
            mock_response,
        ]

        with patch("src.retrieval.embedder._get_openai_client", return_value=mock_client):
            result = await _embed_with_retry("hello")

        assert result == (0.1, 0.2)
        assert mock_client.embeddings.create.call_count == 2

    async def test_raises_after_max_attempts(self):
        mock_client = AsyncMock()
        mock_client.embeddings.create.side_effect = APITimeoutError(request=None)

        with (
            patch("src.retrieval.embedder._get_openai_client", return_value=mock_client),
            pytest.raises(APITimeoutError),
        ):
            await _embed_with_retry("hello")

        # 3 attempts total (initial + 2 retries)
        assert mock_client.embeddings.create.call_count == 3

    async def test_no_retry_on_permanent_error(self):
        """Auth errors, bad requests, etc. should fail immediately."""
        mock_client = AsyncMock()
        mock_client.embeddings.create.side_effect = ValueError("bad input")

        with (
            patch("src.retrieval.embedder._get_openai_client", return_value=mock_client),
            pytest.raises(ValueError, match="bad input"),
        ):
            await _embed_with_retry("hello")

        # Only 1 attempt — no retry on non-transient errors
        assert mock_client.embeddings.create.call_count == 1


class TestQdrantRetry:
    """Test retry behavior for Qdrant search calls."""

    async def test_retries_on_timeout(self):
        from src.retrieval.strategies import _search_qdrant

        mock_response = AsyncMock()
        mock_response.points = []

        mock_client = AsyncMock()
        mock_client.query_points.side_effect = [
            httpx.ReadTimeout("timed out"),
            mock_response,
        ]

        with patch("src.retrieval.strategies.get_settings") as mock_settings:
            mock_settings.return_value.qdrant_collection = "test"
            result = await _search_qdrant(mock_client, [0.1, 0.2])

        assert result == []
        assert mock_client.query_points.call_count == 2

    async def test_raises_after_max_attempts(self):
        from src.retrieval.strategies import _search_qdrant

        mock_client = AsyncMock()
        mock_client.query_points.side_effect = httpx.ConnectError("connection refused")

        with (
            patch("src.retrieval.strategies.get_settings") as mock_settings,
            pytest.raises(httpx.ConnectError),
        ):
            mock_settings.return_value.qdrant_collection = "test"
            await _search_qdrant(mock_client, [0.1, 0.2])

        # 2 attempts total (initial + 1 retry)
        assert mock_client.query_points.call_count == 2
