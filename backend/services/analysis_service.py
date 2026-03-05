from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator

from domain.analysis.keyword_extractor import extract_keywords, extract_keywords_per_paper
from domain.analysis.gap_finder import find_gaps, GapAnalysis
from domain.analysis.review_generator import generate_review, stream_review, generate_gap_narrative
from domain.generation.prompts import SYSTEM_PROMPT, SUMMARY_PROMPT_TEMPLATE, build_context_block
from infrastructure.db.crud.paper_crud import get_paper, get_papers_by_session
from infrastructure.db.crud.chunk_crud import get_chunks_by_paper
from infrastructure.llm.fallback_chain import FallbackChain
from shared.enums import PaperStatus
from shared.errors import NotFoundError, InsufficientDataError
from shared.logger import get_logger

logger = get_logger(__name__)

_MAX_KEYWORD_TEXT_LENGTH = 15_000
_PRIORITY_SECTIONS = frozenset({
    "abstract", "introduction", "conclusion",
    "summary", "discussion", "results",
})
_SUMMARY_PRIORITY_SECTIONS = frozenset({
    "abstract", "introduction", "conclusion",
    "summary", "discussion", "results",
    "methodology", "methods", "approach",
    "contributions", "findings", "evaluation",
})
_SUMMARY_MAX_CHUNKS = 25
_SUMMARY_PRIORITY_SLOTS = 15
_SUMMARY_BODY_SLOTS = 10

def _prepare_keyword_text(
    chunks: list,
    max_length: int = _MAX_KEYWORD_TEXT_LENGTH,
) -> str:
    priority: list[str] = []
    other: list[str] = []
    for c in chunks:
        section = (getattr(c, "section_title", None) or "").lower()
        bucket = priority if any(s in section for s in _PRIORITY_SECTIONS) else other
        bucket.append(c.text if hasattr(c, "text") else str(c))
    combined = " ".join(priority + other)
    return combined[:max_length] if len(combined) > max_length else combined

async def _get_paper_titles(papers: list) -> dict[str, str]:
    return {str(p.id): p.title or p.filename for p in papers}

async def get_paper_keywords(
    paper_id: str,
    db: AsyncSession,
    top_n: int = 10,
) -> list[dict]:
    paper = await get_paper(db, paper_id)
    if not paper:
        raise NotFoundError("Paper", paper_id)

    chunks = await get_chunks_by_paper(db, paper_id)
    prepared_text = _prepare_keyword_text(chunks)
    return extract_keywords(prepared_text, top_n=top_n)

async def get_session_gap_analysis(
    session_id: str,
    db: AsyncSession,
    llm: FallbackChain | None = None,
) -> dict:
    papers = await get_papers_by_session(db, session_id, status=PaperStatus.COMPLETED)
    if len(papers) < 2:
        raise InsufficientDataError(
            "Gap analysis requires at least 2 completed papers in the session. "
            "Currently only {} completed paper(s) found. "
            "Please upload and wait for more papers to finish processing, "
            "then try again.".format(len(papers))
        )

    chunks_by_paper: dict[str, list] = {}
    paper_texts: dict[str, str] = {}
    for paper in papers:
        chunks = await get_chunks_by_paper(db, str(paper.id))
        chunks_by_paper[str(paper.id)] = chunks[:15]
        paper_texts[str(paper.id)] = _prepare_keyword_text(chunks)

    paper_keywords = extract_keywords_per_paper(paper_texts)
    gap_result: GapAnalysis = find_gaps(paper_keywords)

    result: dict = {
        "themes": [
            {
                "label": t.theme_label,
                "keywords": t.keywords,
                "papers_covering": t.papers_covering,
                "coverage_ratio": t.coverage_ratio,
            }
            for t in gap_result.themes
        ],
        "underexplored": [
            {
                "label": t.theme_label,
                "keywords": t.keywords,
                "coverage_ratio": t.coverage_ratio,
            }
            for t in gap_result.underexplored
        ],
    }

    if llm and chunks_by_paper:
        paper_titles = await _get_paper_titles(papers)
        narrative, provider = await generate_gap_narrative(
            chunks_by_paper, llm, paper_titles,
        )
        result["narrative"] = narrative
        result["provider"] = provider.value

    return result

