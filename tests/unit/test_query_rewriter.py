"""Tests for query_rewriter.py — synonym expansion."""

from __future__ import annotations

from src.retrieval.query_rewriter import expand_query


class TestExpandQuery:
    def test_rack_rate_expansion(self):
        result = expand_query("What is the rack rate?")
        assert "accommodation" in result
        assert "tariff" in result

    def test_menu_expansion(self):
        result = expand_query("What is on the menu?")
        assert "dinner" in result
        assert "restaurant" in result

    def test_spa_expansion(self):
        result = expand_query("Do you have a spa?")
        assert "wellness" in result
        assert "massage" in result

    def test_no_match_returns_original(self):
        result = expand_query("Tell me about the property")
        assert result == "Tell me about the property"

    def test_property_name_appended(self):
        result = expand_query("What are the rates?", property_name="La Fontaine")
        assert "La Fontaine" in result
        assert "tariff" in result

    def test_property_name_only(self):
        result = expand_query("Tell me about it", property_name="Camp Figtree")
        assert result == "Tell me about it Camp Figtree"

    def test_multiple_matches(self):
        result = expand_query("What is the spa menu?")
        assert "wellness" in result
        assert "restaurant" in result

    def test_case_insensitive(self):
        result = expand_query("RACK RATE please")
        assert "accommodation" in result

    def test_shuttle_expansion(self):
        result = expand_query("Is there a shuttle service?")
        assert "transfer" in result
        assert "airport" in result

    def test_check_in_expansion(self):
        result = expand_query("What is the check in time?")
        assert "arrival" in result
