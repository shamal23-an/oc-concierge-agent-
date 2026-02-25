from __future__ import annotations

from dataclasses import dataclass, field

import structlog
from llama_index.core.node_parser import SentenceSplitter

from src.config.settings import get_settings

logger = structlog.get_logger()


@dataclass
class Chunk:
    """A text chunk with metadata."""

    text: str
    chunk_index: int
    metadata: dict = field(default_factory=dict)


def chunk_text(
    text: str,
    *,
    metadata: dict | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[Chunk]:
    """Split text into chunks using SentenceSplitter.

    Attaches metadata to each chunk for downstream use.
    """
    settings = get_settings()
    size = chunk_size or settings.chunk_size
    overlap = chunk_overlap or settings.chunk_overlap

    splitter = SentenceSplitter(chunk_size=size, chunk_overlap=overlap)
    splits = splitter.split_text(text)

    base_meta = metadata or {}
    chunks = []
    for i, split_text in enumerate(splits):
        chunks.append(
            Chunk(
                text=split_text,
                chunk_index=i,
                metadata={**base_meta, "chunk_index": i},
            )
        )

    logger.debug("chunked_text", num_chunks=len(chunks), chunk_size=size)
    return chunks
