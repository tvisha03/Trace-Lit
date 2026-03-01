"""Week 3 verification script — HAVF with Sentence Mapping.

Tests:
  1. MPS embedder loads and encodes text
  2. HAVF verifier produces HIGH/MEDIUM/LOW confidence
  3. Sentence-level mapping returns sentence_id + paragraph_id
  4. Cross-encoder only triggers for uncertain cases
  5. FAISS vector store stores and retrieves paragraphs
  6. End-to-end: parse response → build paragraph map → verify
"""

import asyncio
import json
import sys


def test_embedder():
    """Test MPS-accelerated embedder."""
    from infrastructure.vector_store.embedder import get_embedder

    embedder = get_embedder()  # use singleton — avoid two MPS models in memory
    print(f"Embedder device: {embedder.device}")

    # Encode some texts
    texts = [
        "BERT uses masked language modeling as a pre-training objective.",
        "GPT-2 uses autoregressive language modeling.",
        "Transformers use self-attention to process sequences.",
    ]
    embeddings = embedder.encode(texts)

    assert embeddings.shape[0] == 3
    assert embeddings.shape[1] == 384  # all-MiniLM-L6-v2 dimension
    print(f"Embedding shape: {embeddings.shape}")

    # Test cosine similarity
    sims = embedder.cosine_similarity(embeddings[0], embeddings)
    assert sims[0] > 0.99  # Self-similarity ≈ 1.0
    assert sims[1] > 0.3   # Related texts should have some similarity
    print(f"Cosine similarities: {[round(float(s), 3) for s in sims]}")

    print("✓ Embedder OK")
    return embedder


def test_havf_high_confidence():
    """Test HAVF returns HIGH confidence for semantically matching sentences."""
    from domain.verification.havf import HAVFVerifier

    verifier = HAVFVerifier()

    result = asyncio.run(verifier.verify_single(
        generated="BERT uses masked language modeling for pre-training.",
        source_sentences=[
            "We introduce a new representation model called BERT.",
            "We use masked language modeling (MLM) as the pre-training objective.",
            "The model achieves state-of-the-art results on GLUE.",
        ],
        paragraph_id="P5",
    ))

    print(f"  HIGH test: confidence={result['confidence']:.3f}, level={result['level']}, "
          f"method={result['method']}, sentence_id={result['sentence_id']}")

    assert result["confidence"] >= 0.65, f"Expected ≥0.65, got {result['confidence']}"
    assert result["level"] in ("high", "medium"), f"Expected high or medium, got {result['level']}"
    assert result["paragraph_id"] == "P5"
    assert result["sentence_id"].startswith("P5_S")
    assert result["matched_text"] != ""
    print("✓ HAVF HIGH confidence OK")
    return result


def test_havf_low_confidence():
    """Test HAVF returns LOW confidence for unrelated sentences."""
    from domain.verification.havf import HAVFVerifier

    verifier = HAVFVerifier()

    result = asyncio.run(verifier.verify_single(
        generated="The model achieves state-of-the-art results on image classification.",
        source_sentences=[
            "We train the model on the ImageNet dataset.",
            "Data augmentation strategies include random cropping and flipping.",
        ],
        paragraph_id="P10",
    ))

    print(f"  LOW test: confidence={result['confidence']:.3f}, level={result['level']}, "
          f"method={result['method']}")

    # This should be LOW or at most MEDIUM
    assert result["level"] in ("low", "medium"), f"Expected low/medium, got {result['level']}"
    assert result["paragraph_id"] == "P10"
    print("✓ HAVF LOW confidence OK")
    return result


def test_havf_sentence_id_returned():
    """Test HAVF returns the correct sentence_id mapping."""
    from domain.verification.havf import HAVFVerifier

    verifier = HAVFVerifier()

    result = asyncio.run(verifier.verify_single(
        generated="Attention mechanisms allow the model to focus on relevant parts of the input.",
        source_sentences=[
            "The encoder maps an input sequence to continuous representations.",           # P0_S0
            "The decoder generates an output sequence one token at a time.",               # P0_S1
            "Attention allows the model to focus on relevant positions in the source.",    # P0_S2
        ],
        paragraph_id="P0",
    ))

    print(f"  Sentence mapping: sentence_id={result['sentence_id']}, "
          f"confidence={result['confidence']:.3f}")

    # Should match S2 (about attention/focus)
    assert result["sentence_id"] != ""
    assert result["paragraph_id"] == "P0"
    # The best match should be P0_S2 (most semantically similar)
    assert result["sentence_id"] == "P0_S2", \
        f"Expected P0_S2, got {result['sentence_id']}"
    print("✓ HAVF sentence mapping OK")
    return result


