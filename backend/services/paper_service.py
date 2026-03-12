import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from domain.extraction.pdf_processor import extract_pdf
from domain.extraction.section_parser import parse_sections
from domain.extraction.metadata_extractor import extract_metadata
from domain.extraction.figure_analyzer import analyze_figures
from domain.extraction.ocr_helper import ocr_author_region
from domain.retrieval.chunker import (
    create_chunks,
    create_figure_chunks,
    create_table_chunks,
    create_formula_chunks,
)
from domain.retrieval.indexer import index_chunks
from infrastructure.db.crud.paper_crud import (
    create_paper,
    update_paper_status,
    get_paper,
    get_papers_by_session,
)
from infrastructure.db.crud.chunk_crud import create_chunks_bulk
from infrastructure.vector_store.faiss_store import FAISSStore
from infrastructure.llm.fallback_chain import FallbackChain
from shared.enums import PaperStatus, ChunkType
from shared.logger import get_logger
from shared.utils.time_utils import timer
from shared.constants import VISION_TABLE_KEYWORDS, VISION_FORMULA_KEYWORDS

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
        # Run synchronous PDF extraction in a thread to avoid blocking the event loop
        extracted = await asyncio.to_thread(extract_pdf, paper.file_path)

    sections = parse_sections(extracted.markdown_text, pages=extracted.pages)
    metadata = extract_metadata(
        extracted.markdown_text,
        pdf_metadata=extracted.pdf_metadata,
        pages=extracted.pages,
    )

    if not metadata.authors:
        ocr_authors = ocr_author_region(paper.file_path, extracted.pages)
        if ocr_authors:
            metadata.authors = ocr_authors

    return extracted, sections, metadata

async def _analyze_paper_figures(extracted, llm_chain: FallbackChain | None):
    from app.config import get_settings as _get_settings
    settings = _get_settings()

    if not extracted.figures or llm_chain is None:
        return []

    if not settings.FIGURE_ANALYSIS_ENABLED:
        logger.info(
            f"Figure analysis disabled (FIGURE_ANALYSIS_ENABLED=false) — "
            f"skipping {len(extracted.figures)} figures"
        )
        return []

    timeout = settings.FIGURE_VISION_TIMEOUT_SECONDS
    try:
        analyzed = await asyncio.wait_for(
            analyze_figures(extracted.figures, llm_chain),
            timeout=float(timeout),
        )
        return analyzed
    except asyncio.TimeoutError:
        logger.warning(
            f"Figure analysis phase timed out after {timeout}s "
            f"({len(extracted.figures)} figures) — continuing without figures"
        )
        return []
    except Exception as exc:
        logger.warning(
            f"Figure analysis failed ({exc}) — continuing without figures"
        )
        return []

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
            "chunk_type": c.chunk_type.value if hasattr(c.chunk_type, "value") else str(c.chunk_type),
            "image_path": getattr(c, "image_path", None),
        }
        for c in chunks
    ]

    _MAX_RETRIES = 2
    for attempt in range(1, _MAX_RETRIES + 2):
        try:
            await create_chunks_bulk(db, chunk_records)
            await db.commit()
            return
        except Exception as exc:
            await db.rollback()
            if attempt > _MAX_RETRIES:
                raise
            logger.warning(
                f"Chunk creation attempt {attempt}/{_MAX_RETRIES + 1} "
                f"failed for {paper_id}: {exc} — retrying"
            )
            await asyncio.sleep(0.5 * attempt)

async def _cleanup_after_failure(paper_id: str, db: AsyncSession):
    # Only clean up partial DB chunks — the uploaded PDF is intentionally kept
    # on disk so that the user does not lose it and can retry processing without
    # having to re-upload.  The file is only removed when the user explicitly
    # deletes the paper via the DELETE /papers/{id} endpoint.
    from infrastructure.db.crud.chunk_crud import delete_chunks_by_paper
    try:
        await delete_chunks_by_paper(db, paper_id)
        await db.commit()
        logger.info(f"Cleaned up partial chunks for failed paper {paper_id}")
    except Exception as exc:
        await db.rollback()
        logger.warning(f"Could not clean up chunks for {paper_id}: {exc}")

