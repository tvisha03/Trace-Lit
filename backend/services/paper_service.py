import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from domain.extraction.pdf_processor import extract_pdf
from domain.extraction.section_parser import parse_sections
from domain.extraction.metadata_extractor import extract_metadata
from domain.retrieval.chunker import create_chunks
from domain.retrieval.indexer import index_chunks
from infrastructure.db.crud.paper_crud import (
    create_paper,
    update_paper_status,
    get_paper,
    get_papers_by_session,
)
from infrastructure.db.crud.chunk_crud import create_chunks_bulk
from infrastructure.vector_store.faiss_store import FAISSStore
from shared.enums import PaperStatus
from shared.logger import get_logger
from shared.utils.time_utils import timer

logger = get_logger(__name__)


async def register_paper(
    db: AsyncSession,
    session_id: str,
    filename: str,
    file_path: str,
    file_size_mb: float,
    content_hash: str | None = None,
) -> str:
    paper = await create_paper(
        db,
        session_id=session_id,
        filename=filename,
        file_path=file_path,
        file_size_mb=file_size_mb,
        content_hash=content_hash,
    )
    return str(paper.id)


async def _update_status_with_progress(
    db: AsyncSession,
    paper_id: str,
    status: PaperStatus,
    progress: float,
    progress_callback=None,
    **kwargs,
) -> None:
    await update_paper_status(db, paper_id, status, progress=progress, **kwargs)
    if progress_callback:
        await progress_callback(progress)


async def _extract_and_parse_paper(paper_id: str, db: AsyncSession, paper):
    with timer(f"Extract {paper.filename}"):
        extracted = extract_pdf(paper.file_path)

    sections = parse_sections(extracted.markdown_text)
    metadata = extract_metadata(extracted.markdown_text)

    return extracted, sections, metadata


async def _persist_chunks_with_retry(db: AsyncSession, chunks, paper_id: str):
    chunk_records = [
        {
            "id": str(uuid.uuid4()),
            "paper_id": paper_id,
            "paragraph_id": c.paragraph_id,
            "text": c.text,
            "enriched_text": c.enriched_text,
            "section_title": c.section_title,
            "page_number": c.page_number,
            "sentence_map": c.sentence_map,
            "token_count": c.token_count,
        }
        for c in chunks
    ]

    _MAX_RETRIES = 2
    for attempt in range(1, _MAX_RETRIES + 2):
        try:
            await create_chunks_bulk(db, chunk_records)
            await db.flush()
            return
        except Exception as exc:
            if attempt > _MAX_RETRIES:
                raise
            logger.warning(
                f"Chunk creation attempt {attempt}/{_MAX_RETRIES + 1} "
                f"failed for {paper_id}: {exc} — retrying"
            )
            import asyncio
            await asyncio.sleep(0.5 * attempt)


async def _cleanup_after_failure(paper_id: str, db: AsyncSession):
    try:
        paper = await get_paper(db, paper_id)
        if paper and paper.file_path:
            from pathlib import Path

            file_path = Path(paper.file_path)
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Cleaned up orphaned upload after failure: {file_path}")
    except Exception as exc:
        logger.warning(f"Could not clean up upload for {paper_id}: {exc}")


async def _chunk_and_index_paper(
    db: AsyncSession,
    faiss_store: FAISSStore,
    paper_id: str,
    paper,
    sections,
    metadata,
) -> int:
    with timer(f"Chunk {paper.filename}"):
        chunks = create_chunks(
            sections, paper_title=metadata.title, paper_id=paper_id
        )

    await _persist_chunks_with_retry(db, chunks, paper_id)

    with timer(f"Index {paper.filename}"):
        await index_chunks(chunks, paper_id, faiss_store)

    await db.commit()
    return len(chunks)


async def _execute_paper_processing(
    paper_id: str,
    db: AsyncSession,
    faiss_store: FAISSStore,
    paper,
    progress_callback=None,
) -> None:
    await _update_status_with_progress(
        db, paper_id, PaperStatus.QUEUED, 0.0, progress_callback
    )

    await _update_status_with_progress(
        db, paper_id, PaperStatus.EXTRACTING, 0.1, progress_callback
    )

    extracted, sections, metadata = await _extract_and_parse_paper(
        paper_id, db, paper
    )

    await _update_status_with_progress(
        db,
        paper_id,
        PaperStatus.EXTRACTING,
        0.3,
        progress_callback,
        page_count=extracted.page_count,
    )

    await _update_status_with_progress(
        db,
        paper_id,
        PaperStatus.CHUNKING,
        0.4,
        progress_callback,
        title=metadata.title,
        authors=metadata.authors,
        year=metadata.year,
        abstract=metadata.abstract,
    )

    await _update_status_with_progress(
        db,
        paper_id,
        PaperStatus.EMBEDDING,
        0.6,
        progress_callback,
    )

    chunk_count = await _chunk_and_index_paper(
        db, faiss_store, paper_id, paper, sections, metadata
    )

    await _update_status_with_progress(
        db, paper_id, PaperStatus.COMPLETED, 1.0, progress_callback
    )

    logger.info(f"Paper {paper.filename} processed: {chunk_count} chunks indexed")


async def process_paper(
    paper_id: str,
    db: AsyncSession,
    faiss_store: FAISSStore,
    progress_callback=None,
) -> None:
    paper = await get_paper(db, paper_id)
    if not paper:
        logger.error(f"Paper {paper_id} not found")
        return

    try:
        await _execute_paper_processing(
            paper_id, db, faiss_store, paper, progress_callback
        )
    except Exception as exc:
        logger.error(f"Paper processing failed for {paper_id}: {exc}")
        await _update_status_with_progress(
            db,
            paper_id,
            PaperStatus.FAILED,
            progress=-1.0,
            progress_callback=progress_callback,
            error_message=str(exc)[:500],
        )

        try:
            await db.commit()
        except Exception as commit_exc:
            logger.warning(f"Could not persist FAILED status for {paper_id}: {commit_exc}")

        await _cleanup_after_failure(paper_id, db)
        raise


async def get_session_papers(
    db: AsyncSession, session_id: str, status: PaperStatus | None = None
):
    return await get_papers_by_session(db, session_id, status=status)


async def mark_paper_failed(db: AsyncSession, paper_id: str, reason: str) -> None:
    await update_paper_status(
        db, paper_id, PaperStatus.FAILED, error_message=reason[:500]
    )


async def delete_paper(
    paper_id: str,
    db: AsyncSession,
    faiss_store: FAISSStore,
) -> bool:
    from infrastructure.db.crud.chunk_crud import delete_chunks_by_paper
    from infrastructure.db.crud.paper_crud import delete_paper as db_delete_paper

    await delete_chunks_by_paper(db, paper_id)
    deleted = await db_delete_paper(db, paper_id)
    if not deleted:
        return False

    try:
        faiss_store.remove_paper(paper_id)
        faiss_store.save()
    except Exception as exc:
        logger.warning(
            f"FAISS removal for paper {paper_id} failed after DB delete — "
            f"index will be reconciled on restart: {exc}"
        )

    return True

