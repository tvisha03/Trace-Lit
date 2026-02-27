"""TraceLit — Chat API Router.

Query endpoint with cited responses using multi-provider LLM.
Streams SSE for real-time responses, falls back to full response.
"""

import json
import re
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from loguru import logger

from app.config import settings
from app.exceptions import AllProvidersFailedError, PaperNotReadyError
from app.llm.multi_provider import classify_query_type, get_llm
from app.llm.prompts import extract_citations
from app.models.database import get_db
from app.models.schemas import (
    Message,
    Paper,
    Paragraph,
    Session as SessionModel,
)
from app.schemas.api_schemas import (
    ChatQueryRequest,
    ChatResponse,
    CitationSource,
    SentenceVerification,
)

router = APIRouter()


# ============================================================
# Helpers
# ============================================================

def _get_context_paragraphs(
    db: Session,
    paper_ids: List[str],
) -> List[Dict]:
    """Retrieve paragraphs from active papers for LLM context.

    In Week 3+, this will use ChromaDB vector retrieval. For now,
    returns all paragraphs from the specified papers (up to a limit).

    Args:
        db: Database session.
        paper_ids: List of paper UUIDs to retrieve from.

    Returns:
        List of paragraph dicts with metadata.
    """
    if not paper_ids:
        return []

    paragraphs = (
        db.query(Paragraph)
        .filter(Paragraph.paper_id.in_(paper_ids))
        .limit(50)  # Safety cap — will be replaced by top-k retrieval
        .all()
    )

    # Enrich with paper metadata
    paper_map = {}
    for paper_id in paper_ids:
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        if paper:
            paper_map[paper_id] = paper

    context = []
    for para in paragraphs:
        paper = paper_map.get(para.paper_id)
        context.append({
            "paragraph_id": para.id,
            "text": para.text or "",
            "paper_id": para.paper_id,
            "paper_title": paper.title if paper else "Unknown",
            "section": "",  # Will come from section join in future
            "page": para.page or 0,
            "sentences": para.sentences,  # JSON string
        })

    return context


def _parse_response_sentences(
    response_text: str,
    context_paragraphs: List[Dict],
) -> List[SentenceVerification]:
    """Parse LLM response into verified sentence objects.

    For Week 2, this does basic citation extraction only.
    HAVF verification (embedding + cross-encoder) comes in Week 3.

    Args:
        response_text: Full LLM response.
        context_paragraphs: Context used for this query.

    Returns:
        List of SentenceVerification objects.
    """
    # Build paragraph lookup
    para_map: Dict[str, Dict] = {}
    for p in context_paragraphs:
        para_map[p["paragraph_id"]] = p

    # Split response into sentences
    pattern = r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<![A-Z]\.)(?<=\.|\?|!)\s+"
    raw_sentences = re.split(pattern, response_text)
    sentences = [s.strip() for s in raw_sentences if s.strip()]

    results = []
    citation_pattern = re.compile(r"\[P(\d+)\]")

    for sent_text in sentences:
        # Extract citations from this sentence
        matches = citation_pattern.findall(sent_text)
        cited_ids = [f"P{m}" for m in matches]

        # Build citation sources
        sources = []
        for pid in cited_ids:
            para = para_map.get(pid)
            if para:
                sources.append(
                    CitationSource(
                        paragraph_id=pid,
                        sentence_id=f"{pid}_S0",  # Placeholder — HAVF will refine
                        paper_id=para.get("paper_id", ""),
                        paper_title=para.get("paper_title", ""),
                        section=para.get("section", ""),
                        page=para.get("page", 0),
                        matched_text=para.get("text", "")[:200],
                    )
                )

        # Determine confidence level (placeholder — HAVF replaces this in Week 3)
        if cited_ids and all(pid in para_map for pid in cited_ids):
            confidence = 0.7  # Moderate — citation exists but unverified
            level = "medium"
            method = "citation_present"
        elif cited_ids:
            confidence = 0.4
            level = "low"
            method = "citation_unmatched"
        else:
            confidence = 0.3
            level = "low"
            method = "no_citation"

        results.append(
            SentenceVerification(
                text=sent_text,
                citations=cited_ids,
                confidence=confidence,
                level=level,
                method=method,
                sources=sources,
            )
        )

    return results


def _save_message(
    db: Session,
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[Dict] = None,
) -> str:
    """Persist a chat message to the database.

    Args:
        db: Database session.
        session_id: Session UUID.
        role: 'user' or 'assistant'.
        content: Message text.
        metadata: Optional metadata dict (confidence, provider, etc.).

    Returns:
        Message UUID.
    """
    message_id = str(uuid.uuid4())
    message = Message(
        id=message_id,
        session_id=session_id,
        role=role,
        content=content,
        timestamp=datetime.utcnow(),
        metadata_=json.dumps(metadata) if metadata else None,
    )
    db.add(message)
    db.commit()
    return message_id


