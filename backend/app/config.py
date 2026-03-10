from functools import lru_cache
from urllib.parse import urlparse

import psutil
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

def _detect_max_parallel_papers() -> int:
    """Set parallelism based on available system RAM."""
    try:
        total_gb = psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        return 2
    if total_gb <= 8:
        return 1
    if total_gb <= 12:
        return 2
    return 3


def _detect_figure_concurrency() -> int:
    """Reduce figure analysis concurrency on low-RAM systems."""
    try:
        total_gb = psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        return 3
    if total_gb <= 8:
        return 2
    return 3

class Settings(BaseSettings):
    APP_NAME: str = "TraceLit"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    DATABASE_URL: str = "sqlite+aiosqlite:///./data/tracelit.db"
    SQLITE_BUSY_TIMEOUT_MS: int = 30_000

    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    USE_LOCAL_LLM: bool = True
    OLLAMA_MODEL: str = "qwen2.5:7b"
    OLLAMA_VISION_MODEL: str = "qwen2.5vl:3b"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_API_KEY: str = ""
    OLLAMA_CLOUD_MODEL: str = "qwen3.5:397b"
    OLLAMA_CLOUD_VISION_MODEL: str = "qwen3-vl:235b"
    OLLAMA_CLOUD_TIMEOUT: int = 120
    OLLAMA_CLOUD_MAX_TOKENS: int = 4096
    OLLAMA_CLOUD_NUM_CTX: int = 8192

    @field_validator("OLLAMA_BASE_URL")
    @classmethod
    def _validate_ollama_url(cls, v: str) -> str:  # noqa: N805
        import ipaddress
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"OLLAMA_BASE_URL must be an http:// or https:// URL, got: {v}"
            )
        if not parsed.hostname:
            raise ValueError(f"OLLAMA_BASE_URL must include a hostname, got: {v}")
        try:
            hostname = parsed.hostname
            if hostname.startswith('[') and hostname.endswith(']'):
                hostname = hostname[1:-1]
            ipaddress.ip_address(hostname)
        except ValueError:
            pass
        return v.rstrip("/")

    LLM_TIMEOUT: int = 60
    OLLAMA_TIMEOUT: int = 600
    OLLAMA_KEEP_ALIVE: str = "0s"
    OLLAMA_NUM_CTX: int = 4096
    OLLAMA_NUM_THREADS: int = 0
    OLLAMA_MAX_TOKENS: int = 2048
    COMPARISON_MAX_TOKENS: int = 4096
    LLM_MAX_RETRIES: int = 1
    LLM_RETRY_DELAY_BASE: float = 1.0
    LLM_RATE_LIMIT_COOLDOWN_SECONDS: int = 60
    LLM_TEMPERATURE: float = 0.3
    REQUEST_TIMEOUT: float = 300.0

    UPLOADS_DIR: str = "data/uploads"
    EXPORTS_DIR: str = "data/exports"
    FAISS_INDEX_DIR: str = "data/faiss_indexes"

    MAX_UPLOAD_FILES: int = 7
    MAX_FILE_SIZE_MB: int = 50
    MAX_PAPERS_PER_SESSION: int = 20
    MAX_SESSIONS: int = 50
    MAX_PARALLEL_PAPERS: int = Field(default_factory=_detect_max_parallel_papers)
    ADAPTIVE_FIGURE_CONCURRENCY: int = Field(default_factory=_detect_figure_concurrency)
    MAX_EXPORT_FILE_SIZE_MB: int = 100
    MIN_DISK_SPACE_MB: int = 500
    MEMORY_PRESSURE_THRESHOLD: float = 0.80
    PAPER_PROCESSING_TIMEOUT_SECONDS: int = 600
    COMPARISON_TIMEOUT_SECONDS: int = 600

    EMBEDDING_MODEL: str = "mixedbread-ai/mxbai-embed-large-v1"
    EMBEDDING_DIMENSIONS: int = 1024
    KEYBERT_MODEL: str = "all-mpnet-base-v2"

    HAVF_HIGH_THRESHOLD: float = 0.85
    HAVF_MEDIUM_THRESHOLD: float = 0.65
    HAVF_CROSS_ENCODER_THRESHOLD: float = 0.75
    HAVF_SHORT_SENTENCE_WORDS: int = 5
    CROSS_ENCODER_MODEL: str = "BAAI/bge-reranker-base"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }

    @property
    def MAX_FILE_SIZE_BYTES(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    def validate_keys(self) -> list[str]:
        if self.USE_LOCAL_LLM:
            return []
        missing = []
        if not self.GEMINI_API_KEY:
            missing.append("GEMINI_API_KEY")
        if not self.GROQ_API_KEY:
            missing.append("GROQ_API_KEY")
        return missing

    def has_llm_provider(self) -> bool:
        return (
            bool(self.GEMINI_API_KEY)
            or bool(self.GROQ_API_KEY)
            or bool(self.OLLAMA_API_KEY)
            or self.USE_LOCAL_LLM
        )

@lru_cache()
def get_settings() -> Settings:
    return Settings()

