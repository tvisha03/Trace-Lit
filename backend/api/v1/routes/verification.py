from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import VerifyRequest, VerifyResponse, VerificationItem
from app.dependencies import get_db, get_faiss_store
from infrastructure.db.crud.paper_crud import get_paper
from infrastructure.db.crud.session_crud import get_session
from services.verification_service import verify_text_against_papers
from shared.errors import NotFoundError, ForbiddenError
from shared.utils.rate_limiter import SlidingWindowRateLimiter

router = APIRouter()

# HAVF is computationally expensive, so cap each client IP at 10 calls/min.
_verify_limiter = SlidingWindowRateLimiter(
    max_calls=10, window_seconds=60.0, resource_name="verification requests",
)


@router.post("/{session_id}", response_model=VerifyResponse)
async def verify_text(
    request: Request,
    session_id: str,
    body: VerifyRequest,
    db: AsyncSession = Depends(get_db),
    faiss_store=Depends(get_faiss_store),
):
    # Enforce rate limit before kicking off the expensive HAVF pipeline.
    _verify_limiter.enforce(request)

    # Validate the session exists so we return a structured 404 rather than
    # an opaque downstream error if the session_id is wrong.
    session = await get_session(db, session_id)
    if not session:
        raise NotFoundError("Session", session_id)

    # CRT-001: Session ownership validation.
    # When auth middleware is present, verify the caller owns this session.
    if hasattr(request.state, "user_id"):
        if str(getattr(session, "owner_id", None)) != request.state.user_id:
            raise ForbiddenError("Session", session_id)

    # Verify every requested paper belongs to this session.  This prevents
    # one user from verifying content against another session's papers.
    for paper_id in body.paper_ids:
        paper = await get_paper(db, paper_id)
        if not paper:
            raise NotFoundError("Paper", paper_id)
        # CRITICAL FIX: Verify paper belongs to this session
        if str(paper.session_id) != session_id:
            raise ForbiddenError("Paper", paper_id)

    results = await verify_text_against_papers(
        text=body.text,
        paper_ids=body.paper_ids,
        faiss_store=faiss_store,
        db_session=db,
    )
    return VerifyResponse(
        results=[VerificationItem(**r) for r in results],
    )
