"""
Pytest configuration and fixtures for TraceLit tests.
"""

import pytest
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    from unittest.mock import MagicMock

    settings = MagicMock()
    settings.HAVF_HIGH_THRESHOLD = 0.85
    settings.HAVF_MEDIUM_THRESHOLD = 0.65
    settings.HAVF_CROSS_ENCODER_THRESHOLD = 0.75
    settings.EMBEDDING_MODEL = "all-MiniLM-L6-v2"
    settings.CROSS_ENCODER_MODEL = "BAAI/bge-reranker-base"
    return settings


@pytest.fixture
def sample_source_sentences():
    """Sample source sentences for testing."""
    return [
        {
            "text": "This is a sample source text from the paper.",
            "paragraph_id": "abc12345_P1",
            "paper_id": "paper-123",
            "sentence_key": "s1",
            "page_number": 1,
        },
        {
            "text": "Another paragraph with important information.",
            "paragraph_id": "abc12345_P2",
            "paper_id": "paper-123",
            "sentence_key": "s2",
            "page_number": 2,
        },
    ]


@pytest.fixture
def sample_claims():
    """Sample claims for testing."""
    return [
        "This is a claim that needs verification.",
        "Another claim from the user query.",
    ]


@pytest.fixture
def mock_faiss_store():
    """Mock FAISS store for testing."""
    from unittest.mock import MagicMock

    store = MagicMock()
    store.is_ready.return_value = True
    store.search.return_value = [
        {"paper_id": "paper-123", "paragraph_id": "abc12345_P1", "score": 0.9},
    ]
    return store
