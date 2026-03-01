import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from domain.extraction.pdf_processor import extract_pdf
from domain.extraction.section_parser import parse_sections
from domain.extraction.metadata_extractor import extract_metadata
from domain.retrieval.chunker import create_chunks
from domain.retrieval.indexer import index_chunks
from infrastructure.db.crud.paper_crud import create_paper, update_paper_status, get_paper, get_papers_by_session
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
    """Create a paper record in QUEUED status. Returns the paper ID."""
    paper_id = str(uuid.uuid4())
    await create_paper(
        db,
        paper_id=paper_id,
        session_id=session_id,
        filename=filename,
        file_path=file_path,
        file_size_mb=file_size_mb,
    )
    return paper_id


async def process_paper(
    paper_id: str,
    db: AsyncSession,
    faiss_store: FAISSStore,
    progress_callback=None,
) -> None:
    """
    Full ingestion pipeline for a single paper.
    Updates DB status at each stage. Calls progress_callback(float) for WS updates.

    Stages: QUEUED → EXTRACTING → CHUNKING → EMBEDDING → COMPLETED (or FAILED).
    """
    try:
        paper = await get_paper(db, paper_id)
        if not paper:
            logger.error(f"Paper {paper_id} not found")
            return

        # --- Stage 1: Extract text ---
        await update_paper_status(db, paper_id, PaperStatus.EXTRACTING, progress=0.1)
        if progress_callback:
            await progress_callback(0.1)

        with timer(f"Extract {paper.filename}"):
            extracted = extract_pdf(paper.file_path)

        await update_paper_status(
            db, paper_id, PaperStatus.EXTRACTING,
            progress=0.3,
            page_count=extracted.page_count,
        )
        if progress_callback:
            await progress_callback(0.3)

        # --- Stage 2: Parse sections + extract metadata ---
        sections = parse_sections(extracted.markdown_text)
        metadata = extract_metadata(extracted.markdown_text)

        await update_paper_status(
            db, paper_id, PaperStatus.CHUNKING,
            progress=0.4,
            title=metadata.title,
            authors=metadata.authors,
            year=metadata.year,
            abstract=metadata.abstract,
        )
        if progress_callback:
            await progress_callback(0.4)

        # --- Stage 3: Chunk ---
        with timer(f"Chunk {paper.filename}"):
            chunks = create_chunks(sections, paper_title=metadata.title)

        # Persist chunks to DB
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

        await update_paper_status(
            db, paper_id, PaperStatus.EMBEDDING,
            progress=0.6,
            chunk_count=len(chunks),
        )
        if progress_callback:
            await progress_callback(0.6)

        # --- Stage 4: Embed + Index into FAISS ---
        with timer(f"Index {paper.filename}"):
            await index_chunks(chunks, paper_id, faiss_store)

        # --- Done ---
        await update_paper_status(db, paper_id, PaperStatus.COMPLETED, progress=1.0)
        if progress_callback:
            await progress_callback(1.0)

        logger.info(f"Paper {paper.filename} processed: {len(chunks)} chunks indexed")

    except Exception as exc:
        logger.error(f"Paper processing failed for {paper_id}: {exc}")
        await update_paper_status(
            db, paper_id, PaperStatus.FAILED,
            error_message=str(exc)[:500],
        )
        if progress_callback:
            await progress_callback(-1.0)  # Signal failure


async def get_session_papers(db: AsyncSession, session_id: str, status: PaperStatus | None = None):
    """List papers in a session, optionally filtered by status."""
    return await get_papers_by_session(db, session_id, status=status)


async def delete_paper(
    paper_id: str,
    db: AsyncSession,
    faiss_store: FAISSStore,
) -> bool:
    """Remove a paper's vectors, chunks, and DB record."""
    from infrastructure.db.crud.chunk_crud import delete_chunks_by_paper
    from infrastructure.db.crud.paper_crud import delete_paper as db_delete_paper

    faiss_store.remove_paper(paper_id)
    faiss_store.save()

    await delete_chunks_by_paper(db, paper_id)
    deleted = await db_delete_paper(db, paper_id)
    return bool(deleted)
