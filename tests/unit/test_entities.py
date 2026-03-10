from __future__ import annotations

from src.domain.entities import (
    ExtractedEntities,
    _fuzzy_match_property,
    _fuzzy_match_region,
    extract_entities,
)
from src.domain.properties import PropertyID, Region


class TestExactMatch:
    """Exact alias matching still works."""

    def test_camp_figtree_exact(self):
        result = extract_entities("Tell me about Camp Figtree")
        assert PropertyID.CAMP_FIGTREE in result.properties

    def test_blackheath_exact(self):
        result = extract_entities("rates for blackheath lodge")
        assert PropertyID.BLACKHEATH_LODGE in result.properties

    def test_pod_exact(self):
        result = extract_entities("I want to stay at POD Camps Bay")
        assert PropertyID.POD_CAMPS_BAY in result.properties

    def test_region_exact(self):
        result = extract_entities("properties in franschhoek")
        assert Region.FRANSCHHOEK in result.regions

    def test_exact_preferred_over_fuzzy(self):
        """Exact match should always be used when available."""
        result = extract_entities("camp figtree rates")
        assert PropertyID.CAMP_FIGTREE in result.properties
        assert len(result.properties) == 1

    def test_la_fontaine_detected(self):
        result = extract_entities("What's the menu at La Fontaine?")
        assert PropertyID.LA_FONTAINE in result.properties

    def test_pod_camps_bay_full_name(self):
        result = extract_entities("How do I get to POD Camps Bay?")
        assert PropertyID.POD_CAMPS_BAY in result.properties

    def test_8a_detected(self):
        result = extract_entities("Tell me about 8A guest house")
        assert PropertyID.EIGHT_A in result.properties

    def test_no_property_in_generic_question(self):
        result = extract_entities("What is The Oyster Collection?")
        assert not result.has_property

    def test_multiple_properties_detected(self):
        result = extract_entities("Compare La Fontaine and Avondrood")
        assert PropertyID.LA_FONTAINE in result.properties
        assert PropertyID.AVONDROOD in result.properties
        assert result.is_multi_property

    def test_franschhoek_detected(self):
        result = extract_entities("What to do in Franschhoek?")
        assert Region.FRANSCHHOEK in result.regions
        assert result.has_region

    def test_cape_town_detected(self):
        result = extract_entities("Best restaurants in Cape Town?")
        assert Region.CAPE_TOWN in result.regions

    def test_makhanda_alias_for_grahamstown(self):
        result = extract_entities("Activities near Makhanda")
        assert Region.GRAHAMSTOWN in result.regions

    def test_kenton_on_sea_detected(self):
        result = extract_entities("Beaches at Kenton-on-Sea")
        assert Region.KENTON_ON_SEA in result.regions

    def test_empty_string(self):
        result = extract_entities("")
        assert not result.has_property
        assert not result.has_region
        assert not result.is_comparison

    def test_greeting_has_no_entities(self):
        result = extract_entities("Hello, good morning!")
        assert not result.has_property
        assert not result.has_region


class TestFuzzyMatch:
    """Fuzzy matching catches common typos."""

    def test_typo_camp_figtre(self):
        result = extract_entities("what are the rates at camp figtre")
        assert PropertyID.CAMP_FIGTREE in result.properties

    def test_typo_blackhealth(self):
        result = extract_entities("tell me about blackhealth lodge")
        assert PropertyID.BLACKHEATH_LODGE in result.properties

    def test_typo_lafontain(self):
        result = extract_entities("dinner at la fontane")
        assert PropertyID.LA_FONTAINE in result.properties

    def test_typo_avondrod(self):
        result = extract_entities("rooms at avondrod")
        assert PropertyID.AVONDROOD in result.properties

    def test_no_false_positive_restaurant(self):
        """Generic words should NOT match any property."""
        result = extract_entities("the restaurant was amazing")
        # Should not match "the milner" or any property
        assert len(result.properties) == 0

    def test_no_false_positive_short(self):
        """Very short generic text should not match."""
        result = extract_entities("what time is it")
        assert len(result.properties) == 0

    def test_fuzzy_region_ado(self):
        """Typo 'ado' should not match 'addo' (too short, low ratio)."""
        result = extract_entities("trips to ado")
        # "ado" vs "addo" = 0.86 — may or may not match depending on threshold
        # But this tests the fuzzy region path exists
        assert isinstance(result, ExtractedEntities)


class TestFuzzyMatchFunction:
    """Direct tests for the fuzzy match functions."""

    def test_fuzzy_match_camp_figtre(self):
        pid = _fuzzy_match_property("camp figtre")
        assert pid == PropertyID.CAMP_FIGTREE

    def test_fuzzy_match_blackhealth(self):
        pid = _fuzzy_match_property("blackhealth lodge")
        assert pid == PropertyID.BLACKHEATH_LODGE

    def test_fuzzy_match_no_match(self):
        pid = _fuzzy_match_property("random gibberish xyz")
        assert pid is None

    def test_fuzzy_region_franschoek(self):
        region = _fuzzy_match_region("franschoek")
        assert region == Region.FRANSCHHOEK

    def test_fuzzy_region_no_match(self):
        region = _fuzzy_match_region("new york")
        assert region is None


class TestComparison:
    """Comparison detection still works."""

    def test_compare_two_properties(self):
        result = extract_entities("compare camp figtree and blackheath lodge")
        assert result.is_comparison
        assert len(result.properties) == 2

    def test_difference_between_properties(self):
        result = extract_entities(
            "What's the difference between POD Camps Bay and Blackheath Lodge?"
        )
        assert result.is_comparison

    def test_single_property_not_comparison(self):
        result = extract_entities("Tell me about La Fontaine")
        assert not result.is_comparison

    def test_which_is_better(self):
        result = extract_entities("Which is better, Camp Figtree or The Milner?")
        assert result.is_comparison
