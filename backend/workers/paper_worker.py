from workers.paper_queue import PaperJob, SmartPaperQueue
from services.paper_service import process_paper
from infrastructure.db.database import async_session_factory
from infrastructure.vector_store.faiss_store import FAISSStore
from shared.logger import get_logger

logger = get_logger(__name__)

_ws_manager = None
_faiss_store: FAISSStore | None = None

def set_ws_manager(manager):
    global _ws_manager
    _ws_manager = manager

def set_faiss_store(faiss_store: FAISSStore) -> None:
    """Register the app-level FAISS store so all workers share one instance.

    Using a single shared FAISSStore prevents race conditions where concurrent
    workers each load a stale copy of the on-disk index, causing later writers
    to silently overwrite changes made by earlier workers.
    """
    global _faiss_store
    _faiss_store = faiss_store

async def paper_job_processor(job: PaperJob):
    if _faiss_store is None:
        raise RuntimeError(
            "FAISS store not initialised in paper worker; "
            "call set_faiss_store() during app startup."
        )

    async with async_session_factory() as db:
        async def progress_callback(progress: float):
            if _ws_manager:
                await _ws_manager.send_progress(
                    session_id=job.session_id,
                    paper_id=job.paper_id,
                    progress=progress,
                )

        try:
            await process_paper(
                paper_id=job.paper_id,
                db=db,
                faiss_store=_faiss_store,
                progress_callback=progress_callback,
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise

def create_paper_queue() -> SmartPaperQueue:
    queue = SmartPaperQueue()
    queue.set_processor(paper_job_processor)
    return queue
