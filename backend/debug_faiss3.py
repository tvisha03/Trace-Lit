"""Debug: FAISS query after write - reproduces test sequence."""
import sys, tempfile
sys.path.insert(0, '/Users/tvishakhanna/Developer/Trace-Lit/backend')

import numpy as np
import faiss

DIM = 384

# Step 1: get singleton embedder (simulating test_embedder)
print("Step 1: Load singleton embedder...")
from app.embeddings.mps_embedder import get_embedder
embedder = get_embedder()
t = embedder.encode(["test text"])
print(f"  Encoded OK, shape={t.shape}")

# Step 2: Create VectorStore with tmpdir (simulating test_vector_store)
print("Step 2: Create VectorStore...")
from app.embeddings.vector_store import VectorStore
with tempfile.TemporaryDirectory() as tmpdir:
    store = VectorStore(persist_dir=tmpdir)

    chunks = [
        {
            "paragraph_id": "P0",
            "text": "BERT uses masked language modeling.",
            "enriched_text": "[Paper: BERT] BERT uses masked language modeling.",
            "sentences": [{"sentence_id": "P0_S0", "text": "BERT uses masked language modeling.", "start_char": 0, "end_char": 35}],
            "section": "Methods", "page": 3,
            "paper_id": "test_paper_001",
            "paper_title": "BERT Paper",
            "token_count": 8,
        },
        {
            "paragraph_id": "P1",
            "text": "The transformer uses self-attention.",
            "enriched_text": "[Paper: BERT] The transformer uses self-attention.",
            "sentences": [{"sentence_id": "P1_S0", "text": "The transformer uses self-attention.", "start_char": 0, "end_char": 36}],
            "section": "Introduction", "page": 1,
            "paper_id": "test_paper_001",
            "paper_title": "BERT Paper",
            "token_count": 10,
        },
    ]

    print("Step 3: add_paragraphs...")
    count = store.add_paragraphs("test_paper_001", chunks)
    print(f"  Stored {count} paragraphs")

    print("Step 4: Check index state...")
    store._ensure_initialized()
    print(f"  ntotal={store._index.ntotal}")
    print(f"  metadata keys={list(store._metadata.keys())}")

    print("Step 5: Encode query (via embedder)...")
    q = embedder.encode_single("What training objective does BERT use?")
    print(f"  query shape={q.shape}, dtype={q.dtype}")

    print("Step 6: Normalize query...")
    norm = np.linalg.norm(q)
    q_normed = (q / norm).astype(np.float32).reshape(1, -1)
    print(f"  q_normed shape={q_normed.shape}, dtype={q_normed.dtype}")

    print("Step 7: FAISS search...")
    search_k = min(store._index.ntotal, 4)
    print(f"  search_k={search_k}")
    scores, ids = store._index.search(q_normed, search_k)
    print(f"  scores={scores}, ids={ids}")

    print("Step 8: Call store.query()...")
    results = store.query(
        query_text="What training objective does BERT use?",
        paper_ids=["test_paper_001"],
        top_k=2,
    )
    print(f"  Got {len(results)} results: {[r['paragraph_id'] for r in results]}")

print("ALL OK")
