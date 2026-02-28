"""Debug: FAISS + sentence-transformers model together (the segfault scenario)."""
import numpy as np
import faiss
import tempfile
import sys

DIM = 384

print("1. Load embedder (as VectorStore.query would)...")
import sys
sys.path.insert(0, '/Users/tvishakhanna/Developer/Trace-Lit/backend')

from app.embeddings.mps_embedder import get_embedder
embedder = get_embedder()
print("   Embedder loaded")

print("2. Encode texts...")
texts = ["BERT uses MLM.", "Transformer uses attention."]
embeddings = embedder.encode(texts)
print(f"   Embeddings shape: {embeddings.shape}")

print("3. Create FAISS index and add vectors...")
flat = faiss.IndexFlatIP(DIM)
index = faiss.IndexIDMap(flat)
norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
normed = (embeddings / norms).astype(np.float32)
ids = np.array([0, 1], dtype=np.int64)
index.add_with_ids(normed, ids)
print(f"   ntotal={index.ntotal}")

print("4. Encode query and search...")
query = embedder.encode_single("What is BERT's training objective?")
qnorm = np.linalg.norm(query)
qvec = (query / qnorm).astype(np.float32).reshape(1, -1)

search_k = min(index.ntotal, 4)
print(f"   search_k={search_k}")
scores, result_ids = index.search(qvec, search_k)
print(f"   Search done! scores={scores}, ids={result_ids}")
print("ALL OK")
