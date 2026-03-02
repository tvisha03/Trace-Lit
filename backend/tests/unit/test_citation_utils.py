"""TraceLit — Citation Parser Unit Tests.

Tests for citation extraction, validation, and removal.
Target coverage: 95%.
"""

import pytest
from domain.generation.citation_utils import (
    extract_citations,
    validate_citations,
    remove_invalid_citations,
    _is_factual_claim,
    _split_response_sentences,
)


class TestExtractCitations:
    """Tests for extract_citations()."""

    def test_single_citation(self):
        assert extract_citations("This is true [P1].") == ["P1"]

    def test_multiple_citations(self):
        result = extract_citations("Claim A [P1]. Claim B [P2]. Also [P3].")
        assert result == ["P1", "P2", "P3"]

    def test_duplicate_citations(self):
        result = extract_citations("[P1] and again [P1].")
        assert result == ["P1", "P1"]

    def test_no_citations(self):
        assert extract_citations("No citations here.") == []

    def test_multi_digit_ids(self):
        result = extract_citations("Result [P123] is significant.")
        assert result == ["P123"]

    def test_adjacent_citations(self):
        result = extract_citations("Combined [P1][P2][P3].")
        assert result == ["P1", "P2", "P3"]

    def test_empty_string(self):
        assert extract_citations("") == []

    def test_malformed_not_matched(self):
        # These should NOT be matched
        assert extract_citations("[p1]") == []  # lowercase
        assert extract_citations("[P]") == []   # no number
        assert extract_citations("P1") == []    # no brackets


class TestValidateCitations:
    """Tests for validate_citations()."""

    def test_all_valid(self):
        result = validate_citations(
            "Claim [P1]. Another [P2].",
            {"P1", "P2", "P3"},
        )
        assert result["invalid_citations"] == set()
        assert result["valid_citations"] == {"P1", "P2"}

    def test_with_invalid(self):
        result = validate_citations(
            "Claim [P1]. Hallucinated [P99].",
            {"P1", "P2"},
        )
        assert "P99" in result["invalid_citations"]
        assert "P1" in result["valid_citations"]

    def test_coverage_calculation(self):
        result = validate_citations(
            "Valid [P1]. Invalid [P99].",
            {"P1"},
        )
        assert result["citation_coverage"] == 0.5

    def test_no_citations_coverage(self):
        result = validate_citations("No citations here.", {"P1"})
        assert result["citation_coverage"] == 0.0

    def test_uncited_factual_sentences(self):
        result = validate_citations(
            "This has no citation. But this one does [P1].",
            {"P1"},
        )
        assert len(result["uncited_factual_sentences"]) >= 1


class TestRemoveInvalidCitations:
    """Tests for remove_invalid_citations()."""

    def test_removes_invalid(self):
        result = remove_invalid_citations("Good [P1]. Bad [P99].", {"P99"})
        assert "[P99]" not in result
        assert "[P1]" in result

    def test_no_invalid(self):
        text = "All good [P1]."
        assert remove_invalid_citations(text, set()) == text

    def test_multiple_invalid(self):
        result = remove_invalid_citations(
            "A [P98]. B [P99]. C [P1].",
            {"P98", "P99"},
        )
        assert "[P98]" not in result
        assert "[P99]" not in result
        assert "[P1]" in result


class TestIsFactualClaim:
    """Tests for _is_factual_claim()."""

    def test_factual_statement(self):
        assert _is_factual_claim("The model achieves 95% accuracy.")

    def test_transitional_summary(self):
        assert not _is_factual_claim("In summary, the results show improvement.")

    def test_transitional_overall(self):
        assert not _is_factual_claim("Overall, the approach is effective.")

    def test_not_found_response(self):
        assert not _is_factual_claim("This information was not found in the provided papers.")


class TestSplitResponseSentences:
    """Tests for _split_response_sentences()."""

    def test_basic_split(self):
        result = _split_response_sentences("First sentence. Second sentence. Third.")
        assert len(result) == 3

    def test_abbreviations_preserved(self):
        result = _split_response_sentences("Dr. Smith et al. found that the method works.")
        # Should not split on "Dr." or "al."
        assert len(result) <= 2

    def test_empty_string(self):
        assert _split_response_sentences("") == []

    def test_single_sentence(self):
        result = _split_response_sentences("Just one sentence.")
        assert len(result) == 1
