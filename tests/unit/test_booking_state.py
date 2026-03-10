from __future__ import annotations

from src.agent.nodes import _extract_booking_details
from src.agent.session import SessionData


class TestBookingSerialization:
    """Booking details persist in session."""

    def test_booking_in_session_dict(self):
        session = SessionData("test-1", booking_details={"property": "camp_figtree", "guests": 2})
        data = session.to_dict()
        assert data["booking_details"]["property"] == "camp_figtree"
        assert data["booking_details"]["guests"] == 2

    def test_booking_from_dict(self):
        data = {
            "session_id": "test-2",
            "booking_details": {"check_in": "15 march", "guests": 4},
            "conversation_history": [],
        }
        session = SessionData.from_dict(data)
        assert session.booking_details["check_in"] == "15 march"
        assert session.booking_details["guests"] == 4

    def test_no_booking_defaults_none(self):
        session = SessionData("test-3")
        assert session.booking_details is None
        data = session.to_dict()
        assert data["booking_details"] is None


class TestDateExtraction:
    """Extract dates from user messages."""

    def test_date_day_month(self):
        result = _extract_booking_details("arriving 15 March 2026", None)
        assert result is not None
        assert "check_in" in result

    def test_two_dates(self):
        result = _extract_booking_details("from 15 March to 20 March", None)
        assert result is not None
        assert "check_in" in result
        assert "check_out" in result

    def test_no_dates(self):
        result = _extract_booking_details("what rooms do you have", None)
        # No dates, no guests — should return None
        assert result is None


class TestGuestCountExtraction:
    """Extract guest count from user messages."""

    def test_guest_count(self):
        result = _extract_booking_details("booking for 4 guests", None)
        assert result is not None
        assert result["guests"] == 4

    def test_people_count(self):
        result = _extract_booking_details("we are 6 people", None)
        assert result is not None
        assert result["guests"] == 6

    def test_pax_count(self):
        result = _extract_booking_details("2 pax please", None)
        assert result is not None
        assert result["guests"] == 2


class TestBookingMerge:
    """Existing booking details are preserved."""

    def test_merge_with_existing(self):
        existing = {"property": "camp_figtree", "check_in": "15 march"}
        result = _extract_booking_details("for 3 guests", existing)
        assert result["property"] == "camp_figtree"
        assert result["check_in"] == "15 march"
        assert result["guests"] == 3

    def test_night_count(self):
        result = _extract_booking_details("staying 3 nights", None)
        assert result is not None
        assert result["nights"] == 3
