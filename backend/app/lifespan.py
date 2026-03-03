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
from infrastructure.db.crud.chunk_crud import get_chunks_by_paper
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
    # MED-002: Refuse to start when absolutely no LLM provider is reachable.
    # This surfaces a clear startup error instead of a silent 500 on the first
    # chat request.  USE_LOCAL_LLM=true (Ollama) is accepted without any key.
    if not settings.has_llm_provider():
        raise RuntimeError(
            "No LLM provider is configured. "
            "Set GEMINI_API_KEY, GROQ_API_KEY, or USE_LOCAL_LLM=true in the .env file."
        )

    ensure_directories()
    await init_db()

    faiss_store = FAISSStore()
    faiss_store.load_or_create()

    # IMP-05: Reconcile FAISS id_map against DB chunks on startup.
    # If a previous run crashed mid-indexing the FAISS index may reference
    # papers/chunks that were never committed to the DB (or vice-versa).
    # We remove orphaned FAISS entries so retrieval doesn't return ghost IDs.
    await _reconcile_faiss_with_db(faiss_store)

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
    # Release lazily-loaded ML models from memory so the process exits cleanly
    # without holding GPU/CPU allocations open (MINOR-001 fix).
    from domain.analysis.keyword_extractor import unload_kw_model
    unload_kw_model()


async def _reconcile_faiss_with_db(faiss_store: FAISSStore) -> None:
    """Remove FAISS entries whose paper_id has no matching chunks in the DB.

    This handles the case where a previous run indexed vectors into FAISS but
    the corresponding DB rows were never committed (crash, rollback, etc.).
    Orphaned vectors would cause score_map KeyErrors in the retriever because
    the DB lookup returns nothing for the ghost paper_id.
    """
    if not faiss_store.is_ready() or faiss_store.total_vectors == 0:
        return

    orphaned = await _get_orphaned_paper_ids(faiss_store)
    if not orphaned:
        logger.info("FAISS reconciliation: all entries have matching DB chunks ✓")
        return

    for pid in orphaned:
        logger.warning(
            f"FAISS reconciliation: removing orphaned vectors for paper {pid}"
        )
        faiss_store.remove_paper(pid)
    faiss_store.save()
    logger.info(
        f"FAISS reconciliation complete — removed {len(orphaned)} orphaned paper(s), "
        f"{faiss_store.total_vectors} vectors remain."
    )


async def _get_orphaned_paper_ids(faiss_store: FAISSStore) -> list[str]:
    """Return paper IDs present in the FAISS id_map but absent from the DB."""
    faiss_paper_ids: set[str] = {
        cid.split("::", 1)[0] for cid in faiss_store._id_map
    }
    orphaned: list[str] = []
    async with async_session_factory() as db:
        for pid in faiss_paper_ids:
            chunks = await get_chunks_by_paper(db, pid)
            if not chunks:
                orphaned.append(pid)
    return orphaned
