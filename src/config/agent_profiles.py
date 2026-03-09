"""Agent retrieval profiles for multi-agent knowledge base access."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.properties import PropertyID


@dataclass(frozen=True)
class AgentProfile:
    """Configuration profile for an agent's retrieval behavior."""

    agent_id: str
    name: str
    top_k: int = 7
    rerank_min_score: float = 0.25
    max_chunks_per_source: int = 3
    allowed_properties: list[PropertyID] | None = None  # None = all
    system_prompt_override: str | None = None


# Default profiles
CONCIERGE_PROFILE = AgentProfile(
    agent_id="concierge",
    name="Concierge Agent",
    top_k=7,
    rerank_min_score=0.25,
    max_chunks_per_source=3,
)

BOOKING_PROFILE = AgentProfile(
    agent_id="booking_agent",
    name="Booking Agent",
    top_k=10,
    rerank_min_score=0.3,
    max_chunks_per_source=5,
    system_prompt_override=(
        "You are a booking assistant for The Oyster Collection. "
        "Focus on rates, availability, room types, and booking procedures. "
        "Always include current rates when available."
    ),
)

WHATSAPP_PROFILE = AgentProfile(
    agent_id="whatsapp_agent",
    name="WhatsApp Agent",
    top_k=5,
    rerank_min_score=0.25,
    max_chunks_per_source=2,
    system_prompt_override=(
        "You are a concierge for The Oyster Collection, responding via WhatsApp. "
        "Keep responses concise (under 300 words). Use short paragraphs."
    ),
)


_PROFILES: dict[str, AgentProfile] = {
    p.agent_id: p for p in [CONCIERGE_PROFILE, BOOKING_PROFILE, WHATSAPP_PROFILE]
}


def get_agent_profile(agent_id: str) -> AgentProfile:
    """Get an agent profile by ID, defaulting to concierge."""
    return _PROFILES.get(agent_id, CONCIERGE_PROFILE)
