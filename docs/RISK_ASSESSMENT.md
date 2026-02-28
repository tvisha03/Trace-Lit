# TraceLit — Risk Assessment & Mitigation

> Risks ranked by probability × impact. Mitigations are actionable and specific.

---

## Risk Matrix

| # | Risk | Probability | Impact | Risk Score | Mitigation | Contingency |
|---|------|------------|--------|-----------|------------|-------------|
| 1 | **Sentence attribution fails** | Medium | 🚨 Critical | HIGH | Implement Week 1, test daily on 3+ real papers | Fallback to paragraph-level attribution |
| 2 | **API rate limits hit during demo** | High | High | HIGH | Multi-provider fallback, pre-test with demo papers | Switch to Groq/Ollama automatically |
| 3 | **Demo crashes** | Low | 🚨 Critical | HIGH | Comprehensive error handling at every layer | Backup demo video prepared |
| 4 | **LLM citation format inconsistent** | High | High | HIGH | Structured validation + automatic fallback attribution | Embedding-based auto-attribution |
| 5 | **RAM overflow (>8GB)** | Medium | High | MEDIUM | Docker mem_limit per container, lazy model loading, monitoring | Reduce batch sizes, limit parallel papers to 2 |
| 6 | **Processing too slow** | Low | Medium | LOW | Progressive availability, MPS acceleration | Reduce parallel papers, show "processing" UI |
| 7 | **PDF extraction fails on certain papers** | Medium | Medium | MEDIUM | Detect scanned/malformed PDFs → warn user | Reject unsupported PDFs with helpful message |
| 8 | **Running out of time** | Medium | High | MEDIUM | Strict Week 8 gate, priority triage | Stop at Phase 1 only, skip Phase 2 |
| 9 | **FAISS index corruption** | Low | Medium | LOW | Persistent index files with automatic rebuild on load failure | Re-embed papers from stored PDFs; FAISS index is fully reconstructable |
| 10 | **MPS not available on test machine** | Low | Medium | LOW | CPU fallback path in embedding code | Slower but functional on CPU |

---

## Detailed Mitigations

### Risk 1: Sentence Attribution Fails

**Why it's critical**: This is TraceLit's core innovation. Without working sentence attribution, the project is just another chatbot.

**Prevention**:
- Implement `SentenceAwareChunker` in Week 1 Day 6–7
- Write and run this test **every day**:

```python
def test_sentence_attribution():
    paper = extract_paper("tests/fixtures/bert.pdf")
    chunks = chunker.chunk_sections(paper.sections, paper.metadata)

    for chunk in chunks:
        assert 'sentences' in chunk
        assert len(chunk['sentences']) > 0
        for sent in chunk['sentences']:
            assert 'sentence_id' in sent
            assert 'text' in sent
            assert sent['sentence_id'].startswith('P')

    # Test HAVF returns sentence_id
    response = llm.generate("What is masked language modeling?", context=chunks[:4])
    for sentence in response.sentences:
        assert sentence.sentence_id is not None
        assert sentence.paragraph_id is not None

    print("✅ Sentence attribution test passed")
```

**Contingency**: If sentence-level fails completely, fall back to paragraph-level highlighting (still better than most tools).

---

### Risk 4: LLM Citation Format Inconsistent

**Problem**: LLMs don't always follow instructions perfectly. The `[P#]` citation format may be:
- Missing entirely
- Using wrong format (e.g., `(P5)` instead of `[P5]`)
- Citing non-existent paragraph IDs

**Prevention**:
1. Citation validation after every LLM response
2. At least 60% of content sentences must have `[P#]` citations
3. Verify all cited P# IDs exist in provided context

```python
def _validate_citations(self, response, context_ids):
    citations = re.findall(r'\[P\d+\]', response)
    valid = [c for c in citations if c.strip('[]') in context_ids]
    return len(valid) / max(len(citations), 1) >= 0.6
```

**Contingency**: Automatic fallback attribution — match each sentence to its most similar source paragraph via embedding similarity. Show yellow warning banner.

---

### Risk 5: RAM Overflow

**Prevention Checklist**:
- [ ] Docker `mem_limit` set on every container (backend: 3g, frontend: 512m)
- [ ] Lazy model loading — don't load `SentenceTransformer` until first query
- [ ] Max 3 papers parallel — enforced in `SmartPaperQueue`
- [ ] Free PDF extraction buffers after chunking complete
- [ ] Monitor memory usage, log warning if >5GB

```python
import psutil

def check_memory():
    mem = psutil.virtual_memory()
    used_gb = mem.used / (1024**3)
    if used_gb > 6.0:
        logger.critical(f"Memory critical: {used_gb:.1f}GB used")
        # Reduce batch sizes, defer non-essential operations
    elif used_gb > 5.0:
        logger.warning(f"Memory high: {used_gb:.1f}GB used")
```

**Advanced Memory Management**: The `check_memory()` snippet above is entry-level monitoring. The full mitigation uses two dedicated classes:

- **`MemoryMonitor`** — Runs as a background task with 3 response tiers:
  - **Warning (60%)**: Trigger garbage collection, log alert
  - **Critical (75%)**: Unload unused models, clear caches, reduce batch sizes
  - **Emergency (90%)**: Reject new paper uploads, force-unload all optional models
- **`LazyModelLoader`** — Defers loading of `SentenceTransformer` (~400MB) and `CrossEncoder` (~500MB) until first query, and auto-unloads after 10 minutes of inactivity. This alone saves ~1.2GB at startup.

> **📖 Full implementation**: See `RAG_AND_CHUNKING_STRATEGY.md` → **Section 20: Memory Management for M3** for complete `LazyModelLoader` and `MemoryMonitor` classes with threshold configurations, GC integration, and model lifecycle management.

---

### Risk 8: Running Out of Time

**Prevention**:
- Follow the strict checkpoint gates:
  - **Week 4**: Chat + Citations must work → if not, cut comparison table
  - **Week 8**: All Phase 1 features → if not, **DO NOT** start Phase 2
  - **Week 10**: System stable → if not, focus on stability only

**Priority Triage Order** (cut bottom-up):
1. ~~Local Ollama toggle~~
2. ~~Docling integration~~
3. ~~Keyword extraction~~
4. ~~Literature review generator~~
5. ~~Research gap finder~~
6. Export (PDF/Excel) — only if desperate
7. Comparison table — only if desperate
8. NEVER cut: chunking, LLM, HAVF, chat UI, source viewer

---

## Frontend Error Handling Matrix

| Error Code | UI Response |
|-----------|-------------|
| `ALL_PROVIDERS_FAILED` | Red banner: "Service unavailable" + Retry button + offline notice |
| `RATE_LIMIT` | Yellow banner: "Switching providers..." with countdown timer |
| `INVALID_CITATIONS` | Response shown + yellow warning: "Citations automatically attributed" |
| `PROCESSING_FAILED` | Red badge on paper + "Extraction failed" tooltip |
| `TIMEOUT` | "Taking longer than expected..." + auto-retry indicator |
| Network error | "Connection lost" + auto-reconnect attempt |
| Unknown | "Something went wrong" + Retry button + error ID for debugging |
