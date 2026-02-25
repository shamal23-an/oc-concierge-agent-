from __future__ import annotations

import structlog
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config.constants import BATCH_EMBEDDING_SIZE
from src.config.settings import get_settings

logger = structlog.get_logger()


def _get_openai_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(api_key=settings.openai_api_key)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
)
def _embed_batch(
    client: OpenAI, texts: list[str], model: str, dimensions: int
) -> list[list[float]]:
    """Embed a single batch with retry."""
    response = client.embeddings.create(input=texts, model=model, dimensions=dimensions)
    return [item.embedding for item in response.data]


def embed_texts(
    texts: list[str],
    *,
    batch_size: int = BATCH_EMBEDDING_SIZE,
    client: OpenAI | None = None,
) -> list[list[float]]:
    """Embed texts in batches with retry logic.

    Returns list of embedding vectors in same order as input texts.
    """
    settings = get_settings()
    client = client or _get_openai_client()
    model = settings.embedding_model
    dimensions = settings.embedding_dimensions

    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        logger.debug("embedding_batch", batch_num=i // batch_size + 1, size=len(batch))
        embeddings = _embed_batch(client, batch, model, dimensions)
        all_embeddings.extend(embeddings)

    logger.info("embedded_texts", total=len(all_embeddings))
    return all_embeddings
