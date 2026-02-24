# TraceLit — Testing Guidelines

> Every feature must be tested before it is "done".  
> This project is evaluated in a viva — broken features are worse than missing features.

---

## 1. Testing Philosophy

- **Test the critical path first**: Upload → Chat → Citations → Verification
- **Favor integration tests** over excessive unit tests (we have limited time)
- **Test error paths**: Every `try/except` should have a matching test
- **Mock external services**: Never call real LLM APIs in tests
- **Run tests before every commit**: No exceptions

---

## 2. Test Structure

```
backend/
  tests/
    conftest.py             # Shared fixtures
    test_papers/            # Sample PDFs for testing
      sample_paper.pdf
      broken_paper.pdf
    unit/
      test_chunking.py
      test_havf.py
      test_citation_parser.py
      test_provider_fallback.py
    integration/
      test_upload_flow.py
      test_chat_flow.py
      test_compare_flow.py
    evaluation/
      test_attribution_accuracy.py
      test_havf_accuracy.py

frontend/
  src/__tests__/
    components/
      CitedSentence.test.jsx
      ConfidenceBadge.test.jsx
    hooks/
      useChat.test.js
    utils/
      citationParser.test.js
```

---

## 3. Backend Testing

### 3.1 Test Framework Setup

```python
# conftest.py
import pytest
import asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.main import app
from app.database import Base, get_db

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def db_session():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine) as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
```

### 3.2 Critical Unit Tests

#### Chunking Tests

```python
# tests/unit/test_chunking.py

def test_sentence_aware_chunking():
    """Each chunk must start and end at sentence boundaries"""
    text = "First sentence. Second sentence. Third sentence."
    chunks = sentence_aware_chunk(text, max_tokens=10, overlap_tokens=2)
    for chunk in chunks:
        assert chunk.text.endswith('.')
        assert chunk.text[0].isupper()

def test_chunk_metadata_has_paragraph_index():
    """Every chunk must carry paragraph and section metadata"""
    chunks = sentence_aware_chunk(sample_text, max_tokens=50)
    for chunk in chunks:
        assert "section_title" in chunk.metadata
        assert "paragraph_index" in chunk.metadata
        assert "paper_id" in chunk.metadata

def test_chunk_overlap_maintains_context():
    """Overlap sentences should appear in consecutive chunks"""
    chunks = sentence_aware_chunk(long_text, max_tokens=30, overlap_sentences=1)
    if len(chunks) > 1:
        last_sentence_of_first = chunks[0].text.rstrip('.').split('.')[-1]
        assert last_sentence_of_first in chunks[1].text

def test_empty_text_returns_no_chunks():
    chunks = sentence_aware_chunk("", max_tokens=50)
    assert chunks == []
```

#### HAVF Tests

```python
# tests/unit/test_havf.py

def test_high_confidence_when_supported():
    """Text closely matching source should get HIGH confidence"""
    source = "Neural networks learn through backpropagation."
    claim = "Neural networks learn through backpropagation."
    result = havf_verify(claim, source)
    assert result.confidence == "HIGH"
    assert result.score >= 0.85

def test_low_confidence_when_unsupported():
    """Text not in source should get LOW confidence"""
    source = "Neural networks learn through backpropagation."
    claim = "Quantum computing will replace classical computing by 2025."
    result = havf_verify(claim, source)
    assert result.confidence == "LOW"
    assert result.score < 0.65

def test_medium_confidence_partial_match():
    """Paraphrased content should get MEDIUM confidence"""
    source = "The study found a 15% improvement in accuracy."
    claim = "Accuracy improved by approximately 15%."
    result = havf_verify(claim, source)
    assert result.confidence == "MEDIUM"

def test_batch_verification():
    """Multiple claims should be verified in batch"""
    claims = ["claim1", "claim2", "claim3"]
    sources = ["source1", "source2", "source3"]
    results = havf_verify_batch(claims, sources)
    assert len(results) == 3
```

