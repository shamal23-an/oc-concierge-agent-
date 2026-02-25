from __future__ import annotations

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

from src.config.constants import (
    MIN_CHUNKS_FOR_CONFIDENCE,
    SCORE_THRESHOLD_PROPERTY,
    SCORE_THRESHOLD_REGION,
    SCORE_THRESHOLD_SHARED,
)
from src.config.settings import get_settings
from src.domain.properties import PropertyID, Region, get_properties_for_region
from src.domain.schemas import QueryScope, RetrievedChunk

logger = structlog.get_logger()


def _search_qdrant(
    client: QdrantClient,
    vector: list[float],
    *,
    filter_: Filter | None = None,
    limit: int = 5,
    score_threshold: float = 0.3,
) -> list[RetrievedChunk]:
    """Raw Qdrant search returning typed chunks."""
    settings = get_settings()
    results = client.search(
        collection_name=settings.qdrant_collection,
        query_vector=vector,
        query_filter=filter_,
        limit=limit,
        score_threshold=score_threshold,
    )
    chunks: list[RetrievedChunk] = []
    for hit in results:
        payload = hit.payload or {}
        chunks.append(
            RetrievedChunk(
                content=payload.get("text", ""),
                score=hit.score,
                property_ids=payload.get("property_ids", []),
                source_file=payload.get("source_file", ""),
                metadata=payload,
            )
        )
    return chunks


def search_property(
    client: QdrantClient,
    vector: list[float],
    property_id: PropertyID,
    *,
    limit: int = 5,
) -> list[RetrievedChunk]:
    """Search chunks for a specific property."""
    return _search_qdrant(
        client,
        vector,
        filter_=Filter(
            must=[
                FieldCondition(
                    key="property_ids",
                    match=MatchValue(value=str(property_id)),
                )
            ]
        ),
        limit=limit,
        score_threshold=SCORE_THRESHOLD_PROPERTY,
    )


def search_region(
    client: QdrantClient,
    vector: list[float],
    region: Region,
    *,
    limit: int = 7,
) -> list[RetrievedChunk]:
    """Search chunks for all properties in a region."""
    property_ids = [str(p) for p in get_properties_for_region(region)]
    return _search_qdrant(
        client,
        vector,
        filter_=Filter(
            must=[
                FieldCondition(
                    key="property_ids",
                    match=MatchAny(any=property_ids),
                )
            ]
        ),
        limit=limit,
        score_threshold=SCORE_THRESHOLD_REGION,
    )


def search_group(
    client: QdrantClient,
    vector: list[float],
    *,
    limit: int = 7,
) -> list[RetrievedChunk]:
    """Search across all properties (collection-wide)."""
    return _search_qdrant(
        client,
        vector,
        limit=limit,
        score_threshold=SCORE_THRESHOLD_SHARED,
    )


def search_cross_property(
    client: QdrantClient,
    vector: list[float],
    property_ids: list[PropertyID],
    *,
    limit: int = 10,
) -> list[RetrievedChunk]:
    """Search chunks for specific properties (comparison queries)."""
    pid_strings = [str(p) for p in property_ids]
    return _search_qdrant(
        client,
        vector,
        filter_=Filter(
            must=[
                FieldCondition(
                    key="property_ids",
                    match=MatchAny(any=pid_strings),
                )
            ]
        ),
        limit=limit,
        score_threshold=SCORE_THRESHOLD_REGION,
    )


def layered_retrieve(
    client: QdrantClient,
    vector: list[float],
    *,
    scope: QueryScope,
    property_id: PropertyID | None = None,
    property_ids: list[PropertyID] | None = None,
    region: Region | None = None,
) -> list[RetrievedChunk]:
    """Execute the appropriate retrieval strategy based on scope.

    Implements 3-tier fallback for property scope:
    1. Property-specific
    2. Region broadening (if <2 results)
    3. Shared/general (if still <2 results)
    """
    settings = get_settings()
    top_k = settings.top_k

    if scope == QueryScope.PROPERTY and property_id:
        chunks = search_property(client, vector, property_id, limit=top_k)

        # Fallback to region if too few results
        if len(chunks) < MIN_CHUNKS_FOR_CONFIDENCE and region:
            logger.info("retrieval_fallback_to_region", property_id=str(property_id))
            region_chunks = search_region(client, vector, region, limit=top_k)
            chunks = _merge_chunks(chunks, region_chunks, max_total=top_k)

        # Fallback to shared if still too few
        if len(chunks) < MIN_CHUNKS_FOR_CONFIDENCE:
            logger.info("retrieval_fallback_to_shared", property_id=str(property_id))
            shared_chunks = search_group(client, vector, limit=top_k)
            chunks = _merge_chunks(chunks, shared_chunks, max_total=top_k)

        return chunks

    if scope == QueryScope.REGION and region:
        return search_region(client, vector, region, limit=top_k + 2)

    if scope == QueryScope.CROSS_PROPERTY and property_ids:
        return search_cross_property(client, vector, property_ids, limit=top_k * 2)

    # GROUP or fallback
    return search_group(client, vector, limit=top_k)


def _merge_chunks(
    primary: list[RetrievedChunk],
    secondary: list[RetrievedChunk],
    *,
    max_total: int,
) -> list[RetrievedChunk]:
    """Merge two chunk lists, deduplicating by content and capping at max_total."""
    seen_content: set[str] = set()
    merged: list[RetrievedChunk] = []

    for chunk in primary:
        key = chunk["content"][:200]
        if key not in seen_content:
            seen_content.add(key)
            merged.append(chunk)

    for chunk in secondary:
        if len(merged) >= max_total:
            break
        key = chunk["content"][:200]
        if key not in seen_content:
            seen_content.add(key)
            merged.append(chunk)

    return merged
