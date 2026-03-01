from sqlalchemy.ext.asyncio import AsyncSession

from domain.generation.chat_engine import generate_comparison
from domain.generation.prompts import build_context_block
from domain.extraction.contribution_extractor import extract_contributions
from infrastructure.db.crud.paper_crud import get_paper
from infrastructure.db.crud.chunk_crud import get_chunks_by_paper
from infrastructure.llm.fallback_chain import FallbackChain
from shared.errors import NotFoundError
from shared.logger import get_logger

logger = get_logger(__name__)


async def compare_papers(
    paper_ids: list[str],
    db: AsyncSession,
    llm: FallbackChain,
) -> dict:
    """
    Compare 2+ papers. Returns structured comparison text with provider info.

    Steps:
    1. Fetch top chunks per paper.
    2. Build context blocks.
    3. Generate comparison via LLM.
    """
    if len(paper_ids) < 2:
        raise ValueError("At least 2 papers required for comparison")

    paper_contexts: dict[str, str] = {}
    paper_titles: list[str] = []

    for pid in paper_ids:
        paper = await get_paper(db, pid)
        if not paper:
            raise NotFoundError("Paper", pid)

        paper_titles.append(paper.title or paper.filename)
        chunks = await get_chunks_by_paper(db, pid)

        # Use the first ~20 chunks as representative context
        context = build_context_block(chunks[:20])
        paper_contexts[pid] = context

    response_text, provider = await generate_comparison(
        paper_ids=paper_ids,
        paper_contexts=paper_contexts,
        llm=llm,
    )

    logger.info(f"Compared {len(paper_ids)} papers using {provider.value}")
    return {
        "comparison": response_text,
        "paper_ids": paper_ids,
        "paper_titles": paper_titles,
        "provider": provider.value,
    }


async def extract_paper_contributions(
    paper_id: str,
    db: AsyncSession,
    llm: FallbackChain,
) -> dict:
    """Extract structured contributions from a single paper."""
    paper = await get_paper(db, paper_id)
    if not paper:
        raise NotFoundError("Paper", paper_id)

    chunks = await get_chunks_by_paper(db, paper_id)
    context = build_context_block(chunks[:15])

    contributions = await extract_contributions(context, llm)
    return {
        "paper_id": paper_id,
        "title": paper.title or paper.filename,
        "contributions": contributions,
    }