async def generate_literature_review(
    session_id: str,
    db: AsyncSession,
    llm: FallbackChain,
) -> dict:
    chunks_by_paper = await _gather_review_chunks(session_id, db)
    papers = await get_papers_by_session(db, session_id, status=PaperStatus.COMPLETED)
    paper_titles = await _get_paper_titles(papers)

    review_text, provider = await generate_review(chunks_by_paper, llm, paper_titles)

    return {
        "review": review_text,
        "paper_count": len(papers),
        "provider": provider.value,
    }

async def _gather_review_chunks(
    session_id: str,
    db: AsyncSession,
) -> dict[str, list]:
    papers = await get_papers_by_session(db, session_id, status=PaperStatus.COMPLETED)
    if not papers:
        raise NotFoundError("Papers", f"no completed papers in session {session_id}")

    chunks_by_paper: dict[str, list] = {}
    for paper in papers:
        chunks = await get_chunks_by_paper(db, str(paper.id))
        if not chunks:
            logger.warning(
                f"Paper '{paper.id}' ({paper.title or paper.filename}) has no chunks "
                "despite COMPLETED status — skipping from literature review."
            )
            continue
        chunks_by_paper[str(paper.id)] = chunks[:15]

    if not chunks_by_paper:
        raise InsufficientDataError(
            "No indexed content found for the completed papers in this session. "
            "Please ensure papers have been fully processed before generating a review."
        )
    return chunks_by_paper

async def stream_literature_review(
    session_id: str,
    db: AsyncSession,
    llm: FallbackChain,
) -> AsyncGenerator[str, None]:
    import json
    from shared.utils.streaming_utils import sse_event

    full_text = ""
    provider = ""

    try:
        chunks_by_paper = await _gather_review_chunks(session_id, db)
        papers = await get_papers_by_session(db, session_id, status=PaperStatus.COMPLETED)
        paper_titles = await _get_paper_titles(papers)

        async for token, provider_obj in stream_review(chunks_by_paper, llm, paper_titles):
            full_text += token
            provider = provider_obj.value
            yield sse_event("token", {"token": token})

        resolved_provider = provider or "unknown"
        yield sse_event("done", json.dumps({
            "provider": resolved_provider,
            "full_text": full_text,
            "paper_count": len(chunks_by_paper),
        }))

    except Exception as exc:
        logger.error(f"Streaming literature review error for session {session_id}: {exc}")
        yield sse_event("error", str(exc))
        yield sse_event("done", json.dumps({
            "provider": provider or "unknown",
            "full_text": full_text,
            "error": True,
        }))

def _select_summary_chunks(chunks: list, max_total: int = _SUMMARY_MAX_CHUNKS) -> list:
    priority: list = []
    body: list = []

    for c in chunks:
        section = (getattr(c, "section_title", None) or "").lower()
        if any(s in section for s in _SUMMARY_PRIORITY_SECTIONS):
            priority.append(c)
        else:
            body.append(c)

    selected = priority[:_SUMMARY_PRIORITY_SLOTS]
    remaining_slots = max_total - len(selected)

    if remaining_slots > 0:
        selected.extend(body[:remaining_slots])

    if not selected:
        selected = chunks[:max_total]

    return selected

async def generate_paper_summary(
    paper_id: str,
    db: AsyncSession,
    llm: FallbackChain,
    user_question: str = "Provide a structured summary of this paper.",
) -> dict:
    paper = await get_paper(db, paper_id)
    if not paper:
        raise NotFoundError("Paper", paper_id)

    chunks = await get_chunks_by_paper(db, paper_id)
    if not chunks:
        raise InsufficientDataError(
            f"Paper '{paper_id}' has no indexed chunks yet. "
            "Please wait for processing to complete before requesting a summary."
        )

    selected = _select_summary_chunks(chunks)
    context = build_context_block(selected)
    user_prompt = SUMMARY_PROMPT_TEMPLATE.format(
        context=context, question=user_question
    )

    summary_text, provider, _ = await llm.generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        max_tokens=4096,
    )

    logger.info(
        f"Generated summary for paper {paper_id} "
        f"({len(selected)} chunks selected) using {provider.value}"
    )
    return {
        "paper_id": paper_id,
        "title": paper.title,
        "summary": summary_text,
        "provider": provider.value,
    }

