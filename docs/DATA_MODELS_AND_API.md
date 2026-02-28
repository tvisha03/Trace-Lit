# TraceLit — Data Models & API Contract

> Database schemas, Pydantic models, and REST API endpoint definitions.  
> This is the contract between frontend and backend.

---

## 1. SQLAlchemy ORM Models

### Papers

```python
class Paper(Base):
    __tablename__ = "papers"
    id = Column(String, primary_key=True)          # UUID
    title = Column(String, nullable=False)
    authors = Column(Text)                          # JSON array: ["Author 1", "Author 2"]
    year = Column(Integer)
    pages = Column(Integer)
    file_path = Column(String)                      # Path to stored PDF
    upload_date = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="processing")   # processing | ready | failed
    keywords = Column(Text)                         # JSON array (Phase 2)
    summary = Column(Text)                          # On-demand summary (Phase 2)
```

### Sections & Paragraphs

```python
class Section(Base):
    __tablename__ = "sections"
    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(String, ForeignKey("papers.id"))
    title = Column(String)
    page_start = Column(Integer)
    order = Column(Integer)

class Paragraph(Base):
    __tablename__ = "paragraphs"
    id = Column(String, primary_key=True)           # P0, P1, P2, ...
    paper_id = Column(String, ForeignKey("papers.id"))
    section_id = Column(Integer, ForeignKey("sections.id"))
    text = Column(Text)
    page = Column(Integer)
    token_count = Column(Integer)
    embedding_id = Column(String)                   # FAISS doc ID (paper_id + paragraph_id)
    sentences = Column(Text)                        # JSON: [{sentence_id, text, start_char, end_char}]
```

### Sessions & Messages

```python
class Session(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True)           # UUID
    name = Column(String, default="Untitled Session")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    paper_ids = Column(Text)                        # JSON array of paper UUIDs

class Message(Base):
    __tablename__ = "messages"
    id = Column(String, primary_key=True)           # UUID
    session_id = Column(String, ForeignKey("sessions.id"))
    role = Column(String)                           # "user" | "assistant"
    content = Column(Text)                          # Raw text / markdown
    timestamp = Column(DateTime, default=datetime.utcnow)
    metadata = Column(Text)                         # JSON: {confidence, sources, provider, sentences[]}
```

### Contributions (Comparison Table)

```python
class Contribution(Base):
    __tablename__ = "contributions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(String, ForeignKey("papers.id"), unique=True)
    problem = Column(Text)
    problem_source = Column(String)                 # paragraph_id
    method = Column(Text)
    method_source = Column(String)
    dataset = Column(Text)
    dataset_source = Column(String)
    metrics = Column(Text)
    metrics_source = Column(String)
    results = Column(Text)
    results_source = Column(String)
```

---

## 2. Pydantic API Schemas

### Request Models

```python
class PaperUploadResponse(BaseModel):
    status: str = "processing"
    paper_ids: List[str]
    websocket_url: str = "/ws/papers/progress"

class ChatQueryRequest(BaseModel):
    query: str                                      # Max 2000 chars
    session_id: str
    active_paper_ids: Optional[List[str]] = None    # Filter by specific papers

class SessionCreateRequest(BaseModel):
    name: Optional[str] = "Untitled Session"
    paper_ids: List[str]
```

### Response Models

```python
class CitationSource(BaseModel):
    paragraph_id: str                               # "P5"
    sentence_id: str                                # "P5_S2"
    paper_id: str
    paper_title: str
    section: str
    page: int
    matched_text: str                               # The specific source sentence

class SentenceVerification(BaseModel):
    text: str                                       # Generated sentence text
    citations: List[str]                            # ["P5", "P12"]
    confidence: float                               # 0.0 - 1.0
    level: str                                      # "high" | "medium" | "low"
    method: str                                     # "embedding_similarity" | "cross_encoder_rerank" | "automatic_fallback"
    sources: List[CitationSource]

class ChatResponse(BaseModel):
    message_id: str
    query: str
    text: str                                       # Full response text
    sentences: List[SentenceVerification]
    overall_confidence: float
    provider: str                                   # "gemini" | "groq" | "ollama"
    warning: Optional[str] = None                   # Fallback attribution warning
    metadata: dict

class PaperSchema(BaseModel):
    id: str
    title: str
    authors: List[str]
    year: Optional[int]
    pages: Optional[int]
    status: str
    upload_date: str

class SessionSchema(BaseModel):
    id: str
    name: str
    created_at: str
    paper_ids: List[str]
```

---

## 3. REST API Endpoints

### Papers

| Method | Endpoint | Request | Response | Description |
|--------|----------|---------|----------|-------------|
| `POST` | `/api/papers/upload` | `multipart/form-data` (files[]) | `PaperUploadResponse` | Upload PDFs, returns 202 |
| `GET` | `/api/papers` | — | `List[PaperSchema]` | List all papers with status |
| `GET` | `/api/papers/{paper_id}` | — | `PaperSchema` | Get single paper details |
| `GET` | `/api/papers/{paper_id}/content` | — | Sections + paragraphs + sentences | Full paper content |
| `DELETE` | `/api/papers/{paper_id}` | — | `204 No Content` | Delete paper + vectors |

### Chat

| Method | Endpoint | Request | Response | Description |
|--------|----------|---------|----------|-------------|
| `POST` | `/api/chat/query` | `ChatQueryRequest` | SSE stream → `ChatResponse` | Send query, get streaming cited response |

### Sessions

| Method | Endpoint | Request | Response | Description |
|--------|----------|---------|----------|-------------|
| `GET` | `/api/sessions` | — | `List[SessionSchema]` | List all sessions |
| `POST` | `/api/sessions` | `SessionCreateRequest` | `SessionSchema` | Create new session |
| `GET` | `/api/sessions/{id}` | — | Session + messages | Get session with history |
| `PATCH` | `/api/sessions/{id}` | `{name: str}` | `SessionSchema` | Rename session |
| `DELETE` | `/api/sessions/{id}` | — | `204 No Content` | Delete session |

### Comparison

| Method | Endpoint | Request | Response | Description |
|--------|----------|---------|----------|-------------|
| `GET` | `/api/compare/{session_id}` | — | Contributions table | Get comparison data |
| `POST` | `/api/compare/{session_id}/generate` | — | Contributions table | Generate comparison via LLM |
| `PATCH` | `/api/compare/{session_id}` | Updated cells | Contributions table | Update edited cells |

### Export

| Method | Endpoint | Request | Response | Description |
|--------|----------|---------|----------|-------------|
| `POST` | `/api/export/pdf` | `{session_id}` | PDF file download | Export session to PDF |
| `POST` | `/api/export/excel` | `{session_id}` | Excel file download | Export comparison to Excel |

### WebSocket

| Endpoint | Direction | Message Format | Description |
|----------|-----------|---------------|-------------|
| `WS /ws/papers/progress` | Server → Client | `{"paper_id": "abc", "stage": "embedding", "progress": 65}` | Paper processing progress |
| | Server → Client | `{"type": "paper_ready", "paper_id": "abc", "message": "Paper ready!"}` | Paper available for queries |
| | Server → Client | `{"type": "error", "paper_id": "abc", "message": "Extraction failed"}` | Processing error |
