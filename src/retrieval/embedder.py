from __future__ import annotations

from collections import OrderedDict

from openai import AsyncOpenAI

from src.config.constants import EMBEDDING_CACHE_MAX_SIZE
from src.config.settings import get_settings

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
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def embed_query(text: str) -> tuple[float, ...]:
    """Embed a single query string with async LRU caching.

    Returns tuple (hashable, immutable). Convert to list if needed.
    """
    if text in _cache:
        _cache.move_to_end(text)  # Mark as recently used
        return _cache[text]

    settings = get_settings()
    client = _get_openai_client()
    response = await client.embeddings.create(
        input=[text],
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
    result = tuple(response.data[0].embedding)

    # Store and evict oldest if over limit
    _cache[text] = result
    if len(_cache) > EMBEDDING_CACHE_MAX_SIZE:
        _cache.popitem(last=False)

    return result
