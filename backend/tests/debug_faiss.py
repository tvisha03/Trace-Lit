"""Quick debug script for FAISS vector store segfault."""
import sys
import os
import tempfile

# Ensure we're in backend dir
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")

from app.embeddings.vector_store import VectorStore
from app.embeddings.mps_embedder import get_embedder

# Pre-load embedder
embedder = get_embedder()
embedder._ensure_model()
print("Embedder loaded")

with tempfile.TemporaryDirectory() as tmpdir:
    store = VectorStore(persist_dir=tmpdir)

    chunks = [
        {
            "paragraph_id": "P0",
            "text": "BERT uses masked language modeling.",
            "enriched_text": "[Paper: BERT] BERT uses masked language modeling.",
            "sentences": [{"sentence_id": "P0_S0", "text": "BERT uses masked language modeling."}],
            "section": "Methods",
            "page": 3,
            "paper_id": "test123",
            "paper_title": "Test",
            "token_count": 8,
        },
        {
            "paragraph_id": "P1",
            "text": "Transformers use self-attention.",
            "enriched_text": "[Paper: BERT] Transformers use self-attention.",
            "sentences": [{"sentence_id": "P1_S0", "text": "Transformers use self-attention."}],
            "section": "Intro",
            "page": 1,
            "paper_id": "test123",
            "paper_title": "Test",
            "token_count": 6,
        },
    ]

    count = store.add_paragraphs("test123", chunks)
    print(f"Stored {count} paragraphs, index ntotal={store._index.ntotal}")

    # Query
    print("Querying...")
    import numpy as np

    # Step by step to find segfault location
    embedder2 = get_embedder()
    print("  Step 1: encoding query...")
    query_embedding = embedder2.encode_single("What is BERT?")
    print(f"  Step 2: query_embedding shape={query_embedding.shape}, dtype={query_embedding.dtype}")

    norm = np.linalg.norm(query_embedding)
    if norm > 0:
        query_embedding = query_embedding / norm
    print(f"  Step 3: normalized, norm now={np.linalg.norm(query_embedding):.4f}")

    query_vec = np.ascontiguousarray(query_embedding.astype(np.float32).reshape(1, -1))
    print(f"  Step 4: query_vec shape={query_vec.shape}, dtype={query_vec.dtype}, contiguous={query_vec.flags['C_CONTIGUOUS']}")

    search_k = min(store._index.ntotal, 2 * 1 * 2)
    print(f"  Step 5: search_k={search_k}, ntotal={store._index.ntotal}")

    print("  Step 6: calling FAISS search...")
    import sys
    sys.stdout.flush()
    scores, ids = store._index.search(query_vec, search_k)
    print(f"  Step 7: scores={scores}, ids={ids}")

    results = store.query("What is BERT?", ["test123"], top_k=2)
    print(f"Query returned {len(results)} results")
    for r in results:
        print(f"  {r['paragraph_id']}: sim={r['similarity']:.3f} | {r['text']}")

    # Delete
    deleted = store.delete_paper("test123")
    print(f"Deleted {deleted} paragraphs, index ntotal={store._index.ntotal}")

    remaining = store.paper_count("test123")
    print(f"Remaining: {remaining}")

print("All vector store operations OK")
