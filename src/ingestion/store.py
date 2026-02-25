from __future__ import annotations

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from src.config.settings import get_settings

logger = structlog.get_logger()


def ensure_collection(client: QdrantClient, *, recreate: bool = False) -> None:
    """Create or recreate the Qdrant collection with proper indexes."""
    settings = get_settings()
    collection_name = settings.qdrant_collection

    if recreate:
        try:
            client.delete_collection(collection_name)
            logger.info("collection_deleted", name=collection_name)
        except Exception:
            pass

    collections = [c.name for c in client.get_collections().collections]
    if collection_name in collections:
        logger.info("collection_exists", name=collection_name)
        return

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=settings.embedding_dimensions,
            distance=Distance.COSINE,
        ),
    )

    # Create payload indexes for filtered search
    for field_name in ("property_ids", "region", "document_type"):
        client.create_payload_index(
            collection_name=collection_name,
            field_name=field_name,
            field_schema=PayloadSchemaType.KEYWORD,
        )

    logger.info("collection_created", name=collection_name)


def upsert_chunks(
    client: QdrantClient,
    *,
    point_ids: list[str],
    vectors: list[list[float]],
    payloads: list[dict],
    batch_size: int = 100,
) -> int:
    """Upsert points to Qdrant in batches. Returns count of upserted points."""
    settings = get_settings()
    collection_name = settings.qdrant_collection
    total = 0

    for i in range(0, len(point_ids), batch_size):
        batch_points = [
            PointStruct(
                id=point_ids[j],
                vector=vectors[j],
                payload=payloads[j],
            )
            for j in range(i, min(i + batch_size, len(point_ids)))
        ]
        client.upsert(collection_name=collection_name, points=batch_points)
        total += len(batch_points)
        logger.debug("upserted_batch", count=len(batch_points), total=total)

    logger.info("upsert_complete", total=total)
    return total


def get_collection_stats(client: QdrantClient) -> dict:
    """Get collection statistics."""
    settings = get_settings()
    try:
        info = client.get_collection(settings.qdrant_collection)
        return {
            "points_count": info.points_count,
            "vectors_count": info.vectors_count,
            "status": info.status.value,
        }
    except Exception:
        return {"points_count": 0, "vectors_count": 0, "status": "not_found"}
