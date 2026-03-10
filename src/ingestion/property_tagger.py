from __future__ import annotations

import re
from pathlib import Path

import structlog

from src.domain.properties import (
    PROPERTY_REGISTRY,
    REGION_ALIASES,
    PropertyID,
    get_properties_for_region,
)

logger = structlog.get_logger()

# Document type classification patterns
DOCUMENT_TYPE_PATTERNS: dict[str, list[str]] = {
    "rates": ["rack", "rates", "rate card", "pricing", "tariff"],
    "restaurant": ["restaurant", "dining", "menu", "food", "braai", "wine list"],
    "activity": ["activity", "activities", "tours", "transfer", "excursion"],
    "spa": ["spa", "beauty", "wellness", "massage"],
    "directions": ["direction", "map", "route", "how to get"],
    "recommendations": ["recommend", "suggestion", "wine farm"],
    "information_guide": ["information guide", "info guide", "guest info"],
    "festive": ["festive", "christmas", "nye", "new year"],
    "brochure": ["brochure"],
    "fact_sheet": ["fact sheet"],
}

# Trade-Portal numbered folder: "1. La Fontaine - Franschhoek"
_NUMBERED_FOLDER_RE = re.compile(r"^\d+\.\s*(.+?)\s*[-–]\s*(.+)$")
# Rate subfolder: "Rates - La Fontaine" or "Rates- Avondrood"
_RATES_FOLDER_RE = re.compile(r"^Rates?\s*[-–]\s*(.+)$", re.IGNORECASE)


def _build_filename_alias_index() -> list[tuple[str, PropertyID]]:
    """Build sorted alias list for filename matching (longest first)."""
    aliases: list[tuple[str, PropertyID]] = []
    for pid, info in PROPERTY_REGISTRY.items():
        if pid == PropertyID.SHARED:
            continue
        # Add property name and aliases
        aliases.append((info.name.lower(), pid))
        for alias in info.aliases:
            aliases.append((alias.lower(), pid))
    # Sort longest first so "pod camps bay" matches before "pod"
    aliases.sort(key=lambda x: len(x[0]), reverse=True)
    return aliases


_FILENAME_ALIASES = _build_filename_alias_index()


def tag_property_ids(file_path: Path, kb_root: Path) -> list[PropertyID]:
    """Determine which properties a document belongs to.

    Strategy (in priority order):
    1. Filename contains a property name/alias → that specific property
    2. Trade-Portal numbered folder → "1. La Fontaine - Franschhoek" → property
    3. Trade-Portal rate subfolder → "Rates - La Fontaine" → property
    4. Parent folder matches a property's kb_folder → that property
    5. Parent folder matches a region → ALL properties in that region
    6. Fallback → shared

    This FIXES the prototype bug where all Franschhoek docs were tagged
    as la_fontaine because region folders matched the first property.
    """
    rel_path = file_path.relative_to(kb_root)
    filename_lower = file_path.stem.lower().replace("_", " ").replace("-", " ")
    folder_parts_raw = list(rel_path.parts[:-1])  # original case
    folder_parts = [p.lower() for p in folder_parts_raw]

    # 1. Check filename for property name/alias
    for alias, pid in _FILENAME_ALIASES:
        if alias in filename_lower:
            logger.debug("tagged_by_filename", file=str(rel_path), property_id=pid)
            return [pid]

    # 2. Check Trade-Portal numbered folders: "1. La Fontaine - Franschhoek"
    for folder in folder_parts_raw:
        match = _NUMBERED_FOLDER_RE.match(folder)
        if match:
            property_name = match.group(1).strip()
            pid = _match_property_name(property_name)
            if pid:
                logger.debug("tagged_by_numbered_folder", file=str(rel_path), property_id=pid)
                return [pid]
        # Also try matching the full folder name (handles cases without dash)
        elif folder and folder[0].isdigit() and ". " in folder:
            # Strip the number prefix: "3. Pink Door Franschhoek Owner's Villa"
            stripped = folder.split(". ", 1)[1] if ". " in folder else folder
            pid = _match_property_name(stripped)
            if pid:
                logger.debug("tagged_by_numbered_folder", file=str(rel_path), property_id=pid)
                return [pid]

    # 3. Check Trade-Portal rate subfolders: "Rates - La Fontaine"
    for folder in folder_parts_raw:
        match = _RATES_FOLDER_RE.match(folder)
        if match:
            property_name = match.group(1).strip()
            pid = _match_property_name(property_name)
            if pid:
                logger.debug("tagged_by_rates_folder", file=str(rel_path), property_id=pid)
                return [pid]

    # 4. Check if any parent folder matches a property's kb_folder
    for pid, info in PROPERTY_REGISTRY.items():
        if pid == PropertyID.SHARED:
            continue
        for kb_folder in info.kb_folders:
            if kb_folder.lower() in folder_parts:
                # Only return this specific property if the folder is
                # property-specific (not a region name)
                if kb_folder.lower() not in REGION_ALIASES:
                    logger.debug("tagged_by_folder", file=str(rel_path), property_id=pid)
                    return [pid]

    # 5. Check if any parent folder is a region → tag ALL properties in that region
    for folder in folder_parts:
        region = REGION_ALIASES.get(folder)
        if region:
            region_pids = get_properties_for_region(region)
            logger.debug(
                "tagged_by_region",
                file=str(rel_path),
                region=region,
                property_ids=[str(p) for p in region_pids],
            )
            return region_pids

    # 6. Fallback to shared
    logger.debug("tagged_as_shared", file=str(rel_path))
    return [PropertyID.SHARED]


def _match_property_name(name: str) -> PropertyID | None:
    """Match a property name from folder text against the alias index."""
    name_lower = name.lower().strip()
    # Try exact alias match first
    for alias, pid in _FILENAME_ALIASES:
        if alias in name_lower:
            return pid
    return None


def classify_document_type(filename: str) -> str:
    """Classify document type from filename patterns."""
    name_lower = filename.lower()
    for doc_type, patterns in DOCUMENT_TYPE_PATTERNS.items():
        if any(p in name_lower for p in patterns):
            return doc_type
    return "general"
