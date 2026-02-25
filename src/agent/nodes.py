from __future__ import annotations

import structlog
from langchain_openai import ChatOpenAI
from qdrant_client import QdrantClient
from redis import Redis

from src.agent.context_resolver import resolve_context
from src.agent.prompts import (
    SYSTEM_PROMPT,
    build_scope_instructions,
    format_context,
    format_history,
)
from src.agent.session import load_session, save_session
from src.config.constants import GREETING_PATTERNS, OUT_OF_SCOPE_PATTERNS
from src.config.settings import get_settings
from src.domain.properties import PROPERTY_REGISTRY, PropertyID
from src.domain.schemas import AgentState, QueryScope
from src.retrieval.embedder import embed_query
from src.retrieval.ranker import rank_chunks
from src.retrieval.strategies import layered_retrieve

logger = structlog.get_logger()

# Greeting responses (no LLM needed)
GREETING_RESPONSES = [
    "Hello! Welcome to The Oyster Collection. I'm your AI concierge — I can help you "
    "with information about our 12 boutique properties across South Africa. Whether "
    "you're looking for restaurant recommendations, activities, rates, or directions, "
    "I'm here to help. What would you like to know?",
]

OUT_OF_SCOPE_RESPONSE = (
    "I appreciate your question, but I'm specifically designed to help with information "
    "about The Oyster Collection's properties, restaurants, activities, and travel in "
    "South Africa. Is there anything about our properties I can help you with?"
)


def _is_greeting(message: str) -> bool:
    """Fast-path greeting detection (no LLM needed)."""
    cleaned = message.lower().strip().rstrip("!?.,:;")
    return cleaned in GREETING_PATTERNS or cleaned in {
        "hi there", "hello there", "hey there", "good day",
    }


def _is_out_of_scope(message: str) -> bool:
    """Fast-path out-of-scope detection."""
    lower = message.lower()
    return any(p in lower for p in OUT_OF_SCOPE_PATTERNS)


def resolve_node(
    state: AgentState,
    *,
    redis_client: Redis,
) -> AgentState:
    """Node 1: Resolve context — session, entities, scope."""
    message = state["message"]
    session_id = state.get("session_id", "")
    request_pid = state.get("property_id")

    # Load session
    session = load_session(redis_client, session_id or None)
    state["session_id"] = session.session_id

    # Fast-path: greeting
    if _is_greeting(message):
        state["response"] = GREETING_RESPONSES[0]
        state["scope"] = QueryScope.GROUP
        state["sources"] = []
        session.add_message("user", message)
        session.add_message("assistant", state["response"])
        save_session(redis_client, session)
        return state

    # Fast-path: out of scope
    if _is_out_of_scope(message):
        state["response"] = OUT_OF_SCOPE_RESPONSE
        state["scope"] = QueryScope.GROUP
        state["sources"] = []
        session.add_message("user", message)
        session.add_message("assistant", state["response"])
        save_session(redis_client, session)
        return state

    # Resolve context
    pid = PropertyID(request_pid) if request_pid else None
    ctx = resolve_context(message, request_property_id=pid, session=session)

    state["scope"] = ctx.scope
    state["resolved_properties"] = [str(p) for p in ctx.property_ids]
    state["resolved_region"] = str(ctx.region) if ctx.region else None
    state["active_property"] = str(ctx.property_id) if ctx.property_id else None
    state["conversation_history"] = session.conversation_history

    # Store session ref for later save
    state["_session"] = session  # type: ignore[typeddict-unknown-key]
    state["_redis"] = redis_client  # type: ignore[typeddict-unknown-key]

    return state


def retrieve_node(
    state: AgentState,
    *,
    qdrant_client: QdrantClient,
) -> AgentState:
    """Node 2: Retrieve relevant chunks from Qdrant."""
    # Skip if already answered (greeting/out-of-scope)
    if state.get("response"):
        return state

    message = state["message"]
    scope = QueryScope(state["scope"])

    # Embed query
    vector = list(embed_query(message))

    # Determine retrieval params
    property_id = None
    property_ids = None
    region = None

    if state.get("active_property"):
        try:
            property_id = PropertyID(state["active_property"])
        except ValueError:
            pass

    if state.get("resolved_properties"):
        property_ids = [PropertyID(p) for p in state["resolved_properties"]]

    if state.get("resolved_region"):
        from src.domain.properties import Region

        try:
            region = Region(state["resolved_region"])
        except ValueError:
            pass

    # Retrieve
    chunks = layered_retrieve(
        qdrant_client,
        vector,
        scope=scope,
        property_id=property_id,
        property_ids=property_ids,
        region=region,
    )

    # Rank
    target_pid = str(property_id) if property_id else None
    ranked = rank_chunks(chunks, target_property_id=target_pid)

    state["chunks"] = ranked
    return state


def generate_node(state: AgentState) -> AgentState:
    """Node 3: Generate response using LLM (single call)."""
    # Skip if already answered
    if state.get("response"):
        return state

    settings = get_settings()
    llm = ChatOpenAI(
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        api_key=settings.openai_api_key,
    )

    # Build scope instructions
    scope = state.get("scope", "group")
    property_name = None
    location = None
    region_name = None
    property_names_str = None

    if state.get("active_property"):
        info = PROPERTY_REGISTRY.get(PropertyID(state["active_property"]))
        if info:
            property_name = info.full_name
            location = info.location

    if state.get("resolved_region"):
        region_name = state["resolved_region"].replace("_", " ").title()

    if state.get("resolved_properties") and len(state["resolved_properties"]) > 1:
        names = []
        for pid_str in state["resolved_properties"]:
            info = PROPERTY_REGISTRY.get(PropertyID(pid_str))
            if info:
                names.append(info.name)
        property_names_str = ", ".join(names)

    scope_instructions = build_scope_instructions(
        scope,
        property_name=property_name,
        location=location,
        region=region_name,
        property_names=property_names_str,
    )

    # Format context and history
    chunks = state.get("chunks", [])
    context_str = format_context(chunks)
    history_str = format_history(state.get("conversation_history", []))

    system_message = SYSTEM_PROMPT.format(
        scope_instructions=scope_instructions,
        context=context_str,
        history=history_str,
    )

    # Single LLM call
    response = llm.invoke([
        {"role": "system", "content": system_message},
        {"role": "user", "content": state["message"]},
    ])

    state["response"] = response.content

    # Extract sources from chunks
    sources = list({c["source_file"] for c in chunks if c.get("source_file")})
    state["sources"] = sources

    # Save session
    session = state.get("_session")  # type: ignore[typeddict-item]
    redis_client = state.get("_redis")  # type: ignore[typeddict-item]
    if session and redis_client:
        session.active_property = state.get("active_property")
        session.add_message("user", state["message"])
        session.add_message("assistant", state["response"])
        save_session(redis_client, session)

    return state
