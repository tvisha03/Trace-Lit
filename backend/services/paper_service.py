import uuid
from pathlib import Path

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
from infrastructure.db.models.chunk import Chunk as ChunkModel
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
) -> str:
    paper = await create_paper(
        db,
        session_id=session_id,
        filename=filename,
        file_path=file_path,
        file_size_mb=file_size_mb,
    )
    return str(paper.id)


async def process_paper(
    paper_id: str,
    db: AsyncSession,
    faiss_store: FAISSStore,
    progress_callback=None,
) -> None:
    try:
        paper = await get_paper(db, paper_id)
        if not paper:
            logger.error(f"Paper {paper_id} not found")
            return

        # MED-005: Transition REGISTERED -> QUEUED -> EXTRACTING explicitly.
        await update_paper_status(db, paper_id, PaperStatus.QUEUED, progress=0.0)

        await update_paper_status(db, paper_id, PaperStatus.EXTRACTING, progress=0.1)
        if progress_callback:
            await progress_callback(0.1)

        with timer(f"Extract {paper.filename}"):
            extracted = extract_pdf(paper.file_path)

        await update_paper_status(
            db,
            paper_id,
            PaperStatus.EXTRACTING,
            progress=0.3,
            page_count=extracted.page_count,
        )
        if progress_callback:
            await progress_callback(0.3)

        sections = parse_sections(extracted.markdown_text)
        metadata = extract_metadata(extracted.markdown_text)

        await update_paper_status(
            db,
            paper_id,
            PaperStatus.CHUNKING,
            progress=0.4,
            title=metadata.title,
            authors=metadata.authors,
            year=metadata.year,
            abstract=metadata.abstract,
        )
        if progress_callback:
            await progress_callback(0.4)

        with timer(f"Chunk {paper.filename}"):
            chunks = create_chunks(
                sections, paper_title=metadata.title, paper_id=paper_id
            )

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
        await create_chunks_bulk(db, chunk_records)
        await db.flush()  # Flush to get IDs

        await update_paper_status(
            db,
            paper_id,
            PaperStatus.EMBEDDING,
            progress=0.6,
            chunk_count=len(chunks),
        )
        if progress_callback:
            await progress_callback(0.6)

        with timer(f"Index {paper.filename}"):
            await index_chunks(chunks, paper_id, faiss_store)
            # index_chunks handles FAISS persistence internally (with rollback
            # on failure), so no additional save call is required here.

        # CRITICAL: Commit the transaction after successful chunk creation and indexing
        await db.commit()

        await update_paper_status(db, paper_id, PaperStatus.COMPLETED, progress=1.0)
        if progress_callback:
            await progress_callback(1.0)

        logger.info(f"Paper {paper.filename} processed: {len(chunks)} chunks indexed")

    except Exception as exc:
        logger.error(f"Paper processing failed for {paper_id}: {exc}")
        await update_paper_status(
            db,
            paper_id,
            PaperStatus.FAILED,
            error_message=str(exc)[:500],
        )
        if progress_callback:
            await progress_callback(-1.0)

        # Commit the FAILED status *before* attempting file cleanup so the
        # status change is durable regardless of cleanup outcome (MED-003 fix).
        # A failed commit is non-fatal here — the queue worker will retry.
        try:
            await db.commit()
        except Exception as commit_exc:
            logger.warning(f"Could not persist FAILED status for {paper_id}: {commit_exc}")

        # Clean up the uploaded file when processing fails mid-way so orphaned
        # files do not accumulate in the uploads directory.
        try:
            paper = await get_paper(db, paper_id)
            if paper and paper.file_path:
                from pathlib import Path as _Path

                _file = _Path(paper.file_path)
                if _file.exists():
                    _file.unlink()
                    logger.info(f"Cleaned up orphaned upload after failure: {_file}")
        except Exception as cleanup_exc:
            logger.warning(
                f"Could not clean up upload for paper {paper_id}: {cleanup_exc}"
            )


async def get_session_papers(
    db: AsyncSession, session_id: str, status: PaperStatus | None = None
):
    return await get_papers_by_session(db, session_id, status=status)


async def mark_paper_failed(db: AsyncSession, paper_id: str, reason: str) -> None:
    """Mark a paper FAILED immediately — called when queue enqueue fails so the
    paper does not sit indefinitely in REGISTERED state without ever processing."""
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

    # Perform DB deletions first so that if they fail the FAISS index is left
    # untouched.  The caller is responsible for committing the DB transaction.
    await delete_chunks_by_paper(db, paper_id)
    deleted = await db_delete_paper(db, paper_id)
    if not deleted:
        return False

    # Remove from the shared in-memory FAISS index after DB ops succeed.  A
    # failed FAISS removal is non-fatal: it will be reconciled on next startup
    # when the index is rebuilt from the committed DB state.
    try:
        faiss_store.remove_paper(paper_id)
        faiss_store.save()
    except Exception as exc:
        logger.warning(
            f"FAISS removal for paper {paper_id} failed after DB delete — "
            f"index will be reconciled on restart: {exc}"
        )

    return True
