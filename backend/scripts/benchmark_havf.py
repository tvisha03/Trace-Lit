"""
HAVF Benchmark — measures verification accuracy, latency, and throughput.

Usage:
    python -m scripts.benchmark_havf
"""

import time
from domain.retrieval.indexer import encode_texts


def benchmark_embedding_similarity():
    """Benchmark Level 1 (embedding) verification speed."""
    print("=" * 60)
    print("HAVF Level 1 — Embedding Similarity Benchmark")
    print("=" * 60)

    # Simulate 10 claims and 100 source sentences
    claims = [f"This is test claim number {i} about machine learning." for i in range(10)]
    sources = [f"Source sentence {i} discussing deep learning methods and results." for i in range(100)]

    # Encode
    start = time.perf_counter()
    claim_vecs = encode_texts(claims)
    source_vecs = encode_texts(sources)
    encode_time = time.perf_counter() - start

    # Similarity
    start = time.perf_counter()
    sim_matrix = claim_vecs @ source_vecs.T
    sim_time = time.perf_counter() - start

    print(f"  Encode {len(claims)} claims + {len(sources)} sources: {encode_time*1000:.1f}ms")
    print(f"  Similarity matrix ({sim_matrix.shape}): {sim_time*1000:.3f}ms")
    print(f"  Total Level 1 latency: {(encode_time + sim_time)*1000:.1f}ms")
    print(f"  Claims/sec: {len(claims) / (encode_time + sim_time):.0f}")


def benchmark_cross_encoder():
    """Benchmark Level 2 (cross-encoder) reranking speed."""
    print("\n" + "=" * 60)
    print("HAVF Level 2 — Cross-Encoder Reranking Benchmark")
    print("=" * 60)

    from sentence_transformers import CrossEncoder
    ce = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

    pairs = [
        ("Transformer models use self-attention.", "Self-attention is a key component of transformers.")
        for _ in range(10)
    ]

    start = time.perf_counter()
    scores = ce.predict(pairs)
    elapsed = time.perf_counter() - start

    print(f"  Rerank {len(pairs)} pairs: {elapsed*1000:.1f}ms")
    print(f"  Avg per pair: {elapsed/len(pairs)*1000:.1f}ms")
    print(f"  Score range: [{float(scores.min()):.3f}, {float(scores.max()):.3f}]")


if __name__ == "__main__":
    benchmark_embedding_similarity()
    benchmark_cross_encoder()
    print("\nBenchmark complete.")
