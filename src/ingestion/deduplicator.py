from __future__ import annotations

import hashlib
import uuid


def content_hash(text: str) -> str:
    """SHA-256 hash of text content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# Namespace UUID for deterministic point IDs
_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def deterministic_point_id(content_hash_hex: str, chunk_index: int) -> str:
    """Generate a deterministic UUID5 from content hash + chunk index.

    This ensures re-ingestion of the same content produces the same point IDs,
    making upserts idempotent (no duplicates).
    """
    key = f"{content_hash_hex}:{chunk_index}"
    return str(uuid.uuid5(_NAMESPACE, key))


class DeduplicationTracker:
    """Track seen content hashes to skip duplicate documents."""

    def __init__(self) -> None:
        self._seen_hashes: dict[str, str] = {}  # hash → first file path

    def is_duplicate(self, text: str, source_path: str = "") -> bool:
        """Check if content has already been seen.

        Returns True if duplicate. Logs which file was kept vs skipped.
        """
        h = content_hash(text)
        if h in self._seen_hashes:
            return True
        self._seen_hashes[h] = source_path
        return False

    def get_kept_source(self, text: str) -> str | None:
        """Return the source path of the first file with this content."""
        h = content_hash(text)
        return self._seen_hashes.get(h)

    @property
    def count(self) -> int:
        return len(self._seen_hashes)
