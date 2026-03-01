"""TraceLit — Paper Service (Business Logic).

Thin-router pattern: all business logic lives here, not in the API router.
Pipeline: upload → validate → save file → extract → chunk → embed → DB + FAISS.

Uses the new layered infrastructure imports.
"""

import json
import os
from pathlib import Path
from typing import List

from fastapi import UploadFile
from loguru import logger
from sqlalchemy.orm import Session as DBSession

from api.v1.schemas import (
    PaperContentResponse,
    PaperSchema,
    PaperUploadResponse,
    ParagraphSchema,
    SectionSchema,
    SentenceSchema,
)
from app.config import settings
from domain.extraction.pdf_processor import extract_paper
from domain.retrieval.chunker import SentenceAwareChunker
from infrastructure.db.models.chunk import Paragraph
from infrastructure.db.models.paper import Paper, Section
from infrastructure.vector_store.faiss_store import get_vector_store
from shared.errors import (
    ExtractionError,
    FileTooLargeError,
    InvalidFileError,
    PaperLimitError,
)
from shared.utils.file_utils import generate_id, safe_filename, validate_pdf_magic_bytes

# Shared chunker instance
_chunker = SentenceAwareChunker()


# ============================================================
# Upload + Processing
# ============================================================

async def process_uploads(
    files: List[UploadFile],
    db: DBSession,
) -> PaperUploadResponse:
    """Validate, save, and process uploaded PDFs.

    Args:
        files: List of uploaded PDF files (each ≤ MAX_UPLOAD_SIZE_MB).
        db: Database session.

    Returns:
        PaperUploadResponse with all paper IDs and status.
    """
    existing_count = db.query(Paper).count()
    if existing_count + len(files) > settings.max_papers:
        raise PaperLimitError(limit=settings.max_papers)

    paper_ids: List[str] = []

    for upload_file in files:
        paper_id = generate_id()

        # -- Validate PDF magic bytes --
        header = await upload_file.read(8)
        await upload_file.seek(0)
        if not validate_pdf_magic_bytes(header):
            raise InvalidFileError(
                filename=upload_file.filename or "unknown",
                reason="File is not a valid PDF",
            )

        content = await upload_file.read()
        size_mb = len(content) / (1024 * 1024)

        if size_mb > settings.max_upload_size_mb:
            raise FileTooLargeError(
                filename=upload_file.filename or "unknown",
                size_mb=size_mb,
                limit_mb=settings.max_upload_size_mb,
            )

        # -- Save to disk --
        filename = safe_filename(upload_file.filename or f"{paper_id}.pdf")
        file_path = os.path.join(settings.upload_dir, f"{paper_id}_{filename}")
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "wb") as fh:
            fh.write(content)

        logger.info("Saved PDF: {} ({:.1f} MB) → {}", filename, size_mb, file_path)

        # -- Create paper DB record (status=processing) --
        paper = Paper(
            id=paper_id,
            title=filename.replace(".pdf", "").replace("_", " "),
            file_path=file_path,
            status="processing",
        )
        db.add(paper)
        db.flush()

        paper_ids.append(paper_id)

        # Phase 1: synchronous processing (async queue in Phase 2)
        try:
            await _process_single_paper(paper_id, file_path, db)
        except Exception as exc:
            logger.error("Processing failed for {}: {}", paper_id, exc)
            paper.status = "failed"
            paper.error_message = str(exc)[:500]

    db.commit()

    return PaperUploadResponse(
        status="processing",
        paper_ids=paper_ids,
        websocket_url="/ws/papers/progress",
    )


