from __future__ import annotations

import logging
import re

import structlog
from langchain_openai import ChatOpenAI
from openai import APIConnectionError, APITimeoutError, RateLimitError
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.agent.context_resolver import resolve_context
from src.agent.prompts import (
    SYSTEM_PROMPT,
    build_property_list,
    build_scope_instructions,
    format_context,
    format_history,
)
from src.agent.session import load_session, save_session
from src.cache.response_cache import (
    get_cached_response,
    get_cached_retrieval,
    set_cached_response,
    set_cached_retrieval,
)
from src.config.constants import BOOKING_PATTERNS, GREETING_PATTERNS, OUT_OF_SCOPE_PATTERNS
from src.config.settings import get_settings
from src.domain.properties import PROPERTY_REGISTRY, PropertyID
from src.domain.schemas import AgentState, QueryScope
from src.retrieval.embedder import embed_query
from src.retrieval.ranker import rank_chunks
from src.retrieval.strategies import layered_retrieve

# Retry on transient OpenAI errors only (timeout, connection, rate limit).
_TRANSIENT_LLM_ERRORS = (APITimeoutError, APIConnectionError, RateLimitError)

logger = structlog.get_logger()

# ── LLM singleton ────────────────────────────────────────────────────────── #
_llm: ChatOpenAI | None = None


def _get_llm() -> ChatOpenAI:
    """Return a cached ChatOpenAI instance (created once, reused)."""
    global _llm
    if _llm is None:
        settings = get_settings()
        _llm = ChatOpenAI(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            api_key=settings.openai_api_key,
            request_timeout=settings.openai_timeout,
        )
    return _llm


# ── Input sanitization ────────────────────────────────────────────────────── #
_INJECTION_PATTERNS = re.compile(
    r"(?i)"
    r"(ignore\s+(all\s+)?previous\s+instructions|"
    r"you\s+are\s+now\s+a|"
    r"system\s*:\s*|"
    r"<\|.*?\|>|"  # special tokens
    r"\[INST\]|"  # Llama-style injection
    r"```system)",
)


def _sanitize_input(message: str) -> str:
    """Strip known prompt injection patterns from user input.

    Returns the cleaned message. Does NOT block the request — the LLM prompt
    already constrains the model to Oyster Collection topics.
    """
    cleaned = _INJECTION_PATTERNS.sub("", message).strip()
    # Truncate excessively long messages (prevent token-stuffing)
    if len(cleaned) > 2000:
        cleaned = cleaned[:2000]
    return cleaned or message[:2000]


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
        "hi there",
        "hello there",
        "hey there",
        "good day",
    }


def _is_out_of_scope(message: str) -> bool:
    """Fast-path out-of-scope detection."""
    lower = message.lower()
    return any(p in lower for p in OUT_OF_SCOPE_PATTERNS)


def _has_booking_intent(message: str) -> bool:
    """Detect booking/reservation intent in a message."""
    lower = message.lower()
    return any(p in lower for p in BOOKING_PATTERNS)


# Threshold: if a property has fewer chunks than this, use sparse scope
_MIN_CHUNKS_SPARSE = 2


def _has_conversation_history(state: AgentState) -> bool:
    """Check if the session has prior conversation turns."""
    history = state.get("conversation_history", [])
    return len(history) > 0


@retry(
    retry=retry_if_exception_type(_TRANSIENT_LLM_ERRORS),
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=2, min=2, max=8),
    before_sleep=before_sleep_log(logging.getLogger("tenacity.llm"), logging.WARNING),
    reraise=True,
)
async def _invoke_llm(llm: ChatOpenAI, messages: list[dict]) -> str:
    """Call the LLM with retry on transient errors."""
    response = await llm.ainvoke(messages)
    return response.content


async def resolve_node(
    state: AgentState,
    *,
    redis_client: Redis,
) -> AgentState:
    """Node 1: Resolve context — session, entities, scope."""
    message = _sanitize_input(state["message"])
    state["message"] = message
    session_id = state.get("session_id", "")
    request_pid = state.get("property_id")

    # Load session (async Redis call)
    session = await load_session(redis_client, session_id or None)
    state["session_id"] = session.session_id

    # Fast-path: greeting
    if _is_greeting(message):
        state["response"] = GREETING_RESPONSES[0]
        state["scope"] = QueryScope.GROUP
        state["sources"] = []
        session.add_message("user", message)
        session.add_message("assistant", state["response"])
        await save_session(redis_client, session)
        return state

    # Fast-path: out of scope
    if _is_out_of_scope(message):
        state["response"] = OUT_OF_SCOPE_RESPONSE
        state["scope"] = QueryScope.GROUP
        state["sources"] = []
        session.add_message("user", message)
        session.add_message("assistant", state["response"])
        await save_session(redis_client, session)
        return state

    # Resolve context (pure Python — no I/O, stays sync)
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


