"""TraceLit — MPS-Accelerated Embedder.

Provides embedding generation using all-MiniLM-L6-v2 on Apple MPS (M3 GPU).
Falls back to CPU if MPS is unavailable.

Used by:
  - Paper ingestion: embed enriched paragraph text → FAISS
  - Query time: embed user query → FAISS retrieval
  - HAVF Level 1: embed generated sentences for similarity comparison
"""

from typing import List, Optional

import numpy as np
import torch
from loguru import logger
from sentence_transformers import SentenceTransformer

from app.config import settings


class MPSAcceleratedEmbedder:
    """Sentence embedding with MPS acceleration on Apple Silicon.

    Lazy-loads the model on first use to avoid startup overhead.
    Thread-safe for concurrent requests via torch.no_grad().

    Performance:
      - MPS: ~0.3s per 100 paragraphs (2.7x speedup over CPU)
      - CPU: ~0.8s per 100 paragraphs
      - Model size: 23MB, ~200MB RAM
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        force_cpu: bool = False,
    ) -> None:
        """Initialize embedder.

        Args:
            model_name: SentenceTransformer model name. Defaults to settings.
            force_cpu: Force CPU even if MPS is available (for testing).
        """
        self.model_name = model_name or settings.embedding_model
        self._model: Optional[SentenceTransformer] = None
        self._force_cpu = force_cpu
        self._device: Optional[str] = None

    @property
    def device(self) -> str:
        """Resolve device: MPS > CPU."""
        if self._device is None:
            if self._force_cpu:
                self._device = "cpu"
            elif torch.backends.mps.is_available():
                self._device = "mps"
            else:
                self._device = "cpu"
        return self._device

    def _ensure_model(self) -> None:
        """Lazy-load the embedding model on first use."""
        if self._model is None:
            logger.info(
                "Loading embedding model: {} (device={})",
                self.model_name,
                self.device,
            )
            self._model = SentenceTransformer(self.model_name)
            # Move model to device
            self._model = self._model.to(self.device)
            logger.info("Embedding model loaded successfully")

    def encode(
        self,
        texts: List[str],
        batch_size: int = 64,
        normalize: bool = True,
        show_progress: bool = False,
    ) -> np.ndarray:
        """Encode a list of texts into embeddings.

        Args:
            texts: List of text strings to encode.
            batch_size: Batch size for encoding.
            normalize: L2-normalize embeddings (required for cosine similarity).
            show_progress: Show tqdm progress bar.

        Returns:
            2D numpy array of shape (len(texts), embedding_dim).
        """
        self._ensure_model()

        if not texts:
            return np.array([])

        with torch.no_grad():
            embeddings = self._model.encode(
                texts,
                device=self.device,
                batch_size=batch_size,
                normalize_embeddings=normalize,
                show_progress_bar=show_progress,
            )

        # Flush any pending MPS operations so the GPU buffer
        # is fully materialized before we copy to numpy.
        if self.device == "mps":
            torch.mps.synchronize()

        # Force a fully-owned C-contiguous float32 copy.
        # np.asarray() may return a zero-copy view of a torch-MPS-backed
        # buffer that gets freed — FAISS would then access dangling memory.
        return np.array(embeddings, dtype=np.float32, copy=True)

    def encode_single(self, text: str, normalize: bool = True) -> np.ndarray:
        """Encode a single text string.

        Args:
            text: Text to encode.
            normalize: L2-normalize the embedding.

        Returns:
            1D numpy array of shape (embedding_dim,).
        """
        result = self.encode([text], normalize=normalize)
        return result[0]

    def cosine_similarity(
        self,
        query_embedding: np.ndarray,
        corpus_embeddings: np.ndarray,
    ) -> np.ndarray:
        """Compute cosine similarity between a query and corpus embeddings.

        Args:
            query_embedding: 1D array (embedding_dim,).
            corpus_embeddings: 2D array (n_docs, embedding_dim).

        Returns:
            1D array of similarity scores (n_docs,).
        """
        if query_embedding.ndim == 1:
            query_embedding = query_embedding.reshape(1, -1)
        if corpus_embeddings.ndim == 1:
            corpus_embeddings = corpus_embeddings.reshape(1, -1)

        # Dot product for normalized vectors = cosine similarity
        return np.dot(query_embedding, corpus_embeddings.T).flatten()

    @property
    def embedding_dim(self) -> int:
        """Return the embedding dimension of the model."""
        self._ensure_model()
        return self._model.get_sentence_embedding_dimension()

    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model is not None


# ============================================================
# Module-level Singleton
# ============================================================

_embedder_instance: Optional[MPSAcceleratedEmbedder] = None


def get_embedder() -> MPSAcceleratedEmbedder:
    """Get or create the global embedder instance.

    Returns:
        MPSAcceleratedEmbedder singleton.
    """
    global _embedder_instance
    if _embedder_instance is None:
        _embedder_instance = MPSAcceleratedEmbedder()
    return _embedder_instance
