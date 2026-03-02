"""TraceLit — MPS-Accelerated Embedder.

Provides embedding generation using all-MiniLM-L6-v2 on Apple MPS (M3 GPU).
Falls back to CPU if MPS is unavailable.
Includes embedding cache for repeat queries.
"""

import hashlib
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
    """

    def __init__(self, model_name: Optional[str] = None, force_cpu: bool = False) -> None:
        self.model_name = model_name or settings.embedding_model
        self._model: Optional[SentenceTransformer] = None
        self._force_cpu = force_cpu
        self._device: Optional[str] = None

    @property
    def device(self) -> str:
        if self._device is None:
            if self._force_cpu:
                self._device = "cpu"
            elif torch.backends.mps.is_available():
                self._device = "mps"
            else:
                self._device = "cpu"
        return self._device

    def _ensure_model(self) -> None:
        if self._model is None:
            logger.info("Loading embedding model: {} (device={})", self.model_name, self.device)
            self._model = SentenceTransformer(self.model_name).to(self.device)
            logger.info("Embedding model loaded successfully")

    def encode(
        self,
        texts: List[str],
        batch_size: int = 64,
        normalize: bool = True,
        show_progress: bool = False,
    ) -> np.ndarray:
        """Encode a list of texts into embeddings.

        Uses a TTL cache to avoid re-encoding identical text.
        """
        self._ensure_model()
        if not texts:
            return np.array([])

        from shared.cache import get_embedding_cache
        cache = get_embedding_cache()

        # Separate cached vs. uncached
        results = [None] * len(texts)
        uncached_indices = []

        for i, text in enumerate(texts):
            key = hashlib.md5(text.encode("utf-8")).hexdigest()
            cached = cache.get(key)
            if cached is not None:
                results[i] = cached
            else:
                uncached_indices.append(i)

        if uncached_indices:
            uncached_texts = [texts[i] for i in uncached_indices]
            with torch.no_grad():
                embeddings = self._model.encode(
                    uncached_texts,
                    device=self.device,
                    batch_size=batch_size,
                    normalize_embeddings=normalize,
                    show_progress_bar=show_progress,
                )

            if self.device == "mps":
                torch.mps.synchronize()

            embeddings = np.array(embeddings, dtype=np.float32, copy=True)

            for local_idx, global_idx in enumerate(uncached_indices):
                emb = embeddings[local_idx]
                results[global_idx] = emb
                key = hashlib.md5(texts[global_idx].encode("utf-8")).hexdigest()
                cache.set(key, emb)

        return np.array(results, dtype=np.float32)

    def encode_single(self, text: str, normalize: bool = True) -> np.ndarray:
        return self.encode([text], normalize=normalize)[0]

    def cosine_similarity(self, query: np.ndarray, corpus: np.ndarray) -> np.ndarray:
        if query.ndim == 1:
            query = query.reshape(1, -1)
        if corpus.ndim == 1:
            corpus = corpus.reshape(1, -1)
        return np.dot(query, corpus.T).flatten()

    @property
    def embedding_dim(self) -> int:
        self._ensure_model()
        return self._model.get_sentence_embedding_dimension()

    def is_loaded(self) -> bool:
        return self._model is not None


# Module-level singleton
_embedder_instance: Optional[MPSAcceleratedEmbedder] = None


def get_embedder() -> MPSAcceleratedEmbedder:
    """Get or create the global embedder instance."""
    global _embedder_instance
    if _embedder_instance is None:
        _embedder_instance = MPSAcceleratedEmbedder()
    return _embedder_instance
