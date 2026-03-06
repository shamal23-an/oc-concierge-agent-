from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog
from llama_index.core.node_parser import SentenceSplitter

from src.config.settings import get_settings

logger = structlog.get_logger()

# Patterns for section detection
_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
_PAGE_MARKER_RE = re.compile(r"<!--\s*PAGE:\s*(\d+)\s*-->")
_TABLE_MARKER_RE = re.compile(r"<!--\s*TABLE:\s*page\s*(\d+)\s*-->")
_MD_TABLE_ROW_RE = re.compile(r"^\|.*\|$")


@dataclass
class Chunk:
    """A text chunk with metadata."""

    text: str
    chunk_index: int
    metadata: dict = field(default_factory=dict)
    section_title: str | None = None
    page_number: int | None = None


def chunk_text(
    text: str,
    *,
    metadata: dict | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[Chunk]:
    """Section-aware chunking with markdown heading detection.

    Strategy:
    1. Split on markdown headings (##, ###) as primary boundaries
    2. Keep markdown tables intact (never split mid-table)
    3. Within large sections, fall back to SentenceSplitter
    4. Extract section_title and page_number into chunk metadata
    """
    settings = get_settings()
    size = chunk_size or settings.chunk_size
    overlap = chunk_overlap or settings.chunk_overlap
    base_meta = metadata or {}

    # Split text into sections by headings
    sections = _split_into_sections(text)

    chunks: list[Chunk] = []
    chunk_idx = 0

    for section in sections:
        section_chunks = _chunk_section(
            section["text"],
            chunk_size=size,
            chunk_overlap=overlap,
        )
        for chunk_text_str in section_chunks:
            chunks.append(
                Chunk(
                    text=chunk_text_str,
                    chunk_index=chunk_idx,
                    metadata={
                        **base_meta,
                        "chunk_index": chunk_idx,
                        "section_title": section["title"],
                        "page_number": section["page"],
                    },
                    section_title=section["title"],
                    page_number=section["page"],
                )
            )
            chunk_idx += 1

    logger.debug(
        "chunked_text",
        num_chunks=len(chunks),
        num_sections=len(sections),
        chunk_size=size,
    )
    return chunks


def _split_into_sections(text: str) -> list[dict]:
    """Split text into sections by markdown headings.

    Returns list of {title, text, page} dicts.
    """
    lines = text.split("\n")
    sections: list[dict] = []
    current_title: str | None = None
    current_page: int | None = None
    current_lines: list[str] = []

    for line in lines:
        # Track page markers
        page_match = _PAGE_MARKER_RE.search(line)
        if page_match:
            current_page = int(page_match.group(1))
            continue  # Don't include marker in output

        # Track table markers (extract page but keep the table)
        table_match = _TABLE_MARKER_RE.search(line)
        if table_match:
            if current_page is None:
                current_page = int(table_match.group(1))
            continue

        # Check for heading
        heading_match = _HEADING_RE.match(line)
        if heading_match:
            # Flush previous section
            if current_lines:
                section_text = "\n".join(current_lines).strip()
                if section_text:
                    sections.append({
                        "title": current_title,
                        "text": section_text,
                        "page": current_page,
                    })
            current_title = heading_match.group(2).strip()
            current_lines = []
            continue

        current_lines.append(line)

    # Flush final section
    if current_lines:
        section_text = "\n".join(current_lines).strip()
        if section_text:
            sections.append({
                "title": current_title,
                "text": section_text,
                "page": current_page,
            })

    # If no sections found (no headings), return the whole text as one section
    if not sections:
        sections.append({
            "title": None,
            "text": text.strip(),
            "page": None,
        })

    return sections


def _chunk_section(
    text: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """Chunk a single section, keeping tables intact.

    If the section fits within chunk_size, return as-is.
    If it contains a markdown table, try to keep the table whole.
    Otherwise, fall back to SentenceSplitter.
    """
    if not text.strip():
        return []

    # If small enough, return as single chunk
    if len(text) <= chunk_size:
        return [text]

    # Check if section contains markdown tables
    table_blocks, non_table_blocks = _separate_tables(text)

    if table_blocks:
        # Chunk non-table parts with SentenceSplitter, keep tables whole
        result = []
        for block in _interleave_blocks(text, table_blocks):
            if block["is_table"]:
                # Keep table as single chunk (even if slightly over size)
                result.append(block["text"])
            else:
                # Split non-table text normally
                sub_chunks = _sentence_split(
                    block["text"], chunk_size=chunk_size, chunk_overlap=chunk_overlap
                )
                result.extend(sub_chunks)
        return [r for r in result if r.strip()]

    # No tables — use SentenceSplitter
    return _sentence_split(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def _sentence_split(text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Fall back to LlamaIndex SentenceSplitter for plain text."""
    if not text.strip():
        return []
    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return splitter.split_text(text)


def _separate_tables(text: str) -> tuple[list[str], list[str]]:
    """Identify markdown table blocks in text.

    Returns (table_blocks, non_table_blocks).
    A table block is consecutive lines matching | ... |.
    """
    lines = text.split("\n")
    tables: list[str] = []
    non_tables: list[str] = []
    current_table: list[str] = []
    current_non_table: list[str] = []

    for line in lines:
        is_table_line = _MD_TABLE_ROW_RE.match(line.strip()) is not None
        if is_table_line:
            if current_non_table:
                non_tables.append("\n".join(current_non_table))
                current_non_table = []
            current_table.append(line)
        else:
            if current_table:
                tables.append("\n".join(current_table))
                current_table = []
            current_non_table.append(line)

    # Flush remaining
    if current_table:
        tables.append("\n".join(current_table))
    if current_non_table:
        non_tables.append("\n".join(current_non_table))

    return tables, non_tables


def _interleave_blocks(
    text: str, table_blocks: list[str]
) -> list[dict]:
    """Split text into alternating table / non-table blocks preserving order."""
    blocks: list[dict] = []
    remaining = text

    for table in table_blocks:
        idx = remaining.find(table)
        if idx == -1:
            continue
        # Text before the table
        before = remaining[:idx].strip()
        if before:
            blocks.append({"is_table": False, "text": before})
        # The table itself
        blocks.append({"is_table": True, "text": table})
        remaining = remaining[idx + len(table) :]

    # Text after last table
    if remaining.strip():
        blocks.append({"is_table": False, "text": remaining.strip()})

    return blocks
