from __future__ import annotations

import logging
from collections import OrderedDict

import structlog
from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, RateLimitError
from qdrant_client.models import SparseVector
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config.constants import EMBEDDING_CACHE_MAX_SIZE
from src.config.settings import get_settings

logger = structlog.get_logger()

# ── Async-compatible LRU cache ───────────────────────────────────────────── #
# stdlib @lru_cache doesn't work with async functions (it caches the
# coroutine object, not the result). This OrderedDict gives us the same
# bounded-LRU semantics with proper async support.

_cache: OrderedDict[str, tuple[float, ...]] = OrderedDict()

_client: AsyncOpenAI | None = None


def _get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.embedding_timeout,
        )
    return _client


# Retry on transient OpenAI errors: timeout, connection, rate limit.
# Permanent errors (auth, bad request) fail immediately.
_TRANSIENT_OPENAI_ERRORS = (APITimeoutError, APIConnectionError, RateLimitError)


@retry(
    retry=retry_if_exception_type(_TRANSIENT_OPENAI_ERRORS),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    before_sleep=before_sleep_log(logging.getLogger("tenacity.embedder"), logging.WARNING),
    reraise=True,
)
async def _embed_with_retry(text: str) -> tuple[float, ...]:
    """Call OpenAI embeddings API with retry on transient errors."""
    settings = get_settings()
    client = _get_openai_client()
    response = await client.embeddings.create(
        input=[text],
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
    return tuple(response.data[0].embedding)


async def embed_query(text: str) -> tuple[float, ...]:
    """Embed a single query string with async LRU caching and retry.

    Returns tuple (hashable, immutable). Convert to list if needed.
    """
    if text in _cache:
        _cache.move_to_end(text)  # Mark as recently used
        return _cache[text]

    result = await _embed_with_retry(text)

    # Store and evict oldest if over limit
    _cache[text] = result
    if len(_cache) > EMBEDDING_CACHE_MAX_SIZE:
        _cache.popitem(last=False)

    return result


async def embed_query_hybrid(text: str) -> tuple[tuple[float, ...], SparseVector]:
    """Embed a query for hybrid search: returns (dense_vector, sparse_vector).

    Dense vector from OpenAI, sparse vector from murmur3 BM25 hashing.
    """
    from src.ingestion.embedder import compute_sparse_vector

    dense = await embed_query(text)
    sparse = compute_sparse_vector(text)
    return dense, sparse
