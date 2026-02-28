"""TraceLit — FAISS Vector Store Service.

Manages the FAISS index for paragraph-level retrieval:
  - Store paper paragraphs with pre-computed MPS embeddings
  - Retrieve top-k per paper using cosine similarity
  - Delete paper vectors on paper removal
  - Persist index + metadata to disk

Replaces ChromaDB to avoid pydantic v1 / Python 3.14 incompatibility.
FAISS is lighter, faster, and dependency-free for this use case.
"""

import json
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional

import faiss
import numpy as np
from loguru import logger

from app.config import settings
from app.embeddings.mps_embedder import get_embedder

# Embedding dimension for all-MiniLM-L6-v2
EMBEDDING_DIM = 384


class VectorStore:
    """FAISS-backed vector store for paragraph retrieval.

    Uses pre-computed embeddings from MPSAcceleratedEmbedder.
    Inner-product index on L2-normalized vectors ≡ cosine similarity.

    Persistence:
      - {persist_dir}/faiss.index  — FAISS IndexIDMap
      - {persist_dir}/metadata.pkl — doc_id → metadata mapping
    """

    def __init__(self, persist_dir: Optional[str] = None) -> None:
        self._persist_dir = Path(persist_dir or settings.chroma_persist_dir)
        self._index: Optional[faiss.IndexIDMap] = None
        self._metadata: Dict[int, Dict[str, Any]] = {}  # int64 id → metadata
        self._doc_id_map: Dict[str, int] = {}  # string doc_id → int64 id
        self._next_id: int = 0
        self._initialized: bool = False

    # ----------------------------------------------------------
    # Paths
    # ----------------------------------------------------------

    @property
    def _index_path(self) -> Path:
        return self._persist_dir / "faiss.index"

    @property
    def _meta_path(self) -> Path:
        return self._persist_dir / "metadata.pkl"

    # ----------------------------------------------------------
    # Initialization & Persistence
    # ----------------------------------------------------------

    def _ensure_initialized(self) -> None:
        """Lazy-initialize FAISS index, loading from disk if available."""
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
                logger.info(
                    "FAISS index loaded: {} vectors from {}",
                    self._index.ntotal,
                    self._persist_dir,
                )
            except Exception as e:
                logger.warning("Failed to load FAISS index: {}, creating new", e)
                self._create_empty_index()
        else:
            self._create_empty_index()

        # Global FAISS setting: single-threaded to avoid OMP threads accessing
        # numpy buffers still owned by MPS. Safe as IndexFlatIP doesn't benefit
        # from parallelism at the paragraph batch sizes we use (<10k vectors).
        faiss.omp_set_num_threads(1)
        self._initialized = True

    def _create_empty_index(self) -> None:
        """Create a new empty FAISS index (inner product on normalized vectors)."""
        # IndexFlatIP on L2-normalized vectors = cosine similarity
        flat_index = faiss.IndexFlatIP(EMBEDDING_DIM)
        self._index = faiss.IndexIDMap(flat_index)
        self._metadata = {}
        self._doc_id_map = {}
        self._next_id = 0
        # Disable OMP threading: prevents cross-thread access to numpy buffers
        # that may still be owned by MPS-backed torch tensors.
        faiss.omp_set_num_threads(1)
        logger.info("Created new FAISS index (dim={})", EMBEDDING_DIM)

    def _save(self) -> None:
        """Persist FAISS index and metadata to disk."""
        try:
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self._index, str(self._index_path))
            with open(self._meta_path, "wb") as f:
                pickle.dump(
                    {
                        "metadata": self._metadata,
                        "doc_id_map": self._doc_id_map,
                        "next_id": self._next_id,
                    },
                    f,
                )
        except Exception as e:
            logger.error("Failed to save FAISS index: {}", e)

    # ----------------------------------------------------------
    # Public API (same interface as old ChromaDB-backed store)
    # ----------------------------------------------------------

    def add_paragraphs(
        self,
        paper_id: str,
        chunks: List[Dict[str, Any]],
    ) -> int:
        """Store paragraph chunks with embeddings in FAISS.

        Args:
            paper_id: Paper UUID.
            chunks: List of chunk dicts from SentenceAwareChunker.
                Each has: paragraph_id, text, enriched_text, sentences,
                section, page, paper_id, paper_title, token_count.

        Returns:
            Number of paragraphs stored.
        """
        if not chunks:
            return 0

        self._ensure_initialized()
        embedder = get_embedder()

        # Collect enriched texts for batch embedding
        enriched_texts = [c["enriched_text"] for c in chunks]

        # Batch encode with MPS acceleration
        embeddings = embedder.encode(enriched_texts, batch_size=64)

        # L2-normalize for cosine similarity via inner product.
        # Use ascontiguousarray to ensure FAISS receives a fully owned
        # C-contiguous buffer (prevents MPS-backed memory access).
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        embeddings_normed = np.ascontiguousarray(embeddings / norms, dtype=np.float32)

        ids_to_add: List[int] = []

        for i, chunk in enumerate(chunks):
            doc_id = f"{paper_id}_{chunk['paragraph_id']}"

            # If doc_id already exists (upsert), remove old entry
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

        # Add all vectors in one batch
        id_array = np.array(ids_to_add, dtype=np.int64)
        self._index.add_with_ids(embeddings_normed, id_array)

        # Persist to disk
        self._save()

        logger.info(
            "Stored {} paragraphs for paper {} in FAISS",
            len(ids_to_add),
            paper_id,
        )
        return len(ids_to_add)

    def query(
        self,
        query_text: str,
        paper_ids: List[str],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Retrieve top-k most relevant paragraphs per paper.

        Uses the query text to find similar paragraphs across active papers.
        Returns top_k results per paper (not global top_k) so every active
        paper is represented in the context.

        Args:
            query_text: User query string.
            paper_ids: List of paper UUIDs to search within.
            top_k: Number of results per paper.

        Returns:
            List of paragraph dicts with metadata and sentences.
        """
        if not paper_ids:
            return []

        self._ensure_initialized()

        if self._index.ntotal == 0:
            return []

        embedder = get_embedder()
        query_embedding = embedder.encode_single(query_text)

        # L2-normalize query vector; force owned contiguous copy for FAISS
        norm = np.linalg.norm(query_embedding)
        if norm > 0:
            query_embedding = query_embedding / norm
        query_vec = np.ascontiguousarray(query_embedding.reshape(1, -1), dtype=np.float32)

        # Search across all vectors (we filter by paper_id after)
        # Request more results than top_k to account for filtering
        search_k = min(self._index.ntotal, top_k * len(paper_ids) * 2)
        if search_k == 0:
            return []

        scores, ids = self._index.search(query_vec, search_k)

        # Collect results per paper
        paper_results: Dict[str, List[Dict[str, Any]]] = {pid: [] for pid in paper_ids}

        for score, int_id in zip(scores[0], ids[0]):
            if int_id == -1:  # FAISS returns -1 for empty slots
                continue

            meta = self._metadata.get(int(int_id))
            if meta is None:
                continue

            pid = meta["paper_id"]
            if pid not in paper_results:
                continue

            if len(paper_results[pid]) >= top_k:
                continue

            # Inner product on normalized vectors = cosine similarity
            similarity = float(score)

            # Parse sentences from JSON
            sentences_json = meta.get("sentences", "[]")
            try:
                sentences = json.loads(sentences_json)
            except (json.JSONDecodeError, TypeError):
                sentences = []

            paper_results[pid].append({
                "paragraph_id": meta.get("paragraph_id", ""),
                "text": meta.get("original_text", ""),
                "paper_id": pid,
                "paper_title": meta.get("paper_title", ""),
                "section": meta.get("section", ""),
                "page": meta.get("page", 0),
                "sentences": sentences,
                "similarity": similarity,
                "token_count": meta.get("token_count", 0),
            })

        # Flatten and sort by similarity (highest first)
        all_results: List[Dict[str, Any]] = []
        for results_list in paper_results.values():
            all_results.extend(results_list)
        all_results.sort(key=lambda x: x.get("similarity", 0), reverse=True)

        logger.debug(
            "Vector retrieval: {} results for {} papers (top_k={})",
            len(all_results),
            len(paper_ids),
            top_k,
        )
        return all_results

    def delete_paper(self, paper_id: str) -> int:
        """Remove all paragraphs for a paper from the FAISS index.

        Args:
            paper_id: Paper UUID to delete.

        Returns:
            Number of documents deleted.
        """
        self._ensure_initialized()

        try:
            # Find all int IDs belonging to this paper
            ids_to_remove: List[int] = []
            doc_ids_to_remove: List[str] = []

            for doc_id, int_id in list(self._doc_id_map.items()):
                meta = self._metadata.get(int_id)
                if meta and meta.get("paper_id") == paper_id:
                    ids_to_remove.append(int_id)
                    doc_ids_to_remove.append(doc_id)

            if not ids_to_remove:
                return 0

            # Remove from FAISS index
            self._index.remove_ids(
                np.array(ids_to_remove, dtype=np.int64)
            )

            # Remove from metadata and doc_id_map
            for int_id in ids_to_remove:
                self._metadata.pop(int_id, None)
            for doc_id in doc_ids_to_remove:
                self._doc_id_map.pop(doc_id, None)

            self._save()

            logger.info(
                "Deleted {} paragraphs for paper {} from FAISS",
                len(ids_to_remove),
                paper_id,
            )
            return len(ids_to_remove)

        except Exception as e:
            logger.warning(
                "Failed to delete paper {} from FAISS: {}", paper_id, e
            )
            return 0

    def count(self) -> int:
        """Return total number of documents in the index."""
        self._ensure_initialized()
        return self._index.ntotal

    def paper_count(self, paper_id: str) -> int:
        """Return number of paragraphs stored for a specific paper."""
        self._ensure_initialized()
        return sum(
            1
            for meta in self._metadata.values()
            if meta.get("paper_id") == paper_id
        )


# ============================================================
# Module-level Singleton
# ============================================================

_store_instance: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """Get or create the global VectorStore instance.

    Returns:
        VectorStore singleton.
    """
    global _store_instance
    if _store_instance is None:
        _store_instance = VectorStore()
    return _store_instance
