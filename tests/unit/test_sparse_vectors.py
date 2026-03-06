from __future__ import annotations

from qdrant_client.models import SparseVector

from src.ingestion.embedder import compute_sparse_vector, compute_sparse_vectors


class TestComputeSparseVector:
    def test_returns_sparse_vector(self):
        result = compute_sparse_vector("hello world")
        assert isinstance(result, SparseVector)

    def test_non_empty_for_text(self):
        result = compute_sparse_vector("The rack rate for a deluxe room is R2500")
        assert len(result.indices) > 0
        assert len(result.values) > 0
        assert len(result.indices) == len(result.values)

    def test_empty_for_empty_text(self):
        result = compute_sparse_vector("")
        assert result.indices == []
        assert result.values == []

    def test_empty_for_punctuation_only(self):
        result = compute_sparse_vector("!!! ... ???")
        assert result.indices == []
        assert result.values == []

    def test_indices_are_sorted(self):
        result = compute_sparse_vector("hello world test multiple tokens here")
        assert result.indices == sorted(result.indices)

    def test_values_are_positive(self):
        result = compute_sparse_vector("hello world")
        for v in result.values:
            assert v > 0

    def test_values_are_bounded(self):
        """BM25 saturation: tf / (tf + k1) is always < 1."""
        result = compute_sparse_vector("word word word word word word word")
        for v in result.values:
            assert 0 < v < 1

    def test_repeated_tokens_have_higher_values(self):
        single = compute_sparse_vector("rate")
        repeated = compute_sparse_vector("rate rate rate rate")
        # Both should have the same index for "rate"
        assert len(single.indices) == 1
        assert len(repeated.indices) == 1
        assert single.indices[0] == repeated.indices[0]
        # Repeated should have higher BM25 weight
        assert repeated.values[0] > single.values[0]

    def test_case_insensitive(self):
        lower = compute_sparse_vector("Hello World")
        upper = compute_sparse_vector("hello world")
        assert lower.indices == upper.indices
        assert lower.values == upper.values

    def test_different_texts_different_vectors(self):
        v1 = compute_sparse_vector("rack rate deluxe room")
        v2 = compute_sparse_vector("spa treatment massage")
        assert set(v1.indices) != set(v2.indices)

    def test_indices_within_vocab_range(self):
        result = compute_sparse_vector("some text with various words and numbers 123")
        for idx in result.indices:
            assert 0 <= idx < 2**16  # _SPARSE_VOCAB_SIZE


class TestComputeSparseVectors:
    def test_batch_returns_list(self):
        texts = ["hello", "world", "test"]
        results = compute_sparse_vectors(texts)
        assert len(results) == 3
        assert all(isinstance(r, SparseVector) for r in results)

    def test_empty_batch(self):
        results = compute_sparse_vectors([])
        assert results == []
