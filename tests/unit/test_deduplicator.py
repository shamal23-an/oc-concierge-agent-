from __future__ import annotations

from src.ingestion.deduplicator import (
    DeduplicationTracker,
    content_hash,
    deterministic_point_id,
)


class TestContentHash:
    def test_same_content_same_hash(self):
        assert content_hash("hello world") == content_hash("hello world")

    def test_different_content_different_hash(self):
        assert content_hash("hello") != content_hash("world")

    def test_returns_hex_string(self):
        h = content_hash("test")
        assert len(h) == 64  # SHA-256 hex length
        assert all(c in "0123456789abcdef" for c in h)


class TestDeterministicPointId:
    def test_same_inputs_same_id(self):
        id1 = deterministic_point_id("abc123", 0)
        id2 = deterministic_point_id("abc123", 0)
        assert id1 == id2

    def test_different_chunk_index_different_id(self):
        id1 = deterministic_point_id("abc123", 0)
        id2 = deterministic_point_id("abc123", 1)
        assert id1 != id2

    def test_different_hash_different_id(self):
        id1 = deterministic_point_id("abc123", 0)
        id2 = deterministic_point_id("def456", 0)
        assert id1 != id2

    def test_returns_valid_uuid(self):
        import uuid

        pid = deterministic_point_id("test", 0)
        uuid.UUID(pid)  # Raises ValueError if invalid


class TestDeduplicationTracker:
    def test_first_seen_not_duplicate(self):
        tracker = DeduplicationTracker()
        assert not tracker.is_duplicate("content A")

    def test_second_seen_is_duplicate(self):
        tracker = DeduplicationTracker()
        tracker.is_duplicate("content A")
        assert tracker.is_duplicate("content A")

    def test_different_content_not_duplicate(self):
        tracker = DeduplicationTracker()
        tracker.is_duplicate("content A")
        assert not tracker.is_duplicate("content B")

    def test_count_tracks_unique(self):
        tracker = DeduplicationTracker()
        tracker.is_duplicate("a")
        tracker.is_duplicate("b")
        tracker.is_duplicate("a")  # duplicate
        assert tracker.count == 2
