# TraceLit — Phase-Wise Implementation Strategy

> **Timeline**: 12 Weeks (10 Weeks Core MVP + 2 Weeks Polish & Evaluation)  
> **Hardware**: M3 MacBook Pro (10-core CPU, 10-core GPU, 8GB Unified Memory)  
> **Checkpoint Philosophy**: Never start Phase 2 if Phase 1 is broken.

---

## Phase 1: Core MVP (Weeks 1–10)

### Week 1: Foundation + Sentence-Aware Chunking 🚨 CRITICAL

| Days | Task | Details | Deliverable |
|------|------|---------|-------------|
| 1–2 | **Project scaffolding** | FastAPI backend + React/Vite frontend + Docker Compose config + `.env` setup | Running dev environment |
| 3–5 | **PDF extraction pipeline** | PyMuPDF4LLM integration, section heading detection, image extraction, metadata parsing | Upload PDF → structured sections output |
| 6–7 | **Sentence-aware chunking** | Implement `SentenceAwareChunker` with boundary tracking, sentence IDs (`P#_S#`), context enrichment prefixes | Upload PDF → extract with sentence boundaries |

**Week 1 Critical Path**:
- `backend/app/chunking/sentence_aware_chunker.py` must be working by Day 7
- Test on at least 3 real ML papers (BERT, GPT-2, Attention Is All You Need)
- Verify each chunk has `sentences[]` array with unique `sentence_id` fields

**Backend Directory Setup (Day 1)**:
```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app entry
│   ├── config.py               # Settings (Pydantic BaseSettings)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── papers.py           # Upload, list, status endpoints
│   │   ├── chat.py             # Query + SSE streaming
│   │   ├── sessions.py         # Session CRUD
│   │   ├── export.py           # PDF/Excel export
│   │   └── compare.py          # Comparison table
│   ├── extraction/
│   │   ├── __init__.py
│   │   ├── pdf_processor.py    # PyMuPDF4LLM wrapper
│   │   └── hybrid_extractor.py # Auto/fast/quality modes
│   ├── chunking/
│   │   ├── __init__.py
│   │   └── sentence_aware_chunker.py  # 🚨 CRITICAL
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── providers.py        # Gemini, Groq, Ollama clients
│   │   ├── multi_provider.py   # Fallback orchestrator
│   │   └── prompts.py          # System prompts, citation templates
│   ├── verification/
│   │   ├── __init__.py
│   │   └── havf.py             # HAVF verifier
│   ├── embeddings/
│   │   ├── __init__.py
│   │   └── mps_embedder.py     # MPS-accelerated embeddings
│   ├── processing/
│   │   ├── __init__.py
│   │   └── smart_queue.py      # Parallel paper processing
│   ├── models/
│   │   ├── __init__.py
│   │   ├── database.py         # SQLAlchemy engine + session
│   │   └── schemas.py          # SQLAlchemy ORM models
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── api_schemas.py      # Pydantic request/response models
│   └── utils/
│       ├── __init__.py
│       └── helpers.py
├── tests/
│   ├── fixtures/               # Sample PDFs for testing
│   ├── test_chunker.py
│   ├── test_havf.py
│   └── test_pipeline.py
├── data/
│   ├── uploads/                # Uploaded PDFs
│   └── exports/                # Generated exports
├── requirements.txt
├── Dockerfile
└── .env.example
```

**Frontend Directory Setup (Day 1)**:
```
frontend/
├── src/
│   ├── main.jsx
│   ├── App.jsx
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Header.jsx
│   │   │   ├── Sidebar.jsx
│   │   │   └── MainLayout.jsx
│   │   ├── chat/
│   │   │   ├── ChatInterface.jsx
│   │   │   ├── MessageBubble.jsx
│   │   │   ├── CitedSentence.jsx
│   │   │   ├── CitationTooltip.jsx
│   │   │   └── ChatControls.jsx
│   │   ├── source/
│   │   │   ├── SourceViewer.jsx
│   │   │   └── SentenceHighlight.jsx
│   │   ├── papers/
│   │   │   ├── PaperUpload.jsx
│   │   │   ├── PaperList.jsx
│   │   │   └── ProcessingProgress.jsx
│   │   ├── compare/
│   │   │   └── ComparisonTable.jsx
│   │   ├── export/
│   │   │   └── ExportPanel.jsx
│   │   └── common/
│   │       ├── ConfidenceBadge.jsx
│   │       ├── LoadingSkeleton.jsx
│   │       └── ErrorBoundary.jsx
│   ├── hooks/
│   │   ├── useChat.js
│   │   ├── usePapers.js
│   │   ├── useWebSocket.js
│   │   └── useSession.js
│   ├── stores/
│   │   ├── chatStore.js       # Zustand
│   │   ├── paperStore.js
│   │   └── sessionStore.js
│   ├── api/
│   │   └── client.js          # Axios/fetch wrapper
│   ├── utils/
│   │   └── helpers.js
│   └── styles/
│       └── index.css          # Tailwind directives + custom
├── index.html
├── vite.config.js
├── tailwind.config.js
├── postcss.config.js
├── package.json
└── Dockerfile
```

