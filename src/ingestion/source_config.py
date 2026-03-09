"""Knowledge base source configuration for ingestion."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from src.config.constants import SUPPORTED_EXTENSIONS

logger = structlog.get_logger()


def _matches_any_exclude(rel_path: str, patterns: list[str]) -> bool:
    """Check if a relative path matches any exclusion pattern.

    Handles directory-based patterns like '**/Logo*/**' by checking
    each path component against the pattern's directory segment.
    """
    for pat in patterns:
        # Direct fnmatch on full path
        if fnmatch.fnmatch(rel_path, pat):
            return True
        # Extract the directory name pattern from patterns like "**/Logo*/**"
        # and check if any path component matches it
        stripped = pat.replace("**/", "").rstrip("/*")
        if stripped and stripped != pat:
            parts = rel_path.split("/")
            for part in parts[:-1]:  # check directories only, not filename
                if fnmatch.fnmatch(part, stripped):
                    return True
    return False


@dataclass
class SourceConfig:
    """Configuration for a knowledge base source directory."""

    root: Path
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)

    def discover_files(self) -> list[Path]:
        """Discover files matching include/exclude patterns.

        If no include_patterns, discovers all supported files.
        Exclude patterns always filter out matches.
        """
        if not self.root.exists():
            logger.warning("source_root_not_found", path=str(self.root))
            return []

        if self.include_patterns:
            files = set()
            for pattern in self.include_patterns:
                for match in self.root.glob(pattern):
                    if match.is_file() and match.suffix.lower() in SUPPORTED_EXTENSIONS:
                        files.add(match)
        else:
            files = set()
            for ext in SUPPORTED_EXTENSIONS:
                files.update(self.root.rglob(f"*{ext}"))

        # Apply exclude patterns
        if self.exclude_patterns:
            filtered = set()
            for f in files:
                rel = str(f.relative_to(self.root))
                rel_fwd = rel.replace("\\", "/")
                if _matches_any_exclude(rel_fwd, self.exclude_patterns):
                    logger.debug("excluded_file", path=rel, pattern="exclude")
                    continue
                filtered.add(f)
            files = filtered

        return sorted(files)


# Logo/brand/photo/video patterns to exclude from Trade-Portal
_TRADE_PORTAL_EXCLUDES = [
    "**/*Logo*/**",
    "**/*logo*/**",
    "**/Videos/**",
    "**/_Brand*/**",
    "**/Photos*/**",
    "**/Image Library/**",
    "**/Document fonts/**",
]

# Useful document patterns in Trade-Portal Properties
_TRADE_PORTAL_PROPERTY_INCLUDES = [
    "Properties/**/*Brochure*.pdf",
    "Properties/**/*brochure*.pdf",
    "Properties/**/*Information*.pdf",
    "Properties/**/*information*.pdf",
    "Properties/**/*Fact*Sheet*.pdf",
    "Properties/**/*fact*sheet*.pdf",
    "Properties/**/*Menu*.pdf",
    "Properties/**/*menu*.pdf",
    "Properties/**/*Map*.pdf",
    "Properties/**/*map*.pdf",
    "Properties/**/*Comparison*.pdf",
    "Properties/**/*Introducing*.pdf",
    "Properties/**/*Resturaunt*.pdf",
    "Properties/**/Rates/**/*.pdf",
]

# Rate card patterns
_TRADE_PORTAL_RATES_INCLUDES = [
    "Rates/**/*.pdf",
]


CONCIERGE_SOURCE = SourceConfig(
    root=Path("D:/Work/Projects/Oyster-Collection/knowldge_base/Curated/Concierge"),
)

TRADE_PORTAL_SOURCE = SourceConfig(
    root=Path("D:/Work/Projects/Oyster-Collection/knowldge_base/Curated/Trade-Portal"),
)

DEFAULT_SOURCES = [TRADE_PORTAL_SOURCE, CONCIERGE_SOURCE]


# ── Validity date extraction ─────────────────────────────────────────────── #

# Patterns like "Oct 2025 - 08 Jan 2027", "2025 - 2026", "2025 and 2026"
_VALIDITY_RE = re.compile(
    r"(?P<from_month>\w+)?\s*(?P<from_year>20\d{2})\s*"
    r"[-–&and]+\s*"
    r"(?:(?P<to_day>\d{1,2})\s+)?(?P<to_month>\w+)?\s*(?P<to_year>20\d{2})",
    re.IGNORECASE,
)

_MONTH_MAP = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def extract_validity_dates(filename: str) -> dict[str, str]:
    """Extract valid_from/valid_to from rate card filenames.

    Returns dict with 'valid_from' and/or 'valid_to' as 'YYYY-MM' strings.
    """
    match = _VALIDITY_RE.search(filename)
    if not match:
        return {}

    result = {}
    from_year = match.group("from_year")
    from_month = match.group("from_month")
    to_year = match.group("to_year")
    to_month = match.group("to_month")

    if from_year:
        month_num = _MONTH_MAP.get(from_month.lower(), 1) if from_month else 1
        result["valid_from"] = f"{from_year}-{month_num:02d}"

    if to_year:
        month_num = _MONTH_MAP.get(to_month.lower(), 12) if to_month else 12
        result["valid_to"] = f"{to_year}-{month_num:02d}"

    return result
