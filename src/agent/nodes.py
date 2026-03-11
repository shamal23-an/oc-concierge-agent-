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
from src.observability.metrics import get_metrics
from src.retrieval.embedder import embed_query_hybrid
from src.retrieval.query_rewriter import expand_query
from src.retrieval.ranker import rerank_chunks
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
    # Preserve session active_property if context resolution didn't find a specific one
    if ctx.property_id:
        state["active_property"] = str(ctx.property_id)
    elif session.active_property:
        # Always preserve session property for continuity (any scope)
        state["active_property"] = session.active_property
    else:
        state["active_property"] = None
    logger.debug(
        "resolve_context_result",
        scope=str(ctx.scope),
        ctx_property=str(ctx.property_id) if ctx.property_id else None,
        session_property=session.active_property,
        active_property=state["active_property"],
        history_len=len(session.conversation_history),
    )
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
    # Expand query with synonyms for better embedding recall
    property_name = None
    if active_pid:
        _info = PROPERTY_REGISTRY.get(PropertyID(active_pid))
        if _info:
            property_name = _info.name
    expanded = expand_query(message, property_name=property_name)

    dense_vector, sparse_vector = await embed_query_hybrid(expanded)
    vector = list(dense_vector)

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
        sparse_vector=sparse_vector,
    )

    # Re-rank with Jina (falls back to local ranker if unconfigured)
    import time as _time

    _t0 = _time.perf_counter()
    ranked = await rerank_chunks(message, chunks)
    _rerank_ms = (_time.perf_counter() - _t0) * 1000

    metrics = get_metrics()
    metrics.rerank_latency.record(_rerank_ms)
    if ranked:
        metrics.record_retrieval_result(ranked[0]["score"], len(ranked))

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
    is_sparse = scope == "property" and active_pid is not None and len(chunks) < _MIN_CHUNKS_SPARSE

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

    # Inject booking progress if we have details
    session = state.get("_session")  # type: ignore[typeddict-item]
    booking_progress = ""
    if session and session.booking_details and _has_booking_intent(state["message"]):
        booking = session.booking_details
        parts = []
        if booking.get("property"):
            parts.append(f"Property: {booking['property']}")
        if booking.get("check_in"):
            parts.append(f"Check-in: {booking['check_in']}")
        if booking.get("check_out"):
            parts.append(f"Check-out: {booking['check_out']}")
        if booking.get("guests"):
            parts.append(f"Guests: {booking['guests']}")
        if booking.get("nights"):
            parts.append(f"Nights: {booking['nights']}")
        if booking.get("room"):
            parts.append(f"Room: {booking['room']}")
        if parts:
            booking_progress = (
                "\n\n## Current Booking Progress\n"
                "The guest has already provided:\n"
                + "\n".join(f"- {p}" for p in parts)
                + "\nOnly ask for details that are MISSING. Do NOT re-ask for these."
            )

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

    if booking_progress:
        system_message += booking_progress

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

    # Record metrics
    metrics = get_metrics()
    metrics.record_query(scope)

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


def _extract_booking_details(message: str, existing: dict | None = None) -> dict | None:
    """Extract booking-related details from user message.

    Merges with existing booking details (doesn't overwrite with None).
    """
    details = dict(existing) if existing else {}
    lower = message.lower()

    # Date patterns (e.g., "15 March", "March 15", "2026-03-15", "15/03/2026")
    date_patterns = [
        r"\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s*(\d{4})?\b",
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+(\d{1,2})\s*,?\s*(\d{4})?\b",
        r"\b(\d{4}[-/]\d{1,2}[-/]\d{1,2})\b",
        r"\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b",
    ]
    dates_found = []
    for pattern in date_patterns:
        matches = re.findall(pattern, lower)
        if matches:
            dates_found.extend(matches)

    if dates_found:
        # Store raw date strings for the LLM to interpret
        date_strs = [" ".join(m) if isinstance(m, tuple) else m for m in dates_found]
        if len(date_strs) >= 2:
            details["check_in"] = date_strs[0].strip()
            details["check_out"] = date_strs[1].strip()
        elif "check_in" not in details:
            details["check_in"] = date_strs[0].strip()

    # Guest count
    guest_match = re.search(r"\b(\d+)\s*(?:guest|person|people|adult|pax)\w*\b", lower)
    if guest_match:
        details["guests"] = int(guest_match.group(1))

    # Night count
    night_match = re.search(r"\b(\d+)\s*(?:night|nite)s?\b", lower)
    if night_match:
        details["nights"] = int(night_match.group(1))

    return details if details else None


async def _save_session(state: AgentState) -> None:
    """Save session to Redis (extracted to avoid duplication)."""
    session = state.get("_session")  # type: ignore[typeddict-item]
    redis_client = state.get("_redis")  # type: ignore[typeddict-item]
    if session and redis_client:
        session.active_property = state.get("active_property")
        # Save region for session continuity
        if state.get("resolved_region"):
            session.active_region = state["resolved_region"]
        # Extract and save booking details from user message
        booking = _extract_booking_details(state["message"], session.booking_details)
        if booking:
            session.booking_details = booking
        session.add_message("user", state["message"])
        session.add_message("assistant", state["response"])
        await save_session(redis_client, session)
