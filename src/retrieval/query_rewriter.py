"""Static synonym expansion for query rewriting (zero latency, no LLM)."""

from __future__ import annotations

# Hospitality-domain synonym expansions.
# Each key is a phrase that may appear in a guest query;
# the value is additional terms appended to the embedding query.
QUERY_SYNONYMS: dict[str, str] = {
    "rack rate": "accommodation rates tariff pricing per night",
    "rate card": "accommodation rates pricing tariff per night",
    "rates": "pricing tariff per night accommodation cost",
    "how much": "rates pricing cost per night tariff",
    "price": "rates pricing cost per night tariff",
    "menu": "dinner lunch breakfast food dining restaurant",
    "restaurant": "dining food menu dinner lunch breakfast",
    "dinner": "restaurant dining menu food evening",
    "lunch": "restaurant dining menu food midday",
    "breakfast": "restaurant dining menu food morning",
    "game drive": "safari game drive bush experience wildlife",
    "safari": "game drive bush experience wildlife",
    "spa": "spa wellness treatment massage beauty",
    "massage": "spa wellness treatment beauty",
    "shuttle": "transfer shuttle transport airport pickup",
    "transfer": "shuttle transport airport pickup",
    "airport": "transfer shuttle transport pickup",
    "check in": "check-in arrival time",
    "check out": "check-out departure time",
    "check-in": "check in arrival time",
    "check-out": "check out departure time",
    "pool": "swimming pool",
    "wifi": "wi-fi internet",
    "wi-fi": "wifi internet",
    "parking": "car parking",
    "wine": "wine list wine tasting vineyard",
    "activities": "things to do tours excursions experiences",
    "things to do": "activities tours excursions experiences",
    "directions": "how to get route map driving directions",
    "pet": "pet friendly pets allowed dog",
    "child": "children kids family child-friendly",
    "kids": "children child family child-friendly",
}


def expand_query(query: str, property_name: str | None = None) -> str:
    """Expand a query with synonym terms for better embedding recall.

    Appends matched synonym terms and optionally the property name.
    Returns the expanded query string (used for embedding, not shown to user).
    """
    lower = query.lower()
    expansions: list[str] = []

    for trigger, synonyms in QUERY_SYNONYMS.items():
        if trigger in lower:
            expansions.append(synonyms)

    result = query
    if expansions:
        result = f"{query} {' '.join(expansions)}"
    if property_name:
        result = f"{result} {property_name}"

    return result
