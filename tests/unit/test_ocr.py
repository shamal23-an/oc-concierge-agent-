"""Tests for OCR fallback parser."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


class TestOcrPdf:
    def test_ocr_success(self):
        mock_img = MagicMock()
        mock_convert = MagicMock(return_value=[mock_img])
        mock_ocr = MagicMock(
            return_value="This is OCR text from the scanned document about hotel rates."
        )

        with (
            patch.dict(
                "sys.modules",
                {
                    "pdf2image": MagicMock(convert_from_path=mock_convert),
                    "pytesseract": MagicMock(image_to_string=mock_ocr),
                },
            ),
        ):
            # Re-import to pick up mocked modules
            import importlib

            import src.ingestion.parsers.ocr as ocr_mod

            importlib.reload(ocr_mod)
            result = ocr_mod.ocr_pdf(Path("scanned.pdf"))

        assert result is not None
        assert "OCR text" in result
        assert "<!-- PAGE: 1 -->" in result

    def test_ocr_empty_text(self):
        mock_convert = MagicMock(return_value=[MagicMock()])
        mock_ocr = MagicMock(return_value="")

        with patch.dict(
            "sys.modules",
            {
                "pdf2image": MagicMock(convert_from_path=mock_convert),
                "pytesseract": MagicMock(image_to_string=mock_ocr),
            },
        ):
            import importlib

            import src.ingestion.parsers.ocr as ocr_mod

            importlib.reload(ocr_mod)
            result = ocr_mod.ocr_pdf(Path("blank.pdf"))

        assert result is None

    def test_ocr_multiple_pages(self):
        mock_convert = MagicMock(return_value=[MagicMock(), MagicMock()])
        mock_ocr = MagicMock(
            side_effect=[
                "Page one content with enough text for validation.",
                "Page two content with additional information.",
            ]
        )

        with patch.dict(
            "sys.modules",
            {
                "pdf2image": MagicMock(convert_from_path=mock_convert),
                "pytesseract": MagicMock(image_to_string=mock_ocr),
            },
        ):
            import importlib

            import src.ingestion.parsers.ocr as ocr_mod

            importlib.reload(ocr_mod)
            result = ocr_mod.ocr_pdf(Path("multi.pdf"))

        assert result is not None
        assert "<!-- PAGE: 1 -->" in result
        assert "<!-- PAGE: 2 -->" in result

    def test_ocr_import_error_returns_none(self):
        """OCR should return None gracefully if deps not installed."""
        # The function catches ImportError internally
        with patch.dict("sys.modules", {"pdf2image": None, "pytesseract": None}):
            import importlib

            import src.ingestion.parsers.ocr as ocr_mod

            importlib.reload(ocr_mod)
            result = ocr_mod.ocr_pdf(Path("test.pdf"))

        assert result is None
