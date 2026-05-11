
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import (
    KeywordResponse,
    KeywordItem,
    ReviewResponse,
    SummaryResponse,
    GapAnalysisResponse,
)
from app.dependencies import get_db
from infrastructure.db.crud.paper_crud import get_paper, get_papers_by_session
from infrastructure.db.crud.session_crud import get_session
from infrastructure.llm.fallback_chain import FallbackChain
from services.analysis_service import (
    get_paper_keywords,
    generate_literature_review,
    generate_paper_summary,
    stream_literature_review,
    stream_paper_summary,
    generate_research_gaps,
    stream_research_gaps,
)
from shared.enums import PaperStatus
from shared.errors import ForbiddenError, InsufficientDataError, NotFoundError
from shared.utils.rate_limiter import SlidingWindowRateLimiter

router = APIRouter()

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
    paper = await get_paper(db, paper_id)
    if not paper:
        raise NotFoundError("Paper", paper_id)

    if str(paper.session_id) != session_id:
        raise ForbiddenError("Paper", paper_id)

    keywords = await get_paper_keywords(paper_id, db)
    return KeywordResponse(
        paper_id=paper_id,
        keywords=[KeywordItem(**k) for k in keywords],
    )



@router.get("/review", response_model=ReviewResponse)
async def literature_review(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _analysis_limiter.enforce(request)
    session = await get_session(db, session_id)
    if not session:
        raise NotFoundError("Session", session_id)

    papers = await get_papers_by_session(db, session_id, status=PaperStatus.COMPLETED)
    if not papers:
        raise InsufficientDataError(
            f"No completed papers in session '{session_id}'. "
            "Please wait for paper processing to finish before generating a review."
        )

    llm = _get_llm(request)
    result = await generate_literature_review(session_id, db, llm)
    return ReviewResponse(**result)

@router.get("/review/stream", response_class=StreamingResponse)
async def literature_review_stream(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _analysis_limiter.enforce(request)

    session = await get_session(db, session_id)
    if not session:
        raise NotFoundError("Session", session_id)

    papers = await get_papers_by_session(db, session_id, status=PaperStatus.COMPLETED)
    if not papers:
        raise InsufficientDataError(
            f"No completed papers in session '{session_id}'. "
            "Please wait for paper processing to finish before generating a review."
        )

    llm = _get_llm(request)
    generator = stream_literature_review(session_id, db, llm)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

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
    paper = await get_paper(db, paper_id)
    if not paper:
        raise NotFoundError("Paper", paper_id)

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


@router.get("/summary/{paper_id}/stream", response_class=StreamingResponse)
async def paper_summary_stream(
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
    paper = await get_paper(db, paper_id)
    if not paper:
        raise NotFoundError("Paper", paper_id)

    if str(paper.session_id) != session_id:
        raise ForbiddenError("Paper", paper_id)

    if paper.status != PaperStatus.COMPLETED:
        raise InsufficientDataError(
            f"Paper '{paper_id}' is not yet fully processed (status: {paper.status.value}). "
            "Please wait for processing to complete before requesting a summary."
        )

    _analysis_limiter.enforce(request)
    llm = _get_llm(request)
    generator = stream_paper_summary(paper_id, db, llm, user_question=question)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
@router.get("/gaps", response_model=GapAnalysisResponse)
async def research_gaps(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _analysis_limiter.enforce(request)
    session = await get_session(db, session_id)
    if not session:
        raise NotFoundError("Session", session_id)

    papers = await get_papers_by_session(db, session_id, status=PaperStatus.COMPLETED)
    if not papers:
        raise InsufficientDataError(
            f"No completed papers in session '{session_id}'. "
            "Please wait for paper processing to finish before analyzing gaps."
        )

    llm = _get_llm(request)
    result = await generate_research_gaps(session_id, db, llm)
    return GapAnalysisResponse(**result)

@router.get("/gaps/stream", response_class=StreamingResponse)
async def research_gaps_stream(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _analysis_limiter.enforce(request)

    session = await get_session(db, session_id)
    if not session:
        raise NotFoundError("Session", session_id)

    papers = await get_papers_by_session(db, session_id, status=PaperStatus.COMPLETED)
    if not papers:
        raise InsufficientDataError(
            f"No completed papers in session '{session_id}'. "
            "Please wait for paper processing to finish before analyzing gaps."
        )

    llm = _get_llm(request)
    generator = stream_research_gaps(session_id, db, llm)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
