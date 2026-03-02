
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
from infrastructure.db.crud.paper_crud import get_paper
from infrastructure.db.crud.session_crud import get_session
from infrastructure.llm.fallback_chain import FallbackChain
from services.analysis_service import (
    get_paper_keywords,
    get_session_gap_analysis,
    generate_literature_review,
)
from shared.errors import NotFoundError

router = APIRouter()

def _get_llm(request: Request) -> FallbackChain:
    return request.app.state.llm

@router.get("/keywords/{paper_id}", response_model=KeywordResponse)
async def paper_keywords(
    paper_id: str,
    db: AsyncSession = Depends(get_db),
):
    # Validate the paper exists before invoking the keyword extractor so the
    # caller receives a structured 404 instead of a silent empty response or
    # an opaque service-layer error (HI-005 fix).
    paper = await get_paper(db, paper_id)
    if not paper:
        raise NotFoundError("Paper", paper_id)

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
    # Validate session exists before running gap analysis (HI-005 fix).
    session = await get_session(db, session_id)
    if not session:
        raise NotFoundError("Session", session_id)

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
    # Validate session exists before generating the review (HI-005 fix).
    session = await get_session(db, session_id)
    if not session:
        raise NotFoundError("Session", session_id)

    llm = _get_llm(request)
    result = await generate_literature_review(session_id, db, llm)
    return ReviewResponse(**result)
