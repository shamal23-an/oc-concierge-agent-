from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from qdrant_client.models import SparseVector

from src.domain.properties import PropertyID, Region
from src.domain.schemas import QueryScope
from src.retrieval.strategies import (
    _search_qdrant,
    layered_retrieve,
    search_property,
)


def _mock_point(score: float, text: str = "chunk", pids: list[str] | None = None):
    """Create a mock Qdrant point."""
    point = MagicMock()
    point.score = score
    point.payload = {
        "text": text,
        "property_ids": pids or ["la_fontaine"],
        "source_file": "test.pdf",
        "region": "franschhoek",
    }
    return point


@pytest.fixture
def mock_client():
    client = AsyncMock()
    return client


@pytest.fixture
def mock_settings():
    with patch("src.retrieval.strategies.get_settings") as m:
        m.return_value = MagicMock(
            qdrant_collection="test_col",
            top_k=5,
        )
        yield m


class TestHybridSearch:
    @pytest.mark.asyncio
    async def test_dense_only_when_no_sparse(self, mock_client, mock_settings):
        """Without sparse vector, should use dense-only query."""
        mock_client.query_points.return_value = MagicMock(
            points=[_mock_point(0.8)]
        )

        results = await _search_qdrant(mock_client, [0.1] * 10)

        call_kwargs = mock_client.query_points.call_args[1]
        assert call_kwargs["using"] == "dense"
        assert "prefetch" not in call_kwargs
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_hybrid_with_sparse_vector(self, mock_client, mock_settings):
        """With sparse vector, should use prefetch + RRF fusion."""
        mock_client.query_points.return_value = MagicMock(
            points=[_mock_point(0.9), _mock_point(0.7)]
        )
        sparse = SparseVector(indices=[1, 5, 10], values=[0.5, 0.8, 0.3])

        results = await _search_qdrant(
            mock_client, [0.1] * 10, sparse_vector=sparse
        )

        call_kwargs = mock_client.query_points.call_args[1]
        assert "prefetch" in call_kwargs
        assert len(call_kwargs["prefetch"]) == 2  # dense + sparse
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_empty_sparse_uses_dense_only(self, mock_client, mock_settings):
        """Empty sparse vector (no indices) should fall back to dense-only."""
        mock_client.query_points.return_value = MagicMock(
            points=[_mock_point(0.6)]
        )
        sparse = SparseVector(indices=[], values=[])

        await _search_qdrant(mock_client, [0.1] * 10, sparse_vector=sparse)

        call_kwargs = mock_client.query_points.call_args[1]
        assert call_kwargs["using"] == "dense"
        assert "prefetch" not in call_kwargs

    @pytest.mark.asyncio
    async def test_search_property_passes_sparse(self, mock_client, mock_settings):
        """search_property should forward sparse_vector."""
        mock_client.query_points.return_value = MagicMock(
            points=[_mock_point(0.8)]
        )
        sparse = SparseVector(indices=[1], values=[0.5])

        await search_property(
            mock_client,
            [0.1] * 10,
            PropertyID.LA_FONTAINE,
            sparse_vector=sparse,
        )

        call_kwargs = mock_client.query_points.call_args[1]
        assert "prefetch" in call_kwargs


class TestLayeredRetrieveHybrid:
    @pytest.mark.asyncio
    async def test_passes_sparse_to_search(self, mock_client, mock_settings):
        """layered_retrieve should pass sparse_vector through."""
        mock_client.query_points.return_value = MagicMock(
            points=[_mock_point(0.8, "chunk1"), _mock_point(0.7, "chunk2")]
        )
        sparse = SparseVector(indices=[1, 2], values=[0.5, 0.8])

        results = await layered_retrieve(
            mock_client,
            [0.1] * 10,
            scope=QueryScope.PROPERTY,
            property_id=PropertyID.LA_FONTAINE,
            region=Region.FRANSCHHOEK,
            sparse_vector=sparse,
        )

        assert len(results) == 2
        call_kwargs = mock_client.query_points.call_args[1]
        assert "prefetch" in call_kwargs

    @pytest.mark.asyncio
    async def test_group_scope_with_sparse(self, mock_client, mock_settings):
        """GROUP scope should also support sparse vectors."""
        mock_client.query_points.return_value = MagicMock(
            points=[_mock_point(0.6)]
        )
        sparse = SparseVector(indices=[5], values=[0.9])

        results = await layered_retrieve(
            mock_client,
            [0.1] * 10,
            scope=QueryScope.GROUP,
            sparse_vector=sparse,
        )

        assert len(results) == 1
