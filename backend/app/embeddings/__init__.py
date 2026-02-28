"""MPS-accelerated embeddings and FAISS vector store."""

from app.embeddings.mps_embedder import MPSAcceleratedEmbedder, get_embedder
from app.embeddings.vector_store import VectorStore, get_vector_store

__all__ = [
    "MPSAcceleratedEmbedder",
    "get_embedder",
    "VectorStore",
    "get_vector_store",
]
