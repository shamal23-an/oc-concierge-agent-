from __future__ import annotations

from src.retrieval.ranker import _detect_query_doc_types, rank_chunks


def _chunk(
    content: str,
    score: float,
    property_ids: list[str] | None = None,
    doc_type: str = "general",
) -> dict:
    return {
        "content": content,
        "score": score,
        "property_ids": property_ids or [],
        "source_file": "test.pdf",
        "metadata": {"document_type": doc_type},
    }


class TestDetectQueryDocTypes:
    def test_rates_query(self):
        assert "rates" in _detect_query_doc_types("what are the rates?")

    def test_restaurant_query(self):
        types = _detect_query_doc_types("what is on the dinner menu?")
        assert "restaurant" in types

    def test_activity_query(self):
        assert "activity" in _detect_query_doc_types("what activities are available?")

    def test_spa_query(self):
        assert "spa" in _detect_query_doc_types("tell me about the spa")

    def test_directions_query(self):
        assert "directions" in _detect_query_doc_types("how to get there from the airport")

    def test_no_match(self):
        assert _detect_query_doc_types("tell me about the property") == set()

    def test_multiple_matches(self):
        types = _detect_query_doc_types("spa menu and rates")
        assert "spa" in types
        assert "restaurant" in types
        assert "rates" in types


class TestRankChunks:
    def test_empty_chunks(self):
        assert rank_chunks([]) == []

    def test_sorts_by_score(self):
        chunks = [_chunk("A", 0.5), _chunk("B", 0.9), _chunk("C", 0.7)]
        ranked = rank_chunks(chunks)
        assert [c["content"] for c in ranked] == ["B", "C", "A"]

    def test_property_boost(self):
        chunks = [
            _chunk("A", 0.5, ["la_fontaine"]),
            _chunk("B", 0.5, ["avondrood"]),
        ]
        ranked = rank_chunks(chunks, target_property_id="la_fontaine")
        assert ranked[0]["content"] == "A"

    def test_doc_type_boost(self):
        chunks = [
            _chunk("General info", 0.5, doc_type="general"),
            _chunk("Rate card info", 0.5, doc_type="rates"),
        ]
        ranked = rank_chunks(chunks, query="what are the rates?")
        assert ranked[0]["content"] == "Rate card info"

    def test_dedup_near_identical(self):
        chunks = [
            _chunk("Same prefix content here..." * 10, 0.9),
            _chunk("Same prefix content here..." * 10, 0.8),
        ]
        ranked = rank_chunks(chunks)
        assert len(ranked) == 1

    def test_no_query_no_doc_boost(self):
        chunks = [
            _chunk("General", 0.5, doc_type="general"),
            _chunk("Rates", 0.5, doc_type="rates"),
        ]
        ranked = rank_chunks(chunks)
        # Without query, both have same score — order preserved
        assert len(ranked) == 2
