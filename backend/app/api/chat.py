"""TraceLit — Chat API Router.

Query endpoint with SSE streaming for cited responses.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.schemas.api_schemas import ChatQueryRequest, ChatResponse

router = APIRouter()


@router.post("/chat/query", response_model=ChatResponse)
async def chat_query(
    request: ChatQueryRequest,
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Send a query and get a cited response.

    In the future, this will return SSE stream. For now, returns full response.
    """
    # TODO: Implement in Week 2 (RAG pipeline + LLM providers)
    raise NotImplementedError("Chat query not yet implemented — coming in Week 2")
