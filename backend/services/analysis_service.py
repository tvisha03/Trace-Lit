from sqlalchemy.ext.asyncio import AsyncSession

from domain.analysis.keyword_extractor import extract_keywords, extract_keywords_per_paper
from domain.analysis.gap_finder import find_gaps, GapAnalysis
from domain.analysis.review_generator import generate_review
from domain.generation.prompts import build_context_block
from infrastructure.db.crud.paper_crud import get_paper, get_papers_by_session
from infrastructure.db.crud.chunk_crud import get_chunks_by_paper
from infrastructure.llm.fallback_chain import FallbackChain
from shared.enums import PaperStatus
from shared.errors import NotFoundError, InsufficientDataError
from shared.logger import get_logger

logger = get_logger(__name__)


async def get_paper_keywords(
    paper_id: str,
    db: AsyncSession,
    top_n: int = 10,
) -> list[dict]:
    """Extract keywords from a single paper's text."""
    paper = await get_paper(db, paper_id)
    if not paper:
        raise NotFoundError("Paper", paper_id)

    chunks = await get_chunks_by_paper(db, paper_id)
    full_text = " ".join(c.text for c in chunks)
    return extract_keywords(full_text, top_n=top_n)


async def get_session_gap_analysis(
    session_id: str,
    db: AsyncSession,
) -> dict:
    """
    Run gap analysis across all completed papers in a session.
    Returns theme clusters and underexplored areas.
    """
    papers = await get_papers_by_session(db, session_id, status=PaperStatus.COMPLETED)
    if len(papers) < 2:
        raise InsufficientDataError("Gap analysis requires at least 2 completed papers")

    # Gather text per paper
    paper_texts: dict[str, str] = {}
    for paper in papers:
        chunks = await get_chunks_by_paper(db, str(paper.id))
        paper_texts[str(paper.id)] = " ".join(c.text for c in chunks)

    # Extract keywords per paper
    paper_keywords = extract_keywords_per_paper(paper_texts)

    # Run gap analysis
    gap_result: GapAnalysis = find_gaps(paper_keywords)

    return {
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


async def generate_literature_review(
    session_id: str,
    db: AsyncSession,
    llm: FallbackChain,
) -> dict:
    """Generate a mini literature review from all papers in a session."""
    papers = await get_papers_by_session(db, session_id, status=PaperStatus.COMPLETED)
    if not papers:
        raise NotFoundError("Papers", f"no completed papers in session {session_id}")

    chunks_by_paper: dict[str, list] = {}
    for paper in papers:
        chunks = await get_chunks_by_paper(db, str(paper.id))
        chunks_by_paper[str(paper.id)] = chunks[:15]

    review_text, provider = await generate_review(chunks_by_paper, llm)

    return {
        "review": review_text,
        "paper_count": len(papers),
        "provider": provider.value,
    }
