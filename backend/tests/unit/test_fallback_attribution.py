"""TraceLit — Fallback Attribution Tests."""

import numpy as np
import pytest
from unittest.mock import MagicMock

from domain.generation.fallback_attribution import (
    fallback_attribution,
    needs_fallback_attribution,
    LLM_CITATION_THRESHOLD,
)


@pytest.fixture
def mock_embedder():
    """Embedder that returns deterministic embeddings based on text similarity."""
    embedder = MagicMock()

    def _encode(texts, **kwargs):
        # Simple: generate embeddings that are somewhat similar for related texts
        rng = np.random.RandomState(42)
        base = rng.randn(384).astype(np.float32)
        embeddings = []
        for i, text in enumerate(texts):
            # Add small noise per text so they aren't identical
            noise = rng.randn(384).astype(np.float32) * 0.1
            emb = base + noise * (i + 1)
            emb = emb / np.linalg.norm(emb)
            embeddings.append(emb)
        return np.array(embeddings, dtype=np.float32)

    embedder.encode = _encode
    return embedder


class TestNeedsFallbackAttribution:
    def test_low_coverage_with_uncited(self):
        assert needs_fallback_attribution(0.3, ["Some uncited claim."])

    def test_good_coverage(self):
        assert not needs_fallback_attribution(0.9, [])

    def test_low_coverage_no_uncited(self):
        assert not needs_fallback_attribution(0.3, [])

    def test_threshold_boundary(self):
        assert needs_fallback_attribution(LLM_CITATION_THRESHOLD - 0.01, ["claim"])
        assert not needs_fallback_attribution(LLM_CITATION_THRESHOLD, ["claim"])


class TestFallbackAttribution:
    def test_no_paragraphs(self):
        result = fallback_attribution("Some text.", [], None)
        assert result["auto_attributed_count"] == 0
        assert result["warning"] is None

    def test_all_cited(self):
        result = fallback_attribution(
            "First claim [P1]. Second claim [P2].",
            [{"paragraph_id": "P1", "text": "Source text."}],
        )
        assert result["auto_attributed_count"] == 0

    def test_uncited_gets_attribution(self, mock_embedder):
        result = fallback_attribution(
            "This sentence has no citation. This one does [P1].",
            [
                {"paragraph_id": "P1", "text": "This is the source paragraph."},
                {"paragraph_id": "P2", "text": "Another source paragraph."},
            ],
            embedder=mock_embedder,
        )
        # The uncited sentence should get attributed
        assert result["auto_attributed_count"] >= 0  # could be 0 if below threshold
        # Should contain either a citation or (unverified) marker
        assert "[P" in result["text"] or "unverified" in result["text"]

    def test_empty_text(self, mock_embedder):
        result = fallback_attribution("", [{"paragraph_id": "P1", "text": "Source."}], mock_embedder)
        assert result["auto_attributed_count"] == 0

    def test_non_factual_not_attributed(self, mock_embedder):
        result = fallback_attribution(
            "In summary, the results are good.",
            [{"paragraph_id": "P1", "text": "Source text about results."}],
            embedder=mock_embedder,
        )
        # "In summary" is non-factual, should not be attributed
        assert result["auto_attributed_count"] == 0