---

### Week 2: RAG Pipeline + Error Handling 🚨 CRITICAL

| Days | Task | Details | Deliverable |
|------|------|---------|-------------|
| 1–3 | **Multi-provider LLM setup** | Gemini 2.0 Flash + Groq Llama 3.1 70B clients, basic provider switching logic | Two working LLM providers |
| 4–5 | **Error handling** | Rate limit handling (429 → switch), timeout retries (exponential backoff), fallback attribution | Robust LLM client that never crashes |
| 6–7 | **Session state + context sharing** | Session manager preserving conversation history, context sharing across provider switches | Query with provider fallback working |

**Key Files**:
- `backend/app/llm/providers.py` — Individual provider clients
- `backend/app/llm/multi_provider.py` — `RobustMultiProviderLLM` with fallback chain
- `backend/app/llm/prompts.py` — Citation system prompt template

**Acceptance Criteria**:
- Query returns cited response using Gemini
- When Gemini is rate-limited, seamlessly falls back to Groq
- When LLM doesn't follow citation format, automatic fallback attribution kicks in
- All errors return structured JSON error responses (never raw stack traces)

---

### Week 3: HAVF with Sentence Mapping ⭐ CORE INNOVATION

| Days | Task | Details | Deliverable |
|------|------|---------|-------------|
| 1–3 | **HAVF Level 1 + Level 2** | Embedding similarity (all-MiniLM-L6-v2) + Cross-encoder reranking (ms-marco-MiniLM-L-6-v2) | Basic verification working |
| 4–7 | **Sentence-level mapping** | HAVF returns `sentence_id` + `paragraph_id`, test on real papers, accuracy benchmarking | Sentence-level attribution verified |

**Key File**: `backend/app/verification/havf.py`

**Acceptance Criteria**:
- HAVF returns confidence scores: HIGH (≥0.85), MEDIUM (0.65–0.84), LOW (<0.65)
- Each verified sentence has both `paragraph_id` AND `sentence_id`
- Level 2 cross-encoder only triggered for uncertain sentences (saves compute)
- Target: >85% attribution accuracy on test set

---

### Week 4: Basic UI

| Task | Component | Details |
|------|-----------|---------|
| Chat interface | `ChatInterface.jsx` | Message list, input bar, streaming display |
| Source viewer | `SourceViewer.jsx` | Paper text with sections/paragraphs, scrollable |
| Citation display | `CitedSentence.jsx` | Inline citations with `[P#]` rendered as superscripts |
| Split-pane layout | `MainLayout.jsx` | Source (40%) + Chat (60%), resizable |
| Paper upload | `PaperUpload.jsx` | Drag-and-drop, file picker, processing queue display |

---

### Week 5: Advanced UI

| Task | Component | Details |
|------|-----------|---------|
| Superscript citations | `CitedSentence.jsx` | Academic-style ¹²³ with color-coded confidence underlines |
| Hover tooltips | `CitationTooltip.jsx` | Paper title, section, page, preview text on hover |
| Sentence highlighting | `SentenceHighlight.jsx` | Click citation → scroll + pulse highlight (3s) |
| Toggle controls | `ChatControls.jsx` | "Clean Reading" ↔ "Full Attribution" toggle |
| Confidence dashboard | `ConfidenceDashboard.jsx` | Modal with per-sentence breakdown |

---

### Week 6: Progressive Processing