def _classify_figure(fig) -> ChunkType:
    fig_type = (getattr(fig, "figure_type", "") or "").lower()
    if any(kw in fig_type for kw in VISION_TABLE_KEYWORDS):
        return ChunkType.TABLE
    if any(kw in fig_type for kw in VISION_FORMULA_KEYWORDS):
        return ChunkType.FORMULA
    return ChunkType.FIGURE

def _partition_analyzed_figures(analyzed_figures: list) -> tuple[list, list, list]:
    figures = []
    table_figs = []
    formula_figs = []
    for fig in analyzed_figures:
        kind = _classify_figure(fig)
        if kind == ChunkType.TABLE:
            table_figs.append(fig)
        elif kind == ChunkType.FORMULA:
            formula_figs.append(fig)
        else:
            figures.append(fig)
    return figures, table_figs, formula_figs

def _vision_figs_to_tables(table_figs: list) -> list:
    if not table_figs:
        return []
    from domain.extraction.table_extractor import ExtractedTable
    return [
        ExtractedTable(
            content=fig.description,
            page_number=fig.page_number,
            caption=getattr(fig, "figure_type", "table"),
        )
        for fig in table_figs
    ]

def _vision_figs_to_formulas(formula_figs: list) -> list:
    if not formula_figs:
        return []
    from domain.extraction.formula_extractor import ExtractedFormula
    return [
        ExtractedFormula(
            content=fig.description,
            page_number=fig.page_number,
            formula_type="vision",
        )
        for fig in formula_figs
    ]

def _assemble_typed_chunks(
    chunks: list,
    analyzed_figures: list | None,
    tables: list | None,
    formulas: list | None,
    paper_title: str | None,
    paper_id: str,
) -> list:
    if analyzed_figures:
        chunks.extend(create_figure_chunks(
            analyzed_figures, paper_title=paper_title,
            paper_id=paper_id, start_idx=len(chunks),
        ))

    if tables:
        chunks.extend(create_table_chunks(
            tables, paper_title=paper_title,
            paper_id=paper_id, start_idx=len(chunks),
        ))

    if formulas:
        chunks.extend(create_formula_chunks(
            formulas, paper_title=paper_title,
            paper_id=paper_id, start_idx=len(chunks),
        ))

    return chunks

async def _chunk_and_index_paper(
    db: AsyncSession,
    faiss_store: FAISSStore,
    paper_id: str,
    paper,
    extraction_results: dict,
) -> int:
    sections = extraction_results["sections"]
    metadata = extraction_results["metadata"]

    with timer(f"Chunk {paper.filename}"):
        chunks = create_chunks(
            sections, paper_title=metadata.title, paper_id=paper_id
        )

    chunks = _assemble_typed_chunks(
        chunks,
        extraction_results.get("analyzed_figures"),
        extraction_results.get("tables"),
        extraction_results.get("formulas"),
        paper_title=metadata.title,
        paper_id=paper_id,
    )

    await _persist_chunks_with_retry(db, chunks, paper_id)

    with timer(f"Index {paper.filename}"):
        await index_chunks(chunks, paper_id, faiss_store)

    return len(chunks)

async def _run_extraction_phase(
    paper_id: str,
    db: AsyncSession,
    paper,
    progress_callback,
    llm_chain,
):
    await _update_status_with_progress(
        db, paper_id, PaperStatus.EXTRACTING, 0.1, progress_callback
    )

    extracted, sections, metadata = await _extract_and_parse_paper(
        paper_id, db, paper
    )

    await _update_status_with_progress(
        db, paper_id, PaperStatus.EXTRACTING, 0.25,
        progress_callback, page_count=extracted.page_count,
    )

    await _update_status_with_progress(
        db, paper_id, PaperStatus.ANALYZING_FIGURES, 0.3,
        progress_callback,
        title=metadata.title, authors=metadata.authors,
        year=metadata.year, abstract=metadata.abstract,
        doi=metadata.doi,
    )

    analyzed_figures = await _analyze_paper_figures(extracted, llm_chain)
    return sections, metadata, analyzed_figures, extracted.tables, extracted.formulas

async def _run_chunking_phase(
    paper_id: str,
    db: AsyncSession,
    faiss_store: FAISSStore,
    paper,
    progress_callback,
    extraction_results: dict,
) -> int:
    await _update_status_with_progress(
        db, paper_id, PaperStatus.CHUNKING, 0.45, progress_callback,
    )

    await _update_status_with_progress(
        db, paper_id, PaperStatus.EMBEDDING, 0.6, progress_callback,
    )

    chunk_count = await _chunk_and_index_paper(
        db, faiss_store, paper_id, paper,
        extraction_results,
    )

    await _update_status_with_progress(
        db, paper_id, PaperStatus.COMPLETED, 1.0, progress_callback,
        chunk_count=chunk_count,
    )

    return chunk_count

