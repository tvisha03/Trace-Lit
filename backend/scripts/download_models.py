def main():
    print("=" * 60)
    print("Trace-Lit Model Downloader")
    print("=" * 60)

    print("\n[1/2] Downloading embedding model: mixedbread-ai/mxbai-embed-large-v1 ...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("mixedbread-ai/mxbai-embed-large-v1")
    print(f"  ✓ Loaded ({model.get_sentence_embedding_dimension()} dims)")

    print("\n[2/2] Downloading cross-encoder: BAAI/bge-reranker-base ...")
    from sentence_transformers import CrossEncoder
    CrossEncoder("BAAI/bge-reranker-base")
    print("  ✓ Loaded")

    print("\n" + "=" * 60)
    print("All models downloaded successfully.")
    print("=" * 60)

if __name__ == "__main__":
    main()
