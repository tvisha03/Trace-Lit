"""
Download required ML models ahead of time.
Run this once before starting the server to avoid first-request latency.

Usage:
    python -m scripts.download_models
"""

import sys


def main():
    print("=" * 60)
    print("Trace-Lit Model Downloader")
    print("=" * 60)

    # 1. Embedding model (all-MiniLM-L6-v2, ~23 MB)
    print("\n[1/2] Downloading embedding model: all-MiniLM-L6-v2 ...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")
    print(f"  ✓ Loaded ({model.get_sentence_embedding_dimension()} dims)")

    # 2. Cross-encoder (ms-marco-MiniLM-L-6-v2, ~80 MB)
    print("\n[2/2] Downloading cross-encoder: cross-encoder/ms-marco-MiniLM-L-6-v2 ...")
    from sentence_transformers import CrossEncoder
    ce = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    print("  ✓ Loaded")

    print("\n" + "=" * 60)
    print("All models downloaded successfully.")
    print("=" * 60)


if __name__ == "__main__":
    main()
