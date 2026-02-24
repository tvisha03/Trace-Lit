# TraceLit — Architecture & Design Standards

> Structural patterns, module organization, and design decisions that MUST be followed.  
> This ensures consistency across the entire codebase.

---

## 1. Backend Architecture Pattern

### Layered Architecture

```
API Layer (FastAPI routers)
  ↓ receives HTTP/WS requests, validates with Pydantic, returns responses
Service Layer (business logic)
  ↓ orchestrates operations, no direct DB/API calls
Data Layer (models, repositories)
  ↓ SQLAlchemy ORM, ChromaDB client
Infrastructure Layer (external services)
  → LLM providers, file system, embedding models
```

### File Organization Rules

```
backend/app/
├── api/           # FastAPI routers ONLY — no business logic here
│   ├── papers.py  # Endpoints call service functions, never touch DB directly
│   ├── chat.py
│   └── ...
├── services/      # Business logic — the core of the application
│   ├── paper_service.py
│   ├── chat_service.py
│   ├── export_service.py
│   └── ...
├── llm/           # LLM provider clients and orchestration
├── verification/  # HAVF verifier
├── chunking/      # Sentence-aware chunker
├── embeddings/    # MPS-accelerated embedder
├── processing/    # Smart queue, background tasks
├── extraction/    # PDF extraction
├── models/        # SQLAlchemy ORM models and DB session
├── schemas/       # Pydantic request/response models
├── config.py      # Settings (Pydantic BaseSettings)
└── main.py        # FastAPI app instance, middleware, startup events
```

### Rule: API Routers Must Be Thin

```python
# ✅ CORRECT — router delegates to service
@router.post("/papers/upload")
async def upload_papers(files: List[UploadFile] = File(...)):
    result = await paper_service.process_uploads(files)
    return result

# ❌ WRONG — business logic in router
@router.post("/papers/upload")
async def upload_papers(files: List[UploadFile] = File(...)):
    for file in files:
        paper_id = str(uuid.uuid4())
        with open(f"./data/{paper_id}.pdf", "wb") as f:
            f.write(await file.read())
        # ... 50 more lines of extraction, chunking, embedding
```

---

## 2. Frontend Architecture Pattern

### Component Hierarchy

```
App
├── MainLayout
│   ├── Header              # Session name, paper count, save/export buttons
│   ├── Sidebar             # Paper list, keywords, settings
│   └── MainWorkspace
│       ├── TabBar           # Chat | Compare | Review | Gaps
│       └── TabContent
│           ├── ChatTab
│           │   ├── SourceViewer (40%)
│           │   └── ChatInterface (60%)
│           │       ├── MessageList
│           │       │   └── MessageBubble
│           │       │       └── CitedSentence
│           │       │           └── CitationTooltip
│           │       ├── ChatControls
│           │       └── ChatInput
│           ├── CompareTab
│           │   └── ComparisonTable
│           ├── ReviewTab (Phase 2)
│           └── GapsTab (Phase 2)
```

### Component Design Rules

1. **Single Responsibility**: Each component does ONE thing
2. **Props Down, Events Up**: Data flows down via props, actions flow up via callbacks
3. **No Direct API Calls in Components**: Use custom hooks (`useChat`, `usePapers`)
4. **Zustand for Global State**: Chat messages, active papers, selected source
5. **TanStack Query for Server State**: Paper list, session data, comparison table

### Custom Hooks Pattern

```javascript
// ✅ CORRECT — encapsulate API logic in hooks
export const useChat = (sessionId) => {
  const addMessage = useChatStore((s) => s.addMessage);

  const sendQuery = useMutation({
    mutationFn: (query) => api.post('/api/chat/query', { query, session_id: sessionId }),
    onSuccess: (data) => addMessage(data),
  });

  return { sendQuery: sendQuery.mutate, isLoading: sendQuery.isPending };
};

// Component just uses the hook
export const ChatInput = ({ sessionId }) => {
  const { sendQuery, isLoading } = useChat(sessionId);
  return <input onSubmit={(q) => sendQuery(q)} disabled={isLoading} />;
};
```

---

## 3. Data Flow Patterns

### Chat Query Flow

