
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import CompareRequest, ComparisonResponse, ContributionResponse
from app.dependencies import get_db
from infrastructure.db.crud.paper_crud import get_paper
from infrastructure.llm.fallback_chain import FallbackChain
from services.comparison_service import compare_papers, extract_paper_contributions
from shared.errors import NotFoundError

router = APIRouter()

def _get_llm(request: Request) -> FallbackChain:
    return request.app.state.llm

async def _verify_papers_belong_to_session(
    paper_ids: list[str],
    session_id: str,
    db: AsyncSession,
) -> None:
    """Raise NotFoundError if any paper_id doesn't exist or belongs to a different session."""
    for pid in paper_ids:
        paper = await get_paper(db, pid)
        if not paper or str(paper.session_id) != session_id:
            raise NotFoundError("Paper", pid)

@router.post("", response_model=ComparisonResponse)
async def compare(
    session_id: str,
    body: CompareRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await _verify_papers_belong_to_session(body.paper_ids, session_id, db)
    llm = _get_llm(request)
    result = await compare_papers(body.paper_ids, db, llm)
    return ComparisonResponse(**result)

@router.get("/contributions/{paper_id}", response_model=ContributionResponse)
async def get_contributions(
    session_id: str,
    paper_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await _verify_papers_belong_to_session([paper_id], session_id, db)
    llm = _get_llm(request)
    return await extract_paper_contributions(paper_id, db, llm)
