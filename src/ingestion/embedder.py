from __future__ import annotations

import re

import mmh3
import structlog
from openai import OpenAI
from qdrant_client.models import SparseVector
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config.constants import BATCH_EMBEDDING_SIZE
from src.config.settings import get_settings

logger = structlog.get_logger()

# Sparse vector config
_SPARSE_VOCAB_SIZE = 2**16  # 65536 buckets — good balance of sparsity vs collisions
_TOKENIZE_RE = re.compile(r"[a-zA-Z0-9]+")
_BM25_K1 = 1.2  # Term frequency saturation
_BM25_B = 0.0  # No document length normalization (each chunk is ~similar length)


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


def compute_sparse_vector(text: str) -> SparseVector:
    """Compute a BM25-weighted sparse vector using murmur3 hashing.

    Vocabulary-free: tokens are hashed to fixed-size buckets.
    Values use BM25 term-frequency saturation: tf / (tf + k1).
    """
    tokens = _TOKENIZE_RE.findall(text.lower())
    if not tokens:
        return SparseVector(indices=[], values=[])

    # Count term frequencies
    tf: dict[int, int] = {}
    for token in tokens:
        idx = mmh3.hash(token, signed=False) % _SPARSE_VOCAB_SIZE
        tf[idx] = tf.get(idx, 0) + 1

    # BM25-saturated weights: tf / (tf + k1)
    indices = sorted(tf.keys())
    values = [tf[i] / (tf[i] + _BM25_K1) for i in indices]

    return SparseVector(indices=indices, values=values)


def compute_sparse_vectors(texts: list[str]) -> list[SparseVector]:
    """Compute sparse vectors for a batch of texts."""
    vectors = [compute_sparse_vector(t) for t in texts]
    logger.info("computed_sparse_vectors", total=len(vectors))
    return vectors
