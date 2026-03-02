
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import CompareRequest, ComparisonResponse, ContributionResponse
from app.dependencies import get_db
from infrastructure.llm.fallback_chain import FallbackChain
from services.comparison_service import compare_papers, extract_paper_contributions

router = APIRouter()

def _get_llm(request: Request) -> FallbackChain:
    return request.app.state.llm

@router.post("", response_model=ComparisonResponse)
async def compare(
    session_id: str,
    body: CompareRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
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
    llm = _get_llm(request)
    return await extract_paper_contributions(paper_id, db, llm)