#### Citation Parser Tests

```python
# tests/unit/test_citation_parser.py

def test_parse_valid_citation():
    text = "Deep learning works [P1]. It scales well [P2]."
    sentences = parse_citations(text)
    assert sentences[0].text == "Deep learning works"
    assert sentences[0].paper_ids == ["P1"]
    assert sentences[1].paper_ids == ["P2"]

def test_multiple_citations_per_sentence():
    text = "Both methods work [P1][P3]."
    sentences = parse_citations(text)
    assert sentences[0].paper_ids == ["P1", "P3"]

def test_no_citation_flagged():
    text = "This is unsupported."
    sentences = parse_citations(text)
    assert sentences[0].paper_ids == []
    assert sentences[0].needs_attribution == True

def test_invalid_citation_format():
    text = "Method works [Paper 1]."
    sentences = parse_citations(text)
    assert sentences[0].paper_ids == []  # [Paper 1] is not valid [P#] format
```

#### Provider Fallback Tests

```python
# tests/unit/test_provider_fallback.py

@pytest.mark.asyncio
async def test_fallback_on_rate_limit(mock_gemini, mock_groq):
    """When Gemini hits rate limit, should fall back to Groq"""
    mock_gemini.side_effect = RateLimitError("gemini", 60)
    mock_groq.return_value = "Response from Groq"

    result = await multi_provider_generate(prompt)
    assert result.provider == "groq"
    assert "Response from Groq" in result.text

@pytest.mark.asyncio
async def test_all_providers_fail(mock_all_providers):
    """When all providers fail, should raise AllProvidersFailedError"""
    for mock in mock_all_providers:
        mock.side_effect = Exception("Failed")

    with pytest.raises(AllProvidersFailedError):
        await multi_provider_generate(prompt)
```

### 3.3 Integration Tests

```python
# tests/integration/test_upload_flow.py

@pytest.mark.asyncio
async def test_full_upload_flow(client, sample_pdf):
    """Upload → Extract → Chunk → Embed → Ready to query"""
    # Upload
    response = await client.post(
        "/api/papers/upload",
        files={"file": ("test.pdf", sample_pdf, "application/pdf")}
    )
    assert response.status_code == 200
    paper_id = response.json()["data"]["paper_id"]

    # Wait for processing
    for _ in range(30):
        status = await client.get(f"/api/papers/{paper_id}")
        if status.json()["data"]["status"] == "ready":
            break
        await asyncio.sleep(1)

    assert status.json()["data"]["status"] == "ready"
    assert status.json()["data"]["total_chunks"] > 0

@pytest.mark.asyncio
async def test_invalid_pdf_upload(client):
    """Uploading non-PDF should return clear error"""
    response = await client.post(
        "/api/papers/upload",
        files={"file": ("test.txt", b"not a pdf", "text/plain")}
    )
    assert response.status_code == 400
```

---

## 4. Frontend Testing

### 4.1 Framework: Vitest + React Testing Library

```javascript
// CitedSentence.test.jsx
import { render, screen, fireEvent } from '@testing-library/react';
import { CitedSentence } from '../CitedSentence';

test('renders sentence with high confidence styling', () => {
  render(
    <CitedSentence
      text="Neural networks learn through backpropagation."
      confidence="HIGH"
      paperId="P1"
      score={0.92}
    />
  );

  const sentence = screen.getByText(/Neural networks/);
  expect(sentence).toHaveClass('border-l-green-500');
});

test('shows tooltip on hover with source info', async () => {
  render(
    <CitedSentence
      text="Some claim."
      confidence="MEDIUM"
      paperId="P2"
      score={0.71}
    />
  );

  fireEvent.mouseEnter(screen.getByText(/Some claim/));
  expect(screen.getByText(/71%/)).toBeInTheDocument();
});

test('clicking citation scrolls to source', () => {
  const onCitationClick = vi.fn();
  render(
    <CitedSentence text="Test." paperId="P1" onCitationClick={onCitationClick} />
  );

  fireEvent.click(screen.getByText('[P1]'));
  expect(onCitationClick).toHaveBeenCalledWith('P1');
});
```

