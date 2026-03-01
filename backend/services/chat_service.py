"""TraceLit — Chat Service (Business Logic).

Extracted from the v1 chat router for reusability.
Handles context retrieval, LLM generation, HAVF verification, and message persistence.
"""

import json
import uuid
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session as DBSession

from api.v1.schemas import ChatQueryRequest, ChatResponse, SentenceVerification
from domain.generation.chat_engine import classify_query_type
from domain.retrieval.retriever import retrieve_context_paragraphs
from domain.verification.runner import run_havf_verification
from infrastructure.db.models.message import Message
from infrastructure.db.models.paper import Paper
from infrastructure.db.models.session import Session as SessionModel
from shared.errors import PaperNotReadyError


def _save_message(
    db: DBSession,
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    message_id = str(uuid.uuid4())
    msg = Message(
        id=message_id,
        session_id=session_id,
        role=role,
        content=content,
        timestamp=datetime.utcnow(),
        metadata_=json.dumps(metadata) if metadata else None,
    )
    db.add(msg)
    db.commit()
    return message_id


def _overall_confidence(sentences: List[SentenceVerification]) -> float:
    if not sentences:
        return 0.0
    return round(sum(s.confidence for s in sentences) / len(sentences), 3)


def _resolve_paper_ids(request: ChatQueryRequest, session: SessionModel) -> List[str]:
    if request.active_paper_ids:
        return request.active_paper_ids
    if session.paper_ids:
        try:
            return json.loads(session.paper_ids)
        except (json.JSONDecodeError, TypeError):
            return []
    return []


async def handle_chat_query(
    request: ChatQueryRequest,
    session: SessionModel,
    db: DBSession,
) -> ChatResponse:
    """Business logic for the non-streaming chat endpoint."""
    from infrastructure.llm.fallback_chain import get_llm

    active_paper_ids = _resolve_paper_ids(request, session)

    for pid in active_paper_ids:
        paper = db.query(Paper).filter(Paper.id == pid).first()
        if paper and paper.status != "ready":
            raise PaperNotReadyError(paper_id=pid)

    context_paragraphs = retrieve_context_paragraphs(
        db=db, paper_ids=active_paper_ids, query=request.query
    )

    _save_message(db, request.session_id, "user", request.query)

    query_type = classify_query_type(request.query)
    is_comparison = query_type == "comparison"

    llm = get_llm()
    result = await llm.generate(
        query=request.query,
        context_paragraphs=context_paragraphs,
        session_id=request.session_id,
        active_paper_ids=active_paper_ids,
        is_comparison=is_comparison,
    )

    response_text: str = result["text"]
    provider: str = result["provider"]
    warning: Optional[str] = result.get("warning")

    verified_sentences = await run_havf_verification(response_text, context_paragraphs)
    overall_conf = _overall_confidence(verified_sentences)

    message_id = _save_message(
        db,
        request.session_id,
        "assistant",
        response_text,
        metadata={
            "provider": provider,
            "overall_confidence": overall_conf,
            "query_type": query_type,
            "warning": warning,
            "sentence_count": len(verified_sentences),
        },
    )

    session.updated_at = datetime.utcnow()
    db.commit()

    return ChatResponse(
        message_id=message_id,
        query=request.query,
        text=response_text,
        sentences=verified_sentences,
        overall_confidence=overall_conf,
        provider=provider,
        warning=warning,
        metadata={
            "query_type": query_type,
            "context_paragraphs_used": len(context_paragraphs),
        },
    )


async def stream_chat_query(
    request: ChatQueryRequest,
    session: SessionModel,
    db: DBSession,
) -> AsyncIterator[str]:
    """Business logic for the SSE streaming chat endpoint.

    Yields raw SSE event strings.
    """
    from infrastructure.llm.fallback_chain import get_llm
    from shared.errors import AllProvidersFailedError

    active_paper_ids = _resolve_paper_ids(request, session)

    context_paragraphs = retrieve_context_paragraphs(
        db=db, paper_ids=active_paper_ids, query=request.query
    )

    _save_message(db, request.session_id, "user", request.query)

    query_type = classify_query_type(request.query)
    is_comparison = query_type == "comparison"
    llm = get_llm()

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

        havf_results = await run_havf_verification(full_text, context_paragraphs)
        overall_conf = _overall_confidence(havf_results)

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

        message_id = _save_message(
            db,
            request.session_id,
            "assistant",
            full_text,
            metadata={
                "provider": provider,
                "query_type": query_type,
                "overall_confidence": overall_conf,
                "sentence_count": len(havf_results),
            },
        )

        session.updated_at = datetime.utcnow()
        db.commit()

        yield (
            f"data: {json.dumps({'type': 'done', 'metadata': {'message_id': message_id, 'provider': provider, 'overall_confidence': overall_conf, 'sentences': havf_data}})}\n\n"
        )

    except AllProvidersFailedError as exc:
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
    except Exception as exc:
        logger.error("Stream error: {}", exc, exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'message': 'An error occurred'})}\n\n"
