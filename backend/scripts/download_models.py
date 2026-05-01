def main():
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app.config import get_settings
    settings = get_settings()

    print("=" * 60)
    print("Trace-Lit Model Downloader")
    print("=" * 60)

    print(f"\n[1/3] Downloading embedding model: {settings.EMBEDDING_MODEL} ...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(settings.EMBEDDING_MODEL)
    print(f"  ✓ Loaded ({model.get_sentence_embedding_dimension()} dims)")

    print(f"\n[2/3] Downloading cross-encoder: {settings.CROSS_ENCODER_MODEL} ...")
    from sentence_transformers import CrossEncoder
    CrossEncoder(settings.CROSS_ENCODER_MODEL)
    print("  ✓ Loaded")

    print(f"\n[3/3] Downloading KeyBERT model: {settings.KEYBERT_MODEL} ...")
    from keybert import KeyBERT
    KeyBERT(model=settings.KEYBERT_MODEL)
    print("  ✓ Loaded")

    print("\n" + "=" * 60)
    print("All models downloaded successfully.")
    print("=" * 60)

if __name__ == "__main__":
    main()
