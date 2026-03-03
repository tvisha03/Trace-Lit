
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import (
    KeywordResponse,
    KeywordItem,
    GapAnalysisResponse,
    ThemeItem,
    ReviewResponse,
    SummaryResponse,
)
from app.dependencies import get_db
from infrastructure.db.crud.paper_crud import get_paper, get_papers_by_session
from infrastructure.db.crud.session_crud import get_session
from infrastructure.llm.fallback_chain import FallbackChain
from services.analysis_service import (
    get_paper_keywords,
    get_session_gap_analysis,
    generate_literature_review,
    generate_paper_summary,
)
from shared.enums import PaperStatus
from shared.errors import ForbiddenError, InsufficientDataError, NotFoundError
from shared.utils.rate_limiter import SlidingWindowRateLimiter

router = APIRouter()

# Analysis endpoints invoke LLM + ML pipelines — rate-limit to prevent
# accidental quota exhaustion and CPU saturation.
_analysis_limiter = SlidingWindowRateLimiter(
    max_calls=10, window_seconds=60.0, resource_name="analysis requests",
)

def _get_llm(request: Request) -> FallbackChain:
    return request.app.state.llm

@router.get("/keywords/{paper_id}", response_model=KeywordResponse)
async def paper_keywords(
    session_id: str,
    paper_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _analysis_limiter.enforce(request)
    # Validate the paper exists before invoking the keyword extractor so the
    # caller receives a structured 404 instead of a silent empty response or
    # an opaque service-layer error (HI-005 fix).
    paper = await get_paper(db, paper_id)
    if not paper:
        raise NotFoundError("Paper", paper_id)

    # HI-001/HI-004: Validate the paper belongs to the caller’s session to
    # prevent cross-session keyword exposure.
    if str(paper.session_id) != session_id:
        raise ForbiddenError("Paper", paper_id)

    keywords = await get_paper_keywords(paper_id, db)
    return KeywordResponse(
        paper_id=paper_id,
        keywords=[KeywordItem(**k) for k in keywords],
    )

@router.get("/gaps", response_model=GapAnalysisResponse)
async def gap_analysis(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _analysis_limiter.enforce(request)
    # Validate session exists before running gap analysis (HI-005 fix).
    session = await get_session(db, session_id)
    if not session:
        raise NotFoundError("Session", session_id)

    # MED-003/BUG-003: Gap analysis requires at least one COMPLETED paper;
    # return a structured 400 instead of silently running on zero context.
    papers = await get_papers_by_session(db, session_id, status=PaperStatus.COMPLETED)
    if not papers:
        raise InsufficientDataError(
            f"No completed papers in session '{session_id}'. "
            "Please wait for paper processing to finish before running gap analysis."
        )

    if len(papers) < 2:
        raise InsufficientDataError(
            f"Gap analysis requires at least 2 completed papers, but session "
            f"'{session_id}' has only {len(papers)}. Upload more papers to "
            f"identify research gaps across multiple studies."
        )

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
    _analysis_limiter.enforce(request)
    # Validate session exists before generating the review (HI-005 fix).
    session = await get_session(db, session_id)
    if not session:
        raise NotFoundError("Session", session_id)

    # BUG-004: Literature review requires at least one COMPLETED paper;
    # return a structured 400 instead of letting the service layer fail silently.
    papers = await get_papers_by_session(db, session_id, status=PaperStatus.COMPLETED)
    if not papers:
        raise InsufficientDataError(
            f"No completed papers in session '{session_id}'. "
            "Please wait for paper processing to finish before generating a review."
        )

    llm = _get_llm(request)
    result = await generate_literature_review(session_id, db, llm)
    return ReviewResponse(**result)


@router.get("/summary/{paper_id}", response_model=SummaryResponse)
async def paper_summary(
    session_id: str,
    paper_id: str,
    request: Request,
    question: str = Query(
        default="Provide a structured summary of this paper.",
        max_length=500,
        description="Optional focus question for the summary (e.g. 'What methodology is used?').",
    ),
    db: AsyncSession = Depends(get_db),
):
    """Generate an on-demand structured summary for a single uploaded paper.

    Returns a cited summary covering the paper's problem, approach, key
    findings, and contributions.  Each point is cited with [P#] tags so the
    response can be verified with HAVF.
    """
    paper = await get_paper(db, paper_id)
    if not paper:
        raise NotFoundError("Paper", paper_id)

    # Verify the paper belongs to the caller's session to prevent cross-session
    # data exposure.
    if str(paper.session_id) != session_id:
        raise ForbiddenError("Paper", paper_id)

    if paper.status != PaperStatus.COMPLETED:
        raise InsufficientDataError(
            f"Paper '{paper_id}' is not yet fully processed (status: {paper.status.value}). "
            "Please wait for processing to complete before requesting a summary."
        )

    _analysis_limiter.enforce(request)
    llm = _get_llm(request)
    result = await generate_paper_summary(paper_id, db, llm, user_question=question)
    return SummaryResponse(**result)
