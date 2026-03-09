"""OCR fallback for image-based PDFs using pytesseract + pdf2image."""

from __future__ import annotations

from pathlib import Path

import structlog

logger = structlog.get_logger()

_MIN_TEXT_LENGTH = 20


def ocr_pdf(path: Path) -> str | None:
    """OCR a PDF file using pdf2image + pytesseract.

    Returns extracted text or None if OCR is unavailable or produces no text.
    Only invoked when primary parsers produce <20 chars.
    """
    try:
        from pdf2image import convert_from_path
        from pytesseract import image_to_string
    except ImportError:
        logger.debug("ocr_deps_not_available", path=str(path))
        return None

    try:
        images = convert_from_path(str(path), dpi=300)
        pages: list[str] = []
        for i, img in enumerate(images, 1):
            text = image_to_string(img, lang="eng")
            if text and text.strip():
                pages.append(f"<!-- PAGE: {i} -->\n{text.strip()}")

        result = "\n\n".join(pages)
        if len(result.strip()) < _MIN_TEXT_LENGTH:
            logger.debug("ocr_insufficient_text", path=str(path))
            return None

        logger.info("ocr_success", path=str(path), pages=len(pages), length=len(result))
        return result
    except Exception:
        logger.warning("ocr_failed", path=str(path), exc_info=True)
        return None
