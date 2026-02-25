from __future__ import annotations

from src.domain.entities import extract_entities
from src.domain.properties import PropertyID, Region


class TestExtractProperties:
    def test_single_property_by_name(self):
        result = extract_entities("What restaurants does Avondrood recommend?")
        assert PropertyID.AVONDROOD in result.properties
        assert result.has_property

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


class TestExtractRegions:
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


class TestComparisonDetection:
    def test_compare_two_properties(self):
        result = extract_entities("Compare La Fontaine vs Avondrood")
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


class TestEdgeCases:
    def test_empty_string(self):
        result = extract_entities("")
        assert not result.has_property
        assert not result.has_region
        assert not result.is_comparison

    def test_greeting_has_no_entities(self):
        result = extract_entities("Hello, good morning!")
        assert not result.has_property
        assert not result.has_region
