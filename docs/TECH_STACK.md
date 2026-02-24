# TraceLit — Technology Stack

> Complete technology stack with rationale for every choice.  
> All decisions are optimized for **M3 MacBook Pro (8GB unified memory)**.

---

## 1. Frontend

| Technology | Version | Purpose | Why This |
|-----------|---------|---------|----------|
| **React** | 18+ | UI framework | Industry standard, rich ecosystem, component model |
| **Vite** | 5+ | Build tool | 10-100x faster HMR than CRA/Webpack |
| **Tailwind CSS** | 3+ | Styling | Utility-first, rapid prototyping, small bundle |
| **Zustand** | 4+ | State management | Tiny (1KB), simpler than Redux, no boilerplate |
| **TanStack Query (React Query)** | 5+ | Server state & caching | Automatic refetch, cache invalidation, loading states |
| **React Router** | v6 | Client-side routing | Standard for React SPA routing |
| **Lucide React** | Latest | Icons | Lightweight, consistent icon set |
| **react-markdown** + **remark-gfm** | Latest | Markdown rendering | Render LLM responses with formatting |
| **Recharts** | Latest | Charts & visualization | Confidence dashboards, analytics |
| **TanStack Table** | Latest | Data tables | Comparison table with sorting, filtering, editing |
| **React Hot Toast** | Latest | Notifications | Lightweight toast notifications |
| **@headlessui/react** | Latest | Accessible UI primitives | Modals, dropdowns, toggles — unstyled, accessible |

### Frontend Architecture

```
State Management:
  Zustand stores (chatStore, paperStore, sessionStore)
    ↕ (subscribe/update)
  React components
    ↕ (fetch/mutate)
  TanStack Query (server state cache)
    ↕ (HTTP/SSE/WebSocket)
  FastAPI backend
```

---

## 2. Backend

| Technology | Version | Purpose | Why This |
|-----------|---------|---------|----------|
| **FastAPI** | 0.100+ | Web framework | Async-native, auto docs, Pydantic integration |
| **AsyncIO** | stdlib | Async I/O | Native Python async for concurrent paper processing |
| **Uvicorn** | Latest | ASGI server | Production-grade, async support |
| **Pydantic** | v2 | Validation & serialization | Type-safe request/response models, fast in v2 |
| **PyMuPDF4LLM** | Latest | PDF extraction (primary) | Fast, reliable, good structure preservation |
| **Docling** | Latest | PDF extraction (Phase 2) | AI-powered, better tables — optional, heavier |
| **Sentence-Transformers** | Latest | Embedding model | MPS-accelerated, all-MiniLM-L6-v2 |
| **CrossEncoder** | Latest | HAVF Level 2 reranking | ms-marco-MiniLM-L-6-v2 for selective reranking |
| **ChromaDB** | 0.4+ | Vector store | Persistent, cosine similarity, Metal-optimized |
| **SQLite** | stdlib | Relational database | Zero-config, file-based, embedded — perfect for local app |
| **SQLAlchemy** | 2.0+ | ORM | Async support, declarative models |
| **Alembic** | Latest | DB migrations | Schema versioning for SQLite |
| **WeasyPrint** | Latest | PDF export | HTML/CSS → PDF, Jinja2 templates |
| **openpyxl** | Latest | Excel export | Comparison tables, metadata sheets |
| **python-docx** | Latest | Word export | Literature review export |
| **KeyBERT** | Latest | Keyword extraction (Phase 2) | MMR diversity, quick setup |
| **scikit-learn** | Latest | Clustering (Phase 2) | DBSCAN for research gap clustering |
| **aiofiles** | Latest | Async file I/O | Non-blocking file reads/writes |

---

## 3. LLM Providers

| Provider | Model | Rate Limit | Latency | Role |
|----------|-------|-----------|---------|------|
| **Google Gemini** | gemini-2.0-flash-exp | 250K TPM | ~1s | Primary |
| **Groq** | llama-3.1-70b-versatile | 30K TPM | ~0.5s | Fallback |
| **Ollama** | llama3.2:3b | Unlimited | ~2–3s | Optional (local/privacy) |

### Python SDK Dependencies

```
google-generativeai    # Gemini
groq                   # Groq
ollama                 # Ollama (local)
```

---

## 4. ML Models

| Model | Size | RAM | Device | Purpose |
|-------|------|-----|--------|---------|
| `all-MiniLM-L6-v2` | 23MB | ~200MB | MPS (M3 GPU) | Embedding generation |
| `cross-encoder/ms-marco-MiniLM-L-6-v2` | ~80MB | ~200MB | CPU | HAVF Level 2 reranking |
| `llama3.2:3b` (Ollama) | ~2GB | ~3GB | MPS | Local LLM (optional) |