### 4.2 Citation Parser Utility Test

```javascript
// citationParser.test.js
import { parseCitations } from '../citationParser';

test('parses single citation', () => {
  const result = parseCitations('Deep learning works [P1].');
  expect(result).toEqual([
    { text: 'Deep learning works', paperIds: ['P1'] }
  ]);
});

test('handles multiple citations in one sentence', () => {
  const result = parseCitations('Both methods work [P1][P3].');
  expect(result[0].paperIds).toEqual(['P1', 'P3']);
});

test('flags uncited sentences', () => {
  const result = parseCitations('Uncited claim.');
  expect(result[0].paperIds).toEqual([]);
  expect(result[0].needsAttribution).toBe(true);
});
```

---

## 5. Performance / Benchmark Tests

```python
# tests/evaluation/test_attribution_accuracy.py

EVALUATION_SET = [
    {
        "source": "Transformer models use self-attention mechanisms.",
        "query": "How do transformers work?",
        "expected_citation": "P1",
        "expected_confidence": "HIGH"
    },
    # Add 20-50 cases
]

@pytest.mark.slow
def test_attribution_accuracy():
    """Sentence-level attribution accuracy should be ≥ 85%"""
    correct = 0
    for case in EVALUATION_SET:
        result = run_pipeline(case["source"], case["query"])
        if case["expected_citation"] in result.citations:
            correct += 1
    accuracy = correct / len(EVALUATION_SET)
    assert accuracy >= 0.85, f"Attribution accuracy {accuracy:.1%} < 85%"

@pytest.mark.slow
def test_havf_latency():
    """HAVF verification should complete within 100ms per claim"""
    import time
    start = time.time()
    for _ in range(100):
        havf_verify("Test claim", "Test source")
    avg_ms = (time.time() - start) / 100 * 1000
    assert avg_ms < 100, f"HAVF avg latency {avg_ms:.0f}ms > 100ms"
```

---

## 6. Required Test Coverage

| Component | Min Coverage | Critical Tests |
|-----------|-------------|----------------|
| Chunking service | 90% | Sentence boundaries, metadata, overlap |
| HAVF verifier | 90% | All 3 confidence levels, batch mode |
| Citation parser | 95% | Valid/invalid formats, multi-citation |
| Provider fallback | 85% | Rate limit, timeout, all-fail |
| Upload pipeline | 80% | Success, invalid PDF, large file |
| Chat flow | 80% | Single paper, multi-paper, streaming |
| Frontend components | 70% | CitedSentence, ConfidenceBadge, ErrorBoundary |

---

## 7. Running Tests

```bash
# Backend
cd backend
pytest --cov=app --cov-report=term-missing -v

# Run only fast tests
pytest -m "not slow" -v

# Run specific test file
pytest tests/unit/test_chunking.py -v

# Frontend
cd frontend
npx vitest run --coverage

# Run specific test
npx vitest run CitedSentence
```

---

## 8. Test Data Management

- Store sample PDFs in `tests/test_papers/` (2-3 real papers, 1 broken PDF)
- Use `conftest.py` fixtures for reusable test data
- Never commit real API keys — use mocks for all LLM calls
- HAVF evaluation dataset: 50 claim–source pairs with expected confidence labels
- Regenerate test embeddings if embedding model changes

---

## 9. Pre-Commit Checklist

Before every commit:
1. `pytest -m "not slow"` passes (fast tests)
2. `npx vitest run` passes (frontend tests)
3. No new linting errors (`ruff check .` + `eslint .`)
4. New features have at least one happy-path test
5. Error-handling changes have matching error-path tests
