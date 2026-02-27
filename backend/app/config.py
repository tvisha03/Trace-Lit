"""TraceLit — Application Configuration.

All configuration via environment variables + Pydantic BaseSettings.
Rule: Never hardcode API keys, thresholds, or paths. Always use settings.xyz.
"""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    # === LLM API Keys ===
    gemini_api_key: str = ""
    groq_api_key: str = ""

    # === Database ===
    database_url: str = "sqlite:///./data/tracelit.db"

    # === ML Models ===
    embedding_model: str = "all-MiniLM-L6-v2"
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # === HAVF Thresholds ===
    high_confidence_threshold: float = 0.85
    medium_confidence_threshold: float = 0.65

    # === Application Limits ===
    max_papers: int = 7
    max_upload_size_mb: int = 50
    max_concurrent_papers: int = 3
    llm_timeout: int = 30
    llm_temperature: float = 0.3
    max_conversation_turns: int = 5

    # === Logging ===
    log_level: str = "INFO"
    log_file: str = "./data/logs/tracelit.log"

    # === Paths ===
    upload_dir: str = "./data/uploads"
    export_dir: str = "./data/exports"

    # === ChromaDB ===
    chroma_persist_dir: str = "./data/chroma"
    chroma_collection_name: str = "tracelit_papers"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def ensure_directories(self) -> None:
        """Create all required data directories if they don't exist."""
        for dir_path in [
            self.upload_dir,
            self.export_dir,
            Path(self.log_file).parent,
            self.chroma_persist_dir,
        ]:
            Path(dir_path).mkdir(parents=True, exist_ok=True)


settings = Settings()
