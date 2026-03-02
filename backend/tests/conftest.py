"""TraceLit — Test Configuration & Fixtures.

Provides async fixtures, test database, and mock clients for all test suites.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

# Ensure backend root is on the path
BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# ============================================================
# Test Database
# ============================================================

TEST_DATABASE_URL = "sqlite:///./test_tracelit.db"


@pytest.fixture(scope="session")
def test_engine():
    """Create a test database engine."""
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    from infrastructure.db.database import Base
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)

    # Cleanup test DB file
    db_path = Path("./test_tracelit.db")
    for f in [db_path, db_path.with_suffix(".db-wal"), db_path.with_suffix(".db-shm")]:
        if f.exists():
            f.unlink()


@pytest.fixture
def db_session(test_engine) -> Generator[Session, None, None]:
    """Provide a transactional test database session.

    Each test gets a clean session that rolls back on completion.
    """
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# ============================================================
# FastAPI Test Client
# ============================================================

@pytest.fixture
def app():
    """Create a test FastAPI application."""
    from app.main import app as fastapi_app
    return fastapi_app


@pytest.fixture
def test_client(app, db_session):
    """Provide an async HTTP test client.

    Overrides the database dependency to use the test session.
    """
    from httpx import AsyncClient, ASGITransport
    from app.dependencies import get_db

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    client = AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    )
    yield client
    app.dependency_overrides.clear()


# ============================================================
# Mock LLM Provider
# ============================================================

@pytest.fixture
def mock_llm():
    """Mock LLM that returns a canned response with citations."""
    mock = AsyncMock()
    mock.generate.return_value = {
        "text": "The model uses attention mechanisms [P1]. It was trained on a large corpus [P2].",
        "provider": "mock",
        "warning": None,
        "valid_paragraph_ids": {"P1", "P2"},
        "query_type": "factual",
        "citation_validation": {
            "valid_citations": {"P1", "P2"},
            "invalid_citations": set(),
            "uncited_factual_sentences": [],
            "citation_coverage": 1.0,
        },
    }
    mock.stream_with_fallback = AsyncMock(return_value=iter(["The model ", "uses attention [P1]."]))
    return mock


@pytest.fixture
def mock_embedder():
    """Mock embedder that returns random but consistent embeddings."""
    import numpy as np

    mock = MagicMock()
    mock.encode.side_effect = lambda texts, **kw: np.random.RandomState(42).randn(len(texts), 384).astype(np.float32)
    mock.encode_single.side_effect = lambda text, **kw: np.random.RandomState(42).randn(384).astype(np.float32)
    mock.embedding_dim = 384
    mock.is_loaded.return_value = True
    return mock


# ============================================================
# Sample Data Fixtures
# ============================================================

@pytest.fixture
def sample_paper_data():
    """Sample paper data for testing."""
    return {
        "id": "test_paper_001",
        "title": "Attention Is All You Need",
        "authors": ["Vaswani", "Shazeer", "Parmar"],
        "year": 2017,
        "pages": 11,
        "filepath": "/tmp/test_paper.pdf",
    }


@pytest.fixture
def sample_paragraphs():
    """Sample paragraph data for testing retrieval and verification."""
    return [
        {
            "paragraph_id": "P1",
            "text": "The Transformer model relies entirely on self-attention mechanisms, dispensing with recurrence and convolutions.",
            "paper_id": "test_paper_001",
            "paper_title": "Attention Is All You Need",
            "section": "Introduction",
            "page": 1,
            "sentences": [
                {"sentence_id": "P1_S1", "text": "The Transformer model relies entirely on self-attention mechanisms, dispensing with recurrence and convolutions."}
            ],
        },
        {
            "paragraph_id": "P2",
            "text": "The model was trained on the WMT 2014 English-to-German dataset consisting of about 4.5 million sentence pairs.",
            "paper_id": "test_paper_001",
            "paper_title": "Attention Is All You Need",
            "section": "Training",
            "page": 7,
            "sentences": [
                {"sentence_id": "P2_S1", "text": "The model was trained on the WMT 2014 English-to-German dataset consisting of about 4.5 million sentence pairs."}
            ],
        },
        {
            "paragraph_id": "P3",
            "text": "Multi-head attention allows the model to jointly attend to information from different representation subspaces at different positions.",
            "paper_id": "test_paper_001",
            "paper_title": "Attention Is All You Need",
            "section": "Model Architecture",
            "page": 4,
            "sentences": [
                {"sentence_id": "P3_S1", "text": "Multi-head attention allows the model to jointly attend to information from different representation subspaces at different positions."}
            ],
        },
    ]


@pytest.fixture
def sample_session_data():
    """Sample session data for testing."""
    return {
        "id": "test_session_001",
        "name": "Test Research Session",
        "paper_ids": json.dumps(["test_paper_001"]),
    }


@pytest.fixture
def sample_messages():
    """Sample chat messages for testing."""
    return [
        {"role": "user", "content": "What is the Transformer model?"},
        {
            "role": "assistant",
            "content": "The Transformer model relies entirely on self-attention mechanisms [P1]. It was trained on WMT 2014 data [P2].",
        },
    ]


# ============================================================
# Markers
# ============================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "integration: marks integration tests")
    config.addinivalue_line("markers", "unit: marks unit tests")
