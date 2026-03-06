from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.schemas import RetrievedChunk
from src.retrieval.ranker import rank_chunks, rerank_chunks


def _chunk(content: str, score: float = 0.5, pids: list[str] | None = None) -> RetrievedChunk:
    return RetrievedChunk(
        content=content,
        score=score,
        property_ids=pids or ["la_fontaine"],
        source_file="test.pdf",
        metadata={"document_type": "general"},
    )


class TestRerankerFallback:
    @pytest.mark.asyncio
    async def test_falls_back_when_no_api_key(self):
        """Without jina_api_key, should use local rank_chunks."""
        chunks = [_chunk("A", 0.5), _chunk("B", 0.8)]
        with patch("src.retrieval.ranker.get_settings") as m:
            m.return_value = MagicMock(jina_api_key="")
            result = await rerank_chunks("test query", chunks)

        # Local ranker sorts by score descending
        assert result[0]["content"] == "B"
        assert result[1]["content"] == "A"

    @pytest.mark.asyncio
    async def test_falls_back_on_empty_chunks(self):
        with patch("src.retrieval.ranker.get_settings") as m:
            m.return_value = MagicMock(jina_api_key="test-key")
            result = await rerank_chunks("test query", [])
        assert result == []


class TestRerankerJina:
    @pytest.mark.asyncio
    async def test_jina_rerank_success(self):
        """Successful Jina rerank should return reordered chunks."""
        chunks = [_chunk("rates info", 0.5), _chunk("spa info", 0.3)]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {"index": 1, "relevance_score": 0.95},
                {"index": 0, "relevance_score": 0.72},
            ]
        }

        with (
            patch("src.retrieval.ranker.get_settings") as mock_settings,
            patch("src.retrieval.ranker.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.return_value = MagicMock(
                jina_api_key="test-key",
                jina_rerank_model="jina-reranker-v2-base-multilingual",
                jina_rerank_timeout=5,
                rerank_min_score=0.25,
            )
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await rerank_chunks("what are the rates", chunks)

        # Spa info ranked first (higher Jina score)
        assert len(result) == 2
        assert result[0]["content"] == "spa info"
        assert result[0]["score"] == 0.95
        assert result[1]["content"] == "rates info"

    @pytest.mark.asyncio
    async def test_jina_filters_by_min_score(self):
        """Chunks below min_score should be filtered out."""
        chunks = [_chunk("good", 0.5), _chunk("bad", 0.3)]

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {"index": 0, "relevance_score": 0.8},
                {"index": 1, "relevance_score": 0.1},  # Below min_score
            ]
        }

        with (
            patch("src.retrieval.ranker.get_settings") as mock_settings,
            patch("src.retrieval.ranker.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.return_value = MagicMock(
                jina_api_key="test-key",
                jina_rerank_model="jina-reranker-v2-base-multilingual",
                jina_rerank_timeout=5,
                rerank_min_score=0.25,
            )
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await rerank_chunks("query", chunks)

        assert len(result) == 1
        assert result[0]["content"] == "good"

    @pytest.mark.asyncio
    async def test_jina_error_falls_back_to_local(self):
        """API error should fall back to local ranker."""
        chunks = [_chunk("A", 0.3), _chunk("B", 0.8)]

        with (
            patch("src.retrieval.ranker.get_settings") as mock_settings,
            patch("src.retrieval.ranker.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.return_value = MagicMock(
                jina_api_key="test-key",
                jina_rerank_model="test",
                jina_rerank_timeout=5,
                rerank_min_score=0.25,
            )
            mock_client = AsyncMock()
            mock_client.post.side_effect = Exception("API down")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await rerank_chunks("query", chunks)

        # Falls back to local: B has higher score
        assert result[0]["content"] == "B"

    @pytest.mark.asyncio
    async def test_jina_deduplicates(self):
        """Duplicate content should be removed during reranking."""
        chunks = [_chunk("same content here", 0.5), _chunk("same content here", 0.4)]

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {"index": 0, "relevance_score": 0.9},
                {"index": 1, "relevance_score": 0.85},
            ]
        }

        with (
            patch("src.retrieval.ranker.get_settings") as mock_settings,
            patch("src.retrieval.ranker.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.return_value = MagicMock(
                jina_api_key="test-key",
                jina_rerank_model="test",
                jina_rerank_timeout=5,
                rerank_min_score=0.25,
            )
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await rerank_chunks("query", chunks)

        assert len(result) == 1


class TestLocalRankerUnchanged:
    def test_existing_rank_chunks_still_works(self):
        """Existing rank_chunks function should be unchanged."""
        chunks = [_chunk("A", 0.3), _chunk("B", 0.8), _chunk("C", 0.5)]
        result = rank_chunks(chunks, query="test")
        assert result[0]["content"] == "B"
        assert result[1]["content"] == "C"
        assert result[2]["content"] == "A"
