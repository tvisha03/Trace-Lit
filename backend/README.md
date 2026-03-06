# Trace-Lit Backend

Intelligent academic literature assistant with **sentence-level verified attribution** (HAVF — Hallucination-Aware Verification Framework).

## Quick Start

### 1. Install dependencies

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your API keys (GEMINI_API_KEY, GROQ_API_KEY, etc.)
```

### 3. Download ML models (one-time)

```bash
python -m scripts.download_models
```

### 4. Run the server

```bash
uvicorn app.main:app --reload --port 8000
```

The API is available at `http://localhost:8000/api/v1`.  
Interactive docs at `http://localhost:8000/docs`.

---

## Architecture

```
backend/
├── api/v1/          # FastAPI routes, schemas, router
├── app/             # Application factory, config, lifespan, dependencies
├── domain/          # Pure business logic (extraction, retrieval, verification, generation, analysis, export)
├── infrastructure/  # External integrations (DB, LLM providers, FAISS, file storage)
├── services/        # Orchestration layer connecting domain + infrastructure
├── workers/         # Background processing (paper queue, export pool)
├── shared/          # Constants, enums, errors, logger, utilities
└── scripts/         # CLI helpers (download models, benchmark, seed DB)
```

### Key Layers

| Layer | Responsibility |
|---|---|
| **shared/** | Constants, enums, custom errors, logger, text/file/time/streaming utils |
| **infrastructure/** | SQLite (async SQLAlchemy), FAISS vector store, LLM providers (Gemini → Groq → Ollama fallback chain), file storage |
| **domain/** | PDF extraction, sentence-aware chunking, embedding indexing, budget-aware retrieval, HAVF 2-stage verification, RAG chat engine, keyword/gap analysis, PDF/Excel export |
| **services/** | Paper processing pipeline, chat orchestration, session management, comparison, export, analysis, verification |
| **workers/** | SmartPaperQueue (max 3 parallel, asyncio priority queue), export thread pool |
| **api/v1/** | REST endpoints + WebSocket for real-time progress |

---

## Core Features

- **Multi-paper RAG chat** with sentence-level citation `[P#]`
- **HAVF verification** — 2-stage pipeline:
  - Level 1: Batch embedding similarity (handles ~89% of claims)
  - Level 2: Cross-encoder reranking for uncertain claims
- **LLM fallback chain**: Gemini 2.0 Flash → Groq Llama 3.1 70B → Ollama (local)
- **Sentence-aware chunking** with section-enriched prefixes
- **Budget-aware retrieval** (configurable token limits)
- **Paper comparison** with structured contribution extraction
- **Literature review & gap analysis** (KeyBERT + DBSCAN clustering)
- **Export** to PDF (WeasyPrint) and Excel (openpyxl)
- **WebSocket** real-time processing progress
- **SSE streaming** for chat responses

---

## API Endpoints

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
| POST | `/sessions/{id}/chat` | Chat (supports `stream=true` for SSE) |
| GET | `/sessions/{id}/messages` | Get chat history |
| POST | `/sessions/{id}/compare` | Compare papers |
| GET | `/papers/{id}/contributions` | Get paper contributions |
| POST | `/sessions/{id}/export` | Export chat/comparison |
| GET | `/exports/{filename}` | Download export file |
| GET | `/papers/{id}/keywords` | Extract keywords |
| GET | `/sessions/{id}/gaps` | Gap analysis |
| GET | `/sessions/{id}/review` | Literature review |
| POST | `/verify` | Verify text against papers |
| WS | `/ws/{session_id}` | Real-time progress |
| GET | `/health` | Health check |

---

## Environment Variables

See `.env.example` for the full list. Key variables:

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | — | Google Gemini API key |
| `GROQ_API_KEY` | — | Groq API key |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `USE_LOCAL_LLM` | `false` | Prefer local Ollama first |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/tracelite.db` | Database path |
| `MAX_FILE_SIZE_MB` | `50` | Max upload size |
| `MAX_FILES_PER_SESSION` | `7` | Max papers per session |
| `MAX_PARALLEL_PAPERS` | `3` | Concurrent processing limit |

---

## Scripts

```bash
# Download embedding + cross-encoder models
python -m scripts.download_models

# Benchmark HAVF verification latency
python -m scripts.benchmark_havf

# Seed database with demo session
python -m scripts.seed_db
```

---

## Hardware Target

Optimised for **8 GB unified memory** (M-series Mac / equivalent):

| Component | Memory |
|---|---|
| Embedding model (mixedbread-ai/mxbai-embed-large-v1) | ~200 MB |
| Cross-encoder (lazy-loaded) | ~80 MB |
| FAISS index (7 papers) | ~5 MB |
| SQLite + app overhead | ~100 MB |
| **Total** | **~3.1 GB headroom** |
