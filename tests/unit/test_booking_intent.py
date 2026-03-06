from __future__ import annotations

from src.agent.nodes import _has_booking_intent
from src.config.constants import BOOKING_PATTERNS
from src.domain.properties import PROPERTY_REGISTRY, PropertyID


class TestBookingPatterns:
    def test_booking_patterns_exist(self):
        assert len(BOOKING_PATTERNS) > 0
        assert "book" in BOOKING_PATTERNS
        assert "reserve" in BOOKING_PATTERNS
        assert "reservation" in BOOKING_PATTERNS

    def test_detects_booking_intent(self):
        assert _has_booking_intent("I want to book a room")
        assert _has_booking_intent("Can I make a reservation?")
        assert _has_booking_intent("Check availability for next week")
        assert _has_booking_intent("I'd like to reserve a suite")
        assert _has_booking_intent("What is check-in time?")

    def test_no_false_positives(self):
        assert not _has_booking_intent("What are the rates?")
        assert not _has_booking_intent("Tell me about the restaurant")
        assert not _has_booking_intent("How do I get there?")
        assert not _has_booking_intent("What activities are available?")


class TestPropertyContactInfo:
    def test_all_properties_have_email(self):
        for pid, info in PROPERTY_REGISTRY.items():
            if pid == PropertyID.SHARED:
                continue
            assert info.email, f"{pid} missing email"

    def test_all_properties_have_phone(self):
        for pid, info in PROPERTY_REGISTRY.items():
            if pid == PropertyID.SHARED:
                continue
            assert info.phone, f"{pid} missing phone"

    def test_la_fontaine_contact(self):
        info = PROPERTY_REGISTRY[PropertyID.LA_FONTAINE]
        assert "lafontaine" in info.email
        assert "+27" in info.phone

    def test_avondrood_contact(self):
        info = PROPERTY_REGISTRY[PropertyID.AVONDROOD]
        assert "avondrood" in info.email
        assert "+27" in info.phone
