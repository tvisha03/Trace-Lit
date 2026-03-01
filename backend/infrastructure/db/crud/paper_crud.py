"""TraceLit — Paper CRUD operations."""

import json
from typing import List, Optional

from sqlalchemy.orm import Session

from infrastructure.db.models.paper import Paper


def get_paper(db: Session, paper_id: str) -> Optional[Paper]:
    return db.query(Paper).filter(Paper.id == paper_id).first()


def get_all_papers(db: Session) -> List[Paper]:
    return db.query(Paper).order_by(Paper.upload_date.desc()).all()


def create_paper(db: Session, paper: Paper) -> Paper:
    db.add(paper)
    db.flush()
    return paper


def update_paper_status(db: Session, paper_id: str, status: str, error: str = None) -> None:
    paper = get_paper(db, paper_id)
    if paper:
        paper.status = status
        if error:
            paper.error_message = error[:500]
        db.flush()


def delete_paper(db: Session, paper_id: str) -> None:
    paper = get_paper(db, paper_id)
    if paper:
        db.delete(paper)
