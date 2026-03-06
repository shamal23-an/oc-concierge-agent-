from __future__ import annotations

from pathlib import Path

import structlog

logger = structlog.get_logger()

_MIN_TEXT_LENGTH = 20


class PdfParser:
    """PDF parser using pymupdf4llm with pdfplumber table extraction.

    Strategy:
    1. pymupdf4llm.to_markdown() for structured text with headings
    2. Overlay pdfplumber table extraction (markdown tables) for rate cards/menus
    3. Fall back to pdfplumber plain text if pymupdf produces nothing
    4. Add <!-- PAGE: N --> markers between pages for downstream chunking
    """

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def parse(self, path: Path) -> str | None:
        # Primary: pymupdf4llm markdown
        md_text = self._try_pymupdf(path)

        # Extract tables separately via pdfplumber
        tables_md = self._extract_tables_as_markdown(path)

        if md_text and len(md_text.strip()) >= _MIN_TEXT_LENGTH:
            # Merge table markdown into the output
            if tables_md:
                md_text = self._merge_tables(md_text, tables_md)
            return md_text.strip()

        # Fallback: pdfplumber plain text + tables
        text = self._try_pdfplumber(path)
        if tables_md:
            table_sections = []
            for page_num in sorted(tables_md):
                for table in tables_md[page_num]:
                    table_sections.append(table)
            table_text = "\n\n".join(table_sections)
            if text:
                text = text + "\n\n" + table_text
            elif table_text.strip():
                text = table_text

        if not text or len(text.strip()) < _MIN_TEXT_LENGTH:
            logger.warning("pdf_parse_empty", path=str(path))
            return None
        return text.strip()

    def _try_pymupdf(self, path: Path) -> str | None:
        try:
            import pymupdf4llm

            md = pymupdf4llm.to_markdown(str(path))
            if not md:
                return None

            # Add page markers by splitting on form-feed or page patterns
            # pymupdf4llm uses "-----" as page separators in some versions
            return md
        except Exception:
            logger.debug("pymupdf_fallback", path=str(path))
            return None

    def _try_pdfplumber(self, path: Path) -> str | None:
        try:
            import pdfplumber

            pages = []
            with pdfplumber.open(path) as pdf:
                for i, page in enumerate(pdf.pages, 1):
                    text = page.extract_text()
                    if text:
                        pages.append(f"<!-- PAGE: {i} -->\n{text}")
            return "\n\n".join(pages)
        except Exception:
            logger.warning("pdfplumber_failed", path=str(path))
            return None

    def _extract_tables_as_markdown(self, path: Path) -> dict[int, list[str]]:
        """Extract tables from each page using pdfplumber.

        Returns {page_number: [markdown_table_string, ...]}.
        """
        try:
            import pdfplumber

            result: dict[int, list[str]] = {}
            with pdfplumber.open(path) as pdf:
                for i, page in enumerate(pdf.pages, 1):
                    tables = page.extract_tables()
                    if not tables:
                        continue
                    page_tables = []
                    for table in tables:
                        md = self._table_to_markdown(table)
                        if md:
                            page_tables.append(md)
                    if page_tables:
                        result[i] = page_tables
            if result:
                logger.debug(
                    "pdf_tables_extracted",
                    path=str(path),
                    pages_with_tables=len(result),
                    total_tables=sum(len(v) for v in result.values()),
                )
            return result
        except Exception:
            logger.debug("pdf_table_extraction_failed", path=str(path))
            return {}

    @staticmethod
    def _table_to_markdown(table: list[list[str | None]]) -> str | None:
        """Convert a pdfplumber table (list of rows) to markdown table format."""
        if not table or len(table) < 2:
            return None

        # Clean cells: replace None with empty string, strip whitespace
        cleaned = []
        for row in table:
            cleaned.append([str(cell).strip() if cell else "" for cell in row])

        # Skip tables where all cells are empty
        if all(all(c == "" for c in row) for row in cleaned):
            return None

        # Build markdown table
        lines = []
        # Header row
        header = cleaned[0]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join("---" for _ in header) + " |")
        # Data rows
        for row in cleaned[1:]:
            # Pad or truncate row to match header length
            padded = row + [""] * (len(header) - len(row))
            lines.append("| " + " | ".join(padded[: len(header)]) + " |")

        return "\n".join(lines)

    @staticmethod
    def _merge_tables(md_text: str, tables_md: dict[int, list[str]]) -> str:
        """Append extracted tables to the end of the markdown text.

        Tables are added under a clear heading so the chunker can detect them.
        """
        extra_sections = []
        for page_num in sorted(tables_md):
            for table in tables_md[page_num]:
                extra_sections.append(f"<!-- TABLE: page {page_num} -->\n{table}")

        if extra_sections:
            return md_text + "\n\n" + "\n\n".join(extra_sections)
        return md_text
