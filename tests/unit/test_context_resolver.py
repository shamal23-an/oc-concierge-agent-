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


class TestSinglePropertyRegionPromotion:
    """Regions with only one property should auto-promote to PROPERTY scope."""

    def test_addo_promotes_to_camp_figtree(self):
        ctx = resolve_context("interested in the Addo area")
        assert ctx.scope == QueryScope.PROPERTY
        assert ctx.property_id == PropertyID.CAMP_FIGTREE
        assert ctx.region == Region.ADDO

    def test_salem_promotes_to_burlington_bush(self):
        ctx = resolve_context("what about Salem properties")
        assert ctx.scope == QueryScope.PROPERTY
        assert ctx.property_id == PropertyID.BURLINGTON_BUSH
        assert ctx.region == Region.SALEM

    def test_franschhoek_stays_region(self):
        """Franschhoek has 3 properties — should stay as REGION scope."""
        ctx = resolve_context("properties in Franschhoek")
        assert ctx.scope == QueryScope.REGION
        assert ctx.region == Region.FRANSCHHOEK
        assert len(ctx.property_ids) == 3

    def test_cape_town_stays_region(self):
        """Cape Town has 2 properties — should stay as REGION scope."""
        ctx = resolve_context("staying in Cape Town")
        assert ctx.scope == QueryScope.REGION
        assert ctx.region == Region.CAPE_TOWN
        assert len(ctx.property_ids) == 2


class TestSessionContinuity:
    """Session-based context resolution."""

    def test_uses_session_active_property(self):
        session = SessionData(session_id="abc", active_property="la_fontaine")
        ctx = resolve_context("What are the rates?", session=session)
        assert ctx.scope == QueryScope.PROPERTY
        assert ctx.property_id == PropertyID.LA_FONTAINE

    def test_message_overrides_session(self):
        """Message entity takes priority over session."""
        session = SessionData(session_id="abc", active_property="la_fontaine")
        ctx = resolve_context("What about Avondrood?", session=session)
        assert ctx.property_id == PropertyID.AVONDROOD

    def test_context_switch_detected(self):
        """Mentioning a new property switches context."""
        session = SessionData(session_id="abc", active_property="la_fontaine")
        ctx = resolve_context("Tell me about Camp Figtree", session=session)
        assert ctx.property_id == PropertyID.CAMP_FIGTREE

    def test_session_property_preserved_on_region(self):
        """If session has active_property and message has no entity, use session."""
        session = SessionData("test-1", active_property="blackheath_lodge")
        ctx = resolve_context("what are the rates?", session=session)
        assert ctx.scope == QueryScope.PROPERTY
        assert ctx.property_id == PropertyID.BLACKHEATH_LODGE

    def test_session_region_fallback(self):
        """If session has active_region and no property/entity found, use region."""
        session = SessionData("test-2", active_region="addo")
        ctx = resolve_context("tell me more about activities", session=session)
        assert ctx.scope == QueryScope.PROPERTY  # Addo auto-promotes
        assert ctx.property_id == PropertyID.CAMP_FIGTREE

    def test_session_region_multi_property(self):
        """Session region with multiple properties stays as REGION."""
        session = SessionData("test-3", active_region="franschhoek")
        ctx = resolve_context("what restaurants are there?", session=session)
        assert ctx.scope == QueryScope.REGION
        assert ctx.region == Region.FRANSCHHOEK

    def test_message_entity_overrides_session(self):
        """Explicit property in message should override session."""
        session = SessionData("test-4", active_property="blackheath_lodge")
        ctx = resolve_context("tell me about Camp Figtree", session=session)
        assert ctx.property_id == PropertyID.CAMP_FIGTREE

    def test_no_session_falls_to_group(self):
        """No session, no entity -> GROUP scope."""
        ctx = resolve_context("what do you offer?")
        assert ctx.scope == QueryScope.GROUP


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