| Days | Task | Details | Deliverable |
|------|------|---------|-------------|
| 1–3 | **Smart queue** | `SmartPaperQueue` — 2–3 papers parallel, rest queued, `asyncio.wait(FIRST_COMPLETED)` | Parallel processing |
| 4–5 | **WebSocket progress** | Per-paper stage updates (extraction → chunking → embedding → indexing) | Real-time progress UI |
| 6–7 | **Progressive availability** | Paper becomes queryable immediately when done, notifications | "Paper 1 ready!" toast |

**Key File**: `backend/app/processing/smart_queue.py`

---

### Week 7: Comparison & Export

| Task | Details |
|------|---------|
| Comparison table | LLM extracts structured contributions (problem, method, dataset, metrics, results) per paper → auto-populated table with editable cells linked to source paragraphs |
| PDF export | WeasyPrint + Jinja2 templates — cover page, messages with citations+confidence, source list |
| Excel export | openpyxl — comparison tables, metadata sheets |
| Session management | Session list/rename/delete in sidebar, SQLite persistence |

---

### Week 8–9: Integration & Testing

| Week | Focus | Tasks |
|------|-------|-------|
| 8 | **End-to-end integration** | Wire all components together, test full user flow (upload → process → query → verify → export) |
| 9 | **Bug fixes + edge cases** | Memory profiling (<6GB peak), error edge cases, empty/malformed PDFs, concurrent requests |

**Week 8 GATE CHECK** 🚨:
- All Phase 1 features must be functional
- If any feature is broken → **DO NOT start Phase 2** — fix Phase 1
- If ahead of schedule → proceed to Phase 2 early

---

### Week 10: Polish & Documentation 🚨 CHECKPOINT

| Task | Details |
|------|---------|
| UI/UX polish | Animations, loading states, empty states, responsive refinements |
| Error states | Friendly error messages for every failure mode |
| Documentation | README, API docs, setup guide |
| Demo preparation | Pre-load 5 ML papers, prepare demo script, rehearse |

**✅ PHASE 1 COMPLETE — FULLY DEMOABLE SYSTEM**

---

## Phase 2: Enhancements (Weeks 11–12)

### Week 11: Quick Wins

| Task | Duration | Details |
|------|----------|---------|
| Keyword extraction | 0.5 days | KeyBERT with MMR diversity, display in sidebar |
| On-demand summaries | 0.5 days | Per-paper summaries generated on demand (not at upload) |
| Literature review generator | 1 day | Special prompt template, streaming output with citations |
| Research gap finder | 3–4 days | Extract limitations → embed → DBSCAN clustering → LLM summarization → "Gaps" tab |
| Local Ollama toggle | 1 day | Settings panel toggle, auto-fallback if local underperforms |
| Docling experiment | 1 day | Test Docling on M3, measure quality vs PyMuPDF4LLM on table-heavy papers |

### Week 12: Evaluation & Final Polish

| Task | Duration | Details |
|------|----------|---------|
| MiniLitAttrib dataset | 2 days | 30–50 QA pairs across 10 papers, ground truth paragraph IDs |
| Run evaluation metrics | 1 day | Attribution accuracy, hallucination rate, latency, confidence calibration |
| Final testing | 1 day | Full regression, edge cases |
| Documentation finalization | 1 day | README, API docs, user manual |
| Demo video | 1 day | 3–5 min walkthrough |
| Demo rehearsal | 1 day | 3+ practice runs |

**✅ PROJECT COMPLETE**

---

## Checkpoint Gates

| Checkpoint | Criteria | If Behind | If Ahead |
|-----------|----------|-----------|----------|
| **Week 4** | Chat + Citations must work | Cut comparison table to Phase 2 | Start HAVF early |
| **Week 8** | All Phase 1 features functional | **DO NOT start Phase 2** — fix Phase 1 | Proceed to Phase 2 |
| **Week 10** | System stable and demoable | Focus entirely on stability | Add stretch features |

---

## Priority Triage (If Behind Schedule)

### Must Have (Never Cut):
1. Sentence-aware chunking
2. Multi-provider LLM with error handling
3. HAVF verification
4. Chat interface with citations
5. Source viewer with sentence highlighting

### Should Have (Cut if 1 week behind):
6. Comparison table
7. Export (PDF/Excel)
8. Progressive processing

### Nice to Have (Phase 2 only):
9. Literature review generator
10. Research gap finder
11. Keyword extraction
12. Local Ollama toggle
13. Docling integration
