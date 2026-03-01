"""
Application lifespan — startup and shutdown hooks.
Initialises the database, ensures data directories, and warms critical models.
Wires up: FAISS store, LLM fallback chain, paper queue, WebSocket manager.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from shared.logger import setup_logging, get_logger
from shared.utils.file_utils import ensure_directories
from infrastructure.db.database import init_db
from infrastructure.vector_store.faiss_store import FAISSStore
from infrastructure.llm.fallback_chain import FallbackChain
from workers.paper_worker import create_paper_queue, set_ws_manager
from workers.export_worker import shutdown_export_pool
from api.v1.routes.websocket import ws_manager
from infrastructure.db.crud.paper_crud import get_stuck_papers, update_paper_status
from infrastructure.db.database import async_session_factory
from shared.enums import PaperStatus

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Runs once on startup and once on shutdown."""
    # ── Startup ────────────────────────────────────────────────────────────
    setup_logging()
    logger.info("TraceLit backend starting …")

    ensure_directories()
    await init_db()

    # Pre-load FAISS store (warm, avoids first-query penalty)
    faiss_store = FAISSStore()
    faiss_store.load_or_create()
    app.state.faiss_store = faiss_store

    # Initialise LLM fallback chain (Gemini → Groq → Ollama)
    llm = FallbackChain()
    app.state.llm = llm

    # Start paper processing queue (max 3 concurrent)
    paper_queue = create_paper_queue()
    set_ws_manager(ws_manager)
    await paper_queue.start()
    app.state.paper_queue = paper_queue

    # Re-queue any papers stuck in non-terminal states (e.g. from a crashed run)
    async with async_session_factory() as db:
        stuck = await get_stuck_papers(db)
        if stuck:
            logger.info(f"Re-queueing {len(stuck)} stuck paper(s) from previous run")
            for paper in stuck:
                await update_paper_status(db, str(paper.id), PaperStatus.QUEUED, progress=0.0)
                await paper_queue.enqueue(str(paper.id), str(paper.session_id))
            await db.commit()

    logger.info("TraceLit backend ready ✓")

    yield

    # ── Shutdown ───────────────────────────────────────────────────────────
    logger.info("TraceLit backend shutting down …")
    await paper_queue.stop()
    shutdown_export_pool()
