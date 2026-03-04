"""TraceLit — FAISS Vector Store.

Manages the FAISS index for paragraph-level retrieval:
  - Store paper paragraphs with pre-computed MPS embeddings
  - Retrieve top-k results per paper using cosine similarity
  - Delete paper vectors on paper removal
  - Persist index + metadata to disk

Replaces ChromaDB to avoid pydantic v1 / Python 3.14 incompatibility.
"""

import json
import pickle
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import faiss
import numpy as np
from loguru import logger

from app.config import settings
from infrastructure.vector_store.embedder import get_embedder

EMBEDDING_DIM = 384  # all-MiniLM-L6-v2


class VectorStore:
    """FAISS-backed vector store for paragraph retrieval.

    Inner-product index on L2-normalised vectors ≡ cosine similarity.

    Persistence:
      - {persist_dir}/faiss.index  — FAISS IndexIDMap
      - {persist_dir}/metadata.pkl — doc_id → metadata mapping
    """

    def __init__(self, persist_dir: Optional[str] = None) -> None:
        self._persist_dir = Path(persist_dir or settings.faiss_index_dir)
        self._index: Optional[faiss.IndexIDMap] = None
        self._metadata: Dict[int, Dict[str, Any]] = {}
        self._doc_id_map: Dict[str, int] = {}
        self._next_id: int = 0
        self._initialized: bool = False
        self._lock = threading.Lock()

    @property
    def _index_path(self) -> Path:
        return self._persist_dir / "faiss.index"

    @property
    def _meta_path(self) -> Path:
        return self._persist_dir / "metadata.pkl"

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._persist_dir.mkdir(parents=True, exist_ok=True)

        if self._index_path.exists() and self._meta_path.exists():
            try:
                self._index = faiss.read_index(str(self._index_path))
                with open(self._meta_path, "rb") as f:
                    saved = pickle.load(f)
                self._metadata = saved["metadata"]
                self._doc_id_map = saved["doc_id_map"]
                self._next_id = saved["next_id"]
                logger.info("FAISS index loaded: {} vectors from {}", self._index.ntotal, self._persist_dir)
            except Exception as e:
                logger.warning("Failed to load FAISS index: {}, creating new", e)
                self._create_empty_index()
        else:
            self._create_empty_index()

        faiss.omp_set_num_threads(1)
        self._initialized = True

    def _create_empty_index(self) -> None:
        flat = faiss.IndexFlatIP(EMBEDDING_DIM)
        self._index = faiss.IndexIDMap(flat)
        self._metadata = {}
        self._doc_id_map = {}
        self._next_id = 0
        faiss.omp_set_num_threads(1)
        logger.info("Created new FAISS index (dim={})", EMBEDDING_DIM)

    def _save(self) -> None:
        try:
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self._index, str(self._index_path))
            with open(self._meta_path, "wb") as f:
                pickle.dump(
                    {"metadata": self._metadata, "doc_id_map": self._doc_id_map, "next_id": self._next_id},
                    f,
                )
        except Exception as e:
            logger.error("Failed to save FAISS index: {}", e)

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def add_paragraphs(self, paper_id: str, chunks: List[Dict[str, Any]]) -> int:
        """Store paragraph chunks with embeddings (thread-safe)."""
        if not chunks:
            return 0

        self._ensure_initialized()
        embedder = get_embedder()
        enriched_texts = [c["enriched_text"] for c in chunks]
        # Compute embeddings outside the lock (CPU-intensive)
        embeddings = embedder.encode(enriched_texts, batch_size=64)

        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        embeddings_normed = np.ascontiguousarray(embeddings / norms, dtype=np.float32)

        with self._lock:
            ids_to_add: List[int] = []

            for i, chunk in enumerate(chunks):
                doc_id = f"{paper_id}_{chunk['paragraph_id']}"

                if doc_id in self._doc_id_map:
                    old_int_id = self._doc_id_map[doc_id]
                    self._index.remove_ids(np.array([old_int_id], dtype=np.int64))
                    del self._metadata[old_int_id]

                int_id = self._next_id
                self._next_id += 1
                self._doc_id_map[doc_id] = int_id
                self._metadata[int_id] = {
                    "doc_id": doc_id,
                    "paper_id": paper_id,
                    "paper_title": chunk.get("paper_title", ""),
                    "paragraph_id": chunk["paragraph_id"],
                    "section": chunk.get("section", ""),
                    "page": chunk.get("page", 0),
                    "original_text": chunk["text"],
                    "sentences": json.dumps(chunk.get("sentences", [])),
                    "token_count": chunk.get("token_count", 0),
                }
                ids_to_add.append(int_id)

            id_array = np.array(ids_to_add, dtype=np.int64)
            self._index.add_with_ids(embeddings_normed, id_array)
            self._save()

        logger.info("Stored {} paragraphs for paper {} in FAISS", len(chunks), paper_id)
        return len(chunks)

    def query(
        self,
        query_text: str,
        paper_ids: List[str],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Retrieve top-k paragraphs most relevant to the query."""
        self._ensure_initialized()

        if self._index is None or self._index.ntotal == 0:
            return []

        embedder = get_embedder()
        q_embed = embedder.encode([query_text])[0]
        norm = np.linalg.norm(q_embed)
        if norm > 0:
            q_embed /= norm
        q_embed = np.ascontiguousarray(q_embed.reshape(1, -1), dtype=np.float32)

        search_k = min(top_k * len(paper_ids) * 3, self._index.ntotal)
        distances, ids = self._index.search(q_embed, search_k)

        results: List[Dict] = []
        paper_id_set = set(paper_ids)

        for dist, int_id in zip(distances[0], ids[0]):
            if int_id < 0:
                continue
            meta = self._metadata.get(int_id)
            if meta is None or meta.get("paper_id") not in paper_id_set:
                continue

            sentences = []
            if meta.get("sentences"):
                try:
                    sentences = json.loads(meta["sentences"])
                except (json.JSONDecodeError, TypeError):
                    sentences = []

            results.append({
                "paragraph_id": meta["paragraph_id"],
                "text": meta["original_text"],
                "paper_id": meta["paper_id"],
                "paper_title": meta.get("paper_title", ""),
                "section": meta.get("section", ""),
                "page": meta.get("page", 0),
                "sentences": sentences,
                "score": float(dist),
            })

            if len(results) >= top_k:
                break

        return results

    def delete_paper(self, paper_id: str) -> int:
        """Remove all vectors for the given paper (thread-safe)."""
        self._ensure_initialized()

        with self._lock:
            ids_to_remove = [
                int_id for doc_id, int_id in self._doc_id_map.items()
                if doc_id.startswith(f"{paper_id}_")
            ]

            if ids_to_remove:
                self._index.remove_ids(np.array(ids_to_remove, dtype=np.int64))
                for int_id in ids_to_remove:
                    self._metadata.pop(int_id, None)
                for doc_id in [d for d in list(self._doc_id_map) if d.startswith(f"{paper_id}_")]:
                    del self._doc_id_map[doc_id]
                self._save()

        logger.info("Deleted {} vectors for paper {}", len(ids_to_remove), paper_id)
        return len(ids_to_remove)

    def count(self) -> int:
        """Return total number of stored vectors."""
        self._ensure_initialized()
        return self._index.ntotal if self._index else 0


# Module-level singleton
_vector_store_instance: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """Get or create the global vector store instance."""
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = VectorStore()
    return _vector_store_instance
