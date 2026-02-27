"""TraceLit — Papers API Router.

Upload, list, get details, get content, delete papers.
Thin router — delegates to paper_service for business logic.
"""

import json
from typing import List

from fastapi import APIRouter, File, UploadFile, Depends, HTTPException
from loguru import logger
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.schemas.api_schemas import (
    PaperSchema,
    PaperUploadResponse,
    PaperContentResponse,
)

router = APIRouter()


@router.post("/papers/upload", response_model=PaperUploadResponse, status_code=202)
async def upload_papers(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> PaperUploadResponse:
    """Upload one or more PDF papers for processing.

    Returns 202 Accepted with paper IDs and WebSocket URL for progress tracking.
    """
    from app.services.paper_service import process_uploads
    return await process_uploads(files=files, db=db)


@router.get("/papers", response_model=List[PaperSchema])
async def list_papers(db: Session = Depends(get_db)) -> List[PaperSchema]:
    """List all uploaded papers with their processing status."""
    from app.services.paper_service import get_all_papers
    return await get_all_papers(db=db)


@router.get("/papers/{paper_id}", response_model=PaperSchema)
async def get_paper(paper_id: str, db: Session = Depends(get_db)) -> PaperSchema:
    """Get details for a single paper."""
    from app.services.paper_service import get_paper_by_id
    return await get_paper_by_id(paper_id=paper_id, db=db)


@router.get("/papers/{paper_id}/content", response_model=PaperContentResponse)
async def get_paper_content(
    paper_id: str,
    db: Session = Depends(get_db),
) -> PaperContentResponse:
    """Get full paper content — sections, paragraphs, and sentences."""
    from app.services.paper_service import get_paper_content
    return await get_paper_content(paper_id=paper_id, db=db)


@router.delete("/papers/{paper_id}", status_code=204)
async def delete_paper(paper_id: str, db: Session = Depends(get_db)) -> None:
    """Delete a paper and its associated vectors."""
    from app.services.paper_service import delete_paper
    await delete_paper(paper_id=paper_id, db=db)
