"""TraceLit — Application Lifespan (Startup / Shutdown).

Extracted from main.py so the lifespan logic can be independently tested.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from app.config import settings
from shared.logger import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # --- Startup ---
    configure_logging(log_level=settings.log_level, log_file=settings.log_file)
    logger.info("TraceLit backend starting up...")

    settings.ensure_directories()
    logger.info("Data directories verified")

    from infrastructure.db.database import init_db
    init_db()
    logger.info("Database initialised")

    logger.info("TraceLit backend ready")
    yield

    # --- Shutdown ---
    logger.info("TraceLit backend shutting down...")

    try:
        from infrastructure.llm.fallback_chain import get_llm
        await get_llm().shutdown()
    except Exception:
        pass
