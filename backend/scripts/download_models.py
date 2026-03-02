def main():
    print("=" * 60)
    print("Trace-Lit Model Downloader")
    print("=" * 60)

    print("\n[1/2] Downloading embedding model: all-MiniLM-L6-v2 ...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")
    print(f"  ✓ Loaded ({model.get_sentence_embedding_dimension()} dims)")

    print("\n[2/2] Downloading cross-encoder: cross-encoder/ms-marco-MiniLM-L-6-v2 ...")
    from sentence_transformers import CrossEncoder
    CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    print("  ✓ Loaded")

    print("\n" + "=" * 60)
    print("All models downloaded successfully.")
    print("=" * 60)

if __name__ == "__main__":
    main()
