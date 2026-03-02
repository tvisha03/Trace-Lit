"""TraceLit — Analysis Service.

Business logic for Phase 2 features:
- Keyword extraction
- Paper summarization
- Literature review generation
- Research gap finding
"""

import json
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session as DBSession


async def extract_paper_keywords_service(
    paper_id: str,
    db: DBSession,
) -> List[str]:
    """Extract keywords for a paper and store them in the DB.

    Args:
        paper_id: Paper identifier.
        db: Database session.

    Returns:
        List of extracted keywords.
    """
    from domain.analysis.keyword_extractor import extract_paper_keywords
    from infrastructure.db.models.paper import Paper, Section
    from infrastructure.db.models.chunk import Paragraph

    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise ValueError(f"Paper {paper_id} not found")

    # Build sections data from paragraphs
    paragraphs = db.query(Paragraph).filter(Paragraph.paper_id == paper_id).all()

    sections_data = []
    section_paras: Dict[str, List[str]] = {}

    for p in paragraphs:
        section_title = "Unknown"
        if p.section_id:
            section = db.query(Section).filter(Section.id == p.section_id).first()
            if section:
                section_title = section.title
        section_paras.setdefault(section_title, []).append(p.text)

    for title, texts in section_paras.items():
        sections_data.append({
            "title": title,
            "paragraphs": [{"text": t} for t in texts],
        })

    keywords = extract_paper_keywords(sections_data, top_n=10)

    # Store in DB
    paper.keywords = json.dumps(keywords)
    db.commit()

    logger.info("Extracted {} keywords for paper {}", len(keywords), paper_id)
    return keywords


async def generate_summary_service(
    paper_id: str,
    db: DBSession,
) -> str:
    """Generate a summary for a paper and store it in the DB.

    Args:
        paper_id: Paper identifier.
        db: Database session.

    Returns:
        Generated summary text.
    """
    from domain.analysis.summary_generator import generate_paper_summary
    from infrastructure.db.models.paper import Paper, Section
    from infrastructure.db.models.chunk import Paragraph

    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise ValueError(f"Paper {paper_id} not found")

    # Return cached summary if it exists
    if paper.summary:
        return paper.summary

    # Build paragraphs data
    paragraphs = db.query(Paragraph).filter(Paragraph.paper_id == paper_id).all()
    para_dicts = []
    for p in paragraphs:
        section_title = "Unknown"
        if p.section_id:
            section = db.query(Section).filter(Section.id == p.section_id).first()
            if section:
                section_title = section.title
        para_dicts.append({
            "paragraph_id": p.id.replace(f"{paper_id}_", "") if p.id.startswith(paper_id) else p.id,
            "text": p.text,
            "section": section_title,
            "page": p.page,
        })

    summary = await generate_paper_summary(
        title=paper.title,
        paragraphs=para_dicts,
    )

    # Store in DB
    paper.summary = summary
    db.commit()

    logger.info("Generated summary for paper {}", paper_id)
    return summary


async def generate_literature_review_service(
    session_id: str,
    focus_area: Optional[str],
    db: DBSession,
) -> str:
    """Generate a literature review for all papers in a session.

    Args:
        session_id: Session identifier.
        focus_area: Optional focus/theme for the review.
        db: Database session.

    Returns:
        Literature review text.
    """
    from domain.analysis.literature_review import generate_literature_review
    from infrastructure.db.models.session import Session as SessionModel
    from infrastructure.db.models.paper import Paper, Section
    from infrastructure.db.models.chunk import Paragraph

    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise ValueError(f"Session {session_id} not found")

    paper_ids = []
    if session.paper_ids:
        try:
            paper_ids = json.loads(session.paper_ids)
        except (json.JSONDecodeError, TypeError):
            paper_ids = []

    papers_data = []
    for pid in paper_ids:
        paper = db.query(Paper).filter(Paper.id == pid).first()
        if not paper or paper.status != "ready":
            continue

        paragraphs = db.query(Paragraph).filter(Paragraph.paper_id == pid).all()
        para_dicts = []
        for p in paragraphs:
            section_title = "Unknown"
            if p.section_id:
                section = db.query(Section).filter(Section.id == p.section_id).first()
                if section:
                    section_title = section.title
            para_dicts.append({
                "paragraph_id": p.id.replace(f"{pid}_", "") if p.id.startswith(pid) else p.id,
                "text": p.text,
                "section": section_title,
                "page": p.page,
            })

        papers_data.append({
            "paper_id": pid,
            "title": paper.title,
            "paragraphs": para_dicts,
        })

    if focus_area is None:
        focus_area = "the main contributions, methods, and findings of these papers"

    review = await generate_literature_review(
        papers_data=papers_data,
        focus_area=focus_area,
    )

    logger.info("Generated literature review for session {} ({} papers)", session_id, len(papers_data))
    return review


async def find_research_gaps_service(
    session_id: str,
    db: DBSession,
) -> Dict[str, Any]:
    """Find research gaps across papers in a session.

    Args:
        session_id: Session identifier.
        db: Database session.

    Returns:
        Dict with gaps, metadata.
    """
    from domain.analysis.research_gaps import find_research_gaps
    from infrastructure.db.models.session import Session as SessionModel
    from infrastructure.db.models.paper import Paper, Section
    from infrastructure.db.models.chunk import Paragraph

    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise ValueError(f"Session {session_id} not found")

    paper_ids = []
    if session.paper_ids:
        try:
            paper_ids = json.loads(session.paper_ids)
        except (json.JSONDecodeError, TypeError):
            paper_ids = []

    papers_data = []
    for pid in paper_ids:
        paper = db.query(Paper).filter(Paper.id == pid).first()
        if not paper or paper.status != "ready":
            continue

        paragraphs = db.query(Paragraph).filter(Paragraph.paper_id == pid).all()
        para_dicts = []
        for p in paragraphs:
            section_title = "Unknown"
            if p.section_id:
                section = db.query(Section).filter(Section.id == p.section_id).first()
                if section:
                    section_title = section.title
            para_dicts.append({
                "paragraph_id": p.id.replace(f"{pid}_", "") if p.id.startswith(pid) else p.id,
                "text": p.text,
                "section": section_title,
                "page": p.page,
            })

        papers_data.append({
            "paper_id": pid,
            "title": paper.title,
            "paragraphs": para_dicts,
        })

    result = await find_research_gaps(papers_data=papers_data)
    logger.info("Found {} research gaps for session {}", len(result.get("gaps", [])), session_id)
    return result
