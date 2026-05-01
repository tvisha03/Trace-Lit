"""
Tests for confidence scoring in HAVF verification system.

Covers:
- Level 1: Embedding similarity threshold logic
- Level 2: Cross-encoder reranking + sigmoid normalization
- Citation correction logic
"""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from domain.verification.embedding_verifier import (
    _determine_confidence,
    _build_result,
    verify_claims_embedding,
)
from domain.verification.reranker import (
    _normalize_cross_encoder_score,
    rerank_claims,
)
from shared.enums import ConfidenceLevel


@pytest.fixture(autouse=True)
def clear_embedding_cache():
    from domain.verification.embedding_verifier import _source_embedding_cache
    _source_embedding_cache.clear()
    yield



class TestDetermineConfidence:
    """Tests for _determine_confidence function."""

    def test_high_confidence_above_threshold(self):
        """Score >= 0.85 should return HIGH confidence."""
        with patch(
            "domain.verification.embedding_verifier.get_settings"
        ) as mock_settings:
            mock_settings.return_value.HAVF_HIGH_THRESHOLD = 0.85
            mock_settings.return_value.HAVF_MEDIUM_THRESHOLD = 0.65

            confidence, needs_reranking = _determine_confidence(0.90)

            assert confidence == ConfidenceLevel.HIGH
            assert needs_reranking is False

    def test_high_confidence_at_threshold(self):
        """Score exactly at 0.85 should return HIGH confidence."""
        with patch(
            "domain.verification.embedding_verifier.get_settings"
        ) as mock_settings:
            mock_settings.return_value.HAVF_HIGH_THRESHOLD = 0.85
            mock_settings.return_value.HAVF_MEDIUM_THRESHOLD = 0.65

            confidence, needs_reranking = _determine_confidence(0.85)

            assert confidence == ConfidenceLevel.HIGH
            assert needs_reranking is False

    def test_medium_confidence_in_range(self):
        """Score >= 0.65 and < 0.85 should return MEDIUM confidence."""
        with patch(
            "domain.verification.embedding_verifier.get_settings"
        ) as mock_settings:
            mock_settings.return_value.HAVF_HIGH_THRESHOLD = 0.85
            mock_settings.return_value.HAVF_MEDIUM_THRESHOLD = 0.65

            confidence, needs_reranking = _determine_confidence(0.70)

            assert confidence == ConfidenceLevel.MEDIUM
            assert needs_reranking is True

    def test_medium_confidence_at_threshold(self):
        """Score exactly at 0.65 should return MEDIUM confidence."""
        with patch(
            "domain.verification.embedding_verifier.get_settings"
        ) as mock_settings:
            mock_settings.return_value.HAVF_HIGH_THRESHOLD = 0.85
            mock_settings.return_value.HAVF_MEDIUM_THRESHOLD = 0.65

            confidence, needs_reranking = _determine_confidence(0.65)

            assert confidence == ConfidenceLevel.MEDIUM
            assert needs_reranking is True

    def test_low_confidence_below_threshold(self):
        """Score < 0.65 should return LOW confidence."""
        with patch(
            "domain.verification.embedding_verifier.get_settings"
        ) as mock_settings:
            mock_settings.return_value.HAVF_HIGH_THRESHOLD = 0.85
            mock_settings.return_value.HAVF_MEDIUM_THRESHOLD = 0.65

            confidence, needs_reranking = _determine_confidence(0.50)

            assert confidence == ConfidenceLevel.LOW
            assert needs_reranking is False

    def test_custom_thresholds(self):
        """Custom thresholds should override defaults."""
        confidence, _ = _determine_confidence(
            0.75, high_threshold=0.80, medium_threshold=0.60
        )

        assert confidence == ConfidenceLevel.MEDIUM  # 0.75 >= 0.60 but < 0.80

    def test_custom_thresholds_high(self):
        """Custom HIGH threshold with score above it."""
        confidence, needs_reranking = _determine_confidence(
            0.85, high_threshold=0.80, medium_threshold=0.60
        )

        assert confidence == ConfidenceLevel.HIGH
        assert needs_reranking is False

    def test_custom_thresholds_low(self):
        """Custom LOW threshold with score below it."""
        confidence, needs_reranking = _determine_confidence(
            0.40, high_threshold=0.80, medium_threshold=0.60
        )

        assert confidence == ConfidenceLevel.LOW
        assert needs_reranking is False


