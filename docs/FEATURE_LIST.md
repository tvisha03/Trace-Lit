# TraceLit — Feature List

> Complete feature inventory organized by implementation phase.  
> Each feature includes user story, key implementation details, and acceptance criteria.

---

## Phase 1 — Core MVP (Weeks 1–10)

### Feature 1: Multi-PDF Upload & Processing

**User Story**: *"As a researcher, I want to upload 5–7 papers and have them automatically processed so I can start asking questions as each finishes."*

**Implementation**:
- `POST /api/papers/upload` — accepts up to 7 PDF files
- Returns `202 Accepted` immediately with `paper_ids[]` and WebSocket URL
- Background processing: Extract (PyMuPDF4LLM) → Sentence-aware chunk → Embed (MPS) → Index (ChromaDB)
- Smart queue: 2–3 papers processed in parallel, rest queued
- WebSocket pushes per-paper stage progress (extraction 0–25%, chunking 25–40%, embedding 40–90%, indexing 90–100%)
- Paper becomes queryable immediately upon completion — progressive availability

**Smart Queue Algorithm**: The `SmartPaperQueue` manages processing with memory-aware scheduling:
- Monitors system RAM before starting each paper (skips if >75% used)
- Enforces `max_concurrent` limit (default 3) based on available memory
- Sends structured WebSocket progress events per-paper: `{paper_id, stage, progress, eta}`
- Enables partial-collection querying — the RAG pipeline queries only `completed` papers while others are still processing

> **📖 Full implementation**: See `RAG_AND_CHUNKING_STRATEGY.md` → **Section 18: Progressive Paper Processing** for the complete `SmartPaperQueue` class with memory-aware scheduling, WebSocket progress protocol, and partial availability handling.

**Key Files**:
- `backend/app/api/papers.py`
- `backend/app/extraction/pdf_processor.py`
- `backend/app/processing/smart_queue.py`

**Acceptance Criteria**:
- [ ] Upload 5 PDFs → all processed within ~2 minutes
- [ ] Paper 1 queryable after ~35 seconds while others still processing
- [ ] WebSocket progress updates received by frontend
- [ ] Rejects files >50MB or >7 papers with clear error message
- [ ] Handles corrupt/scanned PDFs gracefully (detect + warn)

---

### Feature 2: Intelligent Multi-Document Chat with Citations

**User Story**: *"As a researcher, I want to ask questions across multiple papers and get cited responses."*

**Implementation**:
- Query text → embed with `all-MiniLM-L6-v2` → ChromaDB similarity search (top-k per active paper)
- Context assembled with `[P#]` paragraph IDs, paper title, section name
- Citation-in-prompting: system prompt instructs LLM to cite every sentence with `[P#]`
- SSE streaming response delivery
- Session state manager preserves conversation history (last 5 turns)
- Multi-provider: Gemini → Groq → Ollama fallback chain

**Key Files**:
- `backend/app/api/chat.py`
- `backend/app/llm/multi_provider.py`
- `backend/app/llm/prompts.py`

