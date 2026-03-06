"""Pipeline trace script — shows the full RAG flow for any query.

Usage:
    uv run python scripts/trace_query.py "What are the rates at Avondrood?"
    uv run python scripts/trace_query.py "What activities can I do at Camp Figtree?"
    uv run python scripts/trace_query.py  # runs all demo queries

Outputs a visual stage-by-stage breakdown of the entire pipeline:
  1. Input & Sanitization
  2. Entity Extraction
  3. Context Resolution (scope, property, region)
  4. Embedding (dense + sparse)
  5. Vector Retrieval (Qdrant hybrid search)
  6. Re-ranking (Jina cross-encoder)
  7. Prompt Construction (system prompt sent to LLM)
  8. LLM Response
"""

from __future__ import annotations

import asyncio
import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── Helpers ─────────────────────────────────────────────────────────────── #

DIVIDER = "=" * 90
SUBDIV = "-" * 70
INDENT = "  "


def banner(title: str, step: int) -> None:
    print(f"\n{DIVIDER}")
    print(f"  STEP {step}: {title}")
    print(DIVIDER)


def kv(key: str, value: object, indent: int = 1) -> None:
    prefix = INDENT * indent
    val_str = str(value)
    if len(val_str) > 120:
        val_str = val_str[:120] + "..."
    print(f"{prefix}{key}: {val_str}")


def text_block(label: str, text: str, max_lines: int = 15) -> None:
    print(f"\n{INDENT}{label}:")
    lines = text.split("\n")
    for line in lines[:max_lines]:
        print(f"{INDENT}{INDENT}{line}")
    if len(lines) > max_lines:
        print(f"{INDENT}{INDENT}... ({len(lines) - max_lines} more lines)")


def chunk_table(chunks: list[dict], label: str = "Chunks") -> None:
    if not chunks:
        print(f"\n{INDENT}{label}: (none)")
        return
    print(f"\n{INDENT}{label} ({len(chunks)} total):")
    print(f"{INDENT}{SUBDIV}")
    print(f"{INDENT}{'#':>3}  {'Score':>7}  {'Property':20}  {'Source':30}  Content Preview")
    print(f"{INDENT}{SUBDIV}")
    for i, c in enumerate(chunks, 1):
        score = f"{c['score']:.3f}"
        pids = ", ".join(c.get("property_ids", []))[:20]
        source = (c.get("source_file") or "?")[:30]
        content = c.get("content", "")[:60].replace("\n", " ")
        section = c.get("metadata", {}).get("section_title", "")
        page = c.get("metadata", {}).get("page_number", "")
        meta = ""
        if section:
            meta += f" [S:{section[:20]}]"
        if page:
            meta += f" [P:{page}]"
        print(f"{INDENT}{i:>3}  {score:>7}  {pids:20}  {source:30}  {content}{meta}")
    print(f"{INDENT}{SUBDIV}")


# ── Main trace ──────────────────────────────────────────────────────────── #


