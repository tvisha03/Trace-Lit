"""TraceLit — Paragraph/Chunk CRUD operations."""

from typing import List, Optional

from sqlalchemy.orm import Session

from infrastructure.db.models.chunk import Paragraph


def get_paragraphs_for_paper(db: Session, paper_id: str) -> List[Paragraph]:
    return db.query(Paragraph).filter(Paragraph.paper_id == paper_id).all()


def get_paragraphs_for_papers(db: Session, paper_ids: List[str], limit: int = 50) -> List[Paragraph]:
    return (
        db.query(Paragraph)
        .filter(Paragraph.paper_id.in_(paper_ids))
        .limit(limit)
        .all()
    )


def create_paragraph(db: Session, paragraph: Paragraph) -> Paragraph:
    db.add(paragraph)
    return paragraph


def delete_paragraphs_for_paper(db: Session, paper_id: str) -> None:
    db.query(Paragraph).filter(Paragraph.paper_id == paper_id).delete()
