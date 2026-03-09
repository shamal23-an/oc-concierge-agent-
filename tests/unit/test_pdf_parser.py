from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.ingestion.parsers.pdf import PdfParser


class TestCanParse:
    def test_accepts_pdf(self):
        assert PdfParser().can_parse(Path("test.pdf")) is True

    def test_rejects_docx(self):
        assert PdfParser().can_parse(Path("test.docx")) is False

    def test_case_insensitive(self):
        assert PdfParser().can_parse(Path("TEST.PDF")) is True


class TestTableToMarkdown:
    def test_basic_table(self):
        table = [
            ["Room", "Rate"],
            ["Standard", "R500"],
            ["Deluxe", "R800"],
        ]
        md = PdfParser._table_to_markdown(table)
        assert md is not None
        assert "| Room | Rate |" in md
        assert "| --- | --- |" in md
        assert "| Standard | R500 |" in md
        assert "| Deluxe | R800 |" in md

    def test_none_cells_replaced(self):
        table = [
            ["Name", "Value"],
            [None, "100"],
        ]
        md = PdfParser._table_to_markdown(table)
        assert md is not None
        assert "|  | 100 |" in md

    def test_single_row_returns_none(self):
        table = [["Header Only"]]
        assert PdfParser._table_to_markdown(table) is None

    def test_empty_table_returns_none(self):
        assert PdfParser._table_to_markdown([]) is None

    def test_all_empty_cells_returns_none(self):
        table = [["", ""], ["", ""]]
        assert PdfParser._table_to_markdown(table) is None

    def test_row_padding(self):
        table = [
            ["A", "B", "C"],
            ["1"],  # Short row — should be padded
        ]
        md = PdfParser._table_to_markdown(table)
        assert md is not None
        lines = md.split("\n")
        # Data row should have 3 columns
        assert lines[2].count("|") == 4  # |col|col|col|


class TestGenericHeaderDetection:
    def test_col1_col2_is_generic(self):
        assert PdfParser._is_generic_header(["Col1", "Col2", "Col3"]) is True

    def test_column_1_is_generic(self):
        assert PdfParser._is_generic_header(["Column 1", "Column 2"]) is True

    def test_empty_header_is_generic(self):
        assert PdfParser._is_generic_header(["", "", ""]) is True

    def test_real_header_is_not_generic(self):
        assert PdfParser._is_generic_header(["Room Type", "Low Season", "High Season"]) is False

    def test_mixed_generic_and_real(self):
        # If at least one cell is non-generic, it's a real header
        assert PdfParser._is_generic_header(["Col1", "Rate"]) is False

    def test_generic_header_promotes_first_data_row(self):
        table = [
            ["Col1", "Col2", "Col3"],
            ["Room Type", "Low Season", "High Season"],
            ["Standard", "R500", "R800"],
        ]
        md = PdfParser._table_to_markdown(table)
        assert md is not None
        assert "| Room Type | Low Season | High Season |" in md
        assert "| Standard | R500 | R800 |" in md
        assert "Col1" not in md

    def test_real_header_not_promoted(self):
        table = [
            ["Room Type", "Rate"],
            ["Standard", "R500"],
        ]
        md = PdfParser._table_to_markdown(table)
        assert md is not None
        assert "| Room Type | Rate |" in md
        assert "| Standard | R500 |" in md


class TestMergeTables:
    def test_appends_tables_with_markers(self):
        md_text = "# Title\nSome content"
        tables_md = {
            1: ["| A | B |\n| 1 | 2 |"],
            3: ["| X | Y |\n| 9 | 8 |"],
        }
        result = PdfParser._merge_tables(md_text, tables_md)
        assert "<!-- TABLE: page 1 -->" in result
        assert "<!-- TABLE: page 3 -->" in result
        assert "| A | B |" in result
        assert "| X | Y |" in result

    def test_empty_tables_returns_original(self):
        md_text = "Original text"
        assert PdfParser._merge_tables(md_text, {}) == md_text


class TestExtractTablesAsMarkdown:
    @patch("pdfplumber.open")
    def test_extracts_tables(self, mock_open):
        # Mock pdfplumber
        mock_page = MagicMock()
        mock_page.extract_tables.return_value = [
            [["Room", "Rate"], ["Standard", "R500"]],
        ]
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = mock_pdf

        parser = PdfParser()
        result = parser._extract_tables_as_markdown(Path("test.pdf"))
        assert 1 in result
        assert len(result[1]) == 1
        assert "| Room | Rate |" in result[1][0]

    @patch("pdfplumber.open")
    def test_no_tables(self, mock_open):
        mock_page = MagicMock()
        mock_page.extract_tables.return_value = []
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_open.return_value = mock_pdf

        result = PdfParser()._extract_tables_as_markdown(Path("test.pdf"))
        assert result == {}


class TestParse:
    @patch.object(PdfParser, "_extract_tables_as_markdown", return_value={})
    @patch.object(PdfParser, "_try_pymupdf")
    def test_pymupdf_primary(self, mock_pymupdf, mock_tables):
        mock_pymupdf.return_value = "# Hotel Info\nGreat property with pool and spa."
        result = PdfParser().parse(Path("test.pdf"))
        assert result is not None
        assert "Great property" in result

    @patch.object(PdfParser, "_extract_tables_as_markdown")
    @patch.object(PdfParser, "_try_pymupdf")
    def test_tables_merged_into_pymupdf(self, mock_pymupdf, mock_tables):
        mock_pymupdf.return_value = "# Rates\nSee table below for pricing."
        mock_tables.return_value = {1: ["| Room | Rate |\n| --- | --- |\n| Std | R500 |"]}
        result = PdfParser().parse(Path("test.pdf"))
        assert "| Room | Rate |" in result
        assert "<!-- TABLE: page 1 -->" in result

    @patch.object(PdfParser, "_extract_tables_as_markdown", return_value={})
    @patch.object(PdfParser, "_try_pymupdf", return_value=None)
    @patch.object(PdfParser, "_try_pdfplumber")
    def test_pdfplumber_fallback(self, mock_plumber, mock_pymupdf, mock_tables):
        mock_plumber.return_value = "<!-- PAGE: 1 -->\nFallback text content here."
        result = PdfParser().parse(Path("test.pdf"))
        assert result is not None
        assert "Fallback text" in result

    @patch.object(PdfParser, "_extract_tables_as_markdown", return_value={})
    @patch.object(PdfParser, "_try_pymupdf", return_value=None)
    @patch.object(PdfParser, "_try_pdfplumber", return_value=None)
    def test_returns_none_when_empty(self, *_):
        assert PdfParser().parse(Path("test.pdf")) is None

    @patch.object(PdfParser, "_extract_tables_as_markdown", return_value={})
    @patch.object(PdfParser, "_try_pymupdf", return_value="short")
    @patch.object(PdfParser, "_try_pdfplumber")
    def test_short_pymupdf_falls_back(self, mock_plumber, *_):
        mock_plumber.return_value = "<!-- PAGE: 1 -->\nLonger fallback text from pdfplumber."
        result = PdfParser().parse(Path("test.pdf"))
        assert "Longer fallback" in result
