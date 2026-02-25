from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.domain.properties import (
    PROPERTY_REGISTRY,
    REGION_ALIASES,
    PropertyID,
    Region,
)


@dataclass(frozen=True)
class ExtractedEntities:
    """Entities extracted from user message text."""

    properties: list[PropertyID] = field(default_factory=list)
    regions: list[Region] = field(default_factory=list)
    is_comparison: bool = False

    @property
    def has_property(self) -> bool:
        return len(self.properties) > 0

    @property
    def has_region(self) -> bool:
        return len(self.regions) > 0

    @property
    def is_multi_property(self) -> bool:
        return len(self.properties) > 1


# Comparison signal words
_COMPARISON_PATTERNS = re.compile(
    r"\b(compare|comparison|versus|vs\.?|difference|between .+ and|"
    r"which (?:is|one)|better|prefer)\b",
    re.IGNORECASE,
)


def extract_entities(text: str) -> ExtractedEntities:
    """Extract property and region references from user message text.

    Uses exact alias matching against the property registry. No LLM needed —
    property/region names are a fixed, small set.
    """
    text_lower = text.lower()
    found_properties: list[PropertyID] = []
    found_regions: list[Region] = []
    seen_pids: set[PropertyID] = set()
    seen_regions: set[Region] = set()

    # Match properties by aliases (longest-first to avoid partial matches)
    all_aliases: list[tuple[str, PropertyID]] = []
    for pid, info in PROPERTY_REGISTRY.items():
        if pid == PropertyID.SHARED:
            continue
        for alias in info.aliases:
            all_aliases.append((alias.lower(), pid))

    # Sort by length descending so "pod camps bay" matches before "pod"
    all_aliases.sort(key=lambda x: len(x[0]), reverse=True)

    for alias, pid in all_aliases:
        if alias in text_lower and pid not in seen_pids:
            found_properties.append(pid)
            seen_pids.add(pid)

    # Match regions
    # Sort by length descending for same reason
    sorted_region_aliases = sorted(REGION_ALIASES.items(), key=lambda x: len(x[0]), reverse=True)
    for alias, region in sorted_region_aliases:
        if alias in text_lower and region not in seen_regions:
            found_regions.append(region)
            seen_regions.add(region)

    # Detect comparison intent
    is_comparison = bool(_COMPARISON_PATTERNS.search(text)) and (
        len(found_properties) > 1 or (len(found_properties) >= 1 and len(found_regions) >= 1)
    )

    return ExtractedEntities(
        properties=found_properties,
        regions=found_regions,
        is_comparison=is_comparison,
    )
