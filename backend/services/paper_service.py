import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from domain.extraction.pdf_processor import extract_pdf
from domain.extraction.section_parser import parse_sections
from domain.extraction.metadata_extractor import extract_metadata
from domain.extraction.figure_analyzer import analyze_figures
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
        extracted = extract_pdf(paper.file_path)

    sections = parse_sections(extracted.markdown_text, pages=extracted.pages)
    metadata = extract_metadata(
        extracted.markdown_text,
        pdf_metadata=extracted.pdf_metadata,
        pages=extracted.pages,
    )

    return extracted, sections, metadata


async def _analyze_paper_figures(extracted, llm_chain: FallbackChain | None):
    if not extracted.figures or llm_chain is None:
        return []

    analyzed = await analyze_figures(extracted.figures, llm_chain)
    return analyzed


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
    pure_figures, table_figs, formula_figs = _partition_analyzed_figures(
        analyzed_figures or []
    )

    if pure_figures:
        chunks.extend(create_figure_chunks(
            pure_figures, paper_title=paper_title,
            paper_id=paper_id, start_idx=len(chunks),
        ))

    all_tables = (tables or []) + _vision_figs_to_tables(table_figs)
    if all_tables:
        chunks.extend(create_table_chunks(
            all_tables, paper_title=paper_title,
            paper_id=paper_id, start_idx=len(chunks),
        ))

    all_formulas = (formulas or []) + _vision_figs_to_formulas(formula_figs)
    if all_formulas:
        chunks.extend(create_formula_chunks(
            all_formulas, paper_title=paper_title,
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

    await db.commit()
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

