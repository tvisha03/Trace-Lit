"""
FAISS vector store with persistent save/load.
Uses IndexFlatIP (inner product → cosine similarity with normalised vectors).
Thread-safety via a simple lock — FAISS is not thread-safe by default.
"""

import threading
from pathlib import Path
from typing import Any

import numpy as np

from shared.constants import FAISS_INDEX_DIR, EMBEDDING_DIMENSIONS, FAISS_TOP_K_PER_PAPER
from shared.logger import get_logger

logger = get_logger(__name__)

try:
    import faiss
    # Apple Silicon safety: single OMP thread avoids SIGSEGV with MPS-backed memory
    faiss.omp_set_num_threads(1)
except ImportError:
    faiss = None  # type: ignore[assignment]
    logger.warning("faiss-cpu not installed — vector search unavailable")


class FAISSStore:
    """
    Manages a flat inner-product FAISS index with a parallel ID map.

    Each vector is tagged with a composite key ``paper_id::paragraph_id``
    so we can do per-paper top-k retrieval.
    """

    def __init__(self, index_dir: str = FAISS_INDEX_DIR) -> None:
        self._index_dir = Path(index_dir)
        self._index: Any | None = None
        self._id_map: list[str] = []   # parallel to index rows: "paper_id::paragraph_id"
        self._lock = threading.Lock()

    # ── Persistence ────────────────────────────────────────────────────────

    def load_or_create(self) -> None:
        """Load existing index from disk or create a fresh one."""
        index_path = self._index_dir / "index.faiss"
        map_path = self._index_dir / "id_map.npy"

        if index_path.exists() and map_path.exists():
            self._index = faiss.read_index(str(index_path))
            self._id_map = list(np.load(str(map_path), allow_pickle=True))
            logger.info(f"FAISS index loaded — {self._index.ntotal} vectors")
        else:
            self._index = faiss.IndexFlatIP(EMBEDDING_DIMENSIONS)
            self._id_map = []
            logger.info("Created fresh FAISS index")

    def save(self) -> None:
        """Persist index + id map to disk."""
        self._index_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            faiss.write_index(self._index, str(self._index_dir / "index.faiss"))
            np.save(str(self._index_dir / "id_map.npy"), np.array(self._id_map, dtype=object))
        logger.info(f"FAISS index saved — {self._index.ntotal} vectors")

    # ── Write ──────────────────────────────────────────────────────────────

    def add_vectors(
        self,
        vectors: np.ndarray,
        ids: list[str],
    ) -> None:
        """
        Add normalised vectors to the index.

        Parameters
        ----------
        vectors : np.ndarray of shape (n, 384)
            L2-normalised embedding vectors.
        ids : list[str]
            Composite keys in the form ``paper_id::paragraph_id``.
        """
        if vectors.shape[0] != len(ids):
            raise ValueError("vectors and ids must have the same length")

        with self._lock:
            self._index.add(vectors.astype(np.float32))
            self._id_map.extend(ids)

    # ── Read ───────────────────────────────────────────────────────────────

    def search(
        self,
        query_vector: np.ndarray,
        paper_ids: list[str],
        top_k_per_paper: int = FAISS_TOP_K_PER_PAPER,
    ) -> list[dict]:
        """
        Per-paper top-k retrieval — ensures every active paper contributes.

        Returns a list of dicts: ``{paper_id, paragraph_id, score}``.
        """
        if self._index is None or self._index.ntotal == 0:
            return []

        total_k = min(self._index.ntotal, top_k_per_paper * len(paper_ids) * 2)
        query = query_vector.reshape(1, -1).astype(np.float32)

        with self._lock:
            scores, indices = self._index.search(query, total_k)

        results_by_paper: dict[str, list[dict]] = {pid: [] for pid in paper_ids}

        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            composite = self._id_map[idx]
            paper_id, paragraph_id = composite.split("::", 1)
            if paper_id not in results_by_paper:
                continue
            if len(results_by_paper[paper_id]) < top_k_per_paper:
                results_by_paper[paper_id].append({
                    "paper_id": paper_id,
                    "paragraph_id": paragraph_id,
                    "score": float(score),
                })

        # Flatten, best score first
        flat: list[dict] = []
        for hits in results_by_paper.values():
            flat.extend(hits)
        flat.sort(key=lambda x: x["score"], reverse=True)
        return flat

    # ── Cleanup ────────────────────────────────────────────────────────────

    def remove_paper(self, paper_id: str) -> None:
        """
        Remove all vectors for *paper_id*.
        Rebuilds the index since FAISS Flat has no native delete.
        """
        with self._lock:
            keep_indices = [
                i for i, cid in enumerate(self._id_map) if not cid.startswith(f"{paper_id}::")
            ]
            if len(keep_indices) == len(self._id_map):
                return  # nothing to remove

            if keep_indices:
                all_vectors = np.array([self._index.reconstruct(i) for i in keep_indices])
                new_index = faiss.IndexFlatIP(EMBEDDING_DIMENSIONS)
                new_index.add(all_vectors)
                self._index = new_index
                self._id_map = [self._id_map[i] for i in keep_indices]
            else:
                self._index = faiss.IndexFlatIP(EMBEDDING_DIMENSIONS)
                self._id_map = []

    @property
    def total_vectors(self) -> int:
        return self._index.ntotal if self._index else 0