async def trace_query(query: str) -> None:
    """Run one query through the full pipeline with detailed tracing."""
    # Late imports so .env is loaded first
    from dotenv import load_dotenv

    load_dotenv()

    from src.agent.context_resolver import resolve_context
    from src.agent.nodes import (
        GREETING_RESPONSES,
        OUT_OF_SCOPE_RESPONSE,
        _get_llm,
        _has_booking_intent,
        _invoke_llm,
        _is_greeting,
        _is_out_of_scope,
        _sanitize_input,
    )
    from src.agent.prompts import (
        SYSTEM_PROMPT,
        build_property_list,
        build_scope_instructions,
        format_context,
        format_history,
    )
    from src.config.settings import get_settings
    from src.domain.entities import extract_entities
    from src.domain.properties import PROPERTY_REGISTRY
    from src.retrieval.embedder import embed_query_hybrid
    from src.retrieval.ranker import rerank_chunks
    from src.retrieval.strategies import layered_retrieve

    settings = get_settings()

    total_start = time.perf_counter()

    print(f"\n{'#' * 90}")
    print(f"#  PIPELINE TRACE: {query!r}")
    print(f"{'#' * 90}")

    # ── STEP 1: Input & Sanitization ─────────────────────────────────── #
    banner("INPUT & SANITIZATION", 1)
    kv("Raw query", query)
    sanitized = _sanitize_input(query)
    kv("Sanitized", sanitized)
    kv("Changed?", sanitized != query)
    kv("Is greeting?", _is_greeting(sanitized))
    kv("Is out-of-scope?", _is_out_of_scope(sanitized))
    kv("Has booking intent?", _has_booking_intent(sanitized))

    if _is_greeting(sanitized):
        print(f"\n{INDENT}>>> FAST PATH: Greeting detected — skipping retrieval & LLM")
        print(f"\n{INDENT}Response: {GREETING_RESPONSES[0][:200]}")
        print(f"\n{DIVIDER}\nTotal time: {time.perf_counter() - total_start:.2f}s")
        return

    if _is_out_of_scope(sanitized):
        print(f"\n{INDENT}>>> FAST PATH: Out-of-scope detected — skipping retrieval & LLM")
        print(f"\n{INDENT}Response: {OUT_OF_SCOPE_RESPONSE[:200]}")
        print(f"\n{DIVIDER}\nTotal time: {time.perf_counter() - total_start:.2f}s")
        return

    # ── STEP 2: Entity Extraction ────────────────────────────────────── #
    banner("ENTITY EXTRACTION", 2)
    entities = extract_entities(sanitized)
    kv("Properties found", [str(p) for p in entities.properties])
    kv("Regions found", [str(r) for r in entities.regions])
    kv("Is comparison?", entities.is_comparison)
    kv("Is multi-property?", entities.is_multi_property)

    # ── STEP 3: Context Resolution ───────────────────────────────────── #
    banner("CONTEXT RESOLUTION", 3)
    ctx = resolve_context(sanitized)
    kv("Scope", ctx.scope)
    kv("Property ID", ctx.property_id)
    kv("Property IDs", [str(p) for p in ctx.property_ids])
    kv("Region", ctx.region)

    property_name = None
    location = None
    email = None
    phone = None
    if ctx.property_id:
        info = PROPERTY_REGISTRY.get(ctx.property_id)
        if info:
            property_name = info.full_name
            location = info.location
            email = info.email
            phone = info.phone
            kv("Property name", property_name)
            kv("Location", location)
            kv("Contact", f"{email} | {phone}")

    # ── STEP 4: Embedding ────────────────────────────────────────────── #
    banner("EMBEDDING (Dense + Sparse)", 4)
    t0 = time.perf_counter()
    dense_vector, sparse_vector = await embed_query_hybrid(sanitized)
    embed_time = time.perf_counter() - t0
    kv("Dense vector dims", len(dense_vector))
    kv("Dense vector sample", list(dense_vector[:5]))
    kv("Sparse vector indices", len(sparse_vector.indices))
    kv(
        "Sparse vector sample (idx:val)",
        [
            f"{idx}:{val:.3f}"
            for idx, val in zip(sparse_vector.indices[:8], sparse_vector.values[:8])
        ],
    )
    kv("Embedding time", f"{embed_time:.2f}s")
    kv("Model", settings.embedding_model)

    # ── STEP 5: Vector Retrieval ─────────────────────────────────────── #
    banner("VECTOR RETRIEVAL (Qdrant Hybrid Search)", 5)
    from qdrant_client import AsyncQdrantClient

    if settings.qdrant_url:
        qdrant = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
            timeout=settings.qdrant_timeout,
        )
    else:
        qdrant = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            timeout=settings.qdrant_timeout,
        )

    kv("Collection", settings.qdrant_collection)
    kv("Top K", settings.top_k)
    kv("Scope", ctx.scope)

    property_id = ctx.property_id
    property_ids = ctx.property_ids or None
    region = ctx.region

    t0 = time.perf_counter()
    raw_chunks = await layered_retrieve(
        qdrant,
        list(dense_vector),
        scope=ctx.scope,
        property_id=property_id,
        property_ids=property_ids,
        region=region,
        sparse_vector=sparse_vector,
    )
    retrieval_time = time.perf_counter() - t0

    kv("Retrieval time", f"{retrieval_time:.2f}s")
    kv("Chunks retrieved", len(raw_chunks))
    chunk_table(raw_chunks, "Raw Retrieved Chunks (before reranking)")

    # ── STEP 6: Re-ranking ───────────────────────────────────────────── #
    banner("RE-RANKING (Jina Cross-Encoder)", 6)
    kv("Jina enabled", bool(settings.jina_api_key))
    kv("Jina model", settings.jina_rerank_model)
    kv("Min score threshold", settings.rerank_min_score)

    t0 = time.perf_counter()
    ranked_chunks = await rerank_chunks(sanitized, raw_chunks)
    rerank_time = time.perf_counter() - t0

    kv("Rerank time", f"{rerank_time:.2f}s")
    kv("Chunks after reranking", len(ranked_chunks))
    kv("Chunks filtered out", len(raw_chunks) - len(ranked_chunks))
    chunk_table(ranked_chunks, "Re-ranked Chunks (sent to LLM)")

    # ── STEP 7: Prompt Construction ──────────────────────────────────── #
    banner("PROMPT CONSTRUCTION", 7)

    scope_str = str(ctx.scope)
    region_name = str(ctx.region).replace("_", " ").title() if ctx.region else None

    property_names_str = None
    if ctx.property_ids and len(ctx.property_ids) > 1:
        names = []
        for pid in ctx.property_ids:
            info = PROPERTY_REGISTRY.get(pid)
            if info:
                names.append(info.name)
        property_names_str = ", ".join(names)

    is_sparse = scope_str == "property" and ctx.property_id is not None and len(ranked_chunks) < 2

    scope_instructions = build_scope_instructions(
        scope_str,
        property_name=property_name,
        location=location,
        region=region_name,
        property_names=property_names_str,
        email=email,
        phone=phone,
        is_sparse=is_sparse,
    )

    context_str = format_context(ranked_chunks)
    history_str = format_history([])

    now = dt.datetime.now(tz=dt.UTC)
    today_str = now.strftime("Today is %A, %d %B %Y.")

    system_message = SYSTEM_PROMPT.format(
        today=today_str,
        property_list=build_property_list(),
        scope_instructions=scope_instructions,
        context=context_str,
        history=history_str,
    )

    kv("Scope instructions type", "SPARSE" if is_sparse else scope_str.upper())
    kv("System prompt length", f"{len(system_message)} chars")
    kv("Context length", f"{len(context_str)} chars")
    kv("LLM model", settings.llm_model)
    kv("Temperature", settings.llm_temperature)

    text_block("Scope Instructions", scope_instructions, max_lines=8)
    text_block("Context (sent to LLM)", context_str, max_lines=25)

    # Print full system prompt (collapsed)
    print(f"\n{INDENT}Full System Prompt ({len(system_message)} chars):")
    print(f"{INDENT}{SUBDIV}")
    for line in system_message.split("\n")[:40]:
        print(f"{INDENT}{INDENT}{line}")
    if system_message.count("\n") > 40:
        print(f"{INDENT}{INDENT}... ({system_message.count(chr(10)) - 40} more lines)")
    print(f"{INDENT}{SUBDIV}")

    # ── STEP 8: LLM Generation ───────────────────────────────────────── #
    banner("LLM GENERATION", 8)
    llm = _get_llm()

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": sanitized},
    ]

    kv("Messages", f"system ({len(system_message)} chars) + user ({len(sanitized)} chars)")

    t0 = time.perf_counter()
    response = await _invoke_llm(llm, messages)
    llm_time = time.perf_counter() - t0

    sources = list({c["source_file"] for c in ranked_chunks if c.get("source_file")})

    kv("LLM time", f"{llm_time:.2f}s")
    kv("Response length", f"{len(response)} chars")
    kv("Sources cited", sources)

    text_block("FINAL RESPONSE", response, max_lines=30)

    # ── SUMMARY ──────────────────────────────────────────────────────── #
    total_time = time.perf_counter() - total_start

    print(f"\n{'=' * 90}")
    print("  PIPELINE SUMMARY")
    print(f"{'=' * 90}")
    kv("Query", query)
    kv("Scope", f"{ctx.scope} -> {property_name or region_name or 'group'}")
    kv("Embedding", f"{embed_time:.2f}s")
    kv("Retrieval", f"{retrieval_time:.2f}s ({len(raw_chunks)} chunks)")
    kv("Reranking", f"{rerank_time:.2f}s ({len(raw_chunks)} -> {len(ranked_chunks)} chunks)")
    kv("LLM", f"{llm_time:.2f}s ({len(response)} chars)")
    kv("Total", f"{total_time:.2f}s")
    kv("Sources", sources)

    latency_budget = (
        f"Embed:{embed_time:.1f}s + Retrieve:{retrieval_time:.1f}s + "
        f"Rerank:{rerank_time:.1f}s + LLM:{llm_time:.1f}s = {total_time:.1f}s"
    )
    kv("Latency breakdown", latency_budget)

    # Quality signals
    print(f"\n{INDENT}Quality Signals:")
    if not ranked_chunks:
        kv("WARNING", "No chunks after reranking — LLM has no context!", indent=2)
    elif ranked_chunks[0]["score"] < 0.3:
        score = ranked_chunks[0]["score"]
        kv("WARNING", f"Top chunk score {score:.3f} is low — may be irrelevant", indent=2)
    else:
        kv("OK", f"Top chunk score {ranked_chunks[0]['score']:.3f}", indent=2)

    if is_sparse:
        kv("WARNING", "Sparse property — limited information available", indent=2)

    if total_time > 5:
        kv("WARNING", f"Total time {total_time:.1f}s exceeds 5s target", indent=2)

    if "I don't have that information" in response:
        kv("WARNING", "Response is a 'don't know' — check context quality", indent=2)
    elif "contact" in response.lower() and "directly" in response.lower():
        kv("NOTE", "Response includes escalation to property contact", indent=2)

    await qdrant.close()


# ── CLI ─────────────────────────────────────────────────────────────────── #

DEMO_QUERIES = [
    "What are the rates at Avondrood?",
    "What activities can I do at Camp Figtree?",
    "Tell me about Pleasance",
    "What properties do you have?",
    "hello",
]


def main() -> None:
    if len(sys.argv) > 1:
        queries = [" ".join(sys.argv[1:])]
    else:
        print("No query provided — running demo queries.\n")
        print('Usage: uv run python scripts/trace_query.py "your question here"\n')
        queries = DEMO_QUERIES

    for query in queries:
        asyncio.run(trace_query(query))
        if len(queries) > 1:
            print("\n\n")


if __name__ == "__main__":
    main()
