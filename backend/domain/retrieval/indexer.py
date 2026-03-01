import numpy as np
from sentence_transformers import SentenceTransformer

from infrastructure.vector_store.faiss_store import FAISSStore
from shared.constants import EMBEDDING_MODEL_NAME
from shared.logger import get_logger
from shared.utils.time_utils import timer

logger = get_logger(__name__)

# Lazy-loaded singleton — avoids loading model until first use
_encoder: SentenceTransformer | None = None


def _get_encoder() -> SentenceTransformer:
    """Load the embedding model lazily (first call only)."""
    global _encoder
    if _encoder is None:
        with timer("Load embedding model"):
            _encoder = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _encoder


def encode_texts(texts: list[str], batch_size: int = 64) -> np.ndarray:
    """
    Encode a list of texts into normalised embedding vectors.
    Returns shape ``(n, EMBEDDING_DIMENSIONS)`` with L2-normalised rows.
    """
    encoder = _get_encoder()
    with timer(f"Encode {len(texts)} texts"):
        embeddings: np.ndarray = encoder.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,  # cosine similarity via dot product
        )
    return embeddings.astype(np.float32)


def encode_query(text: str) -> np.ndarray:
    """Encode a single query string. Returns shape ``(1, EMBEDDING_DIMENSIONS)``."""
    encoder = _get_encoder()
    vec: np.ndarray = encoder.encode(
        [text],
        normalize_embeddings=True,
    )
    return vec.astype(np.float32)


async def index_chunks(
    chunks: list,
    paper_id: str,
    faiss_store: FAISSStore,
) -> int:
    """
    Embed enriched texts of all chunks and insert into the FAISS store.
    Returns the number of vectors added.
    """
    if not chunks:
        return 0

    texts = [c.enriched_text for c in chunks]
    ids = [f"{paper_id}::{c.paragraph_id}" for c in chunks]

    vectors = encode_texts(texts)
    faiss_store.add_vectors(vectors, ids)
    faiss_store.save()

    logger.info(f"Indexed {len(chunks)} chunks for paper {paper_id}")
    return len(chunks)
