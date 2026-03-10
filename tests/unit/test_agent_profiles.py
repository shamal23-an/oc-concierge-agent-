"""Tests for agent profiles."""

from __future__ import annotations

from src.config.agent_profiles import (
    BOOKING_PROFILE,
    CONCIERGE_PROFILE,
    WHATSAPP_PROFILE,
    get_agent_profile,
)


class TestAgentProfiles:
    def test_concierge_defaults(self):
        p = CONCIERGE_PROFILE
        assert p.agent_id == "concierge"
        assert p.top_k == 7
        assert p.rerank_min_score == 0.25
        assert p.max_chunks_per_source == 3
        assert p.allowed_properties is None

    def test_booking_profile(self):
        p = BOOKING_PROFILE
        assert p.agent_id == "booking_agent"
        assert p.top_k == 10
        assert p.rerank_min_score == 0.3
        assert p.system_prompt_override is not None
        assert "booking" in p.system_prompt_override.lower()

    def test_whatsapp_profile(self):
        p = WHATSAPP_PROFILE
        assert p.agent_id == "whatsapp_agent"
        assert p.top_k == 5
        assert p.system_prompt_override is not None
        assert "WhatsApp" in p.system_prompt_override

    def test_get_profile_by_id(self):
        assert get_agent_profile("concierge") is CONCIERGE_PROFILE
        assert get_agent_profile("booking_agent") is BOOKING_PROFILE
        assert get_agent_profile("whatsapp_agent") is WHATSAPP_PROFILE

    def test_unknown_profile_defaults_to_concierge(self):
        assert get_agent_profile("unknown") is CONCIERGE_PROFILE
