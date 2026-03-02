"""TraceLit — v1 Analysis Router.

Endpoints for Phase 2 analysis features:
- Keyword extraction
- Paper summarization
- Literature review generation
- Research gap finding
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional

from app.dependencies import get_db

router = APIRouter()


# ============================================================
# Request/Response Models
# ============================================================

class LiteratureReviewRequest(BaseModel):
    """Request body for literature review generation."""
    session_id: str
    focus_area: Optional[str] = None


class ResearchGapRequest(BaseModel):
    """Request body for research gap analysis."""
    session_id: str


# ============================================================
# Keyword Extraction
# ============================================================

@router.post("/papers/{paper_id}/keywords")
async def extract_keywords(paper_id: str, db: Session = Depends(get_db)):
    """Extract keywords from a paper using KeyBERT with MMR diversity.

    Returns a list of the top 10 most representative keyphrases.
    """
    from services.analysis_service import extract_paper_keywords_service

    try:
        keywords = await extract_paper_keywords_service(paper_id, db)
        return {"paper_id": paper_id, "keywords": keywords}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/papers/{paper_id}/keywords")
async def get_keywords(paper_id: str, db: Session = Depends(get_db)):
    """Get stored keywords for a paper. Extracts on-demand if not cached."""
    from infrastructure.db.models.paper import Paper

    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id} not found")

    if paper.keywords:
        try:
            keywords = json.loads(paper.keywords)
            return {"paper_id": paper_id, "keywords": keywords, "cached": True}
        except (json.JSONDecodeError, TypeError):
            pass

    # Extract on-demand
    from services.analysis_service import extract_paper_keywords_service
    keywords = await extract_paper_keywords_service(paper_id, db)
    return {"paper_id": paper_id, "keywords": keywords, "cached": False}


# ============================================================
# Paper Summary
# ============================================================

@router.post("/papers/{paper_id}/summary")
async def generate_summary(paper_id: str, db: Session = Depends(get_db)):
    """Generate an on-demand summary for a paper.

    Uses the LLM to create a concise 150-300 word summary.
    Results are cached in the database.
    """
    from services.analysis_service import generate_summary_service

    try:
        summary = await generate_summary_service(paper_id, db)
        return {"paper_id": paper_id, "summary": summary}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/papers/{paper_id}/summary")
async def get_summary(paper_id: str, db: Session = Depends(get_db)):
    """Get stored summary for a paper. Returns null if not yet generated."""
    from infrastructure.db.models.paper import Paper

    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id} not found")

    return {
        "paper_id": paper_id,
        "summary": paper.summary,
        "has_summary": paper.summary is not None,
    }


# ============================================================
# Literature Review
# ============================================================

@router.post("/analysis/literature-review")
async def generate_literature_review(
    request: LiteratureReviewRequest,
    db: Session = Depends(get_db),
):
    """Generate a structured literature review from session papers.

    Creates a thematic literature review with proper citations,
    covering all active papers in the session.
    """
    from services.analysis_service import generate_literature_review_service

    try:
        review = await generate_literature_review_service(
            session_id=request.session_id,
            focus_area=request.focus_area,
            db=db,
        )
        return {
            "session_id": request.session_id,
            "review": review,
            "focus_area": request.focus_area,
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/analysis/literature-review/stream")
async def stream_literature_review(
    request: LiteratureReviewRequest,
    db: Session = Depends(get_db),
):
    """Stream a literature review generation via SSE."""
    from domain.analysis.literature_review import stream_literature_review
    from infrastructure.db.models.session import Session as SessionModel
    from infrastructure.db.models.paper import Paper, Section
    from infrastructure.db.models.chunk import Paragraph

    session = db.query(SessionModel).filter(SessionModel.id == request.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {request.session_id} not found")

    paper_ids = []
    if session.paper_ids:
        try:
            paper_ids = json.loads(session.paper_ids)
        except (json.JSONDecodeError, TypeError):
            pass

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

    focus = request.focus_area or "the main contributions, methods, and findings of these papers"

    async def event_stream():
        async for chunk in stream_literature_review(papers_data, focus):
            yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================================
# Research Gap Finder
# ============================================================

@router.post("/analysis/research-gaps")
async def find_research_gaps(
    request: ResearchGapRequest,
    db: Session = Depends(get_db),
):
    """Find research gaps across papers in a session.

    Extracts limitations → clusters with DBSCAN → LLM summarizes
    each cluster as a research gap.
    """
    from services.analysis_service import find_research_gaps_service

    try:
        result = await find_research_gaps_service(request.session_id, db)
        return {
            "session_id": request.session_id,
            **result,
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