### Why These Models

- **all-MiniLM-L6-v2**: Best speed/size/quality ratio. 23MB fits easily. MPS gives 2.7x speedup over CPU.
- **ms-marco-MiniLM-L-6-v2**: Best lightweight cross-encoder for semantic similarity reranking.
- **all-mpnet-base-v2**: Better quality but 420MB — ruled out for memory constraints.
- **instructor-xl**: Best quality but 5GB — won't fit in 8GB budget.

---

## 5. Infrastructure

| Technology | Purpose |
|-----------|---------|
| **Docker** + **Docker Compose** | Container orchestration |
| **Nginx** (in frontend container) | Static file serving, reverse proxy |
| **Git** | Version control |

### Docker Memory Budget

| Container | Allocation |
|-----------|-----------|
| backend | 3GB (embeddings + cross-encoder + FastAPI + processing) |
| chromadb | 1GB |
| frontend | 512MB |
| System overhead | ~2GB |
| **Total peak** | **~4–6GB** (within 8GB budget) |

---

## 6. M3-Specific Optimizations

| Optimization | Implementation | Impact |
|-------------|----------------|--------|
| **MPS acceleration** | `SentenceTransformer.to('mps')` | 2.7x faster embeddings |
| **Parallel processing** | 3 papers concurrently (4P + 6E cores) | ~2 min for 5 papers |
| **Lazy model loading** | Load embedding/cross-encoder on first use | Lower idle memory |
| **Batch embedding** | `batch_size=64` | Fewer MPS kernel launches |
| **Metal-optimized ChromaDB** | Persistent mode, cosine distance | Native M3 performance |
| **Memory monitoring** | Alert if >6GB usage | Prevent OOM crashes |

---

## 7. Development Tools

| Tool | Purpose |
|------|---------|
| **pytest** | Backend testing |
| **httpx** | Async test client for FastAPI |
| **Vitest** or **Jest** | Frontend testing |
| **ESLint** + **Prettier** | Code linting/formatting (frontend) |
| **Black** + **isort** | Code formatting (backend) |
| **Ruff** | Fast Python linter |

---

## 8. requirements.txt (Backend)

```
# Web Framework
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
pydantic>=2.0.0
python-multipart
aiofiles

# PDF Extraction
pymupdf4llm>=0.0.5
pymupdf>=1.23.0

# ML / Embeddings
sentence-transformers>=2.2.0
torch>=2.0.0
numpy>=1.24.0

# Vector Store
chromadb>=0.4.0

# Database
sqlalchemy>=2.0.0
alembic>=1.12.0

# LLM Providers
google-generativeai>=0.3.0
groq>=0.4.0
ollama>=0.1.0

# Export
weasyprint>=60.0
openpyxl>=3.1.0
python-docx>=0.8.11
jinja2>=3.1.0

# Phase 2
keybert>=0.8.0
scikit-learn>=1.3.0

# Utilities
python-dotenv>=1.0.0
loguru>=0.7.0
```

---

## 9. package.json (Frontend — Key Dependencies)

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.20.0",
    "zustand": "^4.4.0",
    "@tanstack/react-query": "^5.0.0",
    "@tanstack/react-table": "^8.10.0",
    "react-markdown": "^9.0.0",
    "remark-gfm": "^4.0.0",
    "recharts": "^2.10.0",
    "lucide-react": "^0.300.0",
    "@headlessui/react": "^1.7.0",
    "react-hot-toast": "^2.4.0",
    "axios": "^1.6.0"
  },
  "devDependencies": {
    "vite": "^5.0.0",
    "@vitejs/plugin-react": "^4.2.0",
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.0",
    "autoprefixer": "^10.4.0",
    "eslint": "^8.50.0",
    "prettier": "^3.1.0"
  }
}
```

---

## 10. Environment Variables

```bash
# LLM API Keys
GEMINI_API_KEY=
GROQ_API_KEY=

# Database
DATABASE_URL=sqlite:///./data/tracelit.db

# ML Models
EMBEDDING_MODEL=all-MiniLM-L6-v2
CROSS_ENCODER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2

# HAVF Thresholds
HIGH_CONFIDENCE_THRESHOLD=0.85
MEDIUM_CONFIDENCE_THRESHOLD=0.65

# Application
MAX_PAPERS=7
MAX_UPLOAD_SIZE_MB=50
MAX_CONCURRENT_PAPERS=3
LLM_TIMEOUT=30
LLM_TEMPERATURE=0.3
```
