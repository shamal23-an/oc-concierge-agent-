from __future__ import annotations

from pathlib import Path

import structlog

logger = structlog.get_logger()


class MsgParser:
    """Outlook MSG parser using extract-msg."""

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
            msg.close()

            text = "\n\n".join(parts)
            if len(text.strip()) < 20:
                logger.warning("msg_parse_empty", path=str(path))
                return None
            return text.strip()
        except Exception:
            logger.warning("msg_parse_failed", path=str(path))
            return None
