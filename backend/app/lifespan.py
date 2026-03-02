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

    # Start background paper processing queue
    from api.v1.websocket.router import paper_progress_callback
    from workers.paper_worker import init_paper_queue
    await init_paper_queue(progress_callback=paper_progress_callback)
    logger.info("Paper processing queue started")

    # Start memory monitor
    from shared.memory_monitor import get_memory_monitor
    mem_monitor = get_memory_monitor()
    mem_monitor.start()
    status = mem_monitor.check_memory()
    logger.info(
        "Memory monitor started — system={}%, process={} GB, available={} GB",
        status["system_percent"], status["process_rss_gb"], status["available_gb"],
    )

    logger.info("TraceLit backend ready")
    yield

    # --- Shutdown ---
    logger.info("TraceLit backend shutting down...")

    # Stop memory monitor
    try:
        from shared.memory_monitor import get_memory_monitor
        get_memory_monitor().stop()
    except Exception:
        pass

    # Stop paper queue
    try:
        from workers.paper_worker import get_paper_queue
        await get_paper_queue().stop()
    except Exception:
        pass

    try:
        from infrastructure.llm.fallback_chain import get_llm
        await get_llm().shutdown()
    except Exception:
        pass
