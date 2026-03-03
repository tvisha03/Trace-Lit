import asyncio
from dataclasses import dataclass
from typing import Callable, Awaitable

from shared.constants import MAX_PARALLEL_PAPERS
from shared.utils.memory_monitor import is_memory_pressure_high
from shared.logger import get_logger

logger = get_logger(__name__)

_MEMORY_BACKOFF_SECONDS: float = 1.0
_MAX_MEMORY_WAITS: int = 6

@dataclass(order=False)
class PaperJob:
    """Represents a paper processing job in the priority queue.

    Uses a monotonic counter as tiebreaker so that PriorityQueue can compare
    tuples without requiring PaperJob to implement ``__lt__``.  This avoids
    TypeError when two jobs share the same priority.
    """
    paper_id: str
    session_id: str
    priority: int = 0
    _seq: int = 0  # monotonic tiebreaker — set by SmartPaperQueue.enqueue()

    def __lt__(self, other: "PaperJob") -> bool:
        """Compare by priority first, then by insertion order (FIFO)."""
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
        self._seq_counter: int = 0  # monotonic tiebreaker for equal priorities

    def set_processor(self, fn: Callable[[PaperJob], Awaitable[None]]):
        self._process_fn = fn

    async def enqueue(self, paper_id: str, session_id: str, priority: int = 0):
        # Guard against duplicate processing if the same paper is re-enqueued
        # (e.g. on retry after transient failure).  This is a best-effort check;
        # the FAISS add is idempotent, so a race here is safe.
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

        # Prevent duplicate concurrent processing of the same paper.
        if job.paper_id in self._active_jobs:
            logger.warning(
                f"Paper {job.paper_id} is already active — ignoring duplicate job"
            )
            return

        # MED-008: Check memory pressure BEFORE acquiring the semaphore so a
        # high-memory situation doesn't waste a concurrency slot while waiting
        # for RAM to free up.  This keeps the semaphore available for jobs
        # that are already in-flight and just need to finish.
        await self._wait_for_memory()

        async with self._semaphore:

            self._active_jobs.add(job.paper_id)
            try:
                logger.info(f"Processing paper {job.paper_id} (active: {len(self._active_jobs)})")
                await self._process_fn(job)
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
