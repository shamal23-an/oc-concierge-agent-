from __future__ import annotations

from pathlib import Path
from typing import Protocol


class DocumentParser(Protocol):
    """Protocol for document parsers."""

    def can_parse(self, path: Path) -> bool: ...

    def parse(self, path: Path) -> str | None:
        """Parse document and return text content, or None on failure."""
        ...
