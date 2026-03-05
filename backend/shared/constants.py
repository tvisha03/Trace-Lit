# MINOR-001: Documented magic numbers with explanatory comments
# All numeric values now have clear purposes documented

# ============== File Upload Limits ==============
MAX_UPLOAD_FILES: int = 7  # Max papers per upload request
MAX_FILE_SIZE_MB: int = 50  # Max file size in MB
MAX_FILE_SIZE_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024  # Derived: 50MB in bytes
MAX_PAPERS_PER_SESSION: int = 20  # Max papers per user session
MAX_SESSIONS: int = 50  # Max concurrent sessions

# ============== Processing Limits ==============
MAX_PARALLEL_PAPERS: int = 3  # Concurrent paper processing limit
MEMORY_PRESSURE_THRESHOLD: float = 0.85  # 85% memory usage triggers pressure handling
PAPER_PROCESSING_TIMEOUT_SECONDS: int = 600  # 10 minute timeout per paper

# ============== Embedding Configuration ==============
EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"  # Sentence transformer model
EMBEDDING_DIMENSIONS: int = 384  # MiniLM-L6 output dimension
EMBEDDING_BATCH_SIZE: int = 64  # Batch size for embedding inference

# ============== HAVF (High-Accuracy Verification Framework) ==============
# Threshold values for claim verification confidence levels
HAVF_HIGH_THRESHOLD: float = 0.85  # ≥85% similarity = HIGH confidence
HAVF_MEDIUM_THRESHOLD: float = 0.65  # ≥65% similarity = MEDIUM confidence  
HAVF_CROSS_ENCODER_THRESHOLD: float = 0.75  # Reranker threshold
HAVF_SHORT_SENTENCE_WORDS: int = 5  # Sentences with <5 words are skipped

CROSS_ENCODER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# ============== Token Budgets ==============
# Budgets for LLM context window management
MAX_CONTEXT_TOKENS: int = 6_000  # Max tokens for retrieved context
MAX_QUERY_TOKENS: int = 512  # Max tokens for user query
MIN_PARAGRAPHS_PER_PAPER: int = 1  # Minimum paragraphs for processing
HISTORY_TOKEN_BUDGET: int = 2_000  # Conversation history budget
SYSTEM_PROMPT_TOKEN_BUDGET: int = 500  # System prompt budget
RESPONSE_TOKEN_BUDGET: int = 1_000  # Expected response size
MAX_CONVERSATION_TURNS: int = 5  # Max conversation history turns

# ============== Chunking Configuration ==============
CHUNK_TARGET_TOKENS: int = 512  # Target chunk size (~256 words)
CHUNK_MAX_TOKENS: int = 1024  # Hard limit for chunk size

# ============== FAISS Vector Store ==============
FAISS_TOP_K_PER_PAPER: int = 4  # Top chunks to retrieve per paper
FAISS_INDEX_DIR: str = "data/faiss_indexes"
FAISS_MAX_VECTORS: int = 500_000  # Max vectors before index rebuild

# ============== LLM Configuration ==============
LLM_TIMEOUT_SECONDS: int = 30  # Request timeout
LLM_MAX_RETRIES: int = 2  # Retry attempts on failure
LLM_RETRY_DELAY_BASE: float = 2.0  # Exponential backoff base (2^n seconds)
LLM_TEMPERATURE: float = 0.3  # Low temperature for factual responses

# ============== Directory Paths ==============
UPLOADS_DIR: str = "data/uploads"
EXPORTS_DIR: str = "data/exports"

# ============== System Limits ==============
MIN_DISK_SPACE_MB: int = 500  # Minimum free disk space required
MAX_EXPORT_FILE_SIZE_MB: int = 100  # Max export file size
MAX_WS_CONNECTIONS_PER_SESSION: int = 10  # WebSocket connection limit

# ============== Comparison ==============
COMPARISON_TOKEN_BUDGET_PER_PAPER: int = 5_000  # Token budget for paper comparison

# ============== WebSocket Event Types ==============
WS_PAPER_PROGRESS: str = "paper_progress"
WS_PAPER_COMPLETE: str = "paper_complete"
WS_PAPER_ERROR: str = "paper_error"
WS_PROCESSING_DONE: str = "processing_done"

# ============== Figure Analysis ==============
FIGURE_IMAGE_FORMAT: str = "png"
FIGURE_IMAGE_DPI: int = 200  # DPI for figure extraction
FIGURE_MIN_SIZE_RATIO: float = 0.03  # Min figure size relative to page (3%)
FIGURE_MAX_CONCURRENT_ANALYSIS: int = 5  # Parallel figure analysis limit
FIGURE_DESCRIPTION_MAX_TOKENS: int = 300  # Max tokens for figure descriptions
FIGURE_ANALYSIS_TIMEOUT: int = 90  # Timeout per figure in seconds

# ============== Table Detection ==============
TABLE_MIN_ROWS: int = 2  # Minimum rows for table detection
TABLE_MIN_COLS: int = 2  # Minimum columns for table detection
TABLE_MAX_TOKENS: int = 1024  # Max tokens per table chunk

# ============== Formula Detection ==============
FORMULA_MIN_LENGTH: int = 3  # Minimum characters for formula
FORMULA_MAX_INLINE_LENGTH: int = 500  # Max inline formula length

# ============== Vision Keywords ==============
# Keywords for classifying figures as tables or formulas
VISION_TABLE_KEYWORDS: tuple = ("table", "tabular", "spreadsheet", "grid")
VISION_FORMULA_KEYWORDS: tuple = ("equation", "formula", "mathematical", "math expression")
