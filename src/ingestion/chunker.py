from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog
from llama_index.core.node_parser import SentenceSplitter

from src.config.settings import get_settings

logger = structlog.get_logger()

# Minimum meaningful chunk length (chars). Chunks shorter than this are dropped.
_MIN_CHUNK_LENGTH = 50

# Patterns for section detection
_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
_PAGE_MARKER_RE = re.compile(r"<!--\s*PAGE:\s*(\d+)\s*-->")
_TABLE_MARKER_RE = re.compile(r"<!--\s*TABLE:\s*page\s*(\d+)\s*-->")
_MD_TABLE_ROW_RE = re.compile(r"^\|.*\|$")

# Boilerplate patterns to strip from chunks
_BOILERPLATE_PATTERNS = [
    # Email signatures / footers
    re.compile(r"^Kind Regards.*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^FRANSCHHOEK\s*\|.*$", re.MULTILINE),
    re.compile(r"^\d{4}(?:,\s*\d{4})*\s+Lilizella.*$", re.MULTILINE),
    re.compile(r"<(?:mailto|tel|http)[^>]*>", re.IGNORECASE),
    # Horizontal rules (standalone)
    re.compile(r"^\s*-{3,}\s*$", re.MULTILINE),
    # Multiple consecutive blank lines → single blank line
    re.compile(r"\n{3,}"),
]


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
    document_type: str | None = None,
) -> list[Chunk]:
    """Section-aware chunking with markdown heading detection.

    Strategy:
    1. Split on markdown headings (##, ###) as primary boundaries
    2. Keep markdown tables intact (never split mid-table)
    3. For rate cards, keep table header + room-type rows together
    4. Within large sections, fall back to SentenceSplitter
    5. Extract section_title and page_number into chunk metadata
    """
    settings = get_settings()
    size = chunk_size or settings.chunk_size
    overlap = chunk_overlap or settings.chunk_overlap
    base_meta = metadata or {}
    doc_type = document_type or base_meta.get("document_type", "")

    # Rate card: use specialized chunking to keep headers with data
    if doc_type == "rates":
        rate_chunks = _chunk_rate_card(text, base_meta, chunk_size=size)
        if rate_chunks:
            return rate_chunks

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

    # Post-process: clean boilerplate and drop tiny chunks
    cleaned_chunks: list[Chunk] = []
    for chunk in chunks:
        cleaned_text = _clean_boilerplate(chunk.text)
        if len(cleaned_text.strip()) < _MIN_CHUNK_LENGTH:
            logger.debug("chunk_dropped_too_short", length=len(cleaned_text.strip()))
            continue
        chunk.text = cleaned_text
        cleaned_chunks.append(chunk)

    # Re-index chunks after filtering
    for i, chunk in enumerate(cleaned_chunks):
        chunk.chunk_index = i
        chunk.metadata["chunk_index"] = i

    logger.debug(
        "chunked_text",
        num_chunks=len(cleaned_chunks),
        num_sections=len(sections),
        chunk_size=size,
        dropped=len(chunks) - len(cleaned_chunks),
    )
    return cleaned_chunks


def _clean_boilerplate(text: str) -> str:
    """Remove boilerplate patterns (email sigs, URLs, excessive separators)."""
    cleaned = text
    for pattern in _BOILERPLATE_PATTERNS:
        cleaned = pattern.sub("\n" if pattern.pattern.startswith("\\n") else "", cleaned)
    # Collapse multiple blank lines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


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
                    sections.append(
                        {
                            "title": current_title,
                            "text": section_text,
                            "page": current_page,
                        }
                    )
            current_title = heading_match.group(2).strip()
            current_lines = []
            continue

        current_lines.append(line)

    # Flush final section
    if current_lines:
        section_text = "\n".join(current_lines).strip()
        if section_text:
            sections.append(
                {
                    "title": current_title,
                    "text": section_text,
                    "page": current_page,
                }
            )

    # If no sections found (no headings), return the whole text as one section
    if not sections:
        sections.append(
            {
                "title": None,
                "text": text.strip(),
                "page": None,
            }
        )

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


def _interleave_blocks(text: str, table_blocks: list[str]) -> list[dict]:
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


# ── Rate card chunking ──────────────────────────────────────────────────── #

_TABLE_HEADER_RE = re.compile(r"^(\|.+\|)\n(\|\s*[-:]+.*\|)$", re.MULTILINE)


def _chunk_rate_card(
    text: str,
    base_meta: dict,
    *,
    chunk_size: int = 512,
) -> list[Chunk]:
    """Rate-card-aware chunking: repeats table header in every chunk.

    Groups markdown table rows so that the header row + separator are
    prepended to each chunk, keeping room-type/rate associations intact.
    """
    sections = _split_into_sections(text)
    chunks: list[Chunk] = []
    chunk_idx = 0

    for section in sections:
        section_text = section["text"]
        table_blocks, _ = _separate_tables(section_text)

        if not table_blocks:
            # Non-table section: chunk normally
            for chunk_str in _chunk_section(section_text, chunk_size=chunk_size, chunk_overlap=64):
                chunks.append(
                    Chunk(
                        text=chunk_str,
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
            continue

        for table_text in table_blocks:
            lines = table_text.split("\n")
            if len(lines) < 3:
                # Too small for splitting, keep as-is
                chunks.append(
                    Chunk(
                        text=table_text,
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
                continue

            # Extract header (first 2 lines: header row + separator)
            header_line = lines[0]
            separator_line = lines[1] if _MD_TABLE_ROW_RE.match(lines[1].strip()) else ""
            header_block = f"{header_line}\n{separator_line}" if separator_line else header_line

            # Check if separator is actually a separator (| --- | --- |)
            data_start = 2 if separator_line and "---" in separator_line else 1
            data_rows = lines[data_start:]

            if not data_rows:
                chunks.append(
                    Chunk(
                        text=table_text,
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
                continue

            # Group data rows into chunks that fit within chunk_size
            header_len = len(header_block) + 1  # +1 for newline
            current_rows: list[str] = []
            current_len = header_len

            for row in data_rows:
                row_len = len(row) + 1  # +1 for newline
                if current_rows and current_len + row_len > chunk_size:
                    # Flush current group
                    chunk_str = header_block + "\n" + "\n".join(current_rows)
                    chunks.append(
                        Chunk(
                            text=chunk_str,
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
                    current_rows = []
                    current_len = header_len

                current_rows.append(row)
                current_len += row_len

            # Flush remaining rows
            if current_rows:
                chunk_str = header_block + "\n" + "\n".join(current_rows)
                chunks.append(
                    Chunk(
                        text=chunk_str,
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

    if chunks:
        logger.debug(
            "rate_card_chunked",
            num_chunks=len(chunks),
            doc_type="rates",
        )
    return chunks
