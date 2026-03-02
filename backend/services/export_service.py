"""TraceLit — Export Service.

Business logic for PDF, Excel, and Word exports.
"""

import json
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session as DBSession

from domain.export.pdf_exporter import generate_session_pdf
from domain.export.excel_exporter import generate_comparison_excel, generate_session_excel


async def export_session_pdf(
    session_id: str,
    db: DBSession,
) -> str:
    """Export a session to PDF.

    Args:
        session_id: Session identifier.
        db: Database session.

    Returns:
        Path to generated PDF file.
    """
    from infrastructure.db.models.session import Session as SessionModel
    from infrastructure.db.models.message import Message
    from infrastructure.db.models.paper import Paper

    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise ValueError(f"Session {session_id} not found")

    # Get messages
    messages = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.timestamp)
        .all()
    )

    message_dicts = []
    for msg in messages:
        metadata = {}
        if msg.metadata_:
            try:
                metadata = json.loads(msg.metadata_)
            except (json.JSONDecodeError, TypeError):
                pass
        message_dicts.append({
            "role": msg.role,
            "content": msg.content,
            "timestamp": msg.timestamp.isoformat() if msg.timestamp else "",
            "metadata": metadata,
        })

    # Get papers
    paper_ids = []
    if session.paper_ids:
        try:
            paper_ids = json.loads(session.paper_ids)
        except (json.JSONDecodeError, TypeError):
            pass

    papers = []
    for pid in paper_ids:
        paper = db.query(Paper).filter(Paper.id == pid).first()
        if paper:
            papers.append({
                "id": pid,
                "title": paper.title,
                "authors": json.loads(paper.authors) if paper.authors else [],
                "year": paper.year,
                "pages": paper.pages,
            })

    session_data = {
        "session_id": session_id,
        "session_name": session.name or "TraceLit Session",
        "messages": message_dicts,
        "papers": papers,
    }

    output_path = generate_session_pdf(session_data)
    logger.info("PDF export complete: {}", output_path)
    return output_path


async def export_comparison_excel(
    session_id: str,
    db: DBSession,
) -> str:
    """Export comparison table to Excel.

    Args:
        session_id: Session identifier.
        db: Database session.

    Returns:
        Path to generated Excel file.
    """
    from services.comparison_service import get_comparison_for_session

    comparison_data = await get_comparison_for_session(session_id, db)

    if not comparison_data.get("rows"):
        # Generate comparison first if none exists
        from services.comparison_service import generate_comparison_for_session
        comparison_data = await generate_comparison_for_session(session_id, db)

    output_path = generate_comparison_excel(comparison_data)
    logger.info("Excel comparison export complete: {}", output_path)
    return output_path


async def export_session_excel(
    session_id: str,
    db: DBSession,
) -> str:
    """Export full session to Excel.

    Args:
        session_id: Session identifier.
        db: Database session.

    Returns:
        Path to generated Excel file.
    """
    from infrastructure.db.models.session import Session as SessionModel
    from infrastructure.db.models.message import Message
    from infrastructure.db.models.paper import Paper

    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise ValueError(f"Session {session_id} not found")

    messages = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.timestamp)
        .all()
    )

    message_dicts = []
    for msg in messages:
        metadata = {}
        if msg.metadata_:
            try:
                metadata = json.loads(msg.metadata_)
            except (json.JSONDecodeError, TypeError):
                pass
        message_dicts.append({
            "role": msg.role,
            "content": msg.content,
            "metadata": metadata,
        })

    paper_ids = []
    if session.paper_ids:
        try:
            paper_ids = json.loads(session.paper_ids)
        except (json.JSONDecodeError, TypeError):
            pass

    papers = []
    for pid in paper_ids:
        paper = db.query(Paper).filter(Paper.id == pid).first()
        if paper:
            papers.append({
                "title": paper.title,
                "authors": json.loads(paper.authors) if paper.authors else [],
                "year": paper.year,
                "pages": paper.pages,
            })

    session_data = {
        "session_id": session_id,
        "session_name": session.name or "TraceLit Session",
        "messages": message_dicts,
        "papers": papers,
    }

    output_path = generate_session_excel(session_data)
    logger.info("Session Excel export complete: {}", output_path)
    return output_path


async def export_session_word(
    session_id: str,
    db: DBSession,
) -> str:
    """Export a session to Word (DOCX).

    Args:
        session_id: Session identifier.
        db: Database session.

    Returns:
        Path to generated DOCX file.
    """
    from infrastructure.db.models.session import Session as SessionModel
    from infrastructure.db.models.message import Message
    from infrastructure.db.models.paper import Paper
    from domain.export.word_exporter import generate_session_docx
    from app.config import settings

    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise ValueError(f"Session {session_id} not found")

    messages = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.timestamp)
        .all()
    )

    message_dicts = [{"role": msg.role, "content": msg.content} for msg in messages]

    paper_ids = []
    if session.paper_ids:
        try:
            paper_ids = json.loads(session.paper_ids)
        except (json.JSONDecodeError, TypeError):
            pass

    papers = []
    for pid in paper_ids:
        paper = db.query(Paper).filter(Paper.id == pid).first()
        if paper:
            papers.append({
                "title": paper.title,
                "authors": json.loads(paper.authors) if paper.authors else [],
                "year": paper.year,
            })

    output_path = str(settings.export_dir / f"session_{session_id}.docx")
    generate_session_docx(
        session_id=session_id,
        session_title=session.name or "TraceLit Session",
        messages=message_dicts,
        papers=papers,
        output_path=output_path,
    )
    logger.info("Word session export complete: {}", output_path)
    return output_path


async def export_literature_review_word(
    session_id: str,
    db: DBSession,
) -> str:
    """Export literature review to Word (DOCX).

    Generates the review first if not cached, then exports to DOCX.

    Args:
        session_id: Session identifier.
        db: Database session.

    Returns:
        Path to generated DOCX file.
    """
    from infrastructure.db.models.session import Session as SessionModel
    from infrastructure.db.models.paper import Paper
    from domain.export.word_exporter import generate_literature_review_docx
    from services.analysis_service import generate_literature_review_service
    from app.config import settings

    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise ValueError(f"Session {session_id} not found")

    paper_ids = []
    if session.paper_ids:
        try:
            paper_ids = json.loads(session.paper_ids)
        except (json.JSONDecodeError, TypeError):
            pass

    if not paper_ids:
        raise ValueError("No papers in session to generate literature review")

    papers = []
    for pid in paper_ids:
        paper = db.query(Paper).filter(Paper.id == pid).first()
        if paper:
            papers.append({
                "id": pid,
                "title": paper.title,
                "authors": json.loads(paper.authors) if paper.authors else [],
                "year": paper.year,
            })

    # Generate the review
    review_text = await generate_literature_review_service(session_id, db)

    output_path = str(settings.export_dir / f"literature_review_{session_id}.docx")
    generate_literature_review_docx(
        title=f"Literature Review — {session.name or 'TraceLit Session'}",
        review_text=review_text,
        papers=papers,
        output_path=output_path,
    )
    logger.info("Literature review DOCX export complete: {}", output_path)
    return output_path
