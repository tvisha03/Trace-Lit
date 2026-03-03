from collections import defaultdict
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import VerifyRequest, VerifyResponse, VerificationItem
from app.dependencies import get_db, get_faiss_store
from infrastructure.db.crud.paper_crud import get_paper
from infrastructure.db.crud.session_crud import get_session
from services.verification_service import verify_text_against_papers

router = APIRouter()

# ---------------------------------------------------------------------------
# Simple in-memory sliding-window rate limiter for the HAVF verify endpoint.
# HAVF is computationally expensive (embedding + cross-encoder reranking), so
# we cap each client IP at _RATE_LIMIT_MAX calls per _RATE_LIMIT_WINDOW seconds
# to prevent accidental or deliberate resource exhaustion.
#
# ⚠️  PRODUCTION NOTE (HI-002): This is a separate rate limiter from the
# upload endpoint's _upload_rate_limit_calls.  Keep them distinct: upload
# allows 5 req/min (expensive PDF pipeline), verification allows 10 req/min
# (faster but still CPU/GPU intensive).  Do NOT merge them.
# In multi-instance deployments replace with a shared Redis-backed limiter.
# ---------------------------------------------------------------------------
_RATE_LIMIT_MAX = 10
_RATE_LIMIT_WINDOW_SECONDS = 60.0
_verify_rate_limit_calls: dict[str, list[float]] = defaultdict(list)


def _enforce_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    now = monotonic()
    cutoff = now - _RATE_LIMIT_WINDOW_SECONDS

    # Evict timestamps that have fallen outside the sliding window.
    calls = _verify_rate_limit_calls[client_ip]
    _verify_rate_limit_calls[client_ip] = [t for t in calls if t > cutoff]

    if len(_verify_rate_limit_calls[client_ip]) >= _RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded: max {_RATE_LIMIT_MAX} verification "
                f"requests per {int(_RATE_LIMIT_WINDOW_SECONDS)} seconds."
            ),
        )

    _verify_rate_limit_calls[client_ip].append(now)


@router.post("/{session_id}", response_model=VerifyResponse)
async def verify_text(
    request: Request,
    session_id: str,
    body: VerifyRequest,
    db: AsyncSession = Depends(get_db),
    faiss_store=Depends(get_faiss_store),
):
    # Enforce rate limit before kicking off the expensive HAVF pipeline.
    _enforce_rate_limit(request)

    # Validate the session exists so we return a structured 404 rather than
    # an opaque downstream error if the session_id is wrong.
    session = await get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    # Verify every requested paper belongs to this session.  This prevents
    # one user from verifying content against another session's papers.
    for paper_id in body.paper_ids:
        paper = await get_paper(db, paper_id)
        if not paper:
            raise HTTPException(status_code=404, detail=f"Paper {paper_id} not found")
        # CRITICAL FIX: Verify paper belongs to this session
        if str(paper.session_id) != session_id:
            raise HTTPException(
                status_code=403,
                detail=f"Paper {paper_id} does not belong to session {session_id}",
            )

    results = await verify_text_against_papers(
        text=body.text,
        paper_ids=body.paper_ids,
        faiss_store=faiss_store,
        db_session=db,
    )
    return VerifyResponse(
        results=[VerificationItem(**r) for r in results],
    )
