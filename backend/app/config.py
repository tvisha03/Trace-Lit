from functools import lru_cache

from pydantic_settings import BaseSettings

class Settings(BaseSettings):

    APP_NAME: str = "TraceLit"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    DATABASE_URL: str = "sqlite+aiosqlite:///./data/tracelit.db"

    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    USE_LOCAL_LLM: bool = False
    OLLAMA_MODEL: str = "llama3.2:3b"
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    LLM_TIMEOUT: int = 30
    LLM_MAX_RETRIES: int = 2
    LLM_RETRY_DELAY_BASE: float = 2.0
    LLM_TEMPERATURE: float = 0.3

    UPLOADS_DIR: str = "data/uploads"
    EXPORTS_DIR: str = "data/exports"
    FAISS_INDEX_DIR: str = "data/faiss_indexes"

    MAX_PARALLEL_PAPERS: int = 3
    MAX_UPLOAD_FILES: int = 7
    MAX_FILE_SIZE_MB: int = 50

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }

@lru_cache()
def get_settings() -> Settings:
    return Settings()
