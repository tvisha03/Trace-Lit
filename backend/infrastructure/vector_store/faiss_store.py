
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np
    import faiss
else:
    try:
        import numpy as np
        import faiss
        faiss.omp_set_num_threads(1)
    except ImportError:
        np = None  # type: ignore
        faiss = None  # type: ignore

from shared.constants import FAISS_INDEX_DIR, EMBEDDING_DIMENSIONS, FAISS_TOP_K_PER_PAPER
from shared.logger import get_logger

logger = get_logger(__name__)

class FAISSStore:

    def __init__(self, index_dir: str = FAISS_INDEX_DIR) -> None:
        self._index_dir = Path(index_dir)
        self._index: Any | None = None
        self._id_map: list[str] = []
        self._lock = threading.Lock()

    def load_or_create(self) -> None:
        if faiss is None or np is None:
            logger.error("faiss or numpy not available")
            return

        index_path = self._index_dir / "index.faiss"
        map_path = self._index_dir / "id_map.npy"

        if index_path.exists() and map_path.exists():
            self._index = faiss.read_index(str(index_path))
            self._id_map = list(np.load(str(map_path), allow_pickle=True))
            if self._index is not None:
                logger.info(f"FAISS index loaded — {self._index.ntotal} vectors")
        else:
            self._index = faiss.IndexFlatIP(EMBEDDING_DIMENSIONS)
            self._id_map = []
            logger.info("Created fresh FAISS index")

    def save(self) -> None:
        if faiss is None or np is None or self._index is None:
            logger.error("Cannot save: faiss/numpy not available or index not initialized")
            return

        self._index_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            faiss.write_index(self._index, str(self._index_dir / "index.faiss"))
            np.save(str(self._index_dir / "id_map.npy"), np.array(self._id_map, dtype=object))
        logger.info(f"FAISS index saved — {self._index.ntotal} vectors")

    def is_ready(self) -> bool:
        """Return True when the index is loaded and operational."""
        return faiss is not None and np is not None and self._index is not None

    def add_vectors(
        self,
        vectors: Any,
        ids: list[str],
    ) -> None:
        if np is None or self._index is None:
            logger.error("Cannot add vectors: numpy not available or index not initialized")
            return

        if vectors.shape[0] != len(ids):
            raise ValueError("vectors and ids must have the same length")

        # CRT-003: Guarantee L2-normalised vectors for IndexFlatIP (cosine sim).
        # encode_texts already passes normalize_embeddings=True, but this is a
        # safety net for any call-site that bypasses the encoder.
        vecs = vectors.astype(np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1  # Avoid division by zero for zero vectors.
        vecs = vecs / norms

        with self._lock:
            self._index.add(vecs)
            self._id_map.extend(ids)

    def search(
        self,
        query_vector: Any,
        paper_ids: list[str],
        top_k_per_paper: int = FAISS_TOP_K_PER_PAPER,
    ) -> list[dict]:
        if np is None or self._index is None:
            logger.error("Cannot search: numpy not available or index not initialized")
            return []

        if self._index.ntotal == 0:
            return []

        total_k = min(self._index.ntotal, top_k_per_paper * len(paper_ids) * 2)
        query = query_vector.reshape(1, -1).astype(np.float32)

        with self._lock:
            scores, indices = self._index.search(query, total_k)
            # The id_map snapshot MUST be taken inside the lock.  Taking it
            # outside would open a window where a concurrent add_vectors() or
            # remove_paper() call mutates self._id_map after the FAISS search
            # returns its indices, causing index-to-id mismatches for newly
            # added or removed vectors.  The lock serialises both operations.
            id_map_snapshot = list(self._id_map)

        return self._filter_search_results(scores[0], indices[0], paper_ids, top_k_per_paper, id_map_snapshot)

    def _filter_search_results(
        self,
        scores: Any,
        indices: Any,
        paper_ids: list[str],
        top_k_per_paper: int,
        id_map_snapshot: list[str],
    ) -> list[dict]:
        results_by_paper: dict[str, list[dict]] = {pid: [] for pid in paper_ids}

        for score, idx in zip(scores, indices):
            if idx == -1:
                continue
            self._add_result_if_valid(results_by_paper, idx, score, top_k_per_paper, id_map_snapshot)

        return self._flatten_and_sort_results(results_by_paper)

    def _flatten_and_sort_results(self, results_by_paper: dict[str, list[dict]]) -> list[dict]:
        """Flatten results from all papers and sort by score."""
        flat: list[dict] = []
        for hits in results_by_paper.values():
            flat.extend(hits)
        flat.sort(key=lambda x: x["score"], reverse=True)
        return flat

    def _add_result_if_valid(
        self,
        results_by_paper: dict[str, list[dict]],
        idx: int,
        score: float,
        top_k_per_paper: int,
        id_map_snapshot: list[str],
    ) -> None:
        if idx >= len(id_map_snapshot):
            # Index was appended to the live map after the snapshot was taken;
            # skip safely rather than raising an IndexError.
            return
        composite = id_map_snapshot[idx]
        paper_id, paragraph_id = composite.split("::", 1)
        if paper_id not in results_by_paper:
            return
        if len(results_by_paper[paper_id]) < top_k_per_paper:
            results_by_paper[paper_id].append({
                "paper_id": paper_id,
                "paragraph_id": paragraph_id,
                "score": float(score),
            })

    def remove_paper(self, paper_id: str) -> None:
        """Remove all vectors associated with a paper from the FAISS index.

        Saves a backup of the index before rebuilding so that a crash
        mid-rebuild does not permanently corrupt the index.
        """
        if not self._is_initialized():
            return

        # Safety: save a backup before destructive rebuild so the index
        # can be recovered if the process crashes mid-operation.
        self._backup_index()

        with self._lock:
            self._remove_paper_from_index(paper_id)

    def _is_initialized(self) -> bool:
        """Check if FAISS and numpy are available and index is initialized."""
        if faiss is None:
            logger.error("Cannot remove paper: faiss not available")
            return False
        if np is None:
            logger.error("Cannot remove paper: numpy not available")
            return False
        if self._index is None:
            logger.error("Cannot remove paper: index not initialized")
            return False
        return True

    def _remove_paper_from_index(self, paper_id: str) -> None:
        """Remove all vectors associated with a paper from the index."""
        keep_indices = self._get_indices_to_keep(paper_id)

        if len(keep_indices) < len(self._id_map):
            self._rebuild_index(keep_indices)

    def _get_indices_to_keep(self, paper_id: str) -> list[int]:
        """Get the list of indices that should be kept after removing a paper."""
        return [
            i for i, cid in enumerate(self._id_map) if not cid.startswith(f"{paper_id}::")
        ]

    def _rebuild_index(self, keep_indices: list[int]) -> None:
        """Rebuild the index with only the specified indices."""
        if self._index is None:
            logger.error("Index is not initialized during rebuild")
            return

        if keep_indices:
            reconstructed = []
            for i in keep_indices:
                try:
                    reconstructed.append(self._index.reconstruct(i))
                except Exception as exc:
                    logger.warning(f"Skipping vector at index {i} during rebuild: {exc}")
            if not reconstructed:
                self._index = faiss.IndexFlatIP(EMBEDDING_DIMENSIONS)
                self._id_map = []
                return
            all_vectors = np.array(reconstructed)
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

    def _backup_index(self) -> None:
        """Write a .bak copy of the FAISS index files before a destructive operation.

        Best-effort: failures are logged but do not block the caller because
        the primary index file is still intact at this point.
        """
        try:
            index_path = self._index_dir / "index.faiss"
            map_path = self._index_dir / "id_map.npy"
            if index_path.exists():
                import shutil
                shutil.copy2(index_path, self._index_dir / "index.faiss.bak")
            if map_path.exists():
                import shutil
                shutil.copy2(map_path, self._index_dir / "id_map.npy.bak")
            logger.info("FAISS backup created before rebuild")
        except Exception as exc:
            logger.warning(f"Could not create FAISS backup: {exc}")
