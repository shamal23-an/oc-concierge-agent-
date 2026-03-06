from __future__ import annotations

import logging

import httpx
import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchAny,
    MatchValue,
    Prefetch,
    SparseVector,
)
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

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

# Qdrant uses httpx under the hood — retry on transient network errors only.
_TRANSIENT_QDRANT_ERRORS = (httpx.TimeoutException, httpx.ConnectError)


def _hits_to_chunks(results: list) -> list[RetrievedChunk]:
    """Convert Qdrant query results to RetrievedChunk list."""
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


@retry(
    retry=retry_if_exception_type(_TRANSIENT_QDRANT_ERRORS),
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    before_sleep=before_sleep_log(logging.getLogger("tenacity.qdrant"), logging.WARNING),
    reraise=True,
)
async def _search_qdrant(
    client: AsyncQdrantClient,
    vector: list[float],
    *,
    sparse_vector: SparseVector | None = None,
    filter_: Filter | None = None,
    limit: int = 5,
    score_threshold: float = 0.3,
) -> list[RetrievedChunk]:
    """Search Qdrant with hybrid (dense+sparse RRF) or dense-only fallback."""
    settings = get_settings()

    if sparse_vector and sparse_vector.indices:
        # Hybrid search: prefetch dense + sparse, fuse with RRF
        response = await client.query_points(
            collection_name=settings.qdrant_collection,
            prefetch=[
                Prefetch(
                    query=vector,
                    using="dense",
                    limit=limit * 3,
                    filter=filter_,
                ),
                Prefetch(
                    query=sparse_vector,
                    using="sparse",
                    limit=limit * 3,
                    filter=filter_,
                ),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=limit,
            query_filter=filter_,
        )
    else:
        # Dense-only fallback
        response = await client.query_points(
            collection_name=settings.qdrant_collection,
            query=vector,
            using="dense",
            query_filter=filter_,
            limit=limit,
            score_threshold=score_threshold,
        )

    return _hits_to_chunks(response.points)


async def search_property(
    client: AsyncQdrantClient,
    vector: list[float],
    property_id: PropertyID,
    *,
    sparse_vector: SparseVector | None = None,
    limit: int = 5,
) -> list[RetrievedChunk]:
    """Search chunks for a specific property."""
    return await _search_qdrant(
        client,
        vector,
        sparse_vector=sparse_vector,
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


async def search_region(
    client: AsyncQdrantClient,
    vector: list[float],
    region: Region,
    *,
    sparse_vector: SparseVector | None = None,
    limit: int = 7,
) -> list[RetrievedChunk]:
    """Search chunks for all properties in a region."""
    property_ids = [str(p) for p in get_properties_for_region(region)]
    return await _search_qdrant(
        client,
        vector,
        sparse_vector=sparse_vector,
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


async def search_group(
    client: AsyncQdrantClient,
    vector: list[float],
    *,
    sparse_vector: SparseVector | None = None,
    limit: int = 7,
) -> list[RetrievedChunk]:
    """Search across all properties (collection-wide)."""
    return await _search_qdrant(
        client,
        vector,
        sparse_vector=sparse_vector,
        limit=limit,
        score_threshold=SCORE_THRESHOLD_SHARED,
    )


async def search_cross_property(
    client: AsyncQdrantClient,
    vector: list[float],
    property_ids: list[PropertyID],
    *,
    sparse_vector: SparseVector | None = None,
    limit: int = 10,
) -> list[RetrievedChunk]:
    """Search chunks for specific properties (comparison queries)."""
    pid_strings = [str(p) for p in property_ids]
    return await _search_qdrant(
        client,
        vector,
        sparse_vector=sparse_vector,
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


async def layered_retrieve(
    client: AsyncQdrantClient,
    vector: list[float],
    *,
    scope: QueryScope,
    property_id: PropertyID | None = None,
    property_ids: list[PropertyID] | None = None,
    region: Region | None = None,
    sparse_vector: SparseVector | None = None,
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
        chunks = await search_property(
            client,
            vector,
            property_id,
            sparse_vector=sparse_vector,
            limit=top_k,
        )

        # Fallback to region if too few results
        if len(chunks) < MIN_CHUNKS_FOR_CONFIDENCE and region:
            logger.info("retrieval_fallback_to_region", property_id=str(property_id))
            region_chunks = await search_region(
                client,
                vector,
                region,
                sparse_vector=sparse_vector,
                limit=top_k,
            )
            chunks = _merge_chunks(chunks, region_chunks, max_total=top_k)

        # Fallback to shared if still too few
        if len(chunks) < MIN_CHUNKS_FOR_CONFIDENCE:
            logger.info("retrieval_fallback_to_shared", property_id=str(property_id))
            shared_chunks = await search_group(
                client,
                vector,
                sparse_vector=sparse_vector,
                limit=top_k,
            )
            chunks = _merge_chunks(chunks, shared_chunks, max_total=top_k)

        return chunks

    if scope == QueryScope.REGION and region:
        return await search_region(
            client,
            vector,
            region,
            sparse_vector=sparse_vector,
            limit=top_k + 2,
        )

    if scope == QueryScope.CROSS_PROPERTY and property_ids:
        return await search_cross_property(
            client,
            vector,
            property_ids,
            sparse_vector=sparse_vector,
            limit=top_k * 2,
        )

    # GROUP or fallback
    return await search_group(
        client,
        vector,
        sparse_vector=sparse_vector,
        limit=top_k,
    )


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
