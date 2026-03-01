"""TraceLit — Paper Query Operations (list, get, content, delete)."""

import json
import os
from typing import List

from loguru import logger
from sqlalchemy.orm import Session as DBSession

from api.v1.schemas import (
    PaperContentResponse,
    PaperSchema,
    ParagraphSchema,
    SectionSchema,
    SentenceSchema,
)
from infrastructure.db.models.chunk import Paragraph
from infrastructure.db.models.paper import Paper, Section
from infrastructure.vector_store.faiss_store import get_vector_store


async def get_all_papers(db: DBSession) -> List[PaperSchema]:
    """List all papers with processing status, newest first."""
    papers = db.query(Paper).order_by(Paper.upload_date.desc()).all()
    return [_paper_to_schema(p) for p in papers]


async def get_paper_by_id(paper_id: str, db: DBSession) -> PaperSchema:
    """Get details for a single paper."""
    from fastapi import HTTPException

    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id} not found")
    return _paper_to_schema(paper)


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
    paragraphs = db.query(Paragraph).filter(Paragraph.paper_id == paper_id).all()

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
                section=next((s.title for s in sections if s.id == p.section_id), "Unknown"),
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

    if paper.file_path and os.path.exists(paper.file_path):
        try:
            os.remove(paper.file_path)
            logger.info("Deleted file: {}", paper.file_path)
        except OSError as exc:
            logger.warning("Failed to delete file {}: {}", paper.file_path, exc)

    try:
        get_vector_store().delete_paper(paper_id)
    except Exception as exc:
        logger.warning("Failed to delete paper {} from FAISS: {}", paper_id, exc)

    db.delete(paper)
    db.commit()
    logger.info("Paper {} deleted.", paper_id)


# ============================================================
# Internal helpers
# ============================================================

def _paper_to_schema(p: Paper) -> PaperSchema:
    return PaperSchema(
        id=p.id,
        title=p.title,
        authors=json.loads(p.authors) if p.authors else [],
        year=p.year,
        pages=p.pages,
        status=p.status,
        upload_date=p.upload_date.isoformat() if p.upload_date else "",
        error_message=p.error_message,
    )
