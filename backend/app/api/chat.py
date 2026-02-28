"""TraceLit — Chat API Router.

Query endpoint with cited responses using multi-provider LLM.
Streams SSE for real-time responses, falls back to full response.
HAVF verification runs on every response for sentence-level attribution.
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
from app.verification.havf import (
    get_havf,
    parse_response_into_sentences,
    build_cited_paragraphs_map,
)
from app.embeddings.vector_store import get_vector_store

router = APIRouter()


# ============================================================
# Helpers
# ============================================================

def _get_context_paragraphs(
    db: Session,
    paper_ids: List[str],
    query: str = "",
    top_k: int = 5,
) -> List[Dict]:
    """Retrieve relevant paragraphs using FAISS vector retrieval.

    Uses MPS-accelerated embeddings to find the most relevant paragraphs
    for the query across active papers. Falls back to DB retrieval if
    FAISS is unavailable.

    Args:
        db: Database session.
        paper_ids: List of paper UUIDs to retrieve from.
        query: User query for semantic similarity search.
        top_k: Number of results per paper.

    Returns:
        List of paragraph dicts with metadata and sentences.
    """
    if not paper_ids:
        return []

    # Try ChromaDB vector retrieval first
    if query:
        try:
            vector_store = get_vector_store()
            results = vector_store.query(
                query_text=query,
                paper_ids=paper_ids,
                top_k=top_k,
            )
            if results:
                logger.debug(
                    "Vector retrieval returned {} paragraphs for query",
                    len(results),
                )
                return results
        except Exception as e:
            logger.warning("FAISS retrieval failed, falling back to DB: {}", e)

    # Fallback: DB retrieval (no semantic ranking)
    paragraphs = (
        db.query(Paragraph)
        .filter(Paragraph.paper_id.in_(paper_ids))
        .limit(50)
        .all()
    )

    paper_map = {}
    for paper_id in paper_ids:
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        if paper:
            paper_map[paper_id] = paper

    context = []
    for para in paragraphs:
        paper = paper_map.get(para.paper_id)

        # Parse sentences
        sentences = []
        if para.sentences:
            try:
                sentences = json.loads(para.sentences)
            except (json.JSONDecodeError, TypeError):
                sentences = []

        context.append({
            "paragraph_id": para.id,
            "text": para.text or "",
            "paper_id": para.paper_id,
            "paper_title": paper.title if paper else "Unknown",
            "section": "",
            "page": para.page or 0,
            "sentences": sentences,
        })

    return context


def _parse_response_sentences(
    response_text: str,
    context_paragraphs: List[Dict],
) -> List[SentenceVerification]:
    """Parse LLM response into verified sentence objects using HAVF.

    Runs the Hybrid Attribution Verification Framework (HAVF) to verify
    each sentence against its cited source paragraphs with embedding
    similarity (Level 1) and cross-encoder reranking (Level 2).

    Args:
        response_text: Full LLM response.
        context_paragraphs: Context used for this query.

    Returns:
        List of SentenceVerification objects with confidence scores.
    """
    import asyncio

    # Build paragraph lookup (handles paper-prefixed IDs)
    para_map = build_cited_paragraphs_map(context_paragraphs)

    # Parse response into sentences with citations
    parsed_sentences = parse_response_into_sentences(response_text)

    if not parsed_sentences:
        return []

    # Run HAVF verification
    havf = get_havf()

    try:
        # Use asyncio to run the async HAVF method
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're already in an async context — create a task inline
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                havf_results = loop.run_in_executor(
                    pool,
                    lambda: asyncio.run(
                        havf.verify_response(parsed_sentences, para_map)
                    ),
                )
                # This won't work inside an async route; use await instead
                # Fall through to the await-based path below
                raise RuntimeError("Use await path")
        else:
            havf_results = asyncio.run(
                havf.verify_response(parsed_sentences, para_map)
            )
    except RuntimeError:
        # We'll handle this in the async route directly
        havf_results = None

    if havf_results is None:
        # Return placeholder results — the async route will call HAVF directly
        return _build_placeholder_verifications(parsed_sentences, para_map)

    # Convert HAVF results to SentenceVerification objects
    return _havf_results_to_verifications(havf_results, para_map)


async def _run_havf_verification(
    response_text: str,
    context_paragraphs: List[Dict],
) -> List[SentenceVerification]:
    """Async HAVF verification — called from async route handlers.

    Args:
        response_text: Full LLM response.
        context_paragraphs: Context used for this query.

    Returns:
        List of SentenceVerification objects.
    """
    para_map = build_cited_paragraphs_map(context_paragraphs)
    parsed_sentences = parse_response_into_sentences(response_text)

    if not parsed_sentences:
        return []

    havf = get_havf()

    try:
        havf_results = await havf.verify_response(parsed_sentences, para_map)
    except Exception as exc:
        logger.error("HAVF verification failed: {}", exc, exc_info=True)
        # Graceful degradation: return placeholder results
        return _build_placeholder_verifications(parsed_sentences, para_map)

    return _havf_results_to_verifications(havf_results, para_map)


def _havf_results_to_verifications(
    havf_results: List[Dict],
    para_map: Dict[str, Dict],
) -> List[SentenceVerification]:
    """Convert raw HAVF results to SentenceVerification Pydantic models."""
    results = []
    for hr in havf_results:
        pid = hr.get("paragraph_id", "")
        sid = hr.get("sentence_id", "")
        para = para_map.get(pid, {})

        sources = []
        if pid and para:
            sources.append(
                CitationSource(
                    paragraph_id=pid,
                    sentence_id=sid or f"{pid}_S0",
                    paper_id=para.get("paper_id", ""),
                    paper_title=para.get("paper_title", ""),
                    section=para.get("section", ""),
                    page=para.get("page", 0),
                    matched_text=hr.get("matched_text", "")[:300],
                )
            )

        # Extract citations from the sentence text
        citation_pattern = re.compile(r"\[P(\d+)\]")
        sent_text = hr.get("text", "")
        cited_ids = [f"P{m}" for m in citation_pattern.findall(sent_text)]

        results.append(
            SentenceVerification(
                text=sent_text,
                citations=cited_ids,
                confidence=hr.get("confidence", 0.0),
                level=hr.get("level", "low"),
                method=hr.get("method", "unknown"),
                sources=sources,
            )
        )

    return results


def _build_placeholder_verifications(
    parsed_sentences: List[Dict],
    para_map: Dict[str, Dict],
) -> List[SentenceVerification]:
    """Build placeholder verifications when HAVF is unavailable (graceful degradation)."""
    results = []
    for sent in parsed_sentences:
        cited_ids = sent.get("citations", [])
        sources = []
        for pid in cited_ids:
            para = para_map.get(pid, {})
            if para:
                sources.append(
                    CitationSource(
                        paragraph_id=pid,
                        sentence_id=f"{pid}_S0",
                        paper_id=para.get("paper_id", ""),
                        paper_title=para.get("paper_title", ""),
                        section=para.get("section", ""),
                        page=para.get("page", 0),
                        matched_text=para.get("text", "")[:200],
                    )
                )

        if cited_ids and all(pid in para_map for pid in cited_ids):
            confidence = 0.7
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
                text=sent.get("text", ""),
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

    # Get context paragraphs via vector retrieval
    context_paragraphs = _get_context_paragraphs(
        db, active_paper_ids or [], query=request.query
    )

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

    # Run HAVF verification (sentence-level attribution)
    verified_sentences = await _run_havf_verification(
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

    context_paragraphs = _get_context_paragraphs(
        db, active_paper_ids or [], query=request.query
    )

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

            # Run HAVF verification on complete response
            havf_results = await _run_havf_verification(
                full_text, context_paragraphs
            )

            # Calculate overall confidence
            if havf_results:
                overall_conf = sum(s.confidence for s in havf_results) / len(havf_results)
            else:
                overall_conf = 0.0

            # Serialize HAVF results for SSE
            havf_data = [
                {
                    "text": s.text,
                    "citations": s.citations,
                    "confidence": s.confidence,
                    "level": s.level,
                    "method": s.method,
                    "sources": [
                        {
                            "paragraph_id": src.paragraph_id,
                            "sentence_id": src.sentence_id,
                            "paper_id": src.paper_id,
                            "paper_title": src.paper_title,
                            "section": src.section,
                            "page": src.page,
                            "matched_text": src.matched_text,
                        }
                        for src in s.sources
                    ],
                }
                for s in havf_results
            ]

            # Save complete response
            message_id = _save_message(
                db,
                request.session_id,
                "assistant",
                full_text,
                metadata={
                    "provider": provider,
                    "query_type": query_type,
                    "overall_confidence": round(overall_conf, 3),
                    "sentence_count": len(havf_results),
                },
            )

            yield f"data: {json.dumps({'type': 'done', 'metadata': {'message_id': message_id, 'provider': provider, 'overall_confidence': round(overall_conf, 3), 'sentences': havf_data}})}\n\n"

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
