from __future__ import annotations

from src.domain.schemas import RetrievedChunk

# Map query keywords to document_type values for boosting relevant docs.
_QUERY_TYPE_KEYWORDS: dict[str, list[str]] = {
    "rates": ["rate", "rates", "price", "pricing", "cost", "tariff", "how much", "per night"],
    "restaurant": [
        "menu",
        "dinner",
        "lunch",
        "breakfast",
        "restaurant",
        "dining",
        "food",
        "wine list",
        "braai",
    ],
    "activity": [
        "activity",
        "activities",
        "things to do",
        "tours",
        "game drive",
        "excursion",
        "what to do",
    ],
    "spa": ["spa", "massage", "wellness", "beauty", "treatment"],
    "directions": [
        "direction",
        "how to get",
        "drive",
        "airport",
        "route",
        "map",
        "far",
        "distance",
    ],
}

_DOC_TYPE_BOOST = 0.08


def _detect_query_doc_types(message: str) -> set[str]:
    """Detect which document types are relevant to the query."""
    lower = message.lower()
    matched = set()
    for doc_type, keywords in _QUERY_TYPE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            matched.add(doc_type)
    return matched


def rank_chunks(
    chunks: list[RetrievedChunk],
    *,
    target_property_id: str | None = None,
    query: str | None = None,
) -> list[RetrievedChunk]:
    """Rank and deduplicate retrieved chunks.

    Scoring: base score + property match bonus + document_type bonus.
    Deduplicates near-identical chunks.
    """
    if not chunks:
        return []

    relevant_doc_types = _detect_query_doc_types(query) if query else set()

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

        # Boost chunks whose document_type matches the query intent
        chunk_doc_type = chunk.get("metadata", {}).get("document_type", "")
        if chunk_doc_type and chunk_doc_type in relevant_doc_types:
            score += _DOC_TYPE_BOOST

        scored.append((score, chunk))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in scored]
