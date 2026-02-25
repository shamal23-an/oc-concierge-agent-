from __future__ import annotations

from pathlib import Path

import structlog

logger = structlog.get_logger()


class PdfParser:
    """PDF parser using pymupdf4llm with pdfplumber fallback."""

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def parse(self, path: Path) -> str | None:
        text = self._try_pymupdf(path)
        if not text or len(text.strip()) < 20:
            text = self._try_pdfplumber(path)
        if not text or len(text.strip()) < 20:
            logger.warning("pdf_parse_empty", path=str(path))
            return None
        return text.strip()

    def _try_pymupdf(self, path: Path) -> str | None:
        try:
            import pymupdf4llm

            return pymupdf4llm.to_markdown(str(path))
        except Exception:
            logger.debug("pymupdf_fallback", path=str(path))
            return None

    def _try_pdfplumber(self, path: Path) -> str | None:
        try:
            import pdfplumber

            pages = []
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages.append(text)
            return "\n\n".join(pages)
        except Exception:
            logger.warning("pdfplumber_failed", path=str(path))
            return None
