from __future__ import annotations

import difflib
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

# Minimum similarity threshold for fuzzy matching
_FUZZY_THRESHOLD = 0.80


def _build_alias_list() -> list[tuple[str, PropertyID]]:
    """Build sorted alias list (longest first) for matching."""
    all_aliases: list[tuple[str, PropertyID]] = []
    for pid, info in PROPERTY_REGISTRY.items():
        if pid == PropertyID.SHARED:
            continue
        for alias in info.aliases:
            all_aliases.append((alias.lower(), pid))
    all_aliases.sort(key=lambda x: len(x[0]), reverse=True)
    return all_aliases


_ALL_ALIASES = _build_alias_list()


def _ngrams(text: str, sizes: tuple[int, ...] = (2, 3, 4)) -> list[str]:
    """Generate word-level n-grams from text."""
    words = text.split()
    grams = []
    for n in sizes:
        for i in range(len(words) - n + 1):
            grams.append(" ".join(words[i : i + n]))
    # Also include single words for single-word aliases
    grams.extend(words)
    return grams


def _fuzzy_match_property(text: str, threshold: float = _FUZZY_THRESHOLD) -> PropertyID | None:
    """Fuzzy-match text against all property aliases using sliding n-gram windows.

    Returns the best match above threshold, or None.
    """
    text_lower = text.lower()
    grams = _ngrams(text_lower)

    best_score = 0.0
    best_pid: PropertyID | None = None

    for gram in grams:
        for alias, pid in _ALL_ALIASES:
            score = difflib.SequenceMatcher(None, gram, alias).ratio()
            if score > best_score and score >= threshold:
                best_score = score
                best_pid = pid

    return best_pid


def _fuzzy_match_region(text: str, threshold: float = _FUZZY_THRESHOLD) -> Region | None:
    """Fuzzy-match text against region aliases.

    Returns the best match above threshold, or None.
    """
    text_lower = text.lower()
    grams = _ngrams(text_lower)

    best_score = 0.0
    best_region: Region | None = None

    for gram in grams:
        for alias, region in REGION_ALIASES.items():
            score = difflib.SequenceMatcher(None, gram, alias.lower()).ratio()
            if score > best_score and score >= threshold:
                best_score = score
                best_region = region

    return best_region


def extract_entities(text: str) -> ExtractedEntities:
    """Extract property and region references from user message text.

    Uses exact alias matching first, then falls back to fuzzy matching
    for typo tolerance. No LLM needed — property/region names are a
    fixed, small set.
    """
    text_lower = text.lower()
    found_properties: list[PropertyID] = []
    found_regions: list[Region] = []
    seen_pids: set[PropertyID] = set()
    seen_regions: set[Region] = set()

    # --- Exact match: properties (longest-first) ---
    for alias, pid in _ALL_ALIASES:
        if alias in text_lower and pid not in seen_pids:
            found_properties.append(pid)
            seen_pids.add(pid)

    # --- Exact match: regions ---
    sorted_region_aliases = sorted(REGION_ALIASES.items(), key=lambda x: len(x[0]), reverse=True)
    for alias, region in sorted_region_aliases:
        if alias in text_lower and region not in seen_regions:
            found_regions.append(region)
            seen_regions.add(region)

    # --- Fuzzy fallback: properties ---
    if not found_properties:
        fuzzy_pid = _fuzzy_match_property(text)
        if fuzzy_pid and fuzzy_pid not in seen_pids:
            found_properties.append(fuzzy_pid)
            seen_pids.add(fuzzy_pid)

    # --- Fuzzy fallback: regions ---
    if not found_regions:
        fuzzy_region = _fuzzy_match_region(text)
        if fuzzy_region and fuzzy_region not in seen_regions:
            found_regions.append(fuzzy_region)
            seen_regions.add(fuzzy_region)

    # Detect comparison intent
    is_comparison = bool(_COMPARISON_PATTERNS.search(text)) and (
        len(found_properties) > 1 or (len(found_properties) >= 1 and len(found_regions) >= 1)
    )

    return ExtractedEntities(
        properties=found_properties,
        regions=found_regions,
        is_comparison=is_comparison,
    )
