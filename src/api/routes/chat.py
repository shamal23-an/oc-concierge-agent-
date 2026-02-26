from __future__ import annotations

import time

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.agent.graph import create_agent
from src.agent.session_lock import SessionLockError, session_lock
from src.api.dependencies import get_qdrant_client, get_redis_client
from src.domain.schemas import AgentState, ChatRequest, ChatResponse, QueryScope

logger = structlog.get_logger()

router = APIRouter()


@router.post("/chat")
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    """Main chat endpoint. property_id is OPTIONAL.

    Uses ainvoke() so the entire LangGraph pipeline runs
    asynchronously — Redis, Qdrant, and LLM calls do not
    block the event loop.
    """
    start = time.perf_counter()

    qdrant_client = get_qdrant_client(request.app)
    redis_client = get_redis_client(request.app)

    agent = create_agent(qdrant_client=qdrant_client, redis_client=redis_client)

    # Ensure we have a session_id before locking (generate if not provided)
    session_id = body.session_id or ""

    # Build initial state
    initial_state: AgentState = {
        "message": body.message,
        "property_id": body.property_id,
        "session_id": session_id,
    }

    # Acquire per-session lock, then run the graph.
    # This prevents concurrent requests for the same session from
    # causing read-modify-write race conditions on session data.
    try:
        async with session_lock(redis_client, session_id):
            result = await agent.ainvoke(initial_state)
    except SessionLockError:
        logger.warning(
            "chat_session_locked",
            session_id=session_id,
        )
        return JSONResponse(
            status_code=429,
            content={
                "detail": "This session is currently processing another request. "
                "Please try again shortly.",
            },
        )

    duration_ms = round((time.perf_counter() - start) * 1000, 2)

    # Determine property_id for response
    response_pid = result.get("active_property") or (
        str(body.property_id) if body.property_id else None
    )

    scope = result.get("scope")
    try:
        scope_enum = QueryScope(scope) if scope else None
    except ValueError:
        scope_enum = None

    cached = result.get("cache_hit", False)

    logger.info(
        "chat_response",
        session_id=result.get("session_id"),
        scope=scope,
        property_id=response_pid,
        num_sources=len(result.get("sources", [])),
        duration_ms=duration_ms,
        cached=cached,
    )

    return ChatResponse(
        response=result.get("response", "I'm sorry, I couldn't process your request."),
        session_id=result.get("session_id", ""),
        property_id=response_pid,
        scope=scope_enum,
        sources=result.get("sources", []),
        cached=cached,
    )
