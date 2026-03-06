from __future__ import annotations

from unittest.mock import MagicMock, patch

from qdrant_client.models import (
    CollectionDescription,
    Distance,
    SparseVector,
)

from src.ingestion.store import ensure_collection, upsert_chunks


class TestEnsureCollection:
    @patch("src.ingestion.store.get_settings")
    def test_creates_collection_with_named_vectors(self, mock_settings):
        mock_settings.return_value = MagicMock(
            qdrant_collection="test_col",
            embedding_dimensions=3072,
        )
        client = MagicMock()
        client.get_collections.return_value = MagicMock(collections=[])

        ensure_collection(client, recreate=False)

        # Verify create_collection was called
        client.create_collection.assert_called_once()
        call_kwargs = client.create_collection.call_args[1]

        # Check named vector config
        assert "test_col" == call_kwargs["collection_name"]
        assert "dense" in call_kwargs["vectors_config"]
        dense_config = call_kwargs["vectors_config"]["dense"]
        assert dense_config.size == 3072
        assert dense_config.distance == Distance.COSINE

        # Check sparse vector config
        assert "sparse" in call_kwargs["sparse_vectors_config"]

    @patch("src.ingestion.store.get_settings")
    def test_skips_if_collection_exists(self, mock_settings):
        mock_settings.return_value = MagicMock(qdrant_collection="test_col")
        client = MagicMock()
        client.get_collections.return_value = MagicMock(
            collections=[CollectionDescription(name="test_col")]
        )

        ensure_collection(client, recreate=False)

        client.create_collection.assert_not_called()

    @patch("src.ingestion.store.get_settings")
    def test_recreate_deletes_first(self, mock_settings):
        mock_settings.return_value = MagicMock(
            qdrant_collection="test_col",
            embedding_dimensions=3072,
        )
        client = MagicMock()
        client.get_collections.return_value = MagicMock(collections=[])

        ensure_collection(client, recreate=True)

        client.delete_collection.assert_called_once_with("test_col")
        client.create_collection.assert_called_once()

    @patch("src.ingestion.store.get_settings")
    def test_creates_payload_indexes(self, mock_settings):
        mock_settings.return_value = MagicMock(
            qdrant_collection="test_col",
            embedding_dimensions=3072,
        )
        client = MagicMock()
        client.get_collections.return_value = MagicMock(collections=[])

        ensure_collection(client, recreate=False)

        index_calls = client.create_payload_index.call_args_list
        indexed_fields = [c[1]["field_name"] for c in index_calls]
        assert "property_ids" in indexed_fields
        assert "region" in indexed_fields
        assert "document_type" in indexed_fields


class TestUpsertChunks:
    @patch("src.ingestion.store.get_settings")
    def test_upsert_with_sparse_vectors(self, mock_settings):
        mock_settings.return_value = MagicMock(qdrant_collection="test_col")
        client = MagicMock()

        sparse = [
            SparseVector(indices=[1, 2], values=[0.5, 0.8]),
            SparseVector(indices=[3], values=[0.6]),
        ]

        count = upsert_chunks(
            client,
            point_ids=["id1", "id2"],
            vectors=[[0.1] * 3072, [0.2] * 3072],
            payloads=[{"text": "a"}, {"text": "b"}],
            sparse_vectors=sparse,
        )

        assert count == 2
        client.upsert.assert_called_once()

        # Verify point structure has named vectors
        upsert_call = client.upsert.call_args
        points = upsert_call[1]["points"]
        assert len(points) == 2
        assert "dense" in points[0].vector
        assert "sparse" in points[0].vector

    @patch("src.ingestion.store.get_settings")
    def test_upsert_without_sparse_vectors(self, mock_settings):
        mock_settings.return_value = MagicMock(qdrant_collection="test_col")
        client = MagicMock()

        count = upsert_chunks(
            client,
            point_ids=["id1"],
            vectors=[[0.1] * 3072],
            payloads=[{"text": "a"}],
        )

        assert count == 1
        points = client.upsert.call_args[1]["points"]
        assert "dense" in points[0].vector
        assert "sparse" not in points[0].vector

    @patch("src.ingestion.store.get_settings")
    def test_batching(self, mock_settings):
        mock_settings.return_value = MagicMock(qdrant_collection="test_col")
        client = MagicMock()

        count = upsert_chunks(
            client,
            point_ids=[f"id{i}" for i in range(5)],
            vectors=[[0.1] * 10 for _ in range(5)],
            payloads=[{"text": f"t{i}"} for i in range(5)],
            batch_size=2,
        )

        assert count == 5
        assert client.upsert.call_count == 3  # 2 + 2 + 1
