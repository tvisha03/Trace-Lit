# TraceLit — Intelligent Academic Literature Assistant

> **Sentence-level attribution, confidence scoring, and hallucination prevention for multi-document research Q&A.**

TraceLit is a local-first full-stack application that lets researchers upload academic PDFs, ask questions, and receive answers with sentence-level citations verified by the **HAVF (Hallucination-Aware Verification Framework)** pipeline.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Tech Stack](#tech-stack)
3. [Quick Start](#quick-start)
   - [Backend](#backend)
   - [Frontend](#frontend)
4. [Frontend Feature Guide](#frontend-feature-guide)
5. [Backend Feature Guide](#backend-feature-guide)
6. [API Reference](#api-reference)
7. [Environment Variables](#environment-variables)
8. [ML Models & Hardware Targets](#ml-models--hardware-targets)
9. [Scripts & Utilities](#scripts--utilities)
10. [Project Structure](#project-structure)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                  Browser (React 18)                 │
│  Split-pane UI: Chat (60%) │ Source Viewer (40%)    │
│  Real-time WebSocket + SSE streaming                │
└───────────────────────┬─────────────────────────────┘
                        │ REST / WS / SSE
┌───────────────────────▼─────────────────────────────┐
│              FastAPI Backend (Python 3.11+)          │
│  Lifespan-managed startup · Dependency Injection     │
│  SmartPaperQueue (max 3 parallel) · Export Pool     │
├──────────┬──────────┬──────────────┬────────────────┤
│  Domain  │ Services │ Infrastructure│  Workers       │
│  Chunks  │ PaperSvc │ SQLite/SQLAlch│ PaperQueue     │
│  HAVF    │ ChatSvc  │ FAISS index  │ ExportWorker   │
│  RAG     │ ExportSvc│ LLM providers│                │
│  Analysis│ AnalysisSvc (KeyBERT)   │                │
└──────────┴──────────┴──────────────┴────────────────┘
                        │
          ┌─────────────┴──────────────┐
          │       LLM Fallback Chain   │
          │  Gemini 2.0 Flash          │
          │    → Groq Llama 3.1 70B   │
          │      → Ollama (local)     │
          └────────────────────────────┘
```

---

## Tech Stack

### Frontend

| Layer | Technology |
|---|---|
| Framework | React 18 + Vite 5 |
| Language | JavaScript (JSX) |
| Styling | Tailwind CSS 3.4 (dark academic theme) |
| State | Zustand 4 |
| Data fetching | Axios + TanStack Query v5 |
| Tables | TanStack Table v8 |
| Charts | Recharts |
| Routing | React Router DOM v6 |
| UI components | Headless UI, Lucide React |
| Notifications | React Hot Toast |
| Markdown rendering | react-markdown + remark-gfm |
| Real-time | Native WebSocket + SSE |
| Testing | Playwright |

### Backend

| Layer | Technology |
|---|---|
| Framework | FastAPI (Python 3.11+) |
| Database | SQLite via async SQLAlchemy 2 + aiosqlite |
| Vector store | FAISS (sentence-level indexing) |
| Embeddings | mixedbread-ai/mxbai-embed-large-v1 (or bge-small for low-RAM) |
| Cross-encoder | BAAI/bge-reranker-base (HAVF Level 2) |
| Keywords | KeyBERT + DBSCAN clustering |
| PDF processing | PyMuPDF / pdfplumber |
| Export | WeasyPrint (PDF), openpyxl (Excel), python-docx (DOCX), LaTeX |
| Background tasks | asyncio priority queue (SmartPaperQueue) + ThreadPoolExecutor |

---

## Quick Start

### Prerequisites

- Python 3.11+ with `pip`
- Node.js 18+ with `npm`
- (Optional) Ollama for fully local LLM inference

---

### Backend

```bash
cd backend

# 1. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — add GEMINI_API_KEY and/or GROQ_API_KEY

# 4. Download ML models (one-time, ~600 MB default / ~140 MB low-RAM)
python -m scripts.download_models

# 5. Start the API server
uvicorn app.main:app --reload --port 8000
```

- API base: `http://localhost:8000/api/v1`
- Swagger docs: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

### Frontend

```bash
cd frontend

# 1. Install Node dependencies
npm install

# 2. Start the dev server (proxies API calls to :8000)
npm run dev
```

App opens at `http://localhost:5173`.

Build for production:

```bash
npm run build     # outputs to frontend/dist/
npm run preview   # serve the production build locally
```

---

## Frontend Feature Guide

### Layout

The UI uses a **three-column split-pane layout**:

| Column | Width | Content |
|---|---|---|
| Left Sidebar | 240 px | Session list, navigation links |
| Center | flex-1 | Primary content area (chat, analysis, settings…) |
| Right Panel | 274 px | Papers · Source Viewer · Web tabs |

On mobile the layout stacks vertically and the right panel collapses.

---

### Chat Interface (`/src/components/chat/`)

- **Streaming responses** via SSE — words render as they arrive
- **Cited sentences** are rendered as interactive `<CitedSentence>` spans with colour-coded confidence badges
- **Hover tooltip** (`<CitationTooltip>`) previews the source excerpt inline
- **Click-to-source** scrolls & pulses the exact sentence in the Source Viewer
- **Follow-up aware** — sends last 5 turns for multi-turn context

Confidence colours mirror the HAVF output:

| Level | Threshold | Colour |
|---|---|---|
| HIGH | ≥ 85 % | `#34d399` green |
| MEDIUM | 65 – 84 % | `#fbbf24` yellow |
| LOW | < 65 % | `#f87171` red |

---

### Paper Management (`/src/components/papers/`)

- **Drag-and-drop upload** with per-file size validation (max 50 MB, max 7 per session)
- **SVG progress ring** on each paper card while processing via WebSocket
- **Real-time stage labels**: `Extracting → Chunking → Embedding → Indexing`
- Papers become queryable as soon as their own processing completes — other papers can still be in-flight

---

### Source Viewer (`/src/components/source/`)

- Renders retrieved paragraph chunks with sentence-level `<SentenceHighlight>` spans
- Clicking a citation in chat triggers a smooth scroll + pulse animation
- Supports switching between papers via the "Source" tab in the right panel

---

### Analysis Panels (`/src/components/analysis/`)

| Panel | Description |
|---|---|
| `GapFinderPanel` | Research gaps across all uploaded papers (DBSCAN-clustered topics) |
| `KeywordsPanel` | Per-paper keyword clouds extracted with KeyBERT |
| `LiteratureReviewPanel` | Auto-generated structured literature review |
| `PaperSummaryPanel` | AI-generated abstract + contribution bullet points per paper |

---

### Comparison View (`/src/components/compare/`)

Side-by-side structured comparison of two papers: methodology, contributions, limitations, findings — rendered as a `TanStack Table`.

---

### Export Panel (`/src/components/export/`)

One-click export of chat history or comparison in four formats: **PDF**, **Excel**, **DOCX**, **LaTeX**.

---

### Verification Panel (`/src/components/verify/`)

Paste any text claim and select a paper — HAVF reruns the 2-stage verification pipeline and returns per-sentence confidence scores in real time.

---

### Settings Panel (`/src/components/settings/`)

Configure LLM provider preference, retrieval budget (token limit), embedding model, and session display options — persisted to localStorage.

---

### Right Panel Tabs

| Tab | Content |
|---|---|
| Papers | List of session papers with progress rings; "+ Upload" button |
| Source | Embedded `SourceViewer` that syncs with chat citations |
| Web | Placeholder external search UI (Phase 2) |

---

## Backend Feature Guide

### HAVF Verification Pipeline (2-stage)

```
Sentence + [P#] citation
        │
        ▼ Level 1: Embedding similarity
   similarity ≥ 0.85 ──→ HIGH  (fast path, ~89 % of claims)
   0.65 ≤ sim < 0.85 ──→ Level 2
   similarity < 0.65 ──→ LOW

        ▼ Level 2: Cross-encoder reranking
   score ≥ 0.75 ──→ MEDIUM
   score < 0.75 ──→ LOW
```

- Level 1 target latency: < 10 ms
- Level 2 target latency: < 50 ms
- Attribution accuracy target: > 85 %

### Sentence-Aware Chunking

Every paragraph chunk stores metadata enabling click-to-sentence navigation:

```json
{
  "paragraph_id": "P5",
  "paper_id": "...",
  "section": "Methods",
  "text": "...",
  "sentences": [
    { "id": "P5S2", "text": "...", "start_char": 142, "end_char": 231 }
  ]
}
```

### SmartPaperQueue

Manages concurrent PDF processing with memory-aware scheduling:

- Default max 3 concurrent papers
- Pauses ingestion when system RAM > 75 %
- Emits WebSocket progress events every ~5 s
- Newly completed papers are immediately queryable

### LLM Fallback Chain

```
Gemini 2.0 Flash  ──→  Groq Llama 3.1 70B  ──→  Ollama (local)
```

Failure at any layer triggers automatic retry on the next provider. The active provider is logged and surfaced in API responses.

---

## API Reference

| Method | Path | Description |
|---|---|---|
| POST | `/sessions` | Create session |
| GET | `/sessions` | List sessions |
| GET | `/sessions/{id}` | Get session detail |
| PATCH | `/sessions/{id}` | Rename session |
| DELETE | `/sessions/{id}` | Delete session + all data |
| POST | `/sessions/{id}/papers` | Upload PDF |
| GET | `/sessions/{id}/papers` | List papers |
| DELETE | `/papers/{id}` | Delete paper |
| POST | `/sessions/{id}/chat` | Chat (`stream=true` enables SSE) |
| GET | `/sessions/{id}/messages` | Chat history |
| POST | `/sessions/{id}/compare` | Compare two papers |
| GET | `/papers/{id}/contributions` | Structured contributions |
| GET | `/papers/{id}/keywords` | KeyBERT keywords |
| GET | `/sessions/{id}/gaps` | Gap analysis |
| GET | `/sessions/{id}/review` | Literature review |
| POST | `/sessions/{id}/export` | Trigger export |
| GET | `/exports/{filename}` | Download export |
| POST | `/verify` | Verify claim against papers |
| WS | `/ws/{session_id}` | Real-time paper processing progress |
| GET | `/health` | Health check |

Full Postman collection: `postman/collections/TraceLit API v2.9/`

---

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and set:

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | — | Google Gemini API key |
| `GROQ_API_KEY` | — | Groq API key |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `USE_LOCAL_LLM` | `false` | Prefer Ollama as primary |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/tracelite.db` | DB path |
| `MAX_FILE_SIZE_MB` | `50` | Max upload size per PDF |
| `MAX_FILES_PER_SESSION` | `7` | Max papers per session |
| `MAX_PARALLEL_PAPERS` | `3` | Concurrent processing limit |
| `EMBEDDING_MODEL` | `mixedbread-ai/mxbai-embed-large-v1` | Embedding model |
| `EMBEDDING_DIMENSIONS` | `1024` | Must match the model |
| `CROSS_ENCODER_MODEL` | `BAAI/bge-reranker-base` | HAVF Level-2 reranker |
| `KEYBERT_MODEL` | `all-mpnet-base-v2` | KeyBERT backbone |

---

## ML Models & Hardware Targets

### Default (≥ 16 GB RAM / CUDA GPU)

| Component | Memory |
|---|---|
| `mixedbread-ai/mxbai-embed-large-v1` | ~430 MB |
| `BAAI/bge-reranker-base` (lazy) | ~90 MB |
| FAISS (7 papers, 1024d) | ~10 MB |
| SQLite + app overhead | ~100 MB |
| **Total** | **~630 MB** |

### Low-RAM (Mac M1/M2/M3, 8 GB unified memory)

Add to `.env`:

```dotenv
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_DIMENSIONS=384
CROSS_ENCODER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
KEYBERT_MODEL=all-MiniLM-L6-v2
```

| Component | Memory |
|---|---|
| `BAAI/bge-small-en-v1.5` | ~90 MB |
| `ms-marco-MiniLM-L-6-v2` (lazy) | ~50 MB |
| FAISS (7 papers, 384d) | ~4 MB |
| SQLite + app overhead | ~100 MB |
| **Total** | **~244 MB** |

> **Note**: After switching models, delete `backend/data/faiss_indexes/` and reprocess all papers. The FAISS index dimension must match `EMBEDDING_DIMENSIONS`.

---

## Scripts & Utilities

```bash
# One-time model download
python -m scripts.download_models

# Benchmark HAVF latency
python -m scripts.benchmark_havf

# Seed database with a demo session
python -m scripts.seed_db

# Reset database (wipe all data)
python -m scripts.reset_db
```

---

## Project Structure

```
Trace-Lit/
├── frontend/                       # React 18 + Vite frontend
│   ├── src/
│   │   ├── api/                    # Axios client + endpoint wrappers
│   │   ├── components/
│   │   │   ├── analysis/           # GapFinder, Keywords, LitReview, Summary
│   │   │   ├── chat/               # ChatInterface, MessageBubble, CitedSentence, Tooltips
│   │   │   ├── common/             # ConfidenceBadge, ErrorBoundary, LoadingSkeleton
│   │   │   ├── compare/            # ComparisonTable
│   │   │   ├── export/             # ExportPanel
│   │   │   ├── layout/             # Header, Sidebar, MainLayout, RightPanel
│   │   │   ├── papers/             # PaperUpload, PaperList, ProcessingProgress
│   │   │   ├── settings/           # SettingsPanel
│   │   │   ├── source/             # SourceViewer, SentenceHighlight
│   │   │   └── verify/             # VerifyPanel
│   │   ├── hooks/                  # useChat, usePapers, useSession, useWebSocket
│   │   ├── stores/                 # Zustand: chatStore, paperStore, sessionStore
│   │   └── utils/                  # helpers
│   ├── index.html
│   ├── tailwind.config.js
│   └── vite.config.js
│
├── backend/
│   ├── api/v1/                     # FastAPI routes, schemas, router
│   ├── app/                        # App factory, config, lifespan, DI
│   ├── domain/                     # Pure business logic
│   │   ├── analysis/               # gap_finder, keyword_extractor
│   │   ├── export/                 # pdf, excel, docx, latex exporters
│   │   ├── extraction/             # PDF text + figure extraction
│   │   ├── generation/             # chat_engine, prompts, streaming
│   │   ├── retrieval/              # chunker, indexer, retriever
│   │   └── verification/           # HAVF pipeline
│   ├── infrastructure/             # SQLite, FAISS, LLM providers, file storage
│   ├── services/                   # Orchestration (paper, chat, export, comparison…)
│   ├── workers/                    # SmartPaperQueue, ExportWorker
│   ├── shared/                     # Constants, enums, errors, logger, utils
│   └── scripts/                    # CLI helpers
│
├── docs/                           # Architecture & design documentation
├── postman/                        # API collection + environment configs
└── instructions/                   # Coding, commenting, security principles
```

---

## Design System (Quick Reference)

| Token | Value |
|---|---|
| Background (deepest) | `#080808` |
| Panel background | `#0f0f0f` |
| Input / bubble bg | `#141414` |
| Primary text | `#ececec` |
| Secondary text | `#aaaaaa` |
| Accent gold (citations) | `#c9a96e` |
| Confidence HIGH | `#34d399` |
| Confidence MEDIUM | `#fbbf24` |
| Confidence LOW | `#f87171` |
| Font — headings | DM Serif Display |
| Font — body | DM Sans |
| Font — code / meta | DM Mono |

---

*Target hallucination rate: < 5 % on MiniLitAttrib evaluation dataset*
