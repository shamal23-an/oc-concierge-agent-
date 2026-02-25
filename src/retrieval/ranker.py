from __future__ import annotations

from src.domain.schemas import RetrievedChunk


def rank_chunks(
    chunks: list[RetrievedChunk],
    *,
    target_property_id: str | None = None,
) -> list[RetrievedChunk]:
    """Rank and deduplicate retrieved chunks.

    Scoring: base score + property match bonus. Deduplicates near-identical chunks.
    """
    if not chunks:
        return []

    scored: list[tuple[float, RetrievedChunk]] = []
    seen_prefixes: set[str] = set()

    for chunk in chunks:
        # Dedup near-identical chunks (same first 150 chars)
        prefix = chunk["content"][:150].strip()
        if prefix in seen_prefixes:
            continue
        seen_prefixes.add(prefix)

        score = chunk["score"]

        # Boost chunks from the target property
        if target_property_id and target_property_id in chunk["property_ids"]:
            score += 0.05

        scored.append((score, chunk))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in scored]
