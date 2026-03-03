import numpy as np
from sentence_transformers import SentenceTransformer

from infrastructure.vector_store.faiss_store import FAISSStore
from shared.constants import EMBEDDING_MODEL_NAME
from shared.logger import get_logger
from shared.utils.time_utils import timer

logger = get_logger(__name__)

_encoder: SentenceTransformer | None = None


def _mps_available() -> bool:
    """Check if MPS (Apple Silicon GPU) is available."""
    try:
        import torch

        return torch.backends.mps.is_available()
    except ImportError:
        return False


def _get_encoder() -> SentenceTransformer:
    global _encoder
    if _encoder is None:
        with timer("Load embedding model"):
            device = "cpu"
            try:
                if _mps_available():
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


def encode_texts(texts: list[str], batch_size: int = 64) -> np.ndarray:
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
        # save() failed: disk index is still the pre-existing snapshot while
        # the in-memory index already contains the new vectors.  Roll back the
        # in-memory state so both sides remain consistent.  The caller will
        # catch the re-raised exception and mark the paper as FAILED.
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
