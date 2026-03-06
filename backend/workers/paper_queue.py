import asyncio
from dataclasses import dataclass
from typing import Callable, Awaitable

from app.config import get_settings
from shared.utils.memory_monitor import is_memory_pressure_high
from shared.logger import get_logger

logger = get_logger(__name__)
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
        self._semaphore = asyncio.Semaphore(1)
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

            await self._process_with_semaphore(job)
            self._queue.task_done()

    async def _wait_for_memory_infinite(self) -> None:
        attempt = 1
        while is_memory_pressure_high():
            logger.warning(
                f"Memory pressure high (>{get_settings().MEMORY_PRESSURE_THRESHOLD}%) — "
                f"Pausing queue to prevent crash (wait #{attempt}, retrying in 5s)..."
            )
            await asyncio.sleep(5.0)
            attempt += 1

    async def _process_with_semaphore(self, job: PaperJob):
        if not self._process_fn:
            logger.error("No processor function set on SmartPaperQueue")
            return

        if job.paper_id in self._active_jobs:
            logger.warning(
                f"Paper {job.paper_id} is already active — ignoring duplicate job"
            )
            return

        async with self._semaphore:
            await self._wait_for_memory_infinite()

            self._active_jobs.add(job.paper_id)
            try:
                logger.info(f"Processing paper {job.paper_id} (active: {len(self._active_jobs)})")
                await asyncio.wait_for(
                    self._process_fn(job),
                    timeout=get_settings().PAPER_PROCESSING_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                timeout_s = get_settings().PAPER_PROCESSING_TIMEOUT_SECONDS
                logger.error(
                    f"Paper {job.paper_id} timed out after "
                    f"{timeout_s}s — marking as failed"
                )
                try:
                    from infrastructure.db.database import async_session_factory
                    from services.paper_service import mark_paper_failed
                    async with async_session_factory() as db:
                        await mark_paper_failed(
                            db, job.paper_id,
                            reason=f"Processing timed out after {timeout_s}s",
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

