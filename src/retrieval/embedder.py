from __future__ import annotations

from functools import lru_cache

from openai import OpenAI

from src.config.constants import EMBEDDING_CACHE_MAX_SIZE
from src.config.settings import get_settings


def _get_openai_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(api_key=settings.openai_api_key)


@lru_cache(maxsize=EMBEDDING_CACHE_MAX_SIZE)
def embed_query(text: str) -> tuple[float, ...]:
    """Embed a single query string with LRU caching.

    Returns tuple (hashable) for caching. Convert to list if needed.
    """
    settings = get_settings()
    client = _get_openai_client()
    response = client.embeddings.create(
        input=[text],
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
    return tuple(response.data[0].embedding)