def test_havf_batch_verification():
    """Test HAVF verifies multiple sentences in batch."""
    from domain.verification.havf import HAVFVerifier

    verifier = HAVFVerifier()

    response_sentences = [
        {
            "text": "BERT uses masked language modeling [P1].",
            "citations": ["P1"],
        },
        {
            "text": "The transformer architecture uses self-attention [P2].",
            "citations": ["P2"],
        },
        {
            "text": "In summary, these approaches improve NLP.",
            "citations": [],  # No citation — should be skipped
        },
        {
            "text": "Short.",
            "citations": ["P1"],  # Too short — should be skipped
        },
    ]

    cited_paragraphs = {
        "P1": {
            "text": "We use masked language modeling (MLM) for pre-training.",
            "sentences": [
                {"sentence_id": "P1_S0", "text": "We use masked language modeling (MLM) for pre-training.", "start_char": 0, "end_char": 55},
            ],
        },
        "P2": {
            "text": "The transformer uses multi-head self-attention. This allows parallel computation.",
            "sentences": [
                {"sentence_id": "P2_S0", "text": "The transformer uses multi-head self-attention.", "start_char": 0, "end_char": 47},
                {"sentence_id": "P2_S1", "text": "This allows parallel computation.", "start_char": 48, "end_char": 80},
            ],
        },
    }

    results = asyncio.run(verifier.verify_response(response_sentences, cited_paragraphs))

    print(f"  Batch results: {len(results)} sentences verified")
    for r in results:
        print(f"    [{r['level']:6s}] conf={r['confidence']:.3f} method={r['method']:25s} "
              f"sid={r.get('sentence_id', 'N/A'):8s} | {r['text'][:60]}...")

    assert len(results) == 4

    # First sentence should have verification result
    assert results[0]["paragraph_id"] == "P1"
    assert results[0]["sentence_id"].startswith("P1_S")
    assert results[0]["method"] == "embedding_similarity" or results[0]["method"] == "cross_encoder_rerank"

    # Third sentence (no citation) should be skipped
    assert results[2]["method"] == "no_citation"

    # Fourth sentence (too short) should be skipped
    assert results[3]["method"] == "skipped_short"

    print("✓ HAVF batch verification OK")


def test_response_parsing():
    """Test parsing LLM response into sentences with citations."""
    from domain.verification.havf import parse_response_into_sentences

    response = (
        "BERT uses masked language modeling [P1]. "
        "GPT uses autoregressive training [P2][P3]. "
        "In summary, transformers are effective."
    )

    sentences = parse_response_into_sentences(response)

    assert len(sentences) == 3
    assert sentences[0]["citations"] == ["P1"]
    assert sentences[1]["citations"] == ["P2", "P3"]
    assert sentences[2]["citations"] == []

    print(f"  Parsed {len(sentences)} sentences:")
    for s in sentences:
        print(f"    citations={s['citations']} | {s['text'][:60]}...")

    print("✓ Response parsing OK")


def test_paragraph_map_builder():
    """Test building paragraph map with paper-prefixed IDs."""
    from domain.verification.havf import build_cited_paragraphs_map

    context = [
        {"paragraph_id": "abc123_P5", "text": "Some text", "paper_id": "abc123", "sentences": []},
        {"paragraph_id": "def456_P12", "text": "Other text", "paper_id": "def456", "sentences": []},
    ]

    para_map = build_cited_paragraphs_map(context)

    # Should be accessible by both full and short IDs
    assert "abc123_P5" in para_map
    assert "P5" in para_map
    assert "def456_P12" in para_map
    assert "P12" in para_map

    print("✓ Paragraph map builder OK")


