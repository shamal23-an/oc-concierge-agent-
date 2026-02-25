from __future__ import annotations

from src.agent.context_resolver import resolve_context
from src.agent.session import SessionData
from src.domain.properties import PropertyID, Region
from src.domain.schemas import QueryScope


class TestExplicitPropertyId:
    def test_request_property_id_takes_priority(self):
        ctx = resolve_context(
            "What restaurants are nearby?",
            request_property_id=PropertyID.LA_FONTAINE,
        )
        assert ctx.scope == QueryScope.PROPERTY
        assert ctx.property_id == PropertyID.LA_FONTAINE
        assert ctx.region == Region.FRANSCHHOEK


class TestMessageDetection:
    def test_single_property_in_message(self):
        ctx = resolve_context("What restaurants does Avondrood recommend?")
        assert ctx.scope == QueryScope.PROPERTY
        assert ctx.property_id == PropertyID.AVONDROOD

    def test_region_in_message(self):
        ctx = resolve_context("What to do in Franschhoek?")
        assert ctx.scope == QueryScope.REGION
        assert ctx.region == Region.FRANSCHHOEK
        assert len(ctx.property_ids) == 3  # 3 Franschhoek properties

    def test_comparison_detected(self):
        ctx = resolve_context("Compare La Fontaine vs Avondrood")
        assert ctx.scope == QueryScope.CROSS_PROPERTY
        assert PropertyID.LA_FONTAINE in ctx.property_ids
        assert PropertyID.AVONDROOD in ctx.property_ids

    def test_multiple_properties_no_comparison_keyword(self):
        ctx = resolve_context("Tell me about La Fontaine and Avondrood")
        assert ctx.scope == QueryScope.CROSS_PROPERTY
        assert len(ctx.property_ids) == 2


class TestSessionContinuity:
    def test_uses_session_active_property(self):
        session = SessionData(session_id="abc", active_property="la_fontaine")
        ctx = resolve_context("What are the rates?", session=session)
        assert ctx.scope == QueryScope.PROPERTY
        assert ctx.property_id == PropertyID.LA_FONTAINE

    def test_message_overrides_session(self):
        """Message entity takes priority over session."""
        session = SessionData(session_id="abc", active_property="la_fontaine")
        ctx = resolve_context(
            "What about Avondrood?", session=session
        )
        assert ctx.property_id == PropertyID.AVONDROOD

    def test_context_switch_detected(self):
        """Mentioning a new property switches context."""
        session = SessionData(session_id="abc", active_property="la_fontaine")
        ctx = resolve_context("Tell me about Camp Figtree", session=session)
        assert ctx.property_id == PropertyID.CAMP_FIGTREE


class TestGroupFallback:
    def test_generic_question_falls_to_group(self):
        ctx = resolve_context("What is The Oyster Collection?")
        assert ctx.scope == QueryScope.GROUP

    def test_greeting_falls_to_group(self):
        ctx = resolve_context("Hello, good morning!")
        assert ctx.scope == QueryScope.GROUP

    def test_no_session_no_property_group(self):
        ctx = resolve_context("What are the rates?")
        assert ctx.scope == QueryScope.GROUP