async def _process_single_paper(
    paper_id: str,
    file_path: str,
    db: DBSession,
) -> None:
    """Extract, chunk, embed, and store a single paper.

    Updates the paper record with metadata and sets status to 'ready'.
    """
    logger.info("Processing paper: {}", paper_id)

    # 1. Extract PDF
    result = await extract_paper(file_path, mode="auto")
    metadata = result["metadata"]
    sections_data = result["sections"]

    # 2. Update paper metadata
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise ExtractionError(message="Paper record not found", paper_id=paper_id)

    paper.title = metadata.get("title", paper.title)
    paper.authors = json.dumps(metadata.get("authors", []))
    paper.year = metadata.get("year")
    paper.pages = metadata.get("pages")

    # 3. Store sections
    section_records = []
    for sect_data in sections_data:
        section = Section(
            paper_id=paper_id,
            title=sect_data["title"],
            page_start=sect_data.get("page_start", 0),
            order=sect_data.get("order", 0),
        )
        db.add(section)
        db.flush()
        section_records.append((section, sect_data))

    # 4. Chunk with sentence tracking
    paper_meta = {"paper_id": paper_id, "title": metadata.get("title", "Unknown")}
    chunks = _chunker.chunk_paper(sections_data, paper_meta)

    # 5. Store paragraphs
    section_id_map = {sect.title: sect.id for sect, _ in section_records}
    for chunk in chunks:
        section_id = section_id_map.get(chunk["section"])
        paragraph = Paragraph(
            id=f"{paper_id}_{chunk['paragraph_id']}",
            paper_id=paper_id,
            section_id=section_id,
            text=chunk["text"],
            page=chunk.get("page", 0),
            token_count=chunk.get("token_count", 0),
            sentences=json.dumps(chunk["sentences"]),
        )
        db.add(paragraph)

    # 6. Embed and index in FAISS
    try:
        vector_store = get_vector_store()
        stored_count = vector_store.add_paragraphs(paper_id, chunks)
        logger.info("Embedded {} paragraphs for paper {} in FAISS", stored_count, paper_id)
    except Exception as exc:
        logger.error(
            "FAISS embedding failed for paper {}: {}. DB fallback active.",
            paper_id,
            exc,
        )

    paper.status = "ready"
    db.flush()

    logger.info(
        "Paper {} ready: {} sections, {} paragraphs",
        paper_id,
        len(sections_data),
        len(chunks),
    )


# ============================================================
# Query Operations
# ============================================================

async def get_all_papers(db: DBSession) -> List[PaperSchema]:
    """List all papers with processing status, newest first."""
    papers = db.query(Paper).order_by(Paper.upload_date.desc()).all()
    return [
        PaperSchema(
            id=p.id,
            title=p.title,
            authors=json.loads(p.authors) if p.authors else [],
            year=p.year,
            pages=p.pages,
            status=p.status,
            upload_date=p.upload_date.isoformat() if p.upload_date else "",
            error_message=p.error_message,
        )
        for p in papers
    ]


async def get_paper_by_id(paper_id: str, db: DBSession) -> PaperSchema:
    """Get details for a single paper."""
    from fastapi import HTTPException

    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id} not found")

    return PaperSchema(
        id=paper.id,
        title=paper.title,
        authors=json.loads(paper.authors) if paper.authors else [],
        year=paper.year,
        pages=paper.pages,
        status=paper.status,
        upload_date=paper.upload_date.isoformat() if paper.upload_date else "",
        error_message=paper.error_message,
    )


async def get_paper_content(paper_id: str, db: DBSession) -> PaperContentResponse:
    """Get full paper content — sections, paragraphs, and sentences."""
    from fastapi import HTTPException

    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id} not found")

    sections = (
        db.query(Section)
        .filter(Section.paper_id == paper_id)
        .order_by(Section.order)
        .all()
    )

    paragraphs = (
        db.query(Paragraph)
        .filter(Paragraph.paper_id == paper_id)
        .all()
    )

    section_schemas = [
        SectionSchema(id=s.id, title=s.title, page_start=s.page_start, order=s.order)
        for s in sections
    ]

    paragraph_schemas = []
    total_sentences = 0
    for p in paragraphs:
        sentences_data = json.loads(p.sentences) if p.sentences else []
        total_sentences += len(sentences_data)

        paragraph_schemas.append(
            ParagraphSchema(
                paragraph_id=p.id,
                text=p.text,
                section=next(
                    (s.title for s in sections if s.id == p.section_id),
                    "Unknown",
                ),
                page=p.page or 0,
                sentences=[
                    SentenceSchema(
                        sentence_id=s["sentence_id"],
                        text=s["text"],
                        start_char=s["start_char"],
                        end_char=s["end_char"],
                        tokens=s.get("tokens", 0),
                    )
                    for s in sentences_data
                ],
            )
        )

    return PaperContentResponse(
        paper_id=paper_id,
        title=paper.title,
        sections=section_schemas,
        paragraphs=paragraph_schemas,
        total_paragraphs=len(paragraph_schemas),
        total_sentences=total_sentences,
    )


async def delete_paper(paper_id: str, db: DBSession) -> None:
    """Delete a paper, its sections/paragraphs, file, and FAISS vectors."""
    from fastapi import HTTPException

    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id} not found")

    # Remove file from disk
    if paper.file_path and os.path.exists(paper.file_path):
        try:
            os.remove(paper.file_path)
            logger.info("Deleted file: {}", paper.file_path)
        except OSError as exc:
            logger.warning("Failed to delete file {}: {}", paper.file_path, exc)

    # Remove from FAISS
    try:
        vector_store = get_vector_store()
        vector_store.delete_paper(paper_id)
    except Exception as exc:
        logger.warning("Failed to delete paper {} from FAISS: {}", paper_id, exc)

    db.delete(paper)
    db.commit()

    logger.info("Paper {} deleted.", paper_id)
