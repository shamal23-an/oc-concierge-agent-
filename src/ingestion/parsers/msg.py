from __future__ import annotations

import tempfile
from pathlib import Path

import structlog

logger = structlog.get_logger()


class MsgParser:
    """Outlook MSG parser using extract-msg with attachment extraction."""

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower() == ".msg"

    def parse(self, path: Path) -> str | None:
        try:
            import extract_msg

            msg = extract_msg.Message(str(path))
            parts = []
            if msg.subject:
                parts.append(f"Subject: {msg.subject}")
            if msg.sender:
                parts.append(f"From: {msg.sender}")
            if msg.body:
                parts.append(msg.body)

            # Extract text from PDF/DOCX attachments
            attachment_texts = self._extract_attachments(msg)
            parts.extend(attachment_texts)

            msg.close()

            text = "\n\n".join(parts)
            if len(text.strip()) < 20:
                logger.warning("msg_parse_empty", path=str(path))
                return None
            return text.strip()
        except Exception:
            logger.warning("msg_parse_failed", path=str(path))
            return None

    def _extract_attachments(self, msg) -> list[str]:
        """Extract text from PDF and DOCX attachments."""
        results = []
        try:
            attachments = msg.attachments or []
        except Exception:
            return results

        for att in attachments:
            try:
                filename = getattr(att, "longFilename", None) or getattr(att, "shortFilename", "")
                if not filename:
                    continue

                suffix = Path(filename).suffix.lower()
                if suffix not in {".pdf", ".docx"}:
                    continue

                data = att.data
                if not data:
                    continue

                # Write to temp file and parse
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(data)
                    tmp_path = Path(tmp.name)

                text = self._parse_attachment(tmp_path, suffix)
                if text and len(text.strip()) >= 20:
                    results.append(f"## Attachment: {filename}\n\n{text}")
                    logger.debug(
                        "msg_attachment_extracted",
                        filename=filename,
                        length=len(text),
                    )

                # Clean up temp file
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

            except Exception:
                logger.debug("msg_attachment_failed", filename=filename)

        return results

    @staticmethod
    def _parse_attachment(path: Path, suffix: str) -> str | None:
        """Parse an attachment file using the appropriate parser."""
        if suffix == ".pdf":
            from src.ingestion.parsers.pdf import PdfParser

            return PdfParser().parse(path)
        if suffix == ".docx":
            from src.ingestion.parsers.docx import DocxParser

            return DocxParser().parse(path)
        return None
