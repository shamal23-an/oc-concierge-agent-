from __future__ import annotations

from src.agent.session import SessionData


class TestSessionData:
    def test_create_empty(self):
        session = SessionData(session_id="abc")
        assert session.session_id == "abc"
        assert session.active_property is None
        assert session.conversation_history == []

    def test_add_message(self):
        session = SessionData(session_id="abc")
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi there!")
        assert len(session.conversation_history) == 2

    def test_history_trimmed_to_max(self):
        session = SessionData(session_id="abc")
        for i in range(25):
            session.add_message("user", f"Message {i}")
        assert len(session.conversation_history) == 20

    def test_round_trip_dict(self):
        session = SessionData(
            session_id="abc",
            active_property="la_fontaine",
            conversation_history=[{"role": "user", "content": "Hi"}],
        )
        data = session.to_dict()
        restored = SessionData.from_dict(data)
        assert restored.session_id == "abc"
        assert restored.active_property == "la_fontaine"
        assert len(restored.conversation_history) == 1
