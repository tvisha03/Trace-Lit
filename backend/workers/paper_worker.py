"""TraceLit — Background Paper Processing Worker.

Manages an async queue for paper processing with concurrency control.
Papers are processed in the background after upload, with real-time
progress updates pushed via WebSocket.
"""

import asyncio
import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

from loguru import logger

from app.config import settings


# ============================================================
# Processing Stages
# ============================================================

class ProcessingStage(str, Enum):
    QUEUED = "queued"
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class PaperJob:
    """A single paper processing job."""

    paper_id: str
    file_path: str
    stage: ProcessingStage = ProcessingStage.QUEUED
    progress: float = 0.0  # 0.0 – 1.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================
# Smart Paper Queue
# ============================================================

class SmartPaperQueue:
    """Async queue with bounded concurrency for paper processing.

    Features:
        - Process up to `max_concurrent` papers in parallel
        - Remaining papers are queued and processed FIFO
        - Progress callbacks for WebSocket integration
        - Graceful cancellation of in-flight jobs
    """

    def __init__(
        self,
        max_concurrent: int = None,
        progress_callback: Optional[Callable[[str, ProcessingStage, float, Optional[str]], Coroutine]] = None,
    ):
        self._max_concurrent = max_concurrent or settings.max_concurrent_papers
        self._semaphore = asyncio.Semaphore(self._max_concurrent)
        self._queue: asyncio.Queue[PaperJob] = asyncio.Queue()
        self._active_jobs: Dict[str, PaperJob] = {}
        self._completed_jobs: Dict[str, PaperJob] = {}
        self._progress_callback = progress_callback
        self._running = False
        self._worker_tasks: List[asyncio.Task] = []

    @property
    def active_count(self) -> int:
        return len(self._active_jobs)

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    def get_job_status(self, paper_id: str) -> Optional[PaperJob]:
        """Get current status of a paper job."""
        if paper_id in self._active_jobs:
            return self._active_jobs[paper_id]
        return self._completed_jobs.get(paper_id)

    def get_all_statuses(self) -> Dict[str, Dict]:
        """Get status of all tracked jobs."""
        statuses = {}
        for pid, job in {**self._active_jobs, **self._completed_jobs}.items():
            statuses[pid] = {
                "paper_id": pid,
                "stage": job.stage.value,
                "progress": job.progress,
                "error": job.error,
            }
        return statuses

    async def submit(self, paper_id: str, file_path: str) -> None:
        """Add a paper to the processing queue."""
        job = PaperJob(paper_id=paper_id, file_path=file_path)
        self._active_jobs[paper_id] = job
        await self._notify(paper_id, ProcessingStage.QUEUED, 0.0)
        await self._queue.put(job)
        logger.info("Paper {} queued for processing (queue size: {})", paper_id, self._queue.qsize())

    async def start(self) -> None:
        """Start the worker loop."""
        if self._running:
            return
        self._running = True
        for i in range(self._max_concurrent):
            task = asyncio.create_task(self._worker_loop(i))
            self._worker_tasks.append(task)
        logger.info("SmartPaperQueue started with {} workers", self._max_concurrent)

    async def stop(self) -> None:
        """Gracefully stop all workers."""
        self._running = False
        for task in self._worker_tasks:
            task.cancel()
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks.clear()
        logger.info("SmartPaperQueue stopped")

    async def _worker_loop(self, worker_id: int) -> None:
        """Continuously process papers from queue."""
        while self._running:
            try:
                job = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            async with self._semaphore:
                try:
                    await self._process_paper(job)
                except Exception as exc:
                    logger.error("Worker {} failed on {}: {}", worker_id, job.paper_id, exc)
                    job.stage = ProcessingStage.FAILED
                    job.error = str(exc)[:500]
                    await self._notify(job.paper_id, ProcessingStage.FAILED, 0.0, str(exc)[:500])
                finally:
                    self._completed_jobs[job.paper_id] = job
                    self._active_jobs.pop(job.paper_id, None)
                    self._queue.task_done()

    async def _process_paper(self, job: PaperJob) -> None:
        """Execute the full paper processing pipeline with stage notifications."""
        from infrastructure.db.database import SessionLocal
        from domain.extraction.pdf_processor import extract_paper
        from domain.retrieval.chunker import SentenceAwareChunker
        from infrastructure.db.models.chunk import Paragraph
        from infrastructure.db.models.paper import Paper, Section
        from infrastructure.vector_store.faiss_store import get_vector_store
        from shared.errors import ExtractionError

        db = SessionLocal()
        chunker = SentenceAwareChunker()

        try:
            # Stage 1: Extraction
            job.stage = ProcessingStage.EXTRACTING
            await self._notify(job.paper_id, ProcessingStage.EXTRACTING, 0.1)

            result = await extract_paper(job.file_path, mode="auto")
            metadata = result["metadata"]
            sections_data = result["sections"]

            await self._notify(job.paper_id, ProcessingStage.EXTRACTING, 0.3)

            # Update paper metadata
            paper = db.query(Paper).filter(Paper.id == job.paper_id).first()
            if not paper:
                raise ExtractionError(message="Paper record not found", paper_id=job.paper_id)

            paper.title = metadata.get("title", paper.title)
            paper.authors = json.dumps(metadata.get("authors", []))
            paper.year = metadata.get("year")
            paper.pages = metadata.get("pages")

            # Store sections
            section_records = []
            for sect_data in sections_data:
                section = Section(
                    paper_id=job.paper_id,
                    title=sect_data["title"],
                    page_start=sect_data.get("page_start", 0),
                    order=sect_data.get("order", 0),
                )
                db.add(section)
                db.flush()
                section_records.append((section, sect_data))

            # Stage 2: Chunking
            job.stage = ProcessingStage.CHUNKING
            await self._notify(job.paper_id, ProcessingStage.CHUNKING, 0.4)

            paper_meta = {"paper_id": job.paper_id, "title": metadata.get("title", "Unknown")}
            chunks = chunker.chunk_paper(sections_data, paper_meta)

            section_id_map = {sect.title: sect.id for sect, _ in section_records}
            for chunk in chunks:
                section_id = section_id_map.get(chunk["section"])
                paragraph = Paragraph(
                    id=f"{job.paper_id}_{chunk['paragraph_id']}",
                    paper_id=job.paper_id,
                    section_id=section_id,
                    text=chunk["text"],
                    page=chunk.get("page", 0),
                    token_count=chunk.get("token_count", 0),
                    sentences=json.dumps(chunk["sentences"]),
                )
                db.add(paragraph)

            await self._notify(job.paper_id, ProcessingStage.CHUNKING, 0.6)

            # Stage 3: Embedding
            job.stage = ProcessingStage.EMBEDDING
            await self._notify(job.paper_id, ProcessingStage.EMBEDDING, 0.7)

            try:
                vector_store = get_vector_store()
                stored_count = vector_store.add_paragraphs(job.paper_id, chunks)
                logger.info("Embedded {} paragraphs for paper {} in FAISS", stored_count, job.paper_id)
            except Exception as exc:
                logger.error("FAISS embedding failed for paper {}: {}. DB fallback active.", job.paper_id, exc)

            await self._notify(job.paper_id, ProcessingStage.EMBEDDING, 0.9)

            # Stage 4: Complete
            job.stage = ProcessingStage.INDEXING
            await self._notify(job.paper_id, ProcessingStage.INDEXING, 0.95)

            paper.status = "ready"
            db.commit()

            job.stage = ProcessingStage.COMPLETE
            job.progress = 1.0
            await self._notify(job.paper_id, ProcessingStage.COMPLETE, 1.0)

            logger.info("Paper {} ready: {} sections, {} paragraphs", job.paper_id, len(sections_data), len(chunks))

        except Exception as exc:
            db.rollback()
            # Mark paper as failed in DB
            paper = db.query(Paper).filter(Paper.id == job.paper_id).first()
            if paper:
                paper.status = "failed"
                paper.error_message = str(exc)[:500]
                db.commit()
            raise
        finally:
            db.close()

    async def _notify(
        self,
        paper_id: str,
        stage: ProcessingStage,
        progress: float,
        error: Optional[str] = None,
    ) -> None:
        """Send progress notification via callback."""
        if self._progress_callback:
            try:
                await self._progress_callback(paper_id, stage, progress, error)
            except Exception as exc:
                logger.warning("Progress callback failed for {}: {}", paper_id, exc)


# ============================================================
# Singleton
# ============================================================

_queue: Optional[SmartPaperQueue] = None


def get_paper_queue() -> SmartPaperQueue:
    """Get or create the singleton paper processing queue."""
    global _queue
    if _queue is None:
        _queue = SmartPaperQueue()
    return _queue


async def init_paper_queue(
    progress_callback: Optional[Callable] = None,
) -> SmartPaperQueue:
    """Initialize and start the paper queue."""
    global _queue
    _queue = SmartPaperQueue(progress_callback=progress_callback)
    await _queue.start()
    return _queue
