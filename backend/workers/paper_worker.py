from workers.paper_queue import PaperJob, SmartPaperQueue
from services.paper_service import process_paper
from infrastructure.db.database import async_session_factory
from infrastructure.vector_store.faiss_store import FAISSStore
from shared.logger import get_logger

import time

logger = get_logger(__name__)

_ws_manager = None
_faiss_store: FAISSStore | None = None

def set_ws_manager(manager):
    global _ws_manager
    _ws_manager = manager

def set_faiss_store(faiss_store: FAISSStore) -> None:
    global _faiss_store
    _faiss_store = faiss_store

def _progress_to_stage(progress: float) -> str:
    if progress < 0:
        return "failed"
    if progress <= 0.3:
        return "extracting"
    if progress <= 0.4:
        return "chunking"
    if progress < 1.0:
        return "embedding"
    return "completed"

async def paper_job_processor(job: PaperJob):
    if _faiss_store is None:
        raise RuntimeError(
            "FAISS store not initialised in paper worker; "
            "call set_faiss_store() during app startup."
        )

    async with async_session_factory() as db:
        _start_time = time.monotonic()

        async def progress_callback(progress: float):
            if _ws_manager:
                stage = _progress_to_stage(progress)

                elapsed = time.monotonic() - _start_time
                if progress < 0:
                    eta_seconds = 0.0
                else:
                    clamped_progress = max(0.01, min(progress, 1.0))
                    if clamped_progress >= 1.0:
                        eta_seconds = 0.0
                    else:
                        eta_seconds = round(
                            elapsed * (1.0 - clamped_progress) / clamped_progress, 1
                        )

                await _ws_manager.send_event(
                    session_id=job.session_id,
                    event_type="paper_progress",
                    data={
                        "paper_id": job.paper_id,
                        "progress": progress,
                        "stage": stage,
                        "eta_seconds": eta_seconds,
                    },
                )

        try:
            await process_paper(
                paper_id=job.paper_id,
                db=db,
                faiss_store=_faiss_store,
                progress_callback=progress_callback,
            )
        except Exception:
            await db.rollback()
            raise

def create_paper_queue() -> SmartPaperQueue:
    queue = SmartPaperQueue()
    queue.set_processor(paper_job_processor)
    return queue

