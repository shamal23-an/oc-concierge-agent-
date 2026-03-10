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


def _default_settings(**overrides):
    """Build a mock settings with defaults for all ranker fields."""
    defaults = {
        "jina_api_key": "",
        "jina_rerank_model": "jina-reranker-v2-base-multilingual",
        "jina_rerank_timeout": 5,
        "rerank_min_score": 0.25,
        "max_chunks_per_source": 10,
        "score_gap_threshold": 0.3,
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


class TestRerankerFallback:
    @pytest.mark.asyncio
    async def test_falls_back_when_no_api_key(self):
        """Without jina_api_key, should use local rank_chunks."""
        chunks = [_chunk("A", 0.5), _chunk("B", 0.8)]
        with patch("src.retrieval.ranker.get_settings") as m:
            m.return_value = _default_settings(jina_api_key="")
            result = await rerank_chunks("test query", chunks)

        # Local ranker sorts by score descending
        assert result[0]["content"] == "B"
        assert result[1]["content"] == "A"

    @pytest.mark.asyncio
    async def test_falls_back_on_empty_chunks(self):
        with patch("src.retrieval.ranker.get_settings") as m:
            m.return_value = _default_settings(jina_api_key="test-key")
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
            mock_settings.return_value = _default_settings(jina_api_key="test-key")
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
        with patch("src.retrieval.ranker.get_settings") as m:
            m.return_value = MagicMock(max_chunks_per_source=3, score_gap_threshold=0.3)
            result = rank_chunks(chunks, query="test")
        assert result[0]["content"] == "B"
        assert result[1]["content"] == "C"
        assert result[2]["content"] == "A"


class TestSourceDiversity:
    def test_limits_chunks_per_source(self):
        """Max 3 chunks from the same source file."""
        chunks = [
            RetrievedChunk(
                content=f"Chunk {i}",
                score=0.9 - i * 0.01,
                property_ids=["la_fontaine"],
                source_file="rates.pdf",
                metadata={"document_type": "rates"},
            )
            for i in range(5)
        ]
        with patch("src.retrieval.ranker.get_settings") as m:
            m.return_value = MagicMock(max_chunks_per_source=3, score_gap_threshold=0.3)
            result = rank_chunks(chunks, query="rates")
        assert len(result) == 3

    def test_diverse_sources_all_kept(self):
        """Chunks from different sources should all be kept."""
        chunks = [
            RetrievedChunk(
                content=f"Chunk from file {i}",
                score=0.8,
                property_ids=["la_fontaine"],
                source_file=f"file{i}.pdf",
                metadata={"document_type": "general"},
            )
            for i in range(5)
        ]
        with patch("src.retrieval.ranker.get_settings") as m:
            m.return_value = MagicMock(max_chunks_per_source=3, score_gap_threshold=0.3)
            result = rank_chunks(chunks, query="test")
        assert len(result) == 5


class TestScoreGap:
    def test_truncates_at_large_gap(self):
        """Chunks after a >0.3 score gap should be dropped."""
        chunks = [
            _chunk("High quality chunk A", 0.9),
            _chunk("High quality chunk B", 0.85),
            _chunk("Irrelevant chunk C", 0.4),  # Gap of 0.45
        ]
        with patch("src.retrieval.ranker.get_settings") as m:
            m.return_value = MagicMock(max_chunks_per_source=10, score_gap_threshold=0.3)
            result = rank_chunks(chunks, query="test")
        assert len(result) == 2

    def test_no_gap_keeps_all(self):
        chunks = [_chunk("A content here", 0.9), _chunk("B content here", 0.7)]
        with patch("src.retrieval.ranker.get_settings") as m:
            m.return_value = MagicMock(max_chunks_per_source=10, score_gap_threshold=0.3)
            result = rank_chunks(chunks, query="test")
        assert len(result) == 2


class TestTemporalBoost:
    def test_current_validity_boosted(self):
        """Chunks with current validity dates get boosted."""
        from src.retrieval.ranker import _temporal_score_adjust

        meta = {"valid_from": "2024-01", "valid_to": "2027-12"}
        assert _temporal_score_adjust(meta) > 0

    def test_expired_penalized(self):
        from src.retrieval.ranker import _temporal_score_adjust

        meta = {"valid_from": "2020-01", "valid_to": "2021-12"}
        assert _temporal_score_adjust(meta) < 0

    def test_no_dates_no_adjustment(self):
        from src.retrieval.ranker import _temporal_score_adjust

        assert _temporal_score_adjust({}) == 0.0
