from __future__ import annotations

from unittest.mock import patch

from src.ingestion.chunker import (
    Chunk,
    _interleave_blocks,
    _separate_tables,
    _split_into_sections,
    chunk_text,
)

# ---------------------------------------------------------------------------
# _split_into_sections
# ---------------------------------------------------------------------------


class TestSplitIntoSections:
    def test_splits_on_headings(self):
        text = "## Breakfast\nEggs and toast\n## Lunch\nSandwich"
        sections = _split_into_sections(text)
        assert len(sections) == 2
        assert sections[0]["title"] == "Breakfast"
        assert "Eggs" in sections[0]["text"]
        assert sections[1]["title"] == "Lunch"
        assert "Sandwich" in sections[1]["text"]

    def test_tracks_page_markers(self):
        text = "<!-- PAGE: 3 -->\n## Spa\nMassage options"
        sections = _split_into_sections(text)
        assert sections[0]["page"] == 3

    def test_tracks_table_markers(self):
        text = "<!-- TABLE: page 5 -->\n| A | B |\n| 1 | 2 |"
        sections = _split_into_sections(text)
        assert sections[0]["page"] == 5

    def test_no_headings_returns_single_section(self):
        text = "Just some plain text\nwith no headings."
        sections = _split_into_sections(text)
        assert len(sections) == 1
        assert sections[0]["title"] is None
        assert "plain text" in sections[0]["text"]

    def test_text_before_first_heading(self):
        text = "Intro paragraph\n## Section One\nContent"
        sections = _split_into_sections(text)
        assert len(sections) == 2
        assert sections[0]["title"] is None
        assert "Intro" in sections[0]["text"]
        assert sections[1]["title"] == "Section One"

    def test_page_marker_not_in_output(self):
        text = "<!-- PAGE: 1 -->\nSome text"
        sections = _split_into_sections(text)
        assert "PAGE" not in sections[0]["text"]

    def test_h3_and_h4_headings(self):
        text = "### Sub Section\nContent A\n#### Deep\nContent B"
        sections = _split_into_sections(text)
        assert len(sections) == 2
        assert sections[0]["title"] == "Sub Section"
        assert sections[1]["title"] == "Deep"


# ---------------------------------------------------------------------------
# _separate_tables
# ---------------------------------------------------------------------------


class TestSeparateTables:
    def test_detects_markdown_table(self):
        text = "Some text\n| A | B |\n| --- | --- |\n| 1 | 2 |\nMore text"
        tables, non_tables = _separate_tables(text)
        assert len(tables) == 1
        assert "| A | B |" in tables[0]
        assert len(non_tables) == 2

    def test_no_tables(self):
        text = "Just text\nNo tables here"
        tables, non_tables = _separate_tables(text)
        assert len(tables) == 0
        assert len(non_tables) == 1


# ---------------------------------------------------------------------------
# _interleave_blocks
# ---------------------------------------------------------------------------


class TestInterleaveBlocks:
    def test_preserves_order(self):
        table = "| A | B |\n| 1 | 2 |"
        text = f"Before\n{table}\nAfter"
        blocks = _interleave_blocks(text, [table])
        assert len(blocks) == 3
        assert blocks[0]["is_table"] is False
        assert blocks[1]["is_table"] is True
        assert blocks[2]["is_table"] is False

    def test_table_at_start(self):
        table = "| X | Y |"
        text = f"{table}\nAfter"
        blocks = _interleave_blocks(text, [table])
        assert blocks[0]["is_table"] is True
        assert blocks[1]["is_table"] is False


# ---------------------------------------------------------------------------
# chunk_text (integration)
# ---------------------------------------------------------------------------


