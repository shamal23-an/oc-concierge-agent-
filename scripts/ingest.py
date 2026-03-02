"""Ingestion CLI — parse, chunk, embed, and upsert KB documents to Qdrant."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import structlog

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config.constants import SUPPORTED_EXTENSIONS
from src.config.logging import setup_logging
from src.config.settings import get_settings
from src.ingestion.chunker import chunk_text
from src.ingestion.deduplicator import (
    DeduplicationTracker,
    content_hash,
    deterministic_point_id,
)
from src.ingestion.parsers.docx import DocxParser
from src.ingestion.parsers.msg import MsgParser
from src.ingestion.parsers.pdf import PdfParser
from src.ingestion.parsers.xlsx import XlsxParser
from src.ingestion.property_tagger import classify_document_type, tag_property_ids

logger = structlog.get_logger()

PARSERS = [PdfParser(), DocxParser(), MsgParser(), XlsxParser()]

# Default KB roots (relative to project root)
DEFAULT_KB_ROOTS = [
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
    kb_roots: list[Path],
    *,
    recreate: bool = False,
    dry_run: bool = False,
    batch_size: int = 100,
) -> dict:
    """Run the full ingestion pipeline."""
    from qdrant_client import QdrantClient

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

    # Collect all chunks across all KB roots
    all_chunks_data: list[dict] = []

    for kb_root in kb_roots:
        if not kb_root.exists():
            logger.warning("kb_root_not_found", path=str(kb_root))
            continue

        files = discover_files(kb_root)
        stats["files_discovered"] += len(files)
        logger.info("discovered_files", kb_root=str(kb_root), count=len(files))

        for file_path in files:
            # Parse
            text = parse_file(file_path)
            if not text:
                continue

            # Dedup
            if dedup.is_duplicate(text):
                stats["files_skipped_duplicate"] += 1
                logger.debug("skipping_duplicate", file=str(file_path))
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

            rel_path = str(file_path.relative_to(kb_root))

            # Chunk
            doc_hash = content_hash(text)
            metadata = {
                "source_file": file_path.name,
                "source_path": rel_path,
                "property_ids": [str(p) for p in property_ids],
                "region": region,
                "document_type": doc_type,
                "content_hash": doc_hash,
            }

            chunks = chunk_text(text, metadata=metadata)
            stats["total_chunks"] += len(chunks)

            for chunk in chunks:
                point_id = deterministic_point_id(doc_hash, chunk.chunk_index)
                all_chunks_data.append({
                    "point_id": point_id,
                    "text": chunk.text,
                    "metadata": chunk.metadata,
                })

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

    # Embed all chunks
    logger.info("embedding_chunks", count=len(all_chunks_data))
    texts = [c["text"] for c in all_chunks_data]
    vectors = embed_texts(texts, batch_size=batch_size)

    # Upsert
    point_ids = [c["point_id"] for c in all_chunks_data]
    payloads = [{**c["metadata"], "text": c["text"]} for c in all_chunks_data]

    stats["points_upserted"] = upsert_chunks(
        client, point_ids=point_ids, vectors=vectors, payloads=payloads
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
        "--batch-size",
        type=int,
        default=100,
        help="Embedding batch size",
    )
    args = parser.parse_args()

    setup_logging(json_output=False)

    kb_roots = args.kb_path if args.kb_path else DEFAULT_KB_ROOTS
    kb_roots = [Path(p) for p in kb_roots]

    start = time.perf_counter()
    run_ingestion(
        kb_roots,
        recreate=args.recreate,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
    )
    elapsed = round(time.perf_counter() - start, 1)
    print(f"\nElapsed: {elapsed}s")


if __name__ == "__main__":
    main()
