# TraceLit — Performance Optimization Guide

> Target: All operations must feel responsive on an M3 MacBook Pro with 8GB RAM.  
> Budget: 6GB for app, 2GB reserved for macOS.

---

## 1. Memory Management

### 1.1 Hard Budget

| Component | Max Memory | Notes |
|-----------|-----------|-------|
| ChromaDB | 1.5 GB | Persistent storage, memory-mapped |
| Embedding model (all-MiniLM-L6-v2) | 256 MB | Load once, keep resident |
| Cross-encoder (ms-marco-MiniLM-L-6-v2) | 256 MB | Load on demand, unload after idle |
| SQLite | 100 MB | WAL mode, small footprint |
| FastAPI + app code | 500 MB | Includes async overhead |
| PDF processing buffer | 500 MB | Per-paper, released after extraction |
| Frontend (browser) | ~800 MB | React + ChromaDB results |
| **Total ceiling** | **~4 GB typical, 6 GB peak** | |

### 1.2 Memory Rules

```python
# RULE 1: Lazy-load ML models
class ModelManager:
    _embedding_model = None
    _cross_encoder = None

    @classmethod
    def get_embedding_model(cls):
        if cls._embedding_model is None:
            cls._embedding_model = SentenceTransformer(
                "all-MiniLM-L6-v2",
                device="mps"  # Apple Silicon GPU
            )
        return cls._embedding_model

    @classmethod
    def get_cross_encoder(cls):
        if cls._cross_encoder is None:
            cls._cross_encoder = CrossEncoder(
                "cross-encoder/ms-marco-MiniLM-L-6-v2"
            )
        return cls._cross_encoder

    @classmethod
    def unload_cross_encoder(cls):
        """Free cross-encoder memory when not in use"""
        if cls._cross_encoder is not None:
            del cls._cross_encoder
            cls._cross_encoder = None
            import gc; gc.collect()
```

```python
# RULE 2: Process papers one at a time
MAX_PARALLEL_PAPERS = 1  # Never process multiple PDFs simultaneously

# RULE 3: Release PDF buffers immediately after extraction
async def process_paper(pdf_path: str):
    raw_text = extract_pdf(pdf_path)
    chunks = chunk_text(raw_text)
    del raw_text  # Free immediately
    import gc; gc.collect()
    await embed_and_store(chunks)
```

```python
# RULE 4: Monitor memory usage
import psutil

def check_memory() -> dict:
    process = psutil.Process()
    mem = process.memory_info()
    return {
        "rss_mb": mem.rss / 1024 / 1024,
        "percent": process.memory_percent(),
        "available_mb": psutil.virtual_memory().available / 1024 / 1024
    }

async def memory_guard():
    """Call before expensive operations"""
    mem = check_memory()
    if mem["rss_mb"] > 5500:  # 5.5GB warning threshold
        logger.warning(f"Memory critical: {mem['rss_mb']:.0f}MB")
        import gc; gc.collect()
    if mem["rss_mb"] > 6000:  # 6GB hard limit
        raise MemoryError("Application memory limit exceeded")
```

---

## 2. MPS (Metal Performance Shaders) Acceleration

Apple Silicon GPU acceleration is critical for embedding performance.

### 2.1 Setup

```python
import torch

def get_device() -> str:
    """Get the best available device for ML inference."""
    if torch.backends.mps.is_available():
        return "mps"
    elif torch.cuda.is_available():
        return "cuda"
    return "cpu"

# Use in model initialization
device = get_device()
model = SentenceTransformer("all-MiniLM-L6-v2", device=device)
```

### 2.2 MPS-Safe Patterns

```python
# DO: Batch embeddings for MPS efficiency
embeddings = model.encode(
    texts,
    batch_size=32,         # Optimal for MPS
    show_progress_bar=False,
    normalize_embeddings=True,
    device=device
)

# DON'T: Encode one at a time
for text in texts:
    embedding = model.encode(text)  # Very slow on MPS

# DO: Move tensors to MPS explicitly when needed
tensor = tensor.to("mps")

# DON'T: Mix MPS and CPU tensors in operations
# result = mps_tensor + cpu_tensor  # This will crash
```

### 2.3 Expected MPS Performance

| Operation | CPU Time | MPS Time | Speedup |
|-----------|---------|----------|---------|
| Embed 100 chunks | 4.2s | 1.1s | ~4x |
| Embed 500 chunks | 21s | 4.8s | ~4.4x |
| Cross-encoder rerank (20 pairs) | 1.8s | 0.6s | ~3x |
| HAVF batch verify (10 claims) | 2.1s | 0.67s | ~3x |

---

## 3. Database Optimization

### 3.1 SQLite Performance

```python
# WAL mode for concurrent reads
engine = create_async_engine(
    "sqlite+aiosqlite:///./data/tracelit.db",
    connect_args={
        "check_same_thread": False,
    }
)

# Set WAL mode on connection
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
```

```sql
-- Essential indexes
CREATE INDEX idx_papers_status ON papers(processing_status);
CREATE INDEX idx_messages_session ON messages(session_id, created_at);
CREATE INDEX idx_sections_paper ON sections(paper_id);
CREATE INDEX idx_paragraphs_section ON paragraphs(section_id);
```

### 3.2 ChromaDB Performance