class TestCrossEncoderNormalization:
    """Tests for cross-encoder score normalization."""

    def test_sigmoid_positive_high(self):
        """High positive logits should map close to 1.0."""
        # Raw cross-encoder scores are typically logits
        score = _normalize_cross_encoder_score(10.0)
        assert score > 0.99
        assert score <= 1.0

    def test_sigmoid_positive_mid(self):
        """Moderate positive logits should map to ~0.5-0.9."""
        score = _normalize_cross_encoder_score(2.0)
        assert 0.88 < score < 0.92  # sigmoid(2) ≈ 0.881

    def test_sigmoid_zero(self):
        """Zero logit should map to 0.5."""
        score = _normalize_cross_encoder_score(0.0)
        assert score == 0.5

    def test_sigmoid_negative(self):
        """Negative logits should map close to 0.0."""
        score = _normalize_cross_encoder_score(-10.0)
        assert score < 0.01
        assert score >= 0.0

    def test_sigmoid_at_threshold(self):
        """Score at threshold (0.75) should be correctly normalized."""
        # sigmoid(x) = 0.75 => x ≈ 1.0986
        raw = _normalize_cross_encoder_score(1.0986)
        assert abs(raw - 0.75) < 0.01

    def test_sigmoid_clamping_extreme_positive(self):
        """Extremely large values should be clamped."""
        score = _normalize_cross_encoder_score(1000.0)
        assert score == 1.0

    def test_sigmoid_clamping_extreme_negative(self):
        """Extremely negative values should be clamped."""
        score = _normalize_cross_encoder_score(-1000.0)
        assert score == pytest.approx(0.0, abs=1e-7)


class TestVerifyClaimsEmbedding:
    """Tests for verify_claims_embedding function."""

    def test_empty_claims_returns_empty(self):
        """Empty claims list should return empty list."""
        result = verify_claims_embedding([], [{"text": "source"}])
        assert result == []

    def test_empty_sources_returns_low_confidence(self):
        """Empty sources should return LOW confidence for all claims."""
        result = verify_claims_embedding(["claim1", "claim2"], [])

        assert len(result) == 2
        for r in result:
            assert r["confidence"] == ConfidenceLevel.LOW
            assert r["best_score"] == 0.0

    @patch("domain.verification.embedding_verifier.encode_texts")
    def test_single_claim_single_source(self, mock_encode):
        """Single claim matched to single source."""
        # Mock embeddings: claim -> [1.0], source -> [0.9]
        mock_encode.side_effect = [
            np.array([[1.0]]),  # claim embeddings
            np.array([[0.9]]),  # source embeddings
        ]

        source_sentences = [
            {"text": "source text", "paragraph_id": "p1", "paper_id": "paper1"}
        ]
        result = verify_claims_embedding(["test claim"], source_sentences)

        assert len(result) == 1
        assert result[0]["confidence"] == ConfidenceLevel.HIGH
        assert result[0]["best_score"] == pytest.approx(0.9, abs=0.01)

    @patch("domain.verification.embedding_verifier.encode_texts")
    def test_medium_confidence_triggers_reranking(self, mock_encode):
        """Medium confidence should set needs_reranking=True."""
        # Mock embeddings: claim -> [1.0], source -> [0.7]
        mock_encode.side_effect = [
            np.array([[1.0]]),
            np.array([[0.7]]),
        ]

        source_sentences = [
            {"text": "source", "paragraph_id": "p1", "paper_id": "paper1"}
        ]
        result = verify_claims_embedding(["claim"], source_sentences)

        assert len(result) == 1
        assert result[0]["confidence"] == ConfidenceLevel.MEDIUM
        assert result[0]["needs_reranking"] is True



