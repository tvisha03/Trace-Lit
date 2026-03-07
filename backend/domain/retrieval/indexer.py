import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import numpy as np
from sentence_transformers import SentenceTransformer

from infrastructure.vector_store.faiss_store import FAISSStore
from app.config import get_settings
from shared.constants import EMBEDDING_MODEL_NAME, EMBEDDING_BATCH_SIZE
from shared.logger import get_logger
from shared.utils.time_utils import timer

logger = get_logger(__name__)

_encoder: SentenceTransformer | None = None

def _mps_available() -> bool:
    try:
        import torch

        return torch.backends.mps.is_available()
    except ImportError:
        return False

def _get_encoder() -> SentenceTransformer:
    """Load the shared SentenceTransformer encoder.

    Uses MPS (Apple Silicon GPU) for embedding acceleration ONLY when
    Ollama is not active, to avoid GPU memory contention on 8GB Macs.
    """
    global _encoder
    if _encoder is None:
        with timer("Load embedding model"):
            device = "cpu"
            settings = get_settings()

            # Only use MPS if Ollama is NOT active — avoids GPU contention
            try:
                if not settings.USE_LOCAL_LLM and _mps_available():
                    device = "mps"
            except Exception as exc:
                logger.warning(f"MPS availability check failed, falling back to CPU: {exc}")

            _encoder = SentenceTransformer(EMBEDDING_MODEL_NAME)

            if device == "mps":
                try:
                    import torch
                    _encoder = _encoder.to(torch.device("mps"))
                    logger.info("Using MPS (Apple Silicon GPU) for embeddings")
                except Exception as mps_exc:
                    logger.warning(
                        f"Failed to move model to MPS device, falling back to CPU: {mps_exc}"
                    )
            else:
                logger.info("Using CPU for embeddings")
    return _encoder

def encode_texts(texts: list[str], batch_size: int = EMBEDDING_BATCH_SIZE) -> np.ndarray:
    encoder = _get_encoder()
    with timer(f"Encode {len(texts)} texts"):
        embeddings: np.ndarray = encoder.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
    return embeddings.astype(np.float32)

def encode_query(text: str) -> np.ndarray:
    encoder = _get_encoder()
    vec: np.ndarray = encoder.encode(
        [text],
        normalize_embeddings=True,
    )
    return vec.astype(np.float32)


def compute_sentence_embeddings(chunks: list) -> dict[str, bytes]:
    """Pre-compute per-sentence embeddings for HAVF caching (LAT-1).

    Returns a dict mapping paragraph_id → serialised numpy float32 bytes.
    The array shape is (n_sentences, EMBEDDING_DIMENSIONS) where sentences
    are in the same order as the keys in chunk.sentence_map.

    Storing these at index time avoids re-encoding source sentences
    on every chat query, reducing HAVF Level 1 latency from ~50-200ms to ~5ms.
    """
    result: dict[str, bytes] = {}
    all_texts: list[str] = []
    chunk_index_map: list[tuple[str, int]] = []  # (paragraph_id, n_sentences)

    for chunk in chunks:
        s_map = getattr(chunk, "sentence_map", {})
        if not isinstance(s_map, dict) or not s_map:
            continue
        texts = [info["text"] for info in s_map.values()]
        if not texts:
            continue
        chunk_index_map.append((chunk.paragraph_id, len(texts)))
        all_texts.extend(texts)

    if not all_texts:
        return result

    # Batch encode all sentences across all chunks in one call
    all_vecs = encode_texts(all_texts)

    offset = 0
    for para_id, n_sentences in chunk_index_map:
        chunk_vecs = all_vecs[offset : offset + n_sentences]
        result[para_id] = chunk_vecs.tobytes()
        offset += n_sentences

    logger.info(
        f"Pre-computed sentence embeddings for {len(result)} chunks "
        f"({len(all_texts)} sentences total)"
    )
    return result

async def index_chunks(
    chunks: list,
    paper_id: str,
    faiss_store: FAISSStore,
) -> int:
    if not chunks:
        return 0

    texts = [c.enriched_text for c in chunks]
    ids = [f"{paper_id}::{c.paragraph_id}" for c in chunks]

    vectors = encode_texts(texts)
    faiss_store.add_vectors(vectors, ids)
    try:
        faiss_store.save()
    except Exception as save_exc:
        logger.error(
            f"FAISS save failed for {paper_id}: {save_exc} "
            "\u2014 rolling back in-memory index to maintain consistency"
        )
        try:
            faiss_store.remove_paper(paper_id)
        except Exception as rb_exc:
            logger.error(f"FAISS rollback also failed for {paper_id}: {rb_exc}")
        raise

    logger.info(f"Indexed {len(chunks)} chunks for paper {paper_id}")
    return len(chunks)

