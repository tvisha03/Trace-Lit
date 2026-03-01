"""TraceLit — Application-wide constants."""

# HTTP status code mapping for TraceLit error codes
STATUS_CODE_MAP: dict[str, int] = {
    "RATE_LIMIT": 429,
    "ALL_PROVIDERS_FAILED": 503,
    "INVALID_CITATION": 422,
    "EXTRACTION_FAILED": 500,
    "PAPER_NOT_READY": 409,
    "PAPER_LIMIT_EXCEEDED": 400,
    "FILE_TOO_LARGE": 413,
    "INVALID_FILE": 400,
}

# FAISS / embedding constants
EMBEDDING_DIM = 384          # all-MiniLM-L6-v2 output dimension
MAX_FAISS_BATCH_SIZE = 64    # vectors per encode call

# Chunking limits
MIN_PARAGRAPH_CHARS = 30
MAX_PARAGRAPH_TOKENS = 512

# Citation format
CITATION_PATTERN = r"\[P(\d+)\]"
