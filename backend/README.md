# Trace-Lit Backend — The Intelligence Engine

> **High-performance academic RAG pipeline with multi-stage verification and layout-aware document intelligence.**

The TraceLit backend is an asynchronous Python service built on FastAPI. It manages the entire lifecycle of research analysis—from layout-aware PDF extraction and sentence-level vector indexing to multi-document synthetic reasoning and automated hallucination verification.

---

## 🚀 Quick Start

### 1. Install dependencies
```bash
python -m venv .venv
source .venv/bin/activate  # macOS / Linux
# .venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env with your API keys (GEMINI_API_KEY, etc.)
```

### 3. Run the server
```bash
python -m scripts.download_models  # One-time model download
uvicorn app.main:app --reload --port 8000
```

---

## 🛠️ Backend Tech Stack

| Layer | Technology | Rationale |
| :--- | :--- | :--- |
| **Framework** | FastAPI | High-performance, async-first, and native OpenAPI support. |
| **Database** | SQLite + SQLAlchemy 2.0 | Local-first persistence with modern async ORM patterns. |
| **Vector Store** | FAISS | Efficient sentence-level similarity search for academic retrieval. |
| **ML Runtime** | Sentence-Transformers | Local execution of embedding and cross-encoder models. |
| **PDF Intelligence** | PyMuPDF + rapidocr | Robust text, table, and figure extraction from academic PDFs. |
| **LLM Orchestration**| Custom Fallback Chain | Resilient routing: Gemini → Groq → Ollama (local fallback). |
| **Reporting** | WeasyPrint + openpyxl | Professional PDF/Excel export for research summaries. |

---

## 🏗️ Core Domain Logic (`domain/`)

The backend is structured around a domain-driven design to isolate complex research logic:

### 1. HAVF (Hallucination-Aware Verification Framework)
The flagship feature of Trace-Lit. It implements a multi-stage verification pipeline for every claim:
*   **Level 1 (Direct Match)**: Batch similarity search using the primary embedding model.
*   **Level 2 (Neural Rerank)**: Cross-encoder reranking (`BAAI/bge-reranker-base`) for complex paraphrases.
*   **Verification**: Categorizes claims into HIGH, MEDIUM, or LOW confidence.

### 2. Layout-Aware Extraction
Unlike standard "blind" chunking, Trace-Lit understands academic structure:
*   **Section Detection**: Prefixes chunks with their corresponding section (e.g., *Methods*, *Results*).
*   **Visual Elements**: Detects and extracts tables and figures, linking them to their textual references.
*   **Sentence-Level Indexing**: Indexes every individual sentence to enable hyper-precise attribution.

### 3. Multi-Paper Intelligence
Orchestrates synthetic reasoning across a user's library:
*   **Gap Finder**: Uses KeyBERT for keyword extraction and DBSCAN for topic clustering to identify research voids.
*   **Structured Comparison**: Extracts methodology, findings, and limitations for side-by-side analysis.
*   **Literature Synthesis**: Merges disparate sources into a cohesive narrative review.

---

## 🚦 Background Processing & Workers

Trace-Lit is designed to handle heavy workloads on consumer hardware:

*   **SmartPaperQueue**: A memory-aware asyncio priority queue that manages document ingestion. It limits parallelism to prevent CPU/RAM exhaustion and provides real-time progress via WebSockets.
*   **ExportPool**: A dedicated thread pool for generating intensive PDF and Excel reports without blocking the main event loop.
*   **Memory Safeguards**: Automatically pauses processing if system RAM exceeds 75%, resuming only when resources are available.

---

## 🔧 Environment & Configuration

Trace-Lit supports different hardware profiles via `.env`:

### Standard Profile (≥ 16 GB RAM / GPU)
Targets high-fidelity retrieval with larger models.
*   **Embedding**: `mixedbread-ai/mxbai-embed-large-v1` (1024d)
*   **Reranker**: `BAAI/bge-reranker-base`

### Low-RAM Profile (Mac M1/M2 or 8 GB RAM)
Optimized for efficiency without sacrificing core utility.
*   **Embedding**: `BAAI/bge-small-en-v1.5` (384d)
*   **Reranker**: `ms-marco-MiniLM-L-6-v2`

---

## 📜 API at a Glance

| Endpoint | Type | Description |
| :--- | :--- | :--- |
| `/api/v1/sessions` | REST | CRUD for research sessions. |
| `/api/v1/papers` | REST/Upload | Ingest and manage PDF sources. |
| `/api/v1/chat` | SSE Stream | Verified research Q&A with real-time streaming. |
| `/api/v1/analysis` | REST | Access Gaps, Reviews, and Comparisons. |
| `/api/v1/ws` | WebSocket | Live document processing progress updates. |

---

*Trace-Lit Backend: Engineering Rigor for Academic Excellence.*
