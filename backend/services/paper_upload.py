"""TraceLit — Paper Upload & Processing Pipeline.

Pipeline: upload → validate → save file → extract → chunk → embed → DB + FAISS.
"""

import json
import os
from pathlib import Path
from typing import List

from fastapi import UploadFile
from loguru import logger
from sqlalchemy.orm import Session as DBSession

from api.v1.schemas import PaperUploadResponse
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

_chunker = SentenceAwareChunker()


async def process_uploads(
    files: List[UploadFile],
    db: DBSession,
) -> PaperUploadResponse:
    """Validate, save, and process uploaded PDFs.

    Args:
        files: List of uploaded PDF files.
        db: Database session.

    Returns:
        PaperUploadResponse with paper IDs and status.
    """
    existing_count = db.query(Paper).count()
    if existing_count + len(files) > settings.max_papers:
        raise PaperLimitError(limit=settings.max_papers)

    paper_ids: List[str] = []

    for upload_file in files:
        paper_id = generate_id()

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

        filename = safe_filename(upload_file.filename or f"{paper_id}.pdf")
        file_path = os.path.join(settings.upload_dir, f"{paper_id}_{filename}")
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "wb") as fh:
            fh.write(content)

        logger.info("Saved PDF: {} ({:.1f} MB) → {}", filename, size_mb, file_path)

        paper = Paper(
            id=paper_id,
            title=filename.replace(".pdf", "").replace("_", " "),
            file_path=file_path,
            status="processing",
        )
        db.add(paper)
        db.flush()
        paper_ids.append(paper_id)

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
    """Extract, chunk, embed, and store a single paper."""
    logger.info("Processing paper: {}", paper_id)

    result = await extract_paper(file_path, mode="auto")
    metadata = result["metadata"]
    sections_data = result["sections"]

    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise ExtractionError(message="Paper record not found", paper_id=paper_id)

    paper.title = metadata.get("title", paper.title)
    paper.authors = json.dumps(metadata.get("authors", []))
    paper.year = metadata.get("year")
    paper.pages = metadata.get("pages")

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

    paper_meta = {"paper_id": paper_id, "title": metadata.get("title", "Unknown")}
    chunks = _chunker.chunk_paper(sections_data, paper_meta)

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

    try:
        vector_store = get_vector_store()
        stored_count = vector_store.add_paragraphs(paper_id, chunks)
        logger.info("Embedded {} paragraphs for paper {} in FAISS", stored_count, paper_id)
    except Exception as exc:
        logger.error(
            "FAISS embedding failed for paper {}: {}. DB fallback active.",
            paper_id, exc,
        )

    paper.status = "ready"
    db.flush()
    logger.info(
        "Paper {} ready: {} sections, {} paragraphs",
        paper_id, len(sections_data), len(chunks),
    )
