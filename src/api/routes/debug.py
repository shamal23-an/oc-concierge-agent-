"""Debug endpoint — returns response + retrieved chunks + scores + timing."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from src.agent.nodes import generate_node, resolve_node, retrieve_node
from src.api.dependencies import get_qdrant_client, get_redis_client
from src.config.settings import get_settings
from src.domain.schemas import AgentState, ChatRequest

router = APIRouter()


class ChunkDebugInfo(BaseModel):
    content_preview: str
    score: float
    source_file: str
    property_ids: list[str]
    document_type: str = ""
    valid_from: str | None = None
    valid_to: str | None = None


class DebugResponse(BaseModel):
    response: str
    session_id: str
    scope: str | None = None
    sources: list[str] = Field(default_factory=list)
    chunks: list[ChunkDebugInfo] = Field(default_factory=list)
    timing: dict[str, float] = Field(default_factory=dict)
    active_property: str | None = None
    resolved_properties: list[str] = Field(default_factory=list)
    cache_hit: bool = False


@router.post("/chat/debug", response_model=DebugResponse)
async def chat_debug(
    http_request: Request,
    request: ChatRequest,
) -> DebugResponse:
    """Debug chat endpoint — returns full pipeline details."""
    qdrant_client = get_qdrant_client(http_request.app)
    redis_client = get_redis_client(http_request.app)
    settings = get_settings()
    if not settings.api_key:
        pass  # Allow in dev mode

    state: AgentState = {
        "message": request.message,
        "property_id": request.property_id,
        "session_id": request.session_id or "",
    }

    timing = {}

    # Resolve
    t0 = time.perf_counter()
    state = await resolve_node(state, redis_client=redis_client)
    timing["resolve_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    # Retrieve
    t0 = time.perf_counter()
    state = await retrieve_node(state, qdrant_client=qdrant_client, redis_client=redis_client)
    timing["retrieve_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    # Generate
    t0 = time.perf_counter()
    state = await generate_node(state)
    timing["generate_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    timing["total_ms"] = round(sum(timing.values()), 1)

    # Build chunk debug info
    chunks_debug = []
    for chunk in state.get("chunks", []):
        meta = chunk.get("metadata", {})
        chunks_debug.append(
            ChunkDebugInfo(
                content_preview=chunk["content"][:200],
                score=round(chunk["score"], 4),
                source_file=chunk.get("source_file", ""),
                property_ids=chunk.get("property_ids", []),
                document_type=meta.get("document_type", ""),
                valid_from=meta.get("valid_from"),
                valid_to=meta.get("valid_to"),
            )
        )

    return DebugResponse(
        response=state.get("response", ""),
        session_id=state.get("session_id", ""),
        scope=state.get("scope"),
        sources=state.get("sources", []),
        chunks=chunks_debug,
        timing=timing,
        active_property=state.get("active_property"),
        resolved_properties=state.get("resolved_properties", []),
        cache_hit=state.get("cache_hit", False),
    )