async def retrieve_node(
    state: AgentState,
    *,
    qdrant_client: AsyncQdrantClient,
    redis_client: Redis,
) -> AgentState:
    """Node 2: Retrieve relevant chunks from Qdrant.

    Checks the retrieval cache first (async Redis). Only caches queries
    without conversation history — follow-up questions depend on
    context and aren't safe to cache.
    """
    # Skip if already answered (greeting/out-of-scope)
    if state.get("response"):
        return state

    message = state["message"]
    scope = QueryScope(state["scope"])
    active_pid = state.get("active_property")
    can_cache = not _has_conversation_history(state)

    # ── Cache check (async) ──────────────────────────────────────────── #
    if can_cache:
        cached = await get_cached_retrieval(redis_client, message, active_pid, scope)
        if cached is not None:
            logger.info("retrieval_cache_hit", message=message[:60])
            state["chunks"] = cached
            state["cache_hit"] = True
            return state

    # ── Normal retrieval (async) ─────────────────────────────────────── #
    vector = list(await embed_query(message))

    property_id = None
    property_ids = None
    region = None

    if active_pid:
        try:
            property_id = PropertyID(active_pid)
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

    chunks = await layered_retrieve(
        qdrant_client,
        vector,
        scope=scope,
        property_id=property_id,
        property_ids=property_ids,
        region=region,
    )

    target_pid = str(property_id) if property_id else None
    ranked = rank_chunks(chunks, target_property_id=target_pid, query=message)

    state["chunks"] = ranked

    # ── Cache store (async) ──────────────────────────────────────────── #
    if can_cache:
        await set_cached_retrieval(
            redis_client,
            message,
            active_pid,
            scope,
            chunks=ranked,
        )

    return state


async def generate_node(state: AgentState) -> AgentState:
    """Node 3: Generate response using LLM (single async call).

    Checks the response cache first (async Redis). On miss, calls the
    LLM and stores the result. Only caches when there is no prior
    conversation history.
    """
    # Skip if already answered
    if state.get("response"):
        return state

    message = state["message"]
    active_pid = state.get("active_property")
    scope = state.get("scope", "group")
    can_cache = not _has_conversation_history(state)

    # ── Response cache check (async) ─────────────────────────────────── #
    if can_cache:
        cached = await get_cached_response(
            state.get("_redis"),  # type: ignore[arg-type]
            message,
            active_pid,
            scope,
        )
        if cached is not None:
            logger.info("response_cache_hit", message=message[:60])
            state["response"] = cached["response"]
            state["sources"] = cached["sources"]
            state["cache_hit"] = True
            await _save_session(state)
            return state

    # ── Normal LLM generation (async) ────────────────────────────────── #
    import datetime as dt

    llm = _get_llm()

    property_name = None
    location = None
    region_name = None
    property_names_str = None
    email = None
    phone = None

    if active_pid:
        info = PROPERTY_REGISTRY.get(PropertyID(active_pid))
        if info:
            property_name = info.full_name
            location = info.location
            email = info.email
            phone = info.phone

    if state.get("resolved_region"):
        region_name = state["resolved_region"].replace("_", " ").title()

    if state.get("resolved_properties") and len(state["resolved_properties"]) > 1:
        names = []
        for pid_str in state["resolved_properties"]:
            info = PROPERTY_REGISTRY.get(PropertyID(pid_str))
            if info:
                names.append(info.name)
        property_names_str = ", ".join(names)

    # Detect sparse property (few retrieved chunks)
    chunks = state.get("chunks", [])
    is_sparse = (
        scope == "property"
        and active_pid is not None
        and len(chunks) < _MIN_CHUNKS_SPARSE
    )

    scope_instructions = build_scope_instructions(
        scope,
        property_name=property_name,
        location=location,
        region=region_name,
        property_names=property_names_str,
        email=email,
        phone=phone,
        is_sparse=is_sparse,
    )

    context_str = format_context(chunks)
    history_str = format_history(state.get("conversation_history", []))

    # Inject current date and dynamic property list
    now = dt.datetime.now(tz=dt.UTC)
    today_str = now.strftime("Today is %A, %d %B %Y.")

    system_message = SYSTEM_PROMPT.format(
        today=today_str,
        property_list=build_property_list(),
        scope_instructions=scope_instructions,
        context=context_str,
        history=history_str,
    )

    # LLM call with retry on transient errors
    state["response"] = await _invoke_llm(
        llm,
        [
            {"role": "system", "content": system_message},
            {"role": "user", "content": state["message"]},
        ],
    )

    sources = list({c["source_file"] for c in chunks if c.get("source_file")})
    state["sources"] = sources

    # ── Response cache store (async) ─────────────────────────────────── #
    redis_client = state.get("_redis")  # type: ignore[typeddict-item]
    if can_cache and redis_client:
        await set_cached_response(
            redis_client,
            message,
            active_pid,
            scope,
            response=state["response"],
            sources=sources,
        )

    await _save_session(state)
    return state


async def _save_session(state: AgentState) -> None:
    """Save session to Redis (extracted to avoid duplication)."""
    session = state.get("_session")  # type: ignore[typeddict-item]
    redis_client = state.get("_redis")  # type: ignore[typeddict-item]
    if session and redis_client:
        session.active_property = state.get("active_property")
        session.add_message("user", state["message"])
        session.add_message("assistant", state["response"])
        await save_session(redis_client, session)
