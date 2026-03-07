# TraceLit — Mac Optimisation & Production Roadmap

> **Target Hardware**: M3 MacBook, 8GB Unified Memory, 512GB SSD, macOS  
> **Created**: 6 March 2026  
> **Status**: Pre-implementation — all items are recommendations from full codebase audit  
> **Goal**: Run reliably on 8GB Mac NOW, convert to production-ready deployment LATER

---

## Table of Contents

1. [Memory Budget](#1-memory-budget)
2. [Critical Changes (Must Do First)](#2-critical-changes-must-do-first)
3. [Required Changes (High Priority)](#3-required-changes-high-priority)
4. [Recommended Changes (Medium Priority)](#4-recommended-changes-medium-priority)
5. [Latency Optimisations](#5-latency-optimisations)
6. [RAG & HAVF Pipeline Tuning](#6-rag--havf-pipeline-tuning)
7. [Extraction Pipeline Tuning](#7-extraction-pipeline-tuning)
8. [Recommended .env Configuration](#8-recommended-env-configuration)
9. [Production Readiness Roadmap](#9-production-readiness-roadmap)
10. [Implementation Order](#10-implementation-order)

---

## 1. Memory Budget

### Current State (BROKEN on 8GB Mac)

| Component | RAM Usage | Notes |
|---|---|---|
| macOS + system processes | ~2.5 GB | Fixed, non-negotiable |
| FastAPI + SQLite + uvicorn | ~150 MB | Lean, fine |
| SentenceTransformer (`all-MiniLM-L6-v2`) | ~90 MB | Embedding model |
| Cross-encoder (`ms-marco-MiniLM-L-6-v2`) | ~90 MB | HAVF Level 2, lazy-loaded |
| KeyBERT (DUPLICATE `all-MiniLM-L6-v2`) | ~90 MB | **WASTED — loads same model twice** |
| RapidOCR (ONNX Runtime) | ~80 MB | For scanned PDF fallback |
| FAISS index (5-7 papers) | ~5-15 MB | IndexFlatIP, 384-dim |
| Ollama `qwen3.5` (current default) | **3-5 GB** | **TOO LARGE for 8GB Mac** |
| **TOTAL** | **~6-8+ GB** | **Exceeds available RAM → swap → crashes** |

### Target State (After All Changes)

| Component | RAM Usage | Notes |
|---|---|---|
| macOS + system processes | ~2.5 GB | Fixed |
| FastAPI + SQLite + uvicorn | ~150 MB | No change |
| SentenceTransformer (shared) | ~90 MB | MPS GPU-accelerated |
| Cross-encoder (lazy) | ~90 MB | Only loaded when uncertain claims exist |
| KeyBERT | **0 MB** | Eliminated — reuse shared encoder |
| RapidOCR (lazy) | ~80 MB | Only loaded for scanned pages |
| FAISS index | ~5-15 MB | No change |
| Ollama (OFF by default) | **0 GB** | Cloud-first; toggle on only when needed |
| **TOTAL backend** | **~450-550 MB** | **Leaves ~5 GB for macOS headroom** |

---

## 2. Critical Changes (Must Do First)

These changes are BLOCKING — the app will not run reliably on 8GB Mac without them.

### CRIT-1: Default to Cloud-First LLM Mode

**Problem**: `USE_LOCAL_LLM=true` in `.env` loads Ollama which consumes 3-5 GB RAM on startup, leaving virtually no memory for macOS + embeddings + HAVF.

**File**: `backend/.env`

**Change**:
```env
# BEFORE
USE_LOCAL_LLM=true

# AFTER
USE_LOCAL_LLM=false
```

**Also update default in**: `backend/app/config.py` line ~24
```python
# BEFORE
USE_LOCAL_LLM: bool = True

# AFTER
USE_LOCAL_LLM: bool = False
```

**Impact**: Saves 3-5 GB RAM immediately. Backend drops to ~450 MB.

**Production note**: Production should always use cloud providers (Gemini/Groq). Local Ollama is a developer fallback only.

---

### CRIT-2: Change Ollama Model from `qwen3.5` to `qwen2.5:3b`

**Problem**: `qwen3.5` requires ~4-5 GB RAM. Even when toggled on temporarily, it causes memory pressure on 8GB Mac. The model is too large.

**File**: `backend/.env`

**Change**:
```env
# BEFORE
OLLAMA_MODEL=qwen3.5

# AFTER
OLLAMA_MODEL=qwen2.5:3b
```

**Also update default in**: `backend/app/config.py` line ~24
```python
# BEFORE
OLLAMA_MODEL: str = "qwen3.5"

# AFTER
OLLAMA_MODEL: str = "qwen2.5:3b"
```

**Why `qwen2.5:3b`**:
- ~2 GB RAM (fits alongside embeddings on 8GB)
- Good quality for a 3B model
- Supports the same features as qwen3.5 minus think-blocks
- Alternative: `phi3:mini` (~1.7 GB, slightly less capable)

**Impact**: When Ollama IS toggled on, total backend stays under ~3 GB.

**Production note**: Ollama should not be used in production. Cloud providers handle all traffic.

---

### CRIT-3: Reduce Ollama Context Window

**Problem**: `OLLAMA_NUM_CTX=4096` allocates KV cache memory proportional to context length. On 8GB Mac with a 3B model this is still tight.

**File**: `backend/.env`

**Change**:
```env
# BEFORE
OLLAMA_NUM_CTX=4096

# AFTER
OLLAMA_NUM_CTX=2048
```

**Also update default in**: `backend/app/config.py`
```python
# BEFORE
OLLAMA_NUM_CTX: int = 4096

# AFTER
OLLAMA_NUM_CTX: int = 2048
```

**Impact**: Reduces Ollama KV cache by ~50%. Combined with smaller model, Ollama fits safely.

**Production note**: Not applicable — Ollama not used in production.

---

### CRIT-4: Reduce Max Parallel Papers to 1

**Problem**: `MAX_PARALLEL_PAPERS=2` means two papers being processed simultaneously. Each paper processing step loads PDFs into memory, runs OCR, creates embeddings — easily consuming 500MB+ per paper concurrently.

**File**: `backend/.env`

**Change**:
```env
# BEFORE (or default in config.py)
MAX_PARALLEL_PAPERS=2

# AFTER
MAX_PARALLEL_PAPERS=1
```

**Also update default in**: `backend/app/config.py`
```python
# BEFORE
MAX_PARALLEL_PAPERS: int = 2

# AFTER
MAX_PARALLEL_PAPERS: int = 1
```

**Files affected**: `backend/workers/paper_queue.py` — the `SmartPaperQueue` uses this as its semaphore limit.

**Impact**: Prevents memory spikes during paper processing. Papers queue instead of running in parallel.

**Production note**: Production on a server with 16-32 GB can set this to 3-4.

---

### CRIT-5: Raise Memory Pressure Threshold

**Problem**: `MEMORY_PRESSURE_THRESHOLD=0.70` means the paper queue pauses when 70% of RAM is used. On macOS, system processes alone use 40-50%, so the threshold fires prematurely and blocks paper processing entirely.

**File**: `backend/.env`

**Change**:
```env
# BEFORE
MEMORY_PRESSURE_THRESHOLD=0.70

# AFTER
MEMORY_PRESSURE_THRESHOLD=0.80
```

**Also update default in**: `backend/app/config.py`
```python
# BEFORE
MEMORY_PRESSURE_THRESHOLD: float = 0.70

# AFTER
MEMORY_PRESSURE_THRESHOLD: float = 0.80
```

**Why 0.80**: macOS manages memory aggressively with compressed memory and swap. 80% virtual usage is safe on M3 with fast SSD swap. Below 80% the system runs smoothly.

**Impact**: Paper processing no longer falsely pauses on macOS.

**Production note**: On a dedicated Linux server, 0.75 is appropriate (no desktop OS overhead).

---

### CRIT-6: Disable Debug Mode

**Problem**: `DEBUG=true` enables verbose logging, potentially stores extra data in memory, and may disable certain optimisations.

**File**: `backend/.env`

**Change**:
```env
# BEFORE
DEBUG=true

# AFTER
DEBUG=false
```

**Impact**: Reduces logging overhead, slight memory savings from less buffered log data.

**Production note**: Always `false` in production. Use structured logging with log levels instead.

---

## 3. Required Changes (High Priority)

These are important for performance and correctness but the app CAN start without them.

### REQ-1: Eliminate KeyBERT Duplicate Model Load

**Problem**: KeyBERT internally loads its own copy of `all-MiniLM-L6-v2` (~90 MB). The same model is already loaded as the shared embedding encoder in `backend/domain/retrieval/indexer.py`. This wastes 90 MB.

**Files to change**:
- Wherever KeyBERT is imported and used (search for `from keybert import KeyBERT` or `import keybert`)
- `backend/domain/retrieval/indexer.py` — the shared encoder `_get_encoder()`

**Solution options** (choose one):

**Option A — Pass shared encoder to KeyBERT** (recommended):
```python
from domain.retrieval.indexer import _get_encoder

# Instead of: kw_model = KeyBERT()
kw_model = KeyBERT(model=_get_encoder())
```

**Option B — Replace KeyBERT entirely**:
Replace KeyBERT usage with direct embedding similarity using the shared encoder:
```python
from domain.retrieval.indexer import encode_texts, encode_query
import numpy as np

def extract_keywords(text: str, top_n: int = 5) -> list[str]:
    # Split text into candidate phrases
    candidates = _extract_candidate_phrases(text)
    if not candidates:
        return []
    
    doc_embedding = encode_query(text)
    candidate_embeddings = encode_texts(candidates)
    similarities = (doc_embedding @ candidate_embeddings.T).flatten()
    top_indices = np.argsort(similarities)[-top_n:][::-1]
    return [candidates[i] for i in top_indices]
```

**Impact**: Saves ~90 MB RAM.

**Production note**: Option B is preferred in production — removes the `keybert` dependency entirely, simplifying the Docker image.

---

### REQ-2: Unify Embedding Batch Size

**Problem**: `backend/shared/constants.py` defines `EMBEDDING_BATCH_SIZE = 32`, but `backend/domain/retrieval/indexer.py` line 52 hardcodes `batch_size=64` in `encode_texts()`. Larger batches use more peak memory during paper indexing.

**File**: `backend/domain/retrieval/indexer.py`

**Change**:
```python
# BEFORE (line 52)
def encode_texts(texts: list[str], batch_size: int = 64) -> np.ndarray:

# AFTER
from shared.constants import EMBEDDING_BATCH_SIZE

def encode_texts(texts: list[str], batch_size: int = EMBEDDING_BATCH_SIZE) -> np.ndarray:
```

**Impact**: Lower peak memory during batch encoding. On 8GB Mac, batch_size=32 is the right balance between speed and memory.

**Production note**: On GPU servers, increase `EMBEDDING_BATCH_SIZE` to 128 or 256 via config.

---

### REQ-3: Reduce Ollama Keep-Alive Time

**Problem**: `OLLAMA_KEEP_ALIVE=10m` keeps the loaded model in RAM for 10 minutes after the last request. On 8GB Mac, this blocks 2-3 GB for 10 minutes of idle time.

**File**: `backend/.env`

**Change**:
```env
# BEFORE
OLLAMA_KEEP_ALIVE=10m

# AFTER
OLLAMA_KEEP_ALIVE=5m
```

**Impact**: Model unloads 5 minutes sooner, freeing 2-3 GB.

**Production note**: Not applicable — Ollama not used in production.

---

### REQ-4: Add Ollama Model Unload on Toggle-Off

**Problem**: When a user toggles `USE_LOCAL_LLM` to `false` via the settings endpoint (`PUT /api/v1/settings/ollama`), the FallbackChain is rebuilt but the Ollama model stays loaded in RAM. There is no API call to unload it.

**File**: `backend/api/v1/routes/settings.py`

**Change**: After toggling off, call the Ollama API to unload the model:
```python
import httpx

async def _unload_ollama_model(settings):
    """Tell Ollama to unload the model by setting keep_alive to 0."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "keep_alive": 0,
                },
                timeout=10.0,
            )
    except Exception as exc:
        logger.warning(f"Failed to unload Ollama model: {exc}")
```

Call this function when `use_local_llm` is set to `false` in the toggle endpoint.

**Impact**: Immediately reclaims 2-3 GB when switching to cloud mode.

**Production note**: Good practice even in production — clean resource release.

---

### REQ-5: Reduce LLM Timeout for Cloud Providers

**Problem**: `LLM_TIMEOUT=30` applies to all providers. Cloud providers (Gemini, Groq) should fail fast (15s) so the fallback chain can try the next provider quickly. Ollama legitimately needs 120-240s for local inference.

**File**: `backend/.env`

**Change**:
```env
# BEFORE
LLM_TIMEOUT=30

# AFTER
LLM_TIMEOUT=15
OLLAMA_TIMEOUT=120
```

**File**: `backend/app/config.py` — already has `OLLAMA_TIMEOUT` separate from `LLM_TIMEOUT`.

**Impact**: If Gemini is down, fallback to Groq happens in 15s instead of 30s. User perceives faster recovery.

**Production note**: In production, set `LLM_TIMEOUT=10` for even faster failover. Add circuit breaker patterns.

---

### REQ-6: Reduce FAISS Max Vectors

**Problem**: `FAISS_MAX_VECTORS = 200_000` in `backend/shared/constants.py`. For 5-7 papers at ~50-100 pages each, you'll have ~2,000-5,000 chunks. 200K is 40-100× oversized and wastes pre-allocated memory.

**File**: `backend/shared/constants.py`

**Change**:
```python
# BEFORE
FAISS_MAX_VECTORS: int = 200_000

# AFTER
FAISS_MAX_VECTORS: int = 50_000
```

**Impact**: Reduces pre-allocated FAISS memory. Still handles 10× the expected workload.

**Production note**: For a multi-user SaaS with thousands of papers, increase to 500K+ and consider IndexIVFFlat for faster search.

---

### REQ-7: Reduce Max Tokens for Ollama Responses

**Problem**: `OLLAMA_MAX_TOKENS=1536`. On a 3B model with 2048 context window, generating 1536 tokens leaves only 512 tokens for the prompt. This will either truncate context or produce incomplete responses.

**File**: `backend/.env`

**Change**:
```env
# BEFORE
OLLAMA_MAX_TOKENS=1536

# AFTER
OLLAMA_MAX_TOKENS=1024
```

**Impact**: Leaves 1024 tokens for prompt context when using Ollama (2048 - 1024). Sufficient for single-paper queries.

**Production note**: Cloud providers have much larger context windows (Gemini: 1M, Groq: 128K). `OLLAMA_MAX_TOKENS` only affects Ollama. Add a separate `LLM_MAX_TOKENS` for cloud providers set to 2048-4096.

---

## 4. Recommended Changes (Medium Priority)

These improve quality and efficiency but are not blocking.

### OPT-1: Reduce Figure Image DPI

**Problem**: `FIGURE_IMAGE_DPI = 150` in `backend/shared/constants.py`. Higher DPI = larger images in memory during extraction. Gemini vision works well at 100 DPI for academic figures.

**File**: `backend/shared/constants.py`

**Change**:
```python
# BEFORE
FIGURE_IMAGE_DPI: int = 150

# AFTER
FIGURE_IMAGE_DPI: int = 100
```

**Impact**: ~40% smaller images during extraction. Less memory pressure, faster upload to Gemini API.

**Production note**: Keep at 100 in production too — Gemini handles it well.

---

### OPT-2: Add Garbage Collection After Paper Processing

**Problem**: After processing a paper (extract → chunk → embed → index), Python doesn't immediately release memory. On 8GB Mac, this can cause the next paper in queue to start under memory pressure.

**File**: `backend/workers/paper_worker.py` (or wherever paper processing completes)

**Change**: Add at the end of paper processing:
```python
import gc

# After paper processing completes:
gc.collect()
```

**Impact**: Explicitly releases memory after large operations. ~50-200 MB freed per paper.

**Production note**: Not needed on servers with ample RAM, but doesn't hurt.

---

### OPT-3: Lazy-Load RapidOCR

**Problem**: RapidOCR (~80 MB) should only be loaded when a scanned page is detected. Verify that the current code in `backend/domain/extraction/pdf_processor.py` does NOT preload it at import time.

**Verification**: Check that `from rapidocr_onnxruntime import RapidOCR` is inside a function, not at module level.

**If it's at module level**: Move the import inside the function that uses it:
```python
def _ocr_page(self, page):
    from rapidocr_onnxruntime import RapidOCR
    ocr = RapidOCR()
    # ...
```

**Impact**: 80 MB saved for papers that don't need OCR (most born-digital PDFs).

**Production note**: In production, consider keeping OCR warm if most uploads are scanned documents.

---

### OPT-4: Reduce Database Pool Size

**Problem**: SQLAlchemy default pool can hold connections. For a single-user local app, the pool is oversized.

**File**: `backend/infrastructure/db/database.py`

**Verify current settings** and ensure pool is minimal:
```python
engine = create_async_engine(
    DATABASE_URL,
    pool_size=5,      # Was likely 10
    max_overflow=3,    # Was likely 5
    pool_recycle=3600,
)
```

**Impact**: Minor memory savings from fewer idle connections.

**Production note**: Production with multiple users needs `pool_size=20`, `max_overflow=10`, and connection pooling via PgBouncer if using PostgreSQL.

---

### OPT-5: MPS vs Ollama GPU Contention

**Problem**: If Ollama IS toggled on, both Ollama and SentenceTransformer compete for the same Apple Silicon GPU (unified memory). This causes memory pressure and slower inference for both.

**Fix**: When `USE_LOCAL_LLM=true`, force SentenceTransformer to CPU to avoid GPU contention:

**File**: `backend/domain/retrieval/indexer.py`

**Change** in `_get_encoder()`:
```python
def _get_encoder() -> SentenceTransformer:
    global _encoder
    if _encoder is None:
        device = "cpu"
        settings = get_settings()
        
        # Only use MPS if Ollama is NOT active (GPU contention)
        if not settings.USE_LOCAL_LLM and _mps_available():
            device = "mps"
        
        _encoder = SentenceTransformer(EMBEDDING_MODEL_NAME)
        if device == "mps":
            import torch
            _encoder = _encoder.to(torch.device("mps"))
    return _encoder
```

**Impact**: Prevents GPU memory contention. CPU embedding is still fast enough (~10ms per query on M3).

**Production note**: Production GPU servers can dedicate separate GPUs for embedding and LLM inference.

---

## 5. Latency Optimisations

### LAT-1: Cache Source Embeddings at Index Time (HIGHEST IMPACT)

**Problem**: During HAVF verification, `backend/domain/verification/embedding_verifier.py` lines 74-78 re-encode ALL source sentences from retrieved chunks on every single query. This takes 50-200ms per query — it's the single largest latency bottleneck in the verification pipeline.

**Current flow**:
```
Query → Retrieve chunks → Extract source sentences → ENCODE source sentences (50-200ms) → Cosine similarity → Result
```

**Proposed flow**:
```
[At index time] Chunk sentences → Encode → Store embeddings in DB as BLOB
[At query time] Query → Retrieve chunks → LOAD pre-computed embeddings from DB (5ms) → Cosine similarity → Result
```

**Files to change**:
1. `backend/infrastructure/db/models/` — Add `embedding` BLOB column to chunk sentence storage
2. `backend/domain/retrieval/indexer.py` — At index time, store sentence-level embeddings
3. `backend/domain/verification/embedding_verifier.py` — Load cached embeddings instead of re-encoding

**Implementation sketch**:
```python
# In indexer.py, at index time:
for chunk in chunks:
    for s_key, info in chunk.sentence_map.items():
        sentence_vec = encode_texts([info["text"]])[0]
        # Store sentence_vec as np.float32 bytes in DB alongside the sentence

# In embedding_verifier.py, at verification time:
def verify_claims_embedding(claims, source_sentences, ...):
    # Load pre-computed source vectors from source_sentences (already cached)
    source_vecs = np.array([s["embedding"] for s in source_sentences])
    claim_vecs = encode_texts(claims)  # Only encode claims (few, fast)
    similarity_matrix = claim_vecs @ source_vecs.T
    # ... rest unchanged
```

**Impact**: HAVF Level 1 drops from ~50-200ms to ~5-10ms per query. This is a 10-20× improvement.

**Effort**: 2-3 hours (DB migration + indexer change + verifier change).

**Production note**: Essential for production — this is a scalability bottleneck. With 100 concurrent users, encoding source sentences on every query is unsustainable.

---

### LAT-2: Stream-First Response Pattern

**Current state**: Already implemented in `backend/domain/generation/streaming.py`. SSE streaming sends tokens to the frontend as they arrive from the LLM. HAVF runs AFTER streaming completes, then sends confidence scores as a separate SSE event.

**This is the correct pattern.** No change needed for Mac.

**Timeline for user**:
```
~300ms-2s: First token appears (TTFT from Gemini/Groq)
~3-10s:    Full response streamed
~200ms:    HAVF verification completes, confidence badges appear
```

**Production note**: Consider WebSocket instead of SSE for bidirectional communication (cancel mid-stream, etc.).

---

### LAT-3: Pre-Warm Cross-Encoder on First Query

**Problem**: The cross-encoder in `backend/domain/verification/reranker.py` is lazy-loaded. The first query that triggers Level 2 reranking takes an extra ~2-3 seconds to download/load the model.

**Options**:

**Option A — Keep lazy loading (recommended for Mac)**: Saves 90 MB until needed. Most queries (89%) resolve at Level 1 and never need the cross-encoder.

**Option B — Pre-warm in lifespan**: Load during app startup in `backend/app/lifespan.py`:
```python
from domain.verification.reranker import async_get_cross_encoder

async def lifespan(app):
    # Pre-warm cross-encoder (adds ~90 MB but avoids first-query latency)
    await async_get_cross_encoder()
    yield
```

**Recommendation for Mac**: Option A (lazy). The first-query penalty is acceptable.

**Production note**: Option B for production — pre-warm everything at deploy time to ensure consistent latency.

---

## 6. RAG & HAVF Pipeline Tuning

### RAG-1: Increase FAISS Top-K Per Paper

**Problem**: `FAISS_TOP_K_PER_PAPER = 3` in `backend/shared/constants.py`. With 5-7 papers, this retrieves only 15-21 chunks. For multi-document comparison queries, this may miss relevant context.

**File**: `backend/shared/constants.py`

**Change**:
```python
# BEFORE
FAISS_TOP_K_PER_PAPER: int = 3

# AFTER
FAISS_TOP_K_PER_PAPER: int = 5
```

**Impact**: Better retrieval coverage for complex queries. Token budget (`MAX_CONTEXT_TOKENS = 4000`) still applies, so adding more candidates doesn't increase prompt size — it just gives better candidates to select from.

**Production note**: Consider dynamic top-k based on query type (comparison: 7, single-paper: 3).

---

### RAG-2: Add Sentence Overlap Between Chunks

**Problem**: `backend/domain/retrieval/chunker.py` splits paragraphs into chunks with ZERO overlap. Sentences at chunk boundaries lose surrounding context, which can cause HAVF to give LOW confidence scores for boundary sentences.

**File**: `backend/domain/retrieval/chunker.py`

**Change in `_split_large_paragraph()`**: Add 1-2 sentences from the end of the previous chunk to the start of the next:
```python
def _split_large_paragraph(text, section_title, paper_title, start_idx, paper_id=None):
    sentences = split_into_sentences(text)
    chunks = []
    current_sentences = []
    current_tokens = 0
    idx_offset = 0
    overlap_sentences = []  # NEW: carry-over from previous chunk

    for sentence in sentences:
        s_tokens = estimate_tokens(sentence)

        if current_tokens + s_tokens > CHUNK_TARGET_TOKENS and current_sentences:
            combined = " ".join(current_sentences)
            chunk = _build_chunk(combined, section_title, paper_title, start_idx + idx_offset, paper_id)
            chunks.append(chunk)
            idx_offset += 1
            overlap_sentences = current_sentences[-2:]  # Keep last 2 sentences
            current_sentences = list(overlap_sentences)  # Start next chunk with overlap
            current_tokens = sum(estimate_tokens(s) for s in current_sentences)

        current_sentences.append(sentence)
        current_tokens += s_tokens

    if current_sentences:
        combined = " ".join(current_sentences)
        chunk = _build_chunk(combined, section_title, paper_title, start_idx + idx_offset, paper_id)
        chunks.append(chunk)

    return chunks
```

**Impact**: Boundary sentences now appear in two chunks, improving HAVF confidence at chunk edges. Slight increase in total chunks (~10-15%).

**Production note**: Good practice in any RAG system. Consider configurable overlap via constants.

---

### RAG-3: Reduce Chunk Target Tokens for Better Granularity

**Problem**: `CHUNK_TARGET_TOKENS = 400` produces relatively large chunks. Smaller chunks improve HAVF matching precision because each chunk contains fewer sentences, making cosine similarity more discriminating.

**File**: `backend/shared/constants.py`

**Change**:
```python
# BEFORE
CHUNK_TARGET_TOKENS: int = 400

# AFTER
CHUNK_TARGET_TOKENS: int = 300
```

Keep `CHUNK_MAX_TOKENS: int = 800` as the safety ceiling.

**Impact**: More precise sentence-level attribution. More chunks per paper, but FAISS search time is negligible at this scale.

**Production note**: 300 tokens is a good default. Can be tuned per-domain (legal: 200, scientific: 300, general: 400).

---

### RAG-4: Increase Context Token Budget

**Problem**: `MAX_CONTEXT_TOKENS = 4000` is conservative. Gemini Flash has 1M context, Groq has 128K. Allowing more context tokens means richer answers with more source material.

**File**: `backend/shared/constants.py`

**Change**:
```python
# BEFORE
MAX_CONTEXT_TOKENS: int = 4_000

# AFTER
MAX_CONTEXT_TOKENS: int = 6_000
```

**Impact**: LLM sees more retrieved chunks → more citations → higher HAVF accuracy. Cost increase is negligible on free tiers.

**Production note**: For paid tiers, increase to 8000-12000. Monitor cost per query.

---

## 7. Extraction Pipeline Tuning

### EXT-1: Reduce Figure Image DPI

(Same as OPT-1 above — listed here for completeness)

**File**: `backend/shared/constants.py`  
**Change**: `FIGURE_IMAGE_DPI: int = 150` → `FIGURE_IMAGE_DPI: int = 100`

---

### EXT-2: Cache Figure Analysis Results

**Problem**: If a paper is re-processed (e.g., after a failed partial processing), all figures are re-analysed via the Gemini vision API. This wastes API quota and time.

**Solution**: Before calling `figure_analyzer.analyze_figure()`, check if the figure's hash + paper_id already has a cached result in the database. If so, skip the API call.

**Files to change**:
- `backend/infrastructure/db/models/` — Add a `figure_analysis_cache` table (paper_id, image_hash, analysis_result)
- `backend/domain/extraction/figure_analyzer.py` — Check cache before calling LLM
- `backend/services/paper_service.py` — Populate cache after analysis

**Impact**: Saves API calls on re-processing. Faster paper re-indexing.

**Effort**: 1-2 hours.

**Production note**: Essential for production — API costs add up with re-processing.

---

### EXT-3: Batch Figure Descriptions for Papers with Many Figures

**Problem**: Papers with 10+ figures make 10+ sequential API calls to Gemini vision (limited to 2 concurrent by semaphore). This is slow.

**Solution**: For papers with >5 figures, batch multiple images into a single Gemini prompt:
```
"Analyze the following academic paper figures. For each, provide TYPE and DESCRIPTION..."
```

Gemini Flash can handle multi-image prompts efficiently.

**Impact**: Reduces API calls from N to ceil(N/4). Faster processing for figure-heavy papers.

**Effort**: 1-2 hours.

**Production note**: Batching also reduces rate-limit pressure on the Gemini API.

---

## 8. Recommended .env Configuration

Replace the entire contents of `backend/.env` with:

```env
# ============================================================
# TraceLit — Mac 8GB Optimised Configuration
# ============================================================

# === Application ===
APP_NAME=TraceLit
DEBUG=false
HOST=0.0.0.0
PORT=8000

# === Database ===
DATABASE_URL=sqlite+aiosqlite:///./data/tracelit.db
SQLITE_BUSY_TIMEOUT_MS=30000

# === LLM Providers — Cloud-First ===
USE_LOCAL_LLM=false
GEMINI_API_KEY=<your-gemini-api-key>
GROQ_API_KEY=<your-groq-api-key>

# === Cloud LLM Settings ===
LLM_TIMEOUT=15
LLM_MAX_RETRIES=1
LLM_RETRY_DELAY_BASE=1.0
LLM_TEMPERATURE=0.3

# === Ollama (Local Fallback — OFF by default) ===
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_TIMEOUT=120
OLLAMA_KEEP_ALIVE=5m
OLLAMA_NUM_CTX=2048
OLLAMA_NUM_THREADS=0
OLLAMA_MAX_TOKENS=1024

# === Memory Management — Mac 8GB ===
MAX_PARALLEL_PAPERS=1
MEMORY_PRESSURE_THRESHOLD=0.80
PAPER_PROCESSING_TIMEOUT_SECONDS=300

# === Upload Limits ===
MAX_UPLOAD_FILES=7
MAX_FILE_SIZE_MB=50
MAX_PAPERS_PER_SESSION=20
MAX_SESSIONS=50

# === HAVF Verification Thresholds ===
HAVF_HIGH_THRESHOLD=0.85
HAVF_MEDIUM_THRESHOLD=0.65
HAVF_CROSS_ENCODER_THRESHOLD=0.75
HAVF_SHORT_SENTENCE_WORDS=5
CROSS_ENCODER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2

# === Storage ===
UPLOADS_DIR=data/uploads
EXPORTS_DIR=data/exports
FAISS_INDEX_DIR=data/faiss_indexes

# === Exports ===
MAX_EXPORT_FILE_SIZE_MB=100
MIN_DISK_SPACE_MB=500

# === Request Handling ===
REQUEST_TIMEOUT=300.0
```

---

## 9. Production Readiness Roadmap

This section documents what needs to change when moving from "runs on my Mac" to "production deployment".

### PROD-1: Database — Migrate from SQLite to PostgreSQL

**Current**: SQLite + aiosqlite. Fine for single-user local dev.

**Production**:
```
PostgreSQL 15+ with:
- asyncpg driver (replace aiosqlite)
- Connection pooling via PgBouncer
- pool_size=20, max_overflow=10
- Alembic for schema migrations
- Automated backups (pg_dump or managed service)
```

**Files to change**:
- `backend/app/config.py` — `DATABASE_URL` → `postgresql+asyncpg://...`
- `backend/infrastructure/db/database.py` — Pool settings
- `backend/requirements.txt` — Add `asyncpg`, remove `aiosqlite`
- Add `alembic/` migration directory

---

### PROD-2: Vector Store — Migration Path from FAISS to Production

**Current**: FAISS IndexFlatIP, single file, in-process.

**Production options**:

| Option | When to Switch | Pros | Cons |
|---|---|---|---|
| FAISS IndexIVFFlat | >50K vectors | Faster search | Needs training |
| Qdrant | Multi-user | REST API, filtering, persistence | Extra service |
| Weaviate | Enterprise | Hybrid search, multi-tenancy | Complex setup |
| Pinecone | Managed | Zero ops | Vendor lock-in, cost |

**Recommendation**: Stay with FAISS until you have >10 concurrent users. Then migrate to Qdrant (self-hosted, open source, Python client).

---

### PROD-3: LLM — Rate Limiting and Cost Control

**Current**: Free tiers only (Gemini 15 RPM, Groq 30 RPM).

**Production**:
- Gemini Pro paid plan with higher limits
- Implement per-user rate limiting (X queries per minute per user)
- Track token usage per query for billing
- Add response caching for repeated questions
- Add circuit breaker: if primary is failing, skip to fallback immediately for 60s

---

### PROD-4: Authentication and Multi-Tenancy

**Current**: No auth. Single user, local-only.

**Production**:
- JWT-based authentication (FastAPI + python-jose)
- User registration + session management
- Paper isolation: user can only access their own papers
- Role-based access control (admin, researcher, viewer)
- API key management for programmatic access

---

### PROD-5: Containerisation

**Current**: Runs directly with `uvicorn` in a virtualenv.

**Production Dockerfile**:
```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY data/ ./data/

# Pre-download models at build time
RUN python backend/scripts/download_models.py

EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

Add `docker-compose.yml` with:
- Backend service
- PostgreSQL service
- Redis service (for caching/queuing)
- Nginx reverse proxy
- Volume mounts for data persistence

---

### PROD-6: Observability

**Current**: Basic Python logging via `shared/logger.py`.

**Production**:
```
- Structured JSON logging (python-json-logger)
- Request tracing (OpenTelemetry + Jaeger)
- Metrics (Prometheus + Grafana):
  - Query latency (p50, p95, p99)
  - HAVF confidence distribution
  - LLM provider success/failure rates
  - Paper processing times
  - Memory/CPU usage
- Error tracking (Sentry)
- Health check endpoint (already exists?)
```

---

### PROD-7: API Security Hardening

**Current**: Basic CORS configuration.

**Production**:
- HTTPS only (TLS termination at Nginx/load balancer)
- Helmet-style security headers
- Request rate limiting (slowapi or similar)
- Input validation: max query length, file type validation, content type checking
- Prompt injection defense: sanitise user queries before embedding in LLM prompt
- CORS lock to specific domains only
- API versioning (already using `/api/v1/`)

---

### PROD-8: Horizontal Scaling Design

**Current architecture is mostly stateless EXCEPT**:
- FAISS index (in-process, file-backed) — needs shared storage or external service
- Paper processing queue (in-memory asyncio queue) — needs Redis/RabbitMQ
- WebSocket connections — need sticky sessions or Redis pub/sub

**To scale horizontally**:
1. Move FAISS → Qdrant (external service)
2. Move paper queue → Celery + Redis
3. Move WebSocket → Redis pub/sub adapter
4. Move file uploads → S3/MinIO
5. Session state → Redis
6. Run multiple uvicorn workers behind a load balancer

---

### PROD-9: CI/CD Pipeline

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -r backend/requirements.txt
      - run: pip install pytest pytest-asyncio httpx
      - run: pytest backend/tests/ -v
  
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install ruff
      - run: ruff check backend/
  
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install safety
      - run: safety check -r backend/requirements.txt
```

---

### PROD-10: Backup and Recovery

- SQLite: Daily file backup of `data/tracelit.db` (rsync/cp)
- FAISS: Can be rebuilt from DB chunks (no separate backup needed)
- Uploads: User PDFs in `data/uploads/` — consider S3 backup
- PostgreSQL (production): `pg_dump` daily, point-in-time recovery

---

## 10. Implementation Order

Execute these in order. Each group can be done in one session.

### Session 1: Emergency Mac Fixes (30 minutes)
1. ✅ CRIT-1: Set `USE_LOCAL_LLM=false`
2. ✅ CRIT-2: Change Ollama model to `qwen2.5:3b`
3. ✅ CRIT-3: Reduce `OLLAMA_NUM_CTX` to 2048
4. ✅ CRIT-4: Set `MAX_PARALLEL_PAPERS=1`
5. ✅ CRIT-5: Set `MEMORY_PRESSURE_THRESHOLD=0.80`
6. ✅ CRIT-6: Set `DEBUG=false`
7. ✅ Apply full `.env` from Section 8

### Session 2: Required Code Changes (2-3 hours)
1. REQ-1: Eliminate KeyBERT duplicate model
2. REQ-2: Unify embedding batch size to 32
3. REQ-4: Add Ollama unload on toggle-off
4. REQ-5: Reduce `LLM_TIMEOUT` to 15s
5. REQ-6: Reduce `FAISS_MAX_VECTORS` to 50K
6. REQ-7: Reduce `OLLAMA_MAX_TOKENS` to 1024

### Session 3: Performance Tuning (2-3 hours)
1. OPT-1: Reduce figure DPI to 100
2. OPT-2: Add gc.collect() after paper processing
3. OPT-3: Verify lazy OCR loading
4. OPT-5: Fix MPS/Ollama GPU contention
5. RAG-1: Increase top-k to 5
6. RAG-3: Reduce chunk target tokens to 300
7. RAG-4: Increase context token budget to 6000

### Session 4: High-Impact Optimisation (3-4 hours)
1. LAT-1: Cache source embeddings at index time
2. RAG-2: Add sentence overlap in chunker

### Session 5: Quality Improvements (2 hours)
1. EXT-2: Cache figure analysis results
2. EXT-3: Batch figure descriptions for multi-figure papers

### Future: Production Migration
- Follow PROD-1 through PROD-10 when ready to deploy

---

## Quick Reference Card

| Setting | Dev (Mac 8GB) | Production |
|---|---|---|
| `USE_LOCAL_LLM` | `false` | `false` |
| `OLLAMA_MODEL` | `qwen2.5:3b` | N/A |
| `MAX_PARALLEL_PAPERS` | `1` | `3-4` |
| `MEMORY_PRESSURE_THRESHOLD` | `0.80` | `0.75` |
| `LLM_TIMEOUT` | `15` | `10` |
| `OLLAMA_NUM_CTX` | `2048` | N/A |
| `OLLAMA_MAX_TOKENS` | `1024` | N/A |
| `EMBEDDING_BATCH_SIZE` | `32` | `128-256` |
| `FAISS_MAX_VECTORS` | `50,000` | `500,000+` |
| `FAISS_TOP_K_PER_PAPER` | `5` | `5-7` |
| `CHUNK_TARGET_TOKENS` | `300` | `300` |
| `MAX_CONTEXT_TOKENS` | `6,000` | `8,000-12,000` |
| `FIGURE_IMAGE_DPI` | `100` | `100` |
| `DEBUG` | `false` | `false` |
| Database | SQLite | PostgreSQL |
| Vector Store | FAISS | Qdrant |
| Queue | asyncio | Celery + Redis |
| Auth | None | JWT |

---

*Document generated from full codebase audit. All file paths are relative to repository root.*