async def _execute_paper_processing(
    paper_id: str,
    db: AsyncSession,
    faiss_store: FAISSStore,
    paper,
    progress_callback=None,
    llm_chain: FallbackChain | None = None,
) -> None:
    await _update_status_with_progress(
        db, paper_id, PaperStatus.QUEUED, 0.0, progress_callback
    )

    sections, metadata, analyzed_figures, tables, formulas = await _run_extraction_phase(
        paper_id, db, paper, progress_callback, llm_chain
    )

    extraction_results = {
        "sections": sections,
        "metadata": metadata,
        "analyzed_figures": analyzed_figures,
        "tables": tables,
        "formulas": formulas,
    }

    chunk_count = await _run_chunking_phase(
        paper_id, db, faiss_store, paper, progress_callback,
        extraction_results,
    )

    fig_count = len(analyzed_figures) if analyzed_figures else 0
    tbl_count = len(tables) if tables else 0
    eq_count = len(formulas) if formulas else 0
    logger.info(
        f"Paper {paper.filename} processed: {chunk_count} chunks indexed "
        f"({fig_count} figures, {tbl_count} tables, {eq_count} formulas)"
    )

async def process_paper(
    paper_id: str,
    db: AsyncSession,
    faiss_store: FAISSStore,
    progress_callback=None,
    llm_chain: FallbackChain | None = None,
) -> None:
    paper = await get_paper(db, paper_id)
    if not paper:
        logger.error(f"Paper {paper_id} not found")
        return

    try:
        await _execute_paper_processing(
            paper_id, db, faiss_store, paper, progress_callback,
            llm_chain=llm_chain,
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

async def _collect_paper_image_paths(paper_id: str, db: AsyncSession) -> list[str]:
    from infrastructure.db.crud.chunk_crud import get_chunks_by_paper
    chunks = await get_chunks_by_paper(db, paper_id)
    return [c.image_path for c in chunks if c.image_path]

def _remove_paper_from_faiss(
    paper_id: str,
    faiss_store: FAISSStore,
) -> None:
    try:
        faiss_store.remove_paper(paper_id)
        faiss_store.save()
    except Exception as exc:
        logger.warning(
            f"FAISS removal for paper {paper_id} failed after DB delete — "
            f"index will be reconciled on restart: {exc}"
        )

def _delete_paper_pdf(
    paper_id: str,
    pdf_path: "Path | None",
) -> None:
    if not pdf_path:
        return
    try:
        pdf_path.unlink(missing_ok=True)
        logger.info(f"Deleted uploaded PDF for paper {paper_id}: {pdf_path}")
    except Exception as exc:
        logger.warning(f"Could not delete PDF for paper {paper_id}: {exc}")

def _delete_paper_images(
    paper_id: str,
    image_paths: list[str],
) -> None:
    from pathlib import Path

    deleted_images = 0
    for img_str in image_paths:
        try:
            Path(img_str).unlink(missing_ok=True)
            deleted_images += 1
        except Exception as exc:
            logger.warning(f"Could not delete image {img_str}: {exc}")
    if deleted_images:
        logger.info(f"Deleted {deleted_images} figure image(s) for paper {paper_id}")

async def delete_paper(
    paper_id: str,
    db: AsyncSession,
    faiss_store: FAISSStore,
) -> bool:
    from pathlib import Path
    from infrastructure.db.crud.chunk_crud import delete_chunks_by_paper
    from infrastructure.db.crud.paper_crud import delete_paper as db_delete_paper

    paper = await get_paper(db, paper_id)
    if not paper:
        return False
    pdf_path = Path(paper.file_path) if paper.file_path else None
    image_paths = await _collect_paper_image_paths(paper_id, db)

    await delete_chunks_by_paper(db, paper_id)
    await db_delete_paper(db, paper_id)

    _remove_paper_from_faiss(paper_id, faiss_store)
    _delete_paper_pdf(paper_id, pdf_path)
    _delete_paper_images(paper_id, image_paths)

    return True