**Acceptance Criteria**:
- [ ] Query returns response with `[P#]` citations on every sentence
- [ ] Response streams in real-time via SSE
- [ ] Follow-up questions use conversation context
- [ ] Provider fallback works transparently (user doesn't notice switch)
- [ ] "Not found in provided papers" returned for unsupported queries

---

### Feature 3: HAVF — Hybrid Attribution Verification Framework ⭐

**User Story**: *"As a researcher, I need to know which claims are well-supported vs uncertain."*

**Implementation**:
- After LLM generates response, parse into sentences with their `[P#]` citations
- Level 1: Batch embedding similarity — all sentences, <10ms each
- Level 2: Cross-encoder reranking — only uncertain sentences (0.65–0.84 similarity), <50ms each
- Returns confidence score + specific `sentence_id` for each sentence
- Confidence levels: HIGH (≥0.85, green), MEDIUM (0.65–0.84, yellow), LOW (<0.65, red)

**Key File**: `backend/app/verification/havf.py`

**Acceptance Criteria**:
- [ ] Each response sentence has a confidence score and level
- [ ] `sentence_id` (not just `paragraph_id`) returned for every verification
- [ ] HIGH confidence sentences have >85% cosine similarity to source
- [ ] Level 2 only triggers for uncertain sentences (saves compute)
- [ ] >85% attribution accuracy on test set

---

### Feature 4: Click-to-Source Viewer with Sentence Highlighting

**User Story**: *"As a researcher, I want to click any citation and see the exact source sentence highlighted."*

**Implementation**:
- Split-pane layout: Source Viewer (40%) | Chat Interface (60%)
- Each sentence rendered as `<span id="P5_S2">` element
- Click citation → `scrollIntoView({ behavior: 'smooth', block: 'center' })`
- Pulse highlight animation (3 seconds, blue glow)
- Source viewer shows paper sections with collapsible headings

**Key Files**:
- `frontend/src/components/source/SourceViewer.jsx`
- `frontend/src/components/chat/CitedSentence.jsx`

**Acceptance Criteria**:
- [ ] Click `[P5]` in chat → source viewer scrolls to exact sentence
- [ ] Sentence highlighted with blue pulse animation (3s)
- [ ] Source viewer shows paper structure (sections, paragraphs)
- [ ] Multiple papers switchable via tabs/dropdown in source viewer

---

### Feature 5: Paper Comparison Table

**User Story**: *"As a researcher, I want to compare key contributions across my uploaded papers."*

**Implementation**:
- LLM extracts structured JSON per paper: `{problem, method, dataset, metrics, results}`
- Each field includes `paragraph_id` for source linking
- Auto-populated table with editable cells
- Click any cell → navigate to source paragraph
- Export to Excel (openpyxl) and LaTeX

**Key Files**:
- `frontend/src/components/compare/ComparisonTable.jsx`
- `backend/app/api/compare.py`

**Acceptance Criteria**:
- [ ] Table auto-generated from LLM extraction
- [ ] Cells are editable by user
- [ ] Click cell → source paragraph highlighted
- [ ] Export to Excel produces valid .xlsx file

---

### Feature 6: Export & Session Management

**User Story**: *"As a researcher, I want to save my session and export results to PDF/Excel."*

**Implementation**:
- Session persistence in SQLite: papers, messages, conversation history, comparison data
- PDF export: WeasyPrint + Jinja2 — cover page, messages with citations + confidence scores, source list
- Excel export: openpyxl — comparison tables, metadata
- Session sidebar: list, rename, delete, load
- Export includes confidence scores and highlighted source references

**Key Files**:
- `backend/app/api/sessions.py`
- `backend/app/api/export.py`

**Acceptance Criteria**:
- [ ] Sessions persist across app restarts
- [ ] PDF export renders properly with citations and confidence colors
- [ ] Excel export contains comparison table + metadata sheet
- [ ] Session list in sidebar allows rename/delete/load

---

## Phase 2 — Power Features (Weeks 11–12)

### Feature 7: Keyword Extraction (0.5 days)

- KeyBERT with MMR diversity: `keyphrase_ngram_range=(1,2), top_n=10, use_mmr=True, diversity=0.5`
- Keywords displayed in sidebar under each paper
- Clickable keywords filter chat context

### Feature 8: Literature Review Generator (1 day)

- Special prompt template generates structured review across all papers
- Sections: Introduction → Methodology Survey → Key Findings → Gaps → Conclusion
- SSE streaming with proper `[P#]` citations throughout
- Exportable to Word (python-docx) and PDF

### Feature 9: Research Gap Finder (3–4 days)

- Auto-extract limitation/future work sections from all papers
- Embed limitation sentences → DBSCAN clustering → group similar limitations
- LLM summarizes each cluster into a "research gap" theme
- Priority scoring based on frequency and recency across papers
- Dedicated "Gaps" tab in UI with expandable gap cards

### Feature 10: On-Demand Paper Summaries (0.5 days)

- Per-paper summaries generated when user clicks "Summarize" (not at upload time)
- Saves processing resources — only summarize if user actually wants it
- Summary cached after first generation

### Feature 11: Local Ollama Toggle (1 day)

- Settings panel: "Cloud (Gemini/Groq) — Faster" vs "Local (Ollama) — Private"
- When local mode: Ollama → Gemini → Groq (reversed priority)
- Note displayed: "Responses may be slower (~20 tokens/sec)"
- Auto-fallback to cloud if Ollama generates poor quality (<60% citation compliance)

---

## Future Scope (Not Implemented)

| Feature | Technology | Effort | Value |
|---------|-----------|--------|-------|
| Citation Graph Visualization | NetworkX + D3.js / react-force-graph | 5–7 days | Visual paper relationships |
| Contradiction Detection | NLI model + claim clustering | 10+ days | Critical for systematic reviews |
| Semantic Paper Recommendations | arXiv API + semantic similarity | 5 days | Discover related papers |
| Multi-Language Support | Multilingual embedding models | High | Global accessibility |
| Collaborative Sessions | WebSocket + Redis | High | Team research projects |
| Advanced Analytics Dashboard | Recharts + aggregated metrics | 3–4 days | Research insights |

---

## Feature Priority Matrix

| Priority | Feature | Phase | Cut If Behind? |
|----------|---------|-------|---------------|
| 🔴 P0 | Sentence-aware chunking | 1 | NEVER |
| 🔴 P0 | Multi-provider LLM + error handling | 1 | NEVER |
| 🔴 P0 | HAVF verification | 1 | NEVER |
| 🔴 P0 | Chat interface + citations | 1 | NEVER |
| 🔴 P0 | Source viewer + sentence highlighting | 1 | NEVER |
| 🟡 P1 | Comparison table | 1 | If 1 week behind |
| 🟡 P1 | Export (PDF/Excel) | 1 | If 1 week behind |
| 🟡 P1 | Progressive processing + WebSocket | 1 | If 1 week behind |
| 🟢 P2 | Keyword extraction | 2 | Yes |
| 🟢 P2 | Literature review generator | 2 | Yes |
| 🟢 P2 | Research gap finder | 2 | Yes |
| 🟢 P2 | On-demand summaries | 2 | Yes |
| 🟢 P2 | Local Ollama toggle | 2 | Yes |