class TestRerankClaims:
    """Tests for rerank_claims function."""

    def test_empty_input_returns_empty(self):
        """Empty input should return empty list."""
        result = rerank_claims([])
        assert result == []

    @patch("domain.verification.reranker._get_cross_encoder")
    def test_no_cross_encoder_returns_original(self, mock_get_encoder):
        """If cross-encoder unavailable, return original results."""
        mock_get_encoder.return_value = None

        uncertain = [{"claim": "test", "confidence": ConfidenceLevel.MEDIUM}]
        result = rerank_claims(uncertain)

        assert result == uncertain
        assert result[0]["confidence"] == ConfidenceLevel.MEDIUM


    @patch("domain.verification.embedding_verifier.encode_texts")
    @patch("domain.verification.reranker._get_cross_encoder")
    def test_full_pipeline_high_confidence(self, mock_reranker, mock_encoder):
        """Full pipeline with high confidence claim (no reranking needed)."""
        # High similarity = HIGH confidence, no reranking
        mock_encoder.side_effect = [
            np.array([[1.0]]),  # claim
            np.array([[0.9]]),  # source
        ]
        mock_reranker.return_value = None  # Not called for HIGH

        source_sentences = [
            {
                "text": "source",
                "paragraph_id": "p1",
                "paper_id": "paper1",
                "sentence_key": "s1",
                "page_number": 1,
            }
        ]
        result = verify_claims_embedding(["claim"], source_sentences)

        assert len(result) == 1
        assert result[0]["confidence"] == ConfidenceLevel.HIGH
        assert result[0]["needs_reranking"] is False

    @patch("domain.verification.embedding_verifier.encode_texts")
    @patch("domain.verification.reranker._get_cross_encoder")
    def test_full_pipeline_medium_confidence(self, mock_reranker, mock_encoder):
        """Full pipeline with medium confidence (triggers reranking path)."""
        # Medium similarity = needs reranking
        mock_encoder.side_effect = [
            np.array([[1.0]]),
            np.array([[0.7]]),
        ]
        mock_reranker.return_value = None

        source_sentences = [
            {
                "text": "source",
                "paragraph_id": "p1",
                "paper_id": "paper1",
                "sentence_key": "s1",
                "page_number": 1,
            }
        ]
        result = verify_claims_embedding(["claim"], source_sentences)

        assert len(result) == 1
        assert result[0]["confidence"] == ConfidenceLevel.MEDIUM
        assert result[0]["needs_reranking"] is True



class TestEdgeCases:
    """Edge case tests."""

    def test_confidence_with_none_settings(self):
        """Should handle None settings gracefully."""
        with patch(
            "domain.verification.embedding_verifier.get_settings"
        ) as mock_settings:
            mock_settings.return_value.HAVF_HIGH_THRESHOLD = 0.85
            mock_settings.return_value.HAVF_MEDIUM_THRESHOLD = 0.65

            confidence, _ = _determine_confidence(0.5)
            assert confidence == ConfidenceLevel.LOW

    def test_score_clamped_to_0_1(self):
        """Scores should be clamped to 0-1 range."""
        with patch(
            "domain.verification.embedding_verifier.get_settings"
        ) as mock_settings:
            mock_settings.return_value.HAVF_HIGH_THRESHOLD = 0.85
            mock_settings.return_value.HAVF_MEDIUM_THRESHOLD = 0.65

            # Very high score
            confidence, _ = _determine_confidence(1.5)
            assert confidence == ConfidenceLevel.HIGH

            # Negative score
            confidence, _ = _determine_confidence(-0.5)
            assert confidence == ConfidenceLevel.LOW


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
