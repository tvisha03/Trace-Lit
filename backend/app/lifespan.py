from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from shared.logger import setup_logging, get_logger
from shared.utils.file_utils import ensure_directories
from infrastructure.db.database import init_db
from infrastructure.vector_store.faiss_store import FAISSStore
from infrastructure.llm.fallback_chain import FallbackChain
from workers.paper_worker import create_paper_queue, set_ws_manager, set_faiss_store, set_llm_chain
from workers.export_worker import shutdown_export_pool
from api.v1.routes.websocket import ws_manager
from infrastructure.db.crud.paper_crud import get_stuck_papers, update_paper_status
from infrastructure.db.database import async_session_factory
from shared.enums import PaperStatus
from app.config import get_settings

logger = get_logger(__name__)


def _validate_llm_providers() -> None:
    settings = get_settings()
    missing_keys = settings.validate_keys()
    if missing_keys:
        logger.warning(
            f"Missing API keys: {missing_keys}. "
            "At least one LLM provider (Gemini or Groq) is required for chat functionality."
        )
    if not settings.has_llm_provider():
        raise RuntimeError(
            "No LLM provider is configured. "
            "Set GEMINI_API_KEY, GROQ_API_KEY, or USE_LOCAL_LLM=true in the .env file."
        )


async def _requeue_stuck_papers(paper_queue) -> None:
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


async def _shutdown_services(paper_queue, faiss_store: FAISSStore) -> None:
    logger.info("TraceLit backend shutting down …")
    await paper_queue.stop()
    shutdown_export_pool()
    try:
        faiss_store.save()
        logger.info("FAISS index saved on shutdown")
    except Exception as exc:
        logger.warning(f"Could not save FAISS on shutdown: {exc}")
    from domain.analysis.keyword_extractor import unload_kw_model
    unload_kw_model()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging()
    logger.info("TraceLit backend starting …")

    _validate_llm_providers()
    ensure_directories()
    await init_db()

    faiss_store = FAISSStore()
    faiss_store.load_or_create()
    await _reconcile_faiss_with_db(faiss_store)
    _cleanup_stale_exports()

    app.state.faiss_store = faiss_store
    app.state.llm = FallbackChain()

    paper_queue = create_paper_queue()
    set_ws_manager(ws_manager)
    set_faiss_store(faiss_store)
    set_llm_chain(app.state.llm)
    await paper_queue.start()
    app.state.paper_queue = paper_queue

    await _requeue_stuck_papers(paper_queue)
    logger.info("TraceLit backend ready ✓")

    yield

    await _shutdown_services(paper_queue, faiss_store)


async def _reconcile_faiss_with_db(faiss_store: FAISSStore) -> None:
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
    faiss_paper_ids: set[str] = {
        cid.split("::", 1)[0] for cid in faiss_store._id_map
    }
    if not faiss_paper_ids:
        return []
    
    # FIXED MED-007: Use batch query instead of N+1 queries
    async with async_session_factory() as db:
        from infrastructure.db.crud.chunk_crud import get_chunks_by_papers
        chunks_by_paper = await get_chunks_by_papers(db, list(faiss_paper_ids))
        
        orphaned: list[str] = []
        for pid in faiss_paper_ids:
            if not chunks_by_paper.get(pid):
                orphaned.append(pid)
    
    return orphaned


def _cleanup_stale_exports() -> None:
    import time
    from pathlib import Path
    from shared.constants import EXPORTS_DIR

    exports_path = Path(EXPORTS_DIR)
    if not exports_path.exists():
        return

    cutoff = time.time() - 3600
    removed = _remove_stale_files(exports_path, cutoff)
    _cleanup_empty_directories(exports_path)

    if removed:
        logger.info(f"Cleaned up {removed} stale export file(s) from previous run")


def _remove_stale_files(exports_path, cutoff: float) -> int:
    removed = 0
    for session_dir in exports_path.iterdir():
        if not session_dir.is_dir():
            continue
        for export_file in session_dir.iterdir():
            if _is_stale_file(export_file, cutoff):
                try:
                    export_file.unlink()
                    removed += 1
                except Exception:
                    pass
    return removed


def _is_stale_file(file_path, cutoff: float) -> bool:
    try:
        return file_path.stat().st_mtime < cutoff
    except Exception:
        return False


def _cleanup_empty_directories(exports_path) -> None:
    for session_dir in exports_path.iterdir():
        if not session_dir.is_dir():
            continue
        try:
            if not any(session_dir.iterdir()):
                session_dir.rmdir()
        except Exception:
            pass

