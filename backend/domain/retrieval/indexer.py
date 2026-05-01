import os
import numpy as np
import torch # Explicit import to ensure it's available
from sentence_transformers import SentenceTransformer
from app.config import get_settings
from infrastructure.vector_store.faiss_store import FAISSStore
from shared.logger import get_logger
from shared.utils.time_utils import timer

# Optimization: Limit CPU threads to prevent the 90% CPU hang
# during data packaging even when using GPU.
torch.set_num_threads(4)

logger = get_logger(__name__)

_encoder: SentenceTransformer | None = None
_encoder_device: str = "cpu"

def _detect_best_device() -> str:
    """Detect the best available device: CUDA > MPS > CPU."""
    if torch.cuda.is_available():
        # Set specific GPU settings for RTX 3060
        torch.cuda.empty_cache()
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"

def _get_encoder() -> SentenceTransformer:
    global _encoder, _encoder_device
    if _encoder is None:
        model_name = get_settings().EMBEDDING_MODEL
        with timer("Load embedding model"):
            device = _detect_best_device()
            try:
                _encoder = SentenceTransformer(model_name, device=device)
                _encoder_device = device
                logger.info(f"🚀 SUCCESS: Using {device.upper()} for embeddings ({model_name})")
            except Exception as exc:
                logger.warning(f"⚠️ GPU Init failed, falling back to CPU: {exc}")
                _encoder = SentenceTransformer(model_name, device="cpu")
                _encoder_device = "cpu"
    return _encoder

def _optimal_batch_size() -> int:
    """Pick batch size based on available device."""
    # Your RTX 3060 can easily handle 128 or even 256 for embeddings
    if _encoder_device == "cuda":
        return 128
    return 32

def encode_texts(texts: list[str], batch_size: int | None = None) -> np.ndarray:
    if batch_size is None:
        batch_size = _optimal_batch_size()

    encoder = _get_encoder()

    # Process in one go to take advantage of GPU parallelism
    with timer(f"Embedding {len(texts)} chunks"):
        embeddings = encoder.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=True, # Helpful for 900+ chunks
            convert_to_numpy=True,
            normalize_embeddings=True
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

