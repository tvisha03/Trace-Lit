
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
    paper_id: str,
    db: AsyncSession = Depends(get_db),
):
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
    llm = _get_llm(request)
    result = await generate_literature_review(session_id, db, llm)
    return ReviewResponse(**result)