class TestChunkText:
    @patch("src.ingestion.chunker.get_settings")
    def test_basic_chunking(self, mock_settings):
        mock_settings.return_value.chunk_size = 512
        mock_settings.return_value.chunk_overlap = 64
        text = "## Menu\nPasta, Steak, Fish"
        chunks = chunk_text(text)
        assert len(chunks) >= 1
        assert isinstance(chunks[0], Chunk)
        assert chunks[0].section_title == "Menu"
        assert chunks[0].chunk_index == 0

    @patch("src.ingestion.chunker.get_settings")
    def test_metadata_populated(self, mock_settings):
        mock_settings.return_value.chunk_size = 512
        mock_settings.return_value.chunk_overlap = 64
        text = "<!-- PAGE: 2 -->\n## Rates\nR500 per night"
        chunks = chunk_text(text, metadata={"source_file": "rates.pdf"})
        assert chunks[0].page_number == 2
        assert chunks[0].section_title == "Rates"
        assert chunks[0].metadata["source_file"] == "rates.pdf"
        assert chunks[0].metadata["section_title"] == "Rates"
        assert chunks[0].metadata["page_number"] == 2

    @patch("src.ingestion.chunker.get_settings")
    def test_table_kept_intact(self, mock_settings):
        mock_settings.return_value.chunk_size = 50
        mock_settings.return_value.chunk_overlap = 10
        table = "| Room | Rate |\n| --- | --- |\n| Standard | R500 |\n| Deluxe | R800 |"
        text = f"## Rates\n{table}"
        chunks = chunk_text(text)
        # The table should appear in a single chunk (not split across chunks)
        table_chunks = [c for c in chunks if "| Room | Rate |" in c.text]
        assert len(table_chunks) >= 1
        # All table rows should be in the same chunk
        assert "| Standard | R500 |" in table_chunks[0].text
        assert "| Deluxe | R800 |" in table_chunks[0].text

    @patch("src.ingestion.chunker.get_settings")
    def test_chunk_indices_sequential(self, mock_settings):
        mock_settings.return_value.chunk_size = 512
        mock_settings.return_value.chunk_overlap = 64
        text = "## Section A\nContent A\n## Section B\nContent B"
        chunks = chunk_text(text)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    @patch("src.ingestion.chunker.get_settings")
    def test_empty_text(self, mock_settings):
        mock_settings.return_value.chunk_size = 512
        mock_settings.return_value.chunk_overlap = 64
        chunks = chunk_text("   ")
        assert len(chunks) == 0

    @patch("src.ingestion.chunker.get_settings")
    def test_custom_chunk_size(self, mock_settings):
        mock_settings.return_value.chunk_size = 1024
        mock_settings.return_value.chunk_overlap = 128
        text = "## Title\nShort content"
        chunks = chunk_text(text, chunk_size=256, chunk_overlap=32)
        assert len(chunks) >= 1


# ---------------------------------------------------------------------------
# Rate card chunking
# ---------------------------------------------------------------------------


class TestRateCardChunking:
    @patch("src.ingestion.chunker.get_settings")
    def test_rate_card_repeats_header(self, mock_settings):
        mock_settings.return_value.chunk_size = 200
        mock_settings.return_value.chunk_overlap = 64
        header = "| Room Type | Low Season | High Season |"
        sep = "| --- | --- | --- |"
        rows = [f"| Room {i} | R{i*100} | R{i*150} |" for i in range(1, 20)]
        table = "\n".join([header, sep] + rows)
        text = f"## Rates\n{table}"

        chunks = chunk_text(
            text,
            metadata={"document_type": "rates"},
            document_type="rates",
        )

        assert len(chunks) > 1
        # Every chunk should start with the header
        for chunk in chunks:
            assert "| Room Type | Low Season | High Season |" in chunk.text

    @patch("src.ingestion.chunker.get_settings")
    def test_rate_card_small_table_single_chunk(self, mock_settings):
        mock_settings.return_value.chunk_size = 512
        mock_settings.return_value.chunk_overlap = 64
        table = (
            "| Room Type | Rate |\n" "| --- | --- |\n" "| Standard | R500 |\n" "| Deluxe | R800 |"
        )
        text = f"## Rates\n{table}"

        chunks = chunk_text(
            text,
            metadata={"document_type": "rates"},
            document_type="rates",
        )

        assert len(chunks) >= 1
        assert "| Standard | R500 |" in chunks[0].text
        assert "| Deluxe | R800 |" in chunks[0].text

    @patch("src.ingestion.chunker.get_settings")
    def test_non_rate_doc_uses_normal_chunking(self, mock_settings):
        mock_settings.return_value.chunk_size = 512
        mock_settings.return_value.chunk_overlap = 64
        text = "## About\nThis is a general document."

        chunks = chunk_text(text, document_type="general")
        assert len(chunks) >= 1
        assert chunks[0].section_title == "About"
