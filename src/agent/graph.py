from __future__ import annotations

from functools import partial

import structlog
from langgraph.graph import END, StateGraph
from qdrant_client import QdrantClient
from redis import Redis

from src.agent.nodes import generate_node, resolve_node, retrieve_node
from src.domain.schemas import AgentState

logger = structlog.get_logger()


def _should_skip_retrieval(state: AgentState) -> str:
    """Route: skip retrieval if already answered (greeting/out-of-scope)."""
    if state.get("response"):
        return "end"
    return "retrieve"


def build_graph(
    *,
    qdrant_client: QdrantClient,
    redis_client: Redis,
) -> StateGraph:
    """Build the LangGraph state machine.

    3 nodes: resolve → retrieve → generate
    Fast-path: resolve → END (for greetings/out-of-scope)
    """
    graph = StateGraph(AgentState)

    # Bind clients to node functions
    resolve_fn = partial(resolve_node, redis_client=redis_client)
    retrieve_fn = partial(
        retrieve_node, qdrant_client=qdrant_client, redis_client=redis_client,
    )

    graph.add_node("resolve", resolve_fn)
    graph.add_node("retrieve", retrieve_fn)
    graph.add_node("generate", generate_node)

    graph.set_entry_point("resolve")

    # Conditional: skip retrieval for greetings/out-of-scope
    graph.add_conditional_edges(
        "resolve",
        _should_skip_retrieval,
        {"retrieve": "retrieve", "end": END},
    )

    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)

    return graph


def create_agent(
    *,
    qdrant_client: QdrantClient,
    redis_client: Redis,
):
    """Create a compiled LangGraph agent."""
    graph = build_graph(qdrant_client=qdrant_client, redis_client=redis_client)
    return graph.compile()
