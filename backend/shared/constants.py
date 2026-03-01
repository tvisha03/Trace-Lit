# ── PDF upload limits ──────────────────────────────────────────────────────
MAX_UPLOAD_FILES: int = 7
MAX_FILE_SIZE_MB: int = 50
MAX_FILE_SIZE_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024

# ── Processing concurrency ─────────────────────────────────────────────────
MAX_PARALLEL_PAPERS: int = 3
MEMORY_PRESSURE_THRESHOLD: float = 0.75  # skip new paper if RAM > 75%

# ── Embedding model ────────────────────────────────────────────────────────
EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS: int = 384
EMBEDDING_BATCH_SIZE: int = 64

# ── HAVF thresholds ────────────────────────────────────────────────────────
HAVF_HIGH_THRESHOLD: float = 0.85
HAVF_MEDIUM_THRESHOLD: float = 0.65
HAVF_CROSS_ENCODER_THRESHOLD: float = 0.75
HAVF_SHORT_SENTENCE_WORDS: int = 5  # skip verification for < 5 words

# ── Cross-encoder model ───────────────────────────────────────────────────
CROSS_ENCODER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# ── Token budgets ──────────────────────────────────────────────────────────
MAX_CONTEXT_TOKENS: int = 6_000
MIN_PARAGRAPHS_PER_PAPER: int = 1
HISTORY_TOKEN_BUDGET: int = 2_000
SYSTEM_PROMPT_TOKEN_BUDGET: int = 500
RESPONSE_TOKEN_BUDGET: int = 1_000
MAX_CONVERSATION_TURNS: int = 5
TOKENS_PER_CHAR: float = 0.25  # rough 1 token ≈ 4 chars

# ── Chunking strategy ──────────────────────────────────────────────────────
CHUNK_TARGET_TOKENS: int = 512  # target size for each chunk during splitting
CHUNK_MAX_TOKENS: int = 1024    # hard limit before splitting at sentence boundaries

# ── FAISS ──────────────────────────────────────────────────────────────────
FAISS_TOP_K_PER_PAPER: int = 4
FAISS_INDEX_DIR: str = "data/faiss_indexes"

# ── LLM defaults ──────────────────────────────────────────────────────────
LLM_TIMEOUT_SECONDS: int = 30
LLM_MAX_RETRIES: int = 2
LLM_RETRY_DELAY_BASE: float = 2.0
LLM_TEMPERATURE: float = 0.3

# ── Export / storage paths ────────────────────────────────────────────────
UPLOADS_DIR: str = "data/uploads"
EXPORTS_DIR: str = "data/exports"

# ── WebSocket event types ─────────────────────────────────────────────────
WS_PAPER_PROGRESS: str = "paper_progress"
WS_PAPER_COMPLETE: str = "paper_complete"
WS_PAPER_ERROR: str = "paper_error"
WS_PROCESSING_DONE: str = "processing_done"
