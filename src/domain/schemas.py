from __future__ import annotations

from enum import StrEnum
from typing import TypedDict

from pydantic import BaseModel, Field

from src.domain.properties import PropertyID

# --------------------------------------------------------------------------- #
# Query scope — determines retrieval strategy
# --------------------------------------------------------------------------- #


class QueryScope(StrEnum):
    """How broadly to search for context."""

    PROPERTY = "property"  # Single property
    REGION = "region"  # All properties in a region
    GROUP = "group"  # Entire Oyster Collection
    CROSS_PROPERTY = "cross_property"  # Comparison between specific properties
    CLARIFY = "clarify"  # Need to ask user which property


# --------------------------------------------------------------------------- #
# API request / response models
# --------------------------------------------------------------------------- #


class ChatRequest(BaseModel):
    """Incoming chat message. property_id is OPTIONAL."""

    message: str = Field(..., min_length=1, max_length=4000)
    property_id: PropertyID | None = None
    session_id: str | None = None


class ChatResponse(BaseModel):
    """Chat response with metadata."""

    response: str
    session_id: str
    property_id: PropertyID | None = None
    scope: QueryScope | None = None
    sources: list[str] = Field(default_factory=list)
    cached: bool = False


# --------------------------------------------------------------------------- #
# LangGraph agent state (TypedDict for native LangGraph compatibility)
# --------------------------------------------------------------------------- #


class RetrievedChunk(TypedDict):
    """A single retrieved document chunk."""

    content: str
    score: float
    property_ids: list[str]
    source_file: str
    metadata: dict


class AgentState(TypedDict, total=False):
    """State passed through LangGraph nodes."""

    # Input
    message: str
    property_id: str | None
    session_id: str

    # Context resolution
    scope: str  # QueryScope value
    resolved_properties: list[str]  # PropertyID values
    resolved_region: str | None  # Region value

    # Retrieval
    chunks: list[RetrievedChunk]

    # Generation
    response: str
    sources: list[str]

    # Session
    conversation_history: list[dict]
    active_property: str | None
