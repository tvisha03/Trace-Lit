"""TraceLit — Query Type Classification Tests.

Tests for the advanced query router with regex patterns.
"""

import pytest
from domain.generation.chat_engine import classify_query_type, get_retrieval_config


class TestClassifyQueryType:
    """Tests for classify_query_type()."""

    # -- Comparison --
    def test_compare_keyword(self):
        assert classify_query_type("Compare the methods used in both papers") == "comparison"

    def test_versus_keyword(self):
        assert classify_query_type("Transformer vs LSTM performance") == "comparison"

    def test_difference_keyword(self):
        assert classify_query_type("What are the differences between BERT and GPT?") == "comparison"

    def test_similar_keyword(self):
        assert classify_query_type("Are these two approaches similar?") == "comparison"

    # -- Summary --
    def test_summarize_keyword(self):
        assert classify_query_type("Summarize the paper") == "summary"

    def test_overview_keyword(self):
        assert classify_query_type("Give me an overview of the approach") == "summary"

    def test_key_findings(self):
        assert classify_query_type("What are the key findings?") == "summary"

    # -- Methodology --
    def test_method_keyword(self):
        assert classify_query_type("What method did they use?") == "methodology"

    def test_algorithm_keyword(self):
        assert classify_query_type("Explain the algorithm in detail") == "methodology"

    def test_how_did_they(self):
        assert classify_query_type("How did they train the model?") == "methodology"

    def test_architecture_keyword(self):
        assert classify_query_type("What is the model architecture?") == "methodology"

    # -- Multi-hop --
    def test_across_papers(self):
        assert classify_query_type("Across all papers, what trends do you see?") == "multi_hop"

    def test_common_theme(self):
        assert classify_query_type("What is the common thread between these results?") == "multi_hop"

    # -- Follow-up --
    def test_what_about(self):
        assert classify_query_type("What about the training data?") == "follow_up"

    def test_elaborate(self):
        assert classify_query_type("Can you elaborate on that point?") == "follow_up"

    def test_you_mentioned(self):
        assert classify_query_type("You mentioned attention earlier — explain more") == "follow_up"

    # -- Metadata --
    def test_who_authors(self):
        assert classify_query_type("Who are the authors?") == "metadata"

    def test_when_published(self):
        assert classify_query_type("When was this published?") == "metadata"

    def test_paper_title(self):
        assert classify_query_type("What is the title of the paper?") == "metadata"

    # -- Default (factual) --
    def test_factual_default(self):
        assert classify_query_type("What is the attention mechanism?") == "factual"

    def test_specific_question(self):
        assert classify_query_type("What BLEU score did they achieve?") == "factual"


class TestGetRetrievalConfig:
    """Tests for get_retrieval_config()."""

    def test_factual_config(self):
        config = get_retrieval_config("factual")
        assert config["top_k"] == 5
        assert config["havf_level"] == "full"

    def test_comparison_config(self):
        config = get_retrieval_config("comparison")
        assert config["top_k"] == 3

    def test_summary_config(self):
        config = get_retrieval_config("summary")
        assert config["top_k"] == 8
        assert config["havf_level"] == "basic"

    def test_unknown_type_falls_back(self):
        config = get_retrieval_config("nonexistent")
        assert config["top_k"] == 5  # falls back to factual