```
User types query
  → ChatInput calls sendQuery(query)
  → POST /api/chat/query (SSE stream)
  → Backend: embed query → retrieve from ChromaDB → assemble context
  → Backend: LLM generate with citation prompt (Gemini → Groq fallback)
  → Backend: HAVF verify each sentence (Level 1 → Level 2 if needed)
  → Backend: Stream response chunks via SSE
  → Frontend: Append chunks to message display
  → Frontend: On stream complete, render full message with CitedSentence components
  → Frontend: Update Zustand store
```

### Paper Processing Flow

```
User uploads PDFs
  → PaperUpload sends files to POST /api/papers/upload
  → Backend returns 202 + paper_ids + WebSocket URL
  → Frontend connects to WebSocket /ws/papers/progress
  → Backend (background): Extract → Chunk → Embed → Index (per paper)
  → WebSocket pushes progress: {paper_id, stage, progress %}
  → Frontend: Update progress bars in PaperList
  → WebSocket pushes: {type: "paper_ready", paper_id}
  → Frontend: Toast "Paper X ready!", add to queryable papers
```

---

## 4. Database Design Rules

### SQLite Best Practices

1. **Single writer**: SQLite handles one write at a time — use write queue if needed
2. **WAL mode**: Enable for better concurrent read performance
3. **JSON columns**: Store complex data (sentences[], authors[]) as JSON text
4. **Foreign keys**: Always define, enable with `PRAGMA foreign_keys = ON`
5. **Indexes**: Add indexes on frequently queried fields (`paper_id`, `session_id`)

```python
# Enable WAL mode and foreign keys on connection
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()
```

### ChromaDB Design Rules

1. **One collection per application** (`tracelit_papers`) — use metadata filtering for per-paper queries
2. **Store enriched text as document** — for search relevance
3. **Store original text in metadata** — for display
4. **Store sentence map as JSON in metadata** — for HAVF verification
5. **Use cosine similarity** (`hnsw:space: cosine`)

---

## 5. Async Patterns

### All I/O Must Be Async

```python
# ✅ CORRECT
async def extract_paper(pdf_path: str) -> Dict:
    async with aiofiles.open(pdf_path, 'rb') as f:
        content = await f.read()
    ...

# ❌ WRONG — blocking I/O in async context
async def extract_paper(pdf_path: str) -> Dict:
    with open(pdf_path, 'rb') as f:  # BLOCKS the event loop!
        content = f.read()
```

### Background Tasks

Use FastAPI's `BackgroundTasks` for fire-and-forget operations:

```python
@router.post("/papers/upload")
async def upload_papers(files: List[UploadFile], background_tasks: BackgroundTasks):
    paper_ids = await save_uploaded_files(files)
    background_tasks.add_task(process_papers_background, paper_ids)
    return {"status": "processing", "paper_ids": paper_ids}
```

### Parallel Processing

Use `asyncio.wait` with `FIRST_COMPLETED` for progressive paper availability:

```python
while active_tasks or remaining:
    done, pending = await asyncio.wait(
        active_tasks.values(),
        return_when=asyncio.FIRST_COMPLETED
    )
    for task in done:
        # Paper is ready — notify user, start next from queue
```

---

## 6. Security Standards

1. **No API keys in code** — always from environment variables
2. **Input validation** — Pydantic models on all API inputs
3. **File upload limits** — 50MB max, PDF only (check magic bytes)
4. **No shell injection** — never pass user input to `subprocess`
5. **CORS restricted** — allow only frontend origin in production
6. **Rate limiting** — consider `slowapi` for endpoint rate limits

---

## 7. Performance Patterns

### Lazy Loading

```python
class LazyModelLoader:
    """Load ML models only when first needed"""
    _embed_model = None
    _cross_encoder = None

    @classmethod
    def get_embed_model(cls):
        if cls._embed_model is None:
            cls._embed_model = SentenceTransformer('all-MiniLM-L6-v2').to('mps')
        return cls._embed_model
```

### Batch Operations

```python
# ✅ CORRECT — batch embedding
embeddings = model.encode(all_texts, batch_size=64, device='mps')

# ❌ WRONG — one at a time
for text in all_texts:
    embedding = model.encode(text)
```

### Caching

- Paper content: Cache in memory after first load (cleared on session switch)
- Embeddings: Stored in ChromaDB (persistent)
- LLM responses: Cached in session messages (SQLite)
- Comparison data: Cached in `contributions` table
