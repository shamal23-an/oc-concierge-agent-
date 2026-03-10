"""Ingestion CLI — parse, chunk, embed, and upsert KB documents to Qdrant."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import structlog

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qdrant_client import QdrantClient

from src.config.constants import SUPPORTED_EXTENSIONS
from src.config.logging import setup_logging
from src.config.settings import get_settings
from src.ingestion.chunker import chunk_text
from src.ingestion.deduplicator import (
    DeduplicationTracker,
    content_hash,
    deterministic_point_id,
)
from src.ingestion.parsers.pdf import PdfParser
from src.ingestion.property_tagger import classify_document_type, tag_property_ids
from src.ingestion.source_config import DEFAULT_SOURCES, SourceConfig, extract_validity_dates

logger = structlog.get_logger()

PARSERS = [PdfParser()]

# Legacy KB roots (used when --kb-path is passed)
LEGACY_KB_ROOTS = [
    Path("D:/Work/Projects/Oyster-Collection/knowldge_base"),
    Path("D:/Work/Projects/Oyster-Collection/Knowledge Base"),
]


def discover_files(kb_root: Path) -> list[Path]:
    """Recursively discover supported files in a KB root."""
    files = []
    for ext in SUPPORTED_EXTENSIONS:
        files.extend(kb_root.rglob(f"*{ext}"))
    return sorted(files)


def parse_file(path: Path) -> str | None:
    """Parse a file using the appropriate parser."""
    for parser in PARSERS:
        if parser.can_parse(path):
            return parser.parse(path)
    logger.warning("no_parser_found", path=str(path), suffix=path.suffix)
    return None


def run_ingestion(
    kb_roots: list[Path] | None = None,
    *,
    sources: list[SourceConfig] | None = None,
    recreate: bool = False,
    dry_run: bool = False,
    batch_size: int = 100,
) -> dict:
    """Run the full ingestion pipeline.

    Can be called with either:
    - sources: list of SourceConfig (preferred, supports include/exclude globs)
    - kb_roots: list of Path (legacy mode, discovers all supported files)
    """
    from src.ingestion.embedder import embed_texts
    from src.ingestion.store import ensure_collection, get_collection_stats, upsert_chunks

    settings = get_settings()
    stats = {
        "files_discovered": 0,
        "files_parsed": 0,
        "files_skipped_duplicate": 0,
        "total_chunks": 0,
        "points_upserted": 0,
        "property_distribution": {},
    }

    if not dry_run:
        if settings.qdrant_url:
            client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key or None,
            )
        else:
            client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
        ensure_collection(client, recreate=recreate)

    dedup = DeduplicationTracker()

    # Build file list from sources or kb_roots
    file_source_pairs: list[tuple[Path, Path]] = []  # (file_path, kb_root)

    if sources:
        for source in sources:
            files = source.discover_files()
            stats["files_discovered"] += len(files)
            logger.info(
                "discovered_files",
                source=str(source.root),
                count=len(files),
                has_filters=bool(source.include_patterns),
            )
            for f in files:
                file_source_pairs.append((f, source.root))
    elif kb_roots:
        for kb_root in kb_roots:
            if not kb_root.exists():
                logger.warning("kb_root_not_found", path=str(kb_root))
                continue
            files = discover_files(kb_root)
            stats["files_discovered"] += len(files)
            logger.info("discovered_files", kb_root=str(kb_root), count=len(files))
            for f in files:
                file_source_pairs.append((f, kb_root))

    # Collect all chunks
    all_chunks_data: list[dict] = []

    for file_path, kb_root in file_source_pairs:
        # Parse
        text = parse_file(file_path)
        if not text:
            continue

        rel_path_str = str(file_path.relative_to(kb_root))

        # Dedup (with source tracking)
        if dedup.is_duplicate(text, source_path=rel_path_str):
            kept = dedup.get_kept_source(text)
            stats["files_skipped_duplicate"] += 1
            logger.debug(
                "skipping_duplicate",
                file=rel_path_str,
                kept_source=kept,
            )
            continue

        stats["files_parsed"] += 1

        # Tag properties
        property_ids = tag_property_ids(file_path, kb_root)
        doc_type = classify_document_type(file_path.name)

        # Determine region from first property
        from src.domain.properties import PROPERTY_REGISTRY

        region = "shared"
        for pid in property_ids:
            info = PROPERTY_REGISTRY.get(pid)
            if info:
                region = str(info.region)
                break

        # Track distribution
        for pid in property_ids:
            pid_str = str(pid)
            stats["property_distribution"][pid_str] = (
                stats["property_distribution"].get(pid_str, 0) + 1
            )

        # Extract validity dates for rate cards
        validity = extract_validity_dates(file_path.name)

        # Chunk
        doc_hash = content_hash(text)
        metadata = {
            "source_file": file_path.name,
            "source_path": rel_path_str,
            "property_ids": [str(p) for p in property_ids],
            "region": region,
            "document_type": doc_type,
            "content_hash": doc_hash,
        }
        if validity:
            metadata.update(validity)

        chunks = chunk_text(text, metadata=metadata, document_type=doc_type)
        stats["total_chunks"] += len(chunks)

        for chunk in chunks:
            point_id = deterministic_point_id(doc_hash, chunk.chunk_index)
            all_chunks_data.append(
                {
                    "point_id": point_id,
                    "text": chunk.text,
                    "metadata": chunk.metadata,
                }
            )

    if dry_run:
        logger.info("dry_run_complete", stats=stats)
        print("\n=== DRY RUN RESULTS ===")
        print(f"Files discovered: {stats['files_discovered']}")
        print(f"Files parsed: {stats['files_parsed']}")
        print(f"Duplicates skipped: {stats['files_skipped_duplicate']}")
        print(f"Total chunks: {stats['total_chunks']}")
        print("\nProperty distribution:")
        for pid, count in sorted(stats["property_distribution"].items()):
            print(f"  {pid}: {count} files")
        return stats

    if not all_chunks_data:
        logger.warning("no_chunks_to_ingest")
        return stats

    # Embed all chunks (dense + sparse)
    logger.info("embedding_chunks", count=len(all_chunks_data))
    texts = [c["text"] for c in all_chunks_data]
    vectors = embed_texts(texts, batch_size=batch_size)

    from src.ingestion.embedder import compute_sparse_vectors

    sparse_vectors = compute_sparse_vectors(texts)

    # Upsert
    point_ids = [c["point_id"] for c in all_chunks_data]
    payloads = [{**c["metadata"], "text": c["text"]} for c in all_chunks_data]

    stats["points_upserted"] = upsert_chunks(
        client,
        point_ids=point_ids,
        vectors=vectors,
        payloads=payloads,
        sparse_vectors=sparse_vectors,
    )

    # Final stats
    collection_stats = get_collection_stats(client)
    logger.info("ingestion_complete", stats=stats, collection=collection_stats)

    print("\n=== INGESTION COMPLETE ===")
    print(f"Files discovered: {stats['files_discovered']}")
    print(f"Files parsed: {stats['files_parsed']}")
    print(f"Duplicates skipped: {stats['files_skipped_duplicate']}")
    print(f"Total chunks: {stats['total_chunks']}")
    print(f"Points upserted: {stats['points_upserted']}")
    print(f"Collection total: {collection_stats['points_count']} points")
    print("\nProperty distribution:")
    for pid, count in sorted(stats["property_distribution"].items()):
        print(f"  {pid}: {count} files")

    return stats


def run_verification(client: QdrantClient) -> None:
    """Run a test query per property to verify ingestion quality."""
    from src.domain.properties import PROPERTY_REGISTRY, PropertyID
    from src.ingestion.embedder import embed_texts

    settings = get_settings()
    collection_name = settings.qdrant_collection

    print("\n=== VERIFICATION ===")

    test_queries = {
        PropertyID.LA_FONTAINE: "What are the rates at La Fontaine?",
        PropertyID.AVONDROOD: "Tell me about Avondrood spa treatments",
        PropertyID.PINK_DOOR: "What rooms does The Pink Door have?",
        PropertyID.POD_CAMPS_BAY: "What are the rates at POD Camps Bay?",
        PropertyID.BLACKHEATH_LODGE: "Tell me about Blackheath Lodge",
        PropertyID.CAMP_FIGTREE: "What activities are at Camp Figtree?",
        PropertyID.THE_MILNER: "What rooms does The Milner have?",
        PropertyID.EIGHT_A: "Tell me about 8A Guest House",
        PropertyID.PLEASANCE: "Tell me about Pleasance",
        PropertyID.BURLINGTON_BUSH: "What is Burlington Bush?",
        PropertyID.OYSTER_BOX: "Tell me about Oyster Box Beach House",
        PropertyID.KENTON_HOUSES: "Tell me about Kenton Houses",
    }

    # Embed all test queries at once
    queries = list(test_queries.values())
    pids = list(test_queries.keys())
    vectors = embed_texts(queries)

    from qdrant_client.models import FieldCondition, Filter, MatchValue

    total_ok = 0
    total_props = 0

    for pid, query, vector in zip(pids, queries, vectors):
        if pid == PropertyID.SHARED:
            continue
        total_props += 1

        # Count total chunks for this property
        count_result = client.count(
            collection_name=collection_name,
            count_filter=Filter(
                must=[FieldCondition(key="property_ids", match=MatchValue(value=str(pid)))]
            ),
        )
        chunk_count = count_result.count

        # Search with property filter
        results = client.query_points(
            collection_name=collection_name,
            query=vector,
            using="dense",
            query_filter=Filter(
                must=[FieldCondition(key="property_ids", match=MatchValue(value=str(pid)))]
            ),
            limit=3,
        )
        top_scores = [round(p.score, 3) for p in results.points]

        # Check metadata fields
        has_section = False
        has_page = False
        for p in results.points:
            payload = p.payload or {}
            if payload.get("section_title"):
                has_section = True
            if payload.get("page_number"):
                has_page = True

        info = PROPERTY_REGISTRY.get(pid)
        name = info.name if info else str(pid)

        status = "OK" if chunk_count > 0 else "EMPTY"
        if chunk_count > 0:
            total_ok += 1

        meta_flags = []
        if has_section:
            meta_flags.append("section")
        if has_page:
            meta_flags.append("page")

        meta_str = f" [{', '.join(meta_flags)}]" if meta_flags else ""
        print(
            f"  {status:5s}  {name:25s}  "
            f"chunks={chunk_count:3d}  "
            f"scores={top_scores}{meta_str}"
        )

    print(f"\n  {total_ok}/{total_props} properties have chunks")

    # Collection-wide stats
    info = client.get_collection(collection_name)
    print(f"  Total points: {info.points_count}")
    print(f"  Vectors config: {list(info.config.params.vectors.keys())}")
    has_sparse_config = info.config.params.sparse_vectors is not None
    print(f"  Sparse vectors: {'yes' if has_sparse_config else 'no'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest knowledge base into Qdrant")
    parser.add_argument(
        "--kb-path",
        type=Path,
        action="append",
        help="Knowledge base root path (can specify multiple)",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate collection before ingestion",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and tag without embedding/upserting (verify tagging)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run test queries per property after ingestion",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Embedding batch size",
    )
    args = parser.parse_args()

    setup_logging(json_output=False)

    start = time.perf_counter()

    if args.kb_path:
        # Legacy mode: raw paths
        kb_roots = [Path(p) for p in args.kb_path]
        run_ingestion(
            kb_roots=kb_roots,
            recreate=args.recreate,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
        )
    else:
        # Default: use SourceConfig with include/exclude filtering
        run_ingestion(
            sources=DEFAULT_SOURCES,
            recreate=args.recreate,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
        )

    if args.verify and not args.dry_run:
        settings = get_settings()
        if settings.qdrant_url:
            client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key or None,
            )
        else:
            client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
        run_verification(client)

    elapsed = round(time.perf_counter() - start, 1)
    print(f"\nElapsed: {elapsed}s")


if __name__ == "__main__":
    main()