# ============================================================
# Chat Endpoint
# ============================================================

@router.post("/chat/query", response_model=ChatResponse)
async def chat_query(
    request: ChatQueryRequest,
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Send a query and get a cited response.

    Uses multi-provider LLM with automatic fallback.
    Validates citations and returns sentence-level verification.

    Args:
        request: ChatQueryRequest with query, session_id, and optional paper filter.
        db: Database session dependency.

    Returns:
        ChatResponse with verified sentences, confidence, and provider info.
    """
    # Validate session exists
    session = db.query(SessionModel).filter(SessionModel.id == request.session_id).first()
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Session {request.session_id} not found",
        )

    # Determine active paper IDs
    active_paper_ids = request.active_paper_ids
    if not active_paper_ids and session.paper_ids:
        try:
            active_paper_ids = json.loads(session.paper_ids)
        except (json.JSONDecodeError, TypeError):
            active_paper_ids = []

    # Verify all papers are ready
    for paper_id in (active_paper_ids or []):
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        if paper and paper.status != "ready":
            raise PaperNotReadyError(paper_id=paper_id)

    # Get context paragraphs
    context_paragraphs = _get_context_paragraphs(db, active_paper_ids or [])

    if not context_paragraphs:
        # No papers/paragraphs — still allow the query but warn
        logger.warning(f"No context paragraphs for session {request.session_id}")

    # Save user message
    _save_message(db, request.session_id, "user", request.query)

    # Classify query type
    query_type = classify_query_type(request.query)
    is_comparison = query_type == "comparison"

    # Generate response via multi-provider LLM
    llm = get_llm()

    try:
        result = await llm.generate(
            query=request.query,
            context_paragraphs=context_paragraphs,
            session_id=request.session_id,
            active_paper_ids=active_paper_ids,
            is_comparison=is_comparison,
        )
    except AllProvidersFailedError:
        raise  # Bubble up — global handler returns structured error

    response_text = result["text"]
    provider = result["provider"]
    warning = result.get("warning")

    # Parse sentences and validate citations
    verified_sentences = _parse_response_sentences(
        response_text, context_paragraphs
    )

    # Calculate overall confidence
    if verified_sentences:
        overall_confidence = sum(
            s.confidence for s in verified_sentences
        ) / len(verified_sentences)
    else:
        overall_confidence = 0.0

    # Save assistant message with metadata
    message_id = _save_message(
        db,
        request.session_id,
        "assistant",
        response_text,
        metadata={
            "provider": provider,
            "overall_confidence": round(overall_confidence, 3),
            "query_type": query_type,
            "warning": warning,
            "sentence_count": len(verified_sentences),
        },
    )

    # Update session timestamp
    session.updated_at = datetime.utcnow()
    db.commit()

    return ChatResponse(
        message_id=message_id,
        query=request.query,
        text=response_text,
        sentences=verified_sentences,
        overall_confidence=round(overall_confidence, 3),
        provider=provider,
        warning=warning,
        metadata={
            "query_type": query_type,
            "context_paragraphs_used": len(context_paragraphs),
        },
    )


@router.post("/chat/query/stream")
async def chat_query_stream(
    request: ChatQueryRequest,
    db: Session = Depends(get_db),
):
    """Stream a cited response via Server-Sent Events.

    SSE format:
    - data: {"type": "chunk", "text": "..."}
    - data: {"type": "done", "metadata": {...}}

    HAVF verification runs after full response is received (not per-chunk).
    """
    # Validate session
    session = db.query(SessionModel).filter(SessionModel.id == request.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    active_paper_ids = request.active_paper_ids
    if not active_paper_ids and session.paper_ids:
        try:
            active_paper_ids = json.loads(session.paper_ids)
        except (json.JSONDecodeError, TypeError):
            active_paper_ids = []

    context_paragraphs = _get_context_paragraphs(db, active_paper_ids or [])

    _save_message(db, request.session_id, "user", request.query)

    query_type = classify_query_type(request.query)
    is_comparison = query_type == "comparison"
    llm = get_llm()

    async def generate_stream():
        full_text = ""
        provider = "unknown"

        try:
            async for chunk in llm.stream_with_fallback(
                query=request.query,
                context_paragraphs=context_paragraphs,
                session_id=request.session_id,
                active_paper_ids=active_paper_ids,
                is_comparison=is_comparison,
            ):
                full_text += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"

            state = llm.get_session_state(request.session_id)
            provider = state.last_provider or "unknown"

            # Save complete response
            message_id = _save_message(
                db,
                request.session_id,
                "assistant",
                full_text,
                metadata={"provider": provider, "query_type": query_type},
            )

            yield f"data: {json.dumps({'type': 'done', 'metadata': {'message_id': message_id, 'provider': provider}})}\n\n"

        except AllProvidersFailedError as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e.message)})}\n\n"

        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': 'An error occurred'})}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
