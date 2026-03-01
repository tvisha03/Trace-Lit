"""
Verification route — verify arbitrary text against uploaded papers.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import VerifyRequest, VerifyResponse, VerificationItem
from app.dependencies import get_db, get_faiss_store
from services.verification_service import verify_text_against_papers

router = APIRouter()


@router.post("", response_model=VerifyResponse)
async def verify_text(
    body: VerifyRequest,
    db: AsyncSession = Depends(get_db),
    faiss_store=Depends(get_faiss_store),
):
    """
    Verify arbitrary text (e.g., own notes) against indexed papers.
    Returns per-sentence HAVF verification results.
    """
    results = await verify_text_against_papers(
        text=body.text,
        paper_ids=body.paper_ids,
        faiss_store=faiss_store,
        db_session=db,
    )
    return VerifyResponse(
        results=[VerificationItem(**r) for r in results],
    )
