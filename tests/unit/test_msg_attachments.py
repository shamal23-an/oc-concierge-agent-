"""Tests for MSG parser attachment extraction."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.ingestion.parsers.msg import MsgParser


class TestMsgAttachmentExtraction:
    def test_extracts_pdf_attachment(self):
        """PDF attachments should be extracted and parsed."""
        mock_att = MagicMock()
        mock_att.longFilename = "rates.pdf"
        mock_att.data = b"fake pdf data"

        mock_msg = MagicMock()
        mock_msg.subject = "Rate Card"
        mock_msg.sender = "test@example.com"
        mock_msg.body = "Please find rates attached."
        mock_msg.attachments = [mock_att]

        with (
            patch("extract_msg.Message", return_value=mock_msg),
            patch.object(
                MsgParser,
                "_parse_attachment",
                return_value="## Rates\nR500 per night standard room",
            ),
        ):
            result = MsgParser().parse(Path("test.msg"))

        assert result is not None
        assert "Rate Card" in result
        assert "## Attachment: rates.pdf" in result
        assert "R500 per night" in result

    def test_skips_non_parseable_attachments(self):
        """Non-PDF/DOCX attachments should be skipped."""
        mock_att = MagicMock()
        mock_att.longFilename = "photo.jpg"
        mock_att.data = b"image data"

        mock_msg = MagicMock()
        mock_msg.subject = "Photos"
        mock_msg.sender = "test@example.com"
        mock_msg.body = "Here are some property photos for the brochure."
        mock_msg.attachments = [mock_att]

        with patch("extract_msg.Message", return_value=mock_msg):
            result = MsgParser().parse(Path("test.msg"))

        assert result is not None
        assert "Attachment" not in result

    def test_no_attachments(self):
        """MSG without attachments should still parse body."""
        mock_msg = MagicMock()
        mock_msg.subject = "Meeting notes"
        mock_msg.sender = "test@example.com"
        mock_msg.body = "Some meeting notes about the property renovation plans."
        mock_msg.attachments = []

        with patch("extract_msg.Message", return_value=mock_msg):
            result = MsgParser().parse(Path("test.msg"))

        assert result is not None
        assert "Meeting notes" in result

    def test_attachment_parse_failure_graceful(self):
        """Failed attachment parsing shouldn't crash the MSG parser."""
        mock_att = MagicMock()
        mock_att.longFilename = "corrupt.pdf"
        mock_att.data = b"corrupt data"

        mock_msg = MagicMock()
        mock_msg.subject = "Document"
        mock_msg.sender = "test@example.com"
        mock_msg.body = "Please find the attached document for your review."
        mock_msg.attachments = [mock_att]

        with (
            patch("extract_msg.Message", return_value=mock_msg),
            patch.object(MsgParser, "_parse_attachment", return_value=None),
        ):
            result = MsgParser().parse(Path("test.msg"))

        assert result is not None
        assert "Attachment" not in result
