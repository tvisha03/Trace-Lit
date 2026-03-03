import asyncio
from dataclasses import dataclass
from typing import Callable, Awaitable

from shared.constants import MAX_PARALLEL_PAPERS, PAPER_PROCESSING_TIMEOUT_SECONDS
from shared.utils.memory_monitor import is_memory_pressure_high
from shared.logger import get_logger

logger = get_logger(__name__)

_MEMORY_BACKOFF_SECONDS: float = 1.0
_MAX_MEMORY_WAITS: int = 6

@dataclass(order=False)
class PaperJob:
    paper_id: str
    session_id: str
    priority: int = 0
    _seq: int = 0

    def __lt__(self, other: "PaperJob") -> bool:
        if not isinstance(other, PaperJob):
            return NotImplemented
        if self.priority != other.priority:
            return self.priority < other.priority
        return self._seq < other._seq

class SmartPaperQueue:

    def __init__(self):
        self._queue: asyncio.PriorityQueue[tuple[int, int, PaperJob]] = asyncio.PriorityQueue()
        self._semaphore = asyncio.Semaphore(MAX_PARALLEL_PAPERS)
        self._active_jobs: set[str] = set()
        self._process_fn: Callable[[PaperJob], Awaitable[None]] | None = None
        self._running = False
        self._seq_counter: int = 0

    def set_processor(self, fn: Callable[[PaperJob], Awaitable[None]]):
        self._process_fn = fn

    async def enqueue(self, paper_id: str, session_id: str, priority: int = 0):
        if paper_id in self._active_jobs:
            logger.warning(
                f"Paper {paper_id} is already being processed — skipping duplicate enqueue"
            )
            return

        self._seq_counter += 1
        job = PaperJob(
            paper_id=paper_id,
            session_id=session_id,
            priority=priority,
            _seq=self._seq_counter,
        )
        await self._queue.put((priority, self._seq_counter, job))
        logger.info(f"Enqueued paper {paper_id} (queue size: {self._queue.qsize()})")

    async def start(self):
        if self._running:
            return
        self._running = True
        logger.info("SmartPaperQueue started")
        asyncio.create_task(self._consumer_loop())

    async def stop(self):
        self._running = False
        logger.info("SmartPaperQueue stopping")

        if self._active_jobs:
            logger.info(
                f"Marking {len(self._active_jobs)} active paper(s) back to QUEUED for retry"
            )
            try:
                from infrastructure.db.database import async_session_factory
                from infrastructure.db.crud.paper_crud import update_paper_status
                from shared.enums import PaperStatus
                async with async_session_factory() as db:
                    for paper_id in list(self._active_jobs):
                        try:
                            await update_paper_status(
                                db, paper_id, PaperStatus.QUEUED, progress=0.0
                            )
                        except Exception as exc:
                            logger.warning(
                                f"Could not reset paper {paper_id} to QUEUED: {exc}"
                            )
                    await db.commit()
            except Exception as exc:
                logger.warning(f"Graceful queue shutdown DB update failed: {exc}")

    async def _consumer_loop(self):
        while self._running:
            try:
                _, _seq, job = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except Exception:
                continue
            asyncio.create_task(self._process_with_semaphore(job))

    async def _wait_for_memory(self) -> None:
        for attempt in range(1, _MAX_MEMORY_WAITS + 1):
            if not is_memory_pressure_high():
                return
            logger.warning(
                f"Memory pressure high — delaying paper job "
                f"(attempt {attempt}/{_MAX_MEMORY_WAITS}, "
                f"retrying in {_MEMORY_BACKOFF_SECONDS}s)"
            )
            await asyncio.sleep(_MEMORY_BACKOFF_SECONDS)

        logger.warning("Max memory-pressure waits exceeded — proceeding anyway")

    async def _process_with_semaphore(self, job: PaperJob):
        if not self._process_fn:
            logger.error("No processor function set on SmartPaperQueue")
            return

        if job.paper_id in self._active_jobs:
            logger.warning(
                f"Paper {job.paper_id} is already active — ignoring duplicate job"
            )
            return

        await self._wait_for_memory()

        async with self._semaphore:

            self._active_jobs.add(job.paper_id)
            try:
                logger.info(f"Processing paper {job.paper_id} (active: {len(self._active_jobs)})")
                await asyncio.wait_for(
                    self._process_fn(job),
                    timeout=PAPER_PROCESSING_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.error(
                    f"Paper {job.paper_id} timed out after "
                    f"{PAPER_PROCESSING_TIMEOUT_SECONDS}s — marking as failed"
                )
                try:
                    from infrastructure.db.database import async_session_factory
                    from services.paper_service import mark_paper_failed
                    async with async_session_factory() as db:
                        await mark_paper_failed(
                            db, job.paper_id,
                            reason=f"Processing timed out after {PAPER_PROCESSING_TIMEOUT_SECONDS}s",
                        )
                        await db.commit()
                except Exception as db_exc:
                    logger.warning(f"Could not persist timeout failure for {job.paper_id}: {db_exc}")
            except Exception as exc:
                logger.error(f"Paper queue job failed for {job.paper_id}: {exc}")
            finally:
                self._active_jobs.discard(job.paper_id)

    @property
    def active_count(self) -> int:
        return len(self._active_jobs)

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