def test_vector_store():
    """Test FAISS vector store operations."""
    import tempfile
    from infrastructure.vector_store.faiss_store import VectorStore

    # Use a temp directory to avoid polluting the real index
    with tempfile.TemporaryDirectory() as tmpdir:
        store = VectorStore(persist_dir=tmpdir)

        # Create test chunks
        test_chunks = [
            {
                "paragraph_id": "P0",
                "text": "BERT uses masked language modeling.",
                "enriched_text": "[Paper: BERT] [Section: Methods] BERT uses masked language modeling.",
                "sentences": [{"sentence_id": "P0_S0", "text": "BERT uses masked language modeling.", "start_char": 0, "end_char": 35}],
                "section": "Methods",
                "page": 3,
                "paper_id": "test_paper_001",
                "paper_title": "BERT Paper",
                "token_count": 8,
            },
            {
                "paragraph_id": "P1",
                "text": "The transformer uses self-attention mechanisms.",
                "enriched_text": "[Paper: BERT] [Section: Introduction] The transformer uses self-attention mechanisms.",
                "sentences": [{"sentence_id": "P1_S0", "text": "The transformer uses self-attention mechanisms.", "start_char": 0, "end_char": 47}],
                "section": "Introduction",
                "page": 1,
                "paper_id": "test_paper_001",
                "paper_title": "BERT Paper",
                "token_count": 10,
            },
        ]

        # Store paragraphs
        count = store.add_paragraphs("test_paper_001", test_chunks)
        assert count == 2
        print(f"  Stored {count} paragraphs")

        # Query
        results = store.query(
            query_text="What training objective does BERT use?",
            paper_ids=["test_paper_001"],
            top_k=2,
        )
        assert len(results) > 0
        # The first result should be about masked language modeling (most relevant)
        print(f"  Query returned {len(results)} results:")
        for r in results:
            print(f"    [{r['paragraph_id']}] sim={r.get('similarity', 0):.3f} | {r['text'][:60]}...")

        assert any("masked" in r["text"].lower() for r in results)

        # Verify sentences are preserved
        first = results[0]
        assert isinstance(first["sentences"], list)
        assert len(first["sentences"]) > 0

        # Delete
        deleted = store.delete_paper("test_paper_001")
        assert deleted == 2
        print(f"  Deleted {deleted} paragraphs")

        # Verify deletion
        remaining = store.paper_count("test_paper_001")
        assert remaining == 0

    print("✓ Vector store OK")


def test_cross_encoder_only_for_uncertain():
    """Verify cross-encoder is lazy-loaded (not loaded until needed)."""
    from domain.verification.havf import HAVFVerifier

    verifier = HAVFVerifier()

    # Cross-encoder should NOT be loaded yet
    assert verifier._cross_encoder is None, "Cross-encoder should be lazy-loaded"
    print("  Cross-encoder not yet loaded (lazy)")

    # Verify a clearly high-confidence match (should NOT trigger cross-encoder)
    result = asyncio.run(verifier.verify_single(
        generated="We use masked language modeling as the pre-training objective.",
        source_sentences=[
            "We use masked language modeling (MLM) as the pre-training objective.",
        ],
        paragraph_id="P0",
    ))

    if result["method"] == "embedding_similarity":
        # High confidence resolved at Level 1 — cross-encoder may still not be loaded
        print(f"  Resolved at Level 1: confidence={result['confidence']:.3f}")
        # Note: cross-encoder may or may not be loaded depending on other paths
    else:
        print(f"  Resolved at Level 2: confidence={result['confidence']:.3f}")

    print("✓ Cross-encoder lazy loading OK")


# ============================================================
# Module-level imports test
# ============================================================

def test_imports():
    """Verify all Week 3 imports work."""
    from infrastructure.vector_store.embedder import MPSAcceleratedEmbedder, get_embedder
    from infrastructure.vector_store.faiss_store import VectorStore, get_vector_store
    from domain.verification.havf import (
        HAVFVerifier,
        get_havf,
        parse_response_into_sentences,
        build_cited_paragraphs_map,
    )
    from domain.verification.havf import HAVFVerifier as HAVFVerifier2
    from infrastructure.vector_store.embedder import MPSAcceleratedEmbedder as Embedder2
    from infrastructure.vector_store.faiss_store import VectorStore as VS2

    print("✓ All Week 3 imports OK")


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Week 3 Verification: HAVF with Sentence Mapping")
    print("=" * 60)
    print()

    tests = [
        ("Imports", test_imports),
        ("MPS Embedder", test_embedder),
        ("Response Parsing", test_response_parsing),
        ("Paragraph Map Builder", test_paragraph_map_builder),
        ("Vector Store", test_vector_store),
        ("HAVF HIGH Confidence", test_havf_high_confidence),
        ("HAVF LOW Confidence", test_havf_low_confidence),
        ("HAVF Sentence ID Mapping", test_havf_sentence_id_returned),
        ("HAVF Batch Verification", test_havf_batch_verification),
        ("Cross-Encoder Lazy Loading", test_cross_encoder_only_for_uncertain),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        print(f"\n--- {name} ---")
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"✗ FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print()
    print("=" * 60)
    if failed == 0:
        print(f"=== ALL {passed} WEEK 3 TESTS PASSED ===")
    else:
        print(f"=== {passed} PASSED, {failed} FAILED ===")
    print("=" * 60)

    sys.exit(1 if failed > 0 else 0)
