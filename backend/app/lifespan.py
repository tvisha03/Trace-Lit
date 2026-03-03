from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from shared.logger import setup_logging, get_logger
from shared.utils.file_utils import ensure_directories
from infrastructure.db.database import init_db
from infrastructure.vector_store.faiss_store import FAISSStore
from infrastructure.llm.fallback_chain import FallbackChain
from workers.paper_worker import create_paper_queue, set_ws_manager, set_faiss_store
from workers.export_worker import shutdown_export_pool
from api.v1.routes.websocket import ws_manager
from infrastructure.db.crud.paper_crud import get_stuck_papers, update_paper_status
from infrastructure.db.database import async_session_factory
from shared.enums import PaperStatus
from app.config import get_settings

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging()
    logger.info("TraceLit backend starting …")

    # Validate API keys at startup
    settings = get_settings()
    missing_keys = settings.validate_keys()
    if missing_keys:
        logger.warning(
            f"Missing API keys: {missing_keys}. "
            "At least one LLM provider (Gemini or Groq) is required for chat functionality."
        )

    ensure_directories()
    await init_db()

    faiss_store = FAISSStore()
    faiss_store.load_or_create()
    app.state.faiss_store = faiss_store

    llm = FallbackChain()
    app.state.llm = llm

    paper_queue = create_paper_queue()
    set_ws_manager(ws_manager)
    # Share the single app-level FAISS instance with paper workers so
    # concurrent jobs don't create independent copies that overwrite each other.
    set_faiss_store(faiss_store)
    await paper_queue.start()
    app.state.paper_queue = paper_queue

    async with async_session_factory() as db:
        stuck = await get_stuck_papers(db)
        if stuck:
            logger.info(f"Re-queueing {len(stuck)} stuck paper(s) from previous run")
            for paper in stuck:
                await update_paper_status(
                    db, str(paper.id), PaperStatus.QUEUED, progress=0.0
                )
                await paper_queue.enqueue(str(paper.id), str(paper.session_id))
            await db.commit()

    logger.info("TraceLit backend ready ✓")

    yield

    logger.info("TraceLit backend shutting down …")
    await paper_queue.stop()
    shutdown_export_pool()
