import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import numpy as np
from sentence_transformers import SentenceTransformer

from infrastructure.vector_store.faiss_store import FAISSStore
from shared.constants import EMBEDDING_MODEL_NAME
from shared.logger import get_logger
from shared.utils.time_utils import timer

logger = get_logger(__name__)

_encoder: SentenceTransformer | None = None
_encoder_device: str = "cpu"

def _detect_best_device() -> str:
    """Detect the best available device: CUDA > MPS > CPU."""
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"

def _get_encoder() -> SentenceTransformer:
    global _encoder, _encoder_device
    if _encoder is None:
        with timer("Load embedding model"):
            device = _detect_best_device()
            _encoder = SentenceTransformer(EMBEDDING_MODEL_NAME)

            if device != "cpu":
                try:
                    import torch
                    _encoder = _encoder.to(torch.device(device))
                    _encoder_device = device
                    logger.info(f"Using {device.upper()} for embeddings")
                except Exception as exc:
                    logger.warning(
                        f"Failed to move model to {device}, falling back to CPU: {exc}"
                    )
                    _encoder_device = "cpu"
            else:
                _encoder_device = "cpu"
                logger.info("Using CPU for embeddings")
    return _encoder

def _optimal_batch_size() -> int:
    """Pick batch size based on available device."""
    if _encoder_device == "cuda":
        return 128
    if _encoder_device == "mps":
        return 64
    return 32

def encode_texts(texts: list[str], batch_size: int | None = None) -> np.ndarray:
    if batch_size is None:
        batch_size = _optimal_batch_size()
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

