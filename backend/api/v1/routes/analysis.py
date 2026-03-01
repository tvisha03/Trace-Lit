"""
Analysis routes — keywords, gap analysis, literature review.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import (
    KeywordResponse,
    KeywordItem,
    GapAnalysisResponse,
    ThemeItem,
    ReviewResponse,
)
from app.dependencies import get_db
from infrastructure.llm.fallback_chain import FallbackChain
from services.analysis_service import (
    get_paper_keywords,
    get_session_gap_analysis,
    generate_literature_review,
)

router = APIRouter()


def _get_llm(request: Request) -> FallbackChain:
    return request.app.state.llm


@router.get("/keywords/{paper_id}", response_model=KeywordResponse)
async def paper_keywords(
    session_id: str,
    paper_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Extract keywords from a paper."""
    keywords = await get_paper_keywords(paper_id, db)
    return KeywordResponse(
        paper_id=paper_id,
        keywords=[KeywordItem(**k) for k in keywords],
    )


@router.get("/gaps", response_model=GapAnalysisResponse)
async def gap_analysis(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Run gap analysis across all papers in the session."""
    result = await get_session_gap_analysis(session_id, db)
    return GapAnalysisResponse(
        themes=[ThemeItem(**t) for t in result["themes"]],
        underexplored=[ThemeItem(**t) for t in result["underexplored"]],
    )


@router.get("/review", response_model=ReviewResponse)
async def literature_review(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Generate a mini literature review from all session papers."""
    llm = _get_llm(request)
    result = await generate_literature_review(session_id, db, llm)
    return ReviewResponse(**result)