```python
# Optimal ChromaDB configuration
client = chromadb.PersistentClient(path="./data/chromadb")

collection = client.get_or_create_collection(
    name="paper_chunks",
    metadata={
        "hnsw:space": "cosine",
        "hnsw:M": 16,              # Default, good balance
        "hnsw:construction_ef": 100, # Higher = better indexing quality
        "hnsw:search_ef": 50,        # Higher = better search quality
    }
)
```

```python
# Batch operations are MUCH faster than single operations
# DO:
collection.add(
    ids=all_ids,
    embeddings=all_embeddings,
    documents=all_documents,
    metadatas=all_metadatas
)

# DON'T:
for i in range(len(chunks)):
    collection.add(
        ids=[chunk_ids[i]],
        embeddings=[embeddings[i]],
        documents=[documents[i]],
        metadatas=[metadatas[i]]
    )
```

---

## 4. API Response Optimization

### 4.1 Streaming for Chat

Always stream chat responses — never wait for the full response:

```python
@router.post("/api/chat")
async def chat(request: ChatRequest):
    return StreamingResponse(
        generate_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )
```

### 4.2 Response Size Limits

```python
# Limit retrieval results to prevent huge payloads
MAX_CHUNKS_PER_QUERY = 15       # Top-k retrieved chunks
MAX_CITATIONS_PER_RESPONSE = 50 # Trim if LLM produces more
MAX_HISTORY_TURNS = 5            # Don't send full history to LLM
```

---

## 5. Frontend Performance

### 5.1 React Optimization Rules

```jsx
// RULE 1: Memoize expensive components
const CitedSentence = React.memo(({ text, confidence, paperId, score }) => {
  // Only re-renders when props actually change
  return (/* ... */);
});

// RULE 2: Use useMemo for expensive computations
const parsedResponse = useMemo(
  () => parseCitations(response.text),
  [response.text]
);

// RULE 3: Virtualize long lists
import { useVirtualizer } from '@tanstack/react-virtual';
// Use for paper lists, search results, long chat histories

// RULE 4: Lazy-load routes and heavy components
const ComparisonView = lazy(() => import('./views/ComparisonView'));
const ConfidenceDashboard = lazy(() => import('./views/ConfidenceDashboard'));
```

### 5.2 TanStack Query Configuration

```javascript
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,   // 5 minutes
      cacheTime: 10 * 60 * 1000,  // 10 minutes
      refetchOnWindowFocus: false,
      retry: 2,
    },
  },
});

// Prefetch paper data on hover
const prefetchPaper = (paperId) => {
  queryClient.prefetchQuery({
    queryKey: ['paper', paperId],
    queryFn: () => fetchPaper(paperId),
    staleTime: 5 * 60 * 1000,
  });
};
```

### 5.3 Bundle Size Targets

| Bundle | Target | Technique |
|--------|--------|-----------|
| Initial JS | < 200 KB gzipped | Code splitting, tree shaking |
| Per-route chunk | < 50 KB gzipped | Lazy imports |
| CSS | < 20 KB gzipped | Tailwind purge |
| Total first load | < 300 KB | Aggressive splitting |

---

## 6. Caching Strategy

```python
# In-memory cache for frequently accessed data
from functools import lru_cache
from cachetools import TTLCache

# Paper metadata cache (rarely changes)
paper_cache = TTLCache(maxsize=100, ttl=300)  # 5 min TTL

# Embedding cache (same text = same embedding)
embedding_cache = TTLCache(maxsize=1000, ttl=3600)  # 1 hour TTL

async def get_embedding(text: str) -> list[float]:
    cache_key = hash(text)
    if cache_key in embedding_cache:
        return embedding_cache[cache_key]
    embedding = model.encode(text).tolist()
    embedding_cache[cache_key] = embedding
    return embedding
```

---

## 7. Performance Benchmarks (Targets)

| Metric | Target | Measured On |
|--------|--------|------------|
| Paper upload (10-page PDF) | < 30s total | M3 MacBook Pro |
| Chat response (first token) | < 2s | With Gemini Flash |
| Chat response (complete) | < 8s | With Gemini Flash |
| Embedding 100 chunks | < 2s | MPS accelerated |
| HAVF verification (10 claims) | < 1s | MPS accelerated |
| ChromaDB query (top-15) | < 200ms | Persistent client |
| Frontend initial load | < 1.5s | Local dev server |
| Memory usage (idle) | < 2 GB | After model loading |
| Memory usage (peak) | < 5 GB | During PDF processing |

---

## 8. Anti-Patterns to Avoid

| Anti-Pattern | Why It's Bad | Better Approach |
|-------------|-------------|-----------------|
| Loading all models at startup | Wastes 1GB+ RAM from the start | Lazy-load on first use |
| Embedding one chunk at a time | 10x slower than batching | Batch with `batch_size=32` |
| Storing embeddings in SQLite | Slow vector search | Use ChromaDB for vectors |
| Fetching all papers on page load | Slow initial render | Paginate, load on demand |
| No streaming for chat | User waits 5-8s for any response | SSE streaming from first token |
| Synchronous PDF processing | Blocks API during upload | Background task with progress |
| Keeping all chat history in memory | Memory grows unbounded | Limit to last 5 turns in prompts |
| Re-computing embeddings on every query | Wasteful computation | Cache embeddings by text hash |
