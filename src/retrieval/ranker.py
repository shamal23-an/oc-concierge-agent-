from __future__ import annotations

import datetime as dt

import httpx
import structlog

from src.config.settings import get_settings
from src.domain.schemas import RetrievedChunk

logger = structlog.get_logger()

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
_TEMPORAL_BOOST = 0.1
_TEMPORAL_PENALTY = -0.15


def _detect_query_doc_types(message: str) -> set[str]:
    """Detect which document types are relevant to the query."""
    lower = message.lower()
    matched = set()
    for doc_type, keywords in _QUERY_TYPE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            matched.add(doc_type)
    return matched


def _temporal_score_adjust(metadata: dict) -> float:
    """Boost current-validity docs, penalize expired ones."""
    valid_from = metadata.get("valid_from")
    valid_to = metadata.get("valid_to")
    if not valid_from and not valid_to:
        return 0.0

    now_str = dt.datetime.now(tz=dt.UTC).strftime("%Y-%m")
    if valid_to and now_str > valid_to:
        return _TEMPORAL_PENALTY  # Expired
    if valid_from and valid_to and valid_from <= now_str <= valid_to:
        return _TEMPORAL_BOOST  # Currently valid
    if valid_from and now_str >= valid_from:
        return _TEMPORAL_BOOST  # Started, no end date or not expired
    return 0.0


def _enforce_diversity(
    chunks: list[tuple[float, RetrievedChunk]],
    max_per_source: int,
) -> list[tuple[float, RetrievedChunk]]:
    """Limit max chunks from same source_file to prevent context flooding."""
    source_counts: dict[str, int] = {}
    result: list[tuple[float, RetrievedChunk]] = []
    for score, chunk in chunks:
        source = chunk.get("source_file", "")
        count = source_counts.get(source, 0)
        if count >= max_per_source:
            continue
        source_counts[source] = count + 1
        result.append((score, chunk))
    return result


def _apply_score_gap(
    chunks: list[tuple[float, RetrievedChunk]],
    gap_threshold: float,
) -> list[tuple[float, RetrievedChunk]]:
    """Truncate results at a large score gap (indicates irrelevant tail)."""
    if len(chunks) <= 1:
        return chunks
    result = [chunks[0]]
    for i in range(1, len(chunks)):
        gap = chunks[i - 1][0] - chunks[i][0]
        if gap > gap_threshold + 1e-9:  # epsilon for float comparison
            break
        result.append(chunks[i])
    return result


def rank_chunks(
    chunks: list[RetrievedChunk],
    *,
    target_property_id: str | None = None,
    query: str | None = None,
) -> list[RetrievedChunk]:
    """Rank and deduplicate retrieved chunks (local fallback ranker).

    Scoring: base score + property match + document_type + temporal + diversity.
    """
    if not chunks:
        return []

    settings = get_settings()
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

        # Temporal boost/penalty
        score += _temporal_score_adjust(chunk.get("metadata", {}))

        scored.append((score, chunk))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Enforce source diversity
    scored = _enforce_diversity(scored, max_per_source=settings.max_chunks_per_source)

    # Apply score gap detection
    scored = _apply_score_gap(scored, gap_threshold=settings.score_gap_threshold)

    return [chunk for _, chunk in scored]


async def rerank_chunks(
    query: str,
    chunks: list[RetrievedChunk],
    *,
    top_k: int = 5,
) -> list[RetrievedChunk]:
    """Re-rank chunks using Jina Reranker API.

    Falls back to local rank_chunks() if Jina is unavailable or unconfigured.
    """
    settings = get_settings()

    if not settings.jina_api_key or not chunks:
        return rank_chunks(chunks, query=query)

    try:
        documents = [c["content"] for c in chunks]
        async with httpx.AsyncClient(timeout=settings.jina_rerank_timeout) as client:
            resp = await client.post(
                "https://api.jina.ai/v1/rerank",
                headers={
                    "Authorization": f"Bearer {settings.jina_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.jina_rerank_model,
                    "query": query,
                    "documents": documents,
                    "top_n": min(top_k, len(documents)),
                },
            )
            resp.raise_for_status()
            data = resp.json()

        min_score = settings.rerank_min_score
        reranked: list[RetrievedChunk] = []
        seen_prefixes: set[str] = set()

        for result in data.get("results", []):
            idx = result["index"]
            relevance = result["relevance_score"]

            if relevance < min_score:
                continue

            chunk = chunks[idx]
            prefix = chunk["content"][:150].strip()
            if prefix in seen_prefixes:
                continue
            seen_prefixes.add(prefix)

            # Replace score with Jina relevance score
            reranked.append(
                RetrievedChunk(
                    content=chunk["content"],
                    score=relevance,
                    property_ids=chunk["property_ids"],
                    source_file=chunk["source_file"],
                    metadata=chunk.get("metadata", {}),
                )
            )

        logger.info(
            "jina_rerank_complete",
            input_chunks=len(chunks),
            output_chunks=len(reranked),
            top_score=round(reranked[0]["score"], 3) if reranked else 0,
        )
        return reranked

    except Exception:
        logger.warning("jina_rerank_failed_fallback", exc_info=True)
        return rank_chunks(chunks, query=query)
