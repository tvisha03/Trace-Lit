EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS: int = 384
EMBEDDING_BATCH_SIZE: int = 64

# Context budget — raised to 12k to utilize Groq/Gemini capacity and
# prevent truncation when multiple papers are uploaded.
MAX_CONTEXT_TOKENS: int = 12_000
MAX_QUERY_TOKENS: int = 512
MIN_PARAGRAPHS_PER_PAPER: int = 1
HISTORY_TOKEN_BUDGET: int = 2_500
SYSTEM_PROMPT_TOKEN_BUDGET: int = 500
RESPONSE_TOKEN_BUDGET: int = 1_500
MAX_CONVERSATION_TURNS: int = 5

CHUNK_TARGET_TOKENS: int = 400
CHUNK_MAX_TOKENS: int = 800

FAISS_TOP_K_PER_PAPER: int = 15
FAISS_MAX_VECTORS: int = 200_000

# Per-paper context budget for comparison — raised to fill Ollama Cloud's
# larger context window and produce richer cross-paper analysis.
COMPARISON_TOKEN_BUDGET_PER_PAPER: int = 3_000

MAX_WS_CONNECTIONS_PER_SESSION: int = 4

WS_PAPER_PROGRESS: str = "paper_progress"
WS_PAPER_COMPLETE: str = "paper_complete"
WS_PAPER_ERROR: str = "paper_error"
WS_PROCESSING_DONE: str = "processing_done"

FIGURE_IMAGE_FORMAT: str = "png"
FIGURE_IMAGE_DPI: int = 150
FIGURE_MIN_SIZE_RATIO: float = 0.03
FIGURE_MAX_CONCURRENT_ANALYSIS: int = 3
FIGURE_DESCRIPTION_MAX_TOKENS: int = 300
FIGURE_ANALYSIS_TIMEOUT: int = 60

TABLE_MIN_ROWS: int = 2
TABLE_MIN_COLS: int = 2
TABLE_MAX_TOKENS: int = 1024

FORMULA_MIN_LENGTH: int = 3
FORMULA_MAX_INLINE_LENGTH: int = 500

VISION_TABLE_KEYWORDS: tuple = ("table", "tabular", "spreadsheet", "grid")
VISION_FORMULA_KEYWORDS: tuple = (
    "equation",
    "formula",
    "mathematical",
    "math expression",
)
