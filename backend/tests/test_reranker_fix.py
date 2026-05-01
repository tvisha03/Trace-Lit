"""
Tests specifically for the reranker bug fix (tuple assignment).

This tests the fix for the critical bug:
Line 145: update_data = results_to_update.get(id(result)), {"score": -1.0, "source": None}
Fixed:   update_data = results_to_update.get(id(result)) or {"score": -1.0, "source": None}
"""

import pytest
from unittest.mock import patch, MagicMock
import numpy as np

from domain.verification.reranker import (
    rerank_claims,
    _find_best_matches,
    _apply_rerank_results,
)
from shared.enums import ConfidenceLevel


class TestRerankerBugFix:
    """Tests to verify the tuple assignment bug is fixed."""

    def test_get_with_missing_key_returns_default(self):
        """Verify .get() with or defaults works correctly when key is missing."""
        results_to_update = {}  # Empty dict - key will NOT be found

        # This is the FIXED version using `or`:
        result_id = id("some_object")
        update_data = results_to_update.get(result_id) or {
            "score": -1.0,
            "source": None,
        }

        # Should return default dict, not a tuple
        assert isinstance(update_data, dict)
        assert update_data["score"] == -1.0
        assert update_data["source"] is None

    def test_get_with_existing_key_returns_value(self):
        """Verify .get() returns existing value when key exists."""
        results_to_update = {}
        result_id = id("some_object")
        results_to_update[result_id] = {"score": 0.8, "source": {"text": "source"}}

        # Should return existing value
        update_data = results_to_update.get(result_id) or {
            "score": -1.0,
            "source": None,
        }

        assert update_data["score"] == 0.8
        assert update_data["source"]["text"] == "source"

    def test_rerank_with_uncertain_results_no_match(self):
        """Test reranking when uncertain results don't match any scored results.

        This was the crash scenario - when id(result) not in results_to_update.
        """
        uncertain_results = [
            {
                "claim": "claim1",
                "confidence": ConfidenceLevel.MEDIUM,
                "needs_reranking": True,
            },
            {
                "claim": "claim2",
                "confidence": ConfidenceLevel.MEDIUM,
                "needs_reranking": True,
            },
        ]

        # Create a mapping where NOT ALL results have matches
        # (simulating the bug scenario)
        with patch("domain.verification.reranker._get_cross_encoder") as mock_encoder:
            # Mock cross encoder
            mock_cross = MagicMock()
            mock_cross.predict.return_value = [0.5]  # Only one score for one claim
            mock_encoder.return_value = mock_cross

            # This should NOT crash now (was crashing before the fix)
            result = rerank_claims(
                uncertain_results,
                source_sentences=[{"text": "source", "paragraph_id": "p1"}],
            )

            # Should return results without crashing
            assert len(result) == 2


class TestFindBestMatches:
    """Tests for _find_best_matches function."""

    def test_single_claim_single_source(self):
        """Single claim with single source."""
        all_scores = [0.8]
        claim_map = [
            ({"claim": "test claim"}, {"text": "source text", "paragraph_id": "p1"})
        ]

        result = _find_best_matches(all_scores, claim_map)

        # Should find the best match
        res_id = id(claim_map[0][0])
        assert res_id in result
        assert result[res_id]["score"] == 0.8

    def test_multiple_sources_per_claim(self):
        """Multiple sources for same claim - should pick best score."""
        all_scores = [0.5, 0.9, 0.3]
        mock_result = {"claim": "test"}

        # Three sources for same claim
        claim_map = [
            (mock_result, {"text": "source1"}),
            (mock_result, {"text": "source2"}),
            (mock_result, {"text": "source3"}),
        ]

        result = _find_best_matches(all_scores, claim_map)

        res_id = id(mock_result)
        assert result[res_id]["score"] == 0.9  # Best score
        assert result[res_id]["source"]["text"] == "source2"

    def test_empty_scores(self):
        """Empty scores should return empty dict."""
        result = _find_best_matches([], [])
        assert result == {}


class TestApplyRerankResults:
    """Tests for _apply_rerank_results function."""

    def test_applies_correct_confidence_high(self):
        """Should set MEDIUM when score >= threshold."""
        result = {"confidence": ConfidenceLevel.MEDIUM, "needs_reranking": True}

        _apply_rerank_results(result, 5.0, {"text": "source"}, 0.75)

        assert result["needs_reranking"] is False
        # sigmoid(5) ≈ 0.993 > 0.75
        assert result["confidence"] == ConfidenceLevel.MEDIUM

    def test_applies_correct_confidence_low(self):
        """Should set LOW when score < threshold."""
        result = {"confidence": ConfidenceLevel.MEDIUM, "needs_reranking": True}

        _apply_rerank_results(result, -2.0, {"text": "source"}, 0.75)

        assert result["needs_reranking"] is False
        # sigmoid(-2) ≈ 0.119 < 0.75
        assert result["confidence"] == ConfidenceLevel.LOW

    def test_handles_none_source(self):
        """Should handle None source gracefully."""
        result = {"confidence": ConfidenceLevel.MEDIUM, "needs_reranking": True}

        _apply_rerank_results(result, 0.0, None, 0.75)

        # Should still set needs_reranking to False
        assert result["needs_reranking"] is False
        # Confidence should remain LOW when no source
        assert result["confidence"] == ConfidenceLevel.LOW


class TestCrossEncoderThreshold:
    """Tests for cross-encoder threshold behavior."""

    @patch("domain.verification.reranker._get_cross_encoder")
    def test_uses_settings_threshold(self, mock_get_encoder):
        """Should use settings.HAVF_CROSS_ENCODER_THRESHOLD by default."""
        mock_cross = MagicMock()
        mock_cross.predict.return_value = [2.0]  # sigmoid(2) ≈ 0.88
        mock_get_encoder.return_value = mock_cross

        uncertain_results = [{"claim": "test", "confidence": ConfidenceLevel.MEDIUM}]

        with patch("domain.verification.reranker.get_settings") as mock_settings:
            mock_settings.return_value.HAVF_CROSS_ENCODER_THRESHOLD = 0.75

            result = rerank_claims(
                uncertain_results,
                source_sentences=[{"text": "source", "paragraph_id": "p1"}],
            )

        # sigmoid(2) ≈ 0.88 > 0.75, so should be MEDIUM
        assert result[0]["confidence"] == ConfidenceLevel.MEDIUM

    @patch("domain.verification.reranker._get_cross_encoder")
    def test_custom_threshold_override(self, mock_get_encoder):
        """Should allow custom threshold override."""
        mock_cross = MagicMock()
        mock_cross.predict.return_value = [0.5]  # sigmoid(0.5) ≈ 0.62
        mock_get_encoder.return_value = mock_cross

        uncertain_results = [{"claim": "test", "confidence": ConfidenceLevel.MEDIUM}]

        # Use higher threshold - 0.62 < 0.80 should become LOW
        result = rerank_claims(
            uncertain_results,
            source_sentences=[{"text": "source", "paragraph_id": "p1"}],
            cross_encoder_threshold=0.80,
        )

        assert result[0]["confidence"] == ConfidenceLevel.LOW


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
