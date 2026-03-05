from __future__ import annotations

import time
import traceback

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.agent.graph import create_agent
from src.agent.session_lock import SessionLockError, session_lock
from src.api.dependencies import get_qdrant_client, get_redis_client
from src.config.settings import get_settings
from src.domain.schemas import AgentState, ChatRequest, ChatResponse, QueryScope
from src.retrieval.embedder import embed_query

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
    except Exception as exc:
        # Safety net: if anything in the pipeline fails (LLM down,
        # Qdrant unreachable, unexpected bug), return a friendly
        # ChatResponse so the frontend can handle it normally.
        logger.exception(
            "chat_pipeline_error",
            session_id=session_id,
            message=body.message[:100],
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "chat_response",
            session_id=session_id,
            scope=None,
            property_id=None,
            num_sources=0,
            duration_ms=duration_ms,
            cached=False,
            error=True,
        )
        return ChatResponse(
            response=(
                "I'm sorry, I'm having trouble processing your request "
                "right now. Please try again in a moment, or contact "
                "our team directly for assistance."
            ),
            session_id=session_id,
            property_id=str(body.property_id) if body.property_id else None,
            sources=[],
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


@router.get("/debug/rag")
async def debug_rag(request: Request):
    """Temporary debug endpoint — tests the full RAG pipeline and returns
    the actual error or raw results. Remove before production."""
    settings = get_settings()
    steps: dict = {"collection_name": settings.qdrant_collection}

    qdrant = get_qdrant_client(request.app)

    # Step 1: List collections
    try:
        collections = await qdrant.get_collections()
        steps["collections"] = [c.name for c in collections.collections]
    except Exception as exc:
        steps["collections_error"] = f"{type(exc).__name__}: {exc}"
        return JSONResponse(content=steps, status_code=500)

    # Step 2: Check target collection info
    try:
        info = await qdrant.get_collection(settings.qdrant_collection)
        steps["collection_info"] = {
            "vectors_count": info.vectors_count,
            "points_count": info.points_count,
            "vector_size": info.config.params.vectors.size
            if hasattr(info.config.params.vectors, "size")
            else str(info.config.params.vectors),
            "status": str(info.status),
        }
    except Exception as exc:
        steps["collection_error"] = f"{type(exc).__name__}: {exc}"
        return JSONResponse(content=steps, status_code=500)

    # Step 3: Embed a test query
    try:
        vector = await embed_query("What restaurants are near La Fontaine?")
        steps["embedding"] = {
            "dimensions": len(vector),
            "configured_dimensions": settings.embedding_dimensions,
            "match": len(vector) == settings.embedding_dimensions,
        }
    except Exception as exc:
        steps["embedding_error"] = f"{type(exc).__name__}: {exc}"
        steps["embedding_traceback"] = traceback.format_exc()
        return JSONResponse(content=steps, status_code=500)

    # Step 4: Search Qdrant
    try:
        results = await qdrant.search(
            collection_name=settings.qdrant_collection,
            query_vector=list(vector),
            limit=3,
        )
        steps["search_results"] = [
            {
                "score": r.score,
                "source_file": (r.payload or {}).get("source_file", ""),
                "text_preview": (r.payload or {}).get("text", "")[:200],
            }
            for r in results
        ]
    except Exception as exc:
        steps["search_error"] = f"{type(exc).__name__}: {exc}"
        steps["search_traceback"] = traceback.format_exc()
        return JSONResponse(content=steps, status_code=500)

    steps["status"] = "all_ok"
    return JSONResponse(content=steps)
