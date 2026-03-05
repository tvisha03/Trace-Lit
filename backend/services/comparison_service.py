from sqlalchemy.ext.asyncio import AsyncSession

from domain.generation.chat_engine import generate_comparison
from domain.generation.prompts import build_context_block
from domain.extraction.contribution_extractor import extract_contributions
from infrastructure.db.crud.paper_crud import get_paper
from infrastructure.db.crud.chunk_crud import get_chunks_by_paper
from infrastructure.llm.fallback_chain import FallbackChain
from shared.errors import NotFoundError
from shared.logger import get_logger
from shared.utils.text_utils import estimate_tokens
from shared.constants import COMPARISON_TOKEN_BUDGET_PER_PAPER

logger = get_logger(__name__)

async def compare_papers(
    paper_ids: list[str],
    db: AsyncSession,
    llm: FallbackChain,
) -> dict:
    paper_contexts: dict[str, str] = {}
    paper_titles: list[str] = []
    paper_title_map: dict[str, str] = {}

    for pid in paper_ids:
        paper = await get_paper(db, pid)
        if not paper:
            raise NotFoundError("Paper", pid)

        title = paper.title or paper.filename
        paper_titles.append(title)
        paper_title_map[pid] = title
        chunks = await get_chunks_by_paper(db, pid)

        selected: list = []
        cumulative_tokens = 0
        for chunk in chunks:
            chunk_text = chunk.text if hasattr(chunk, "text") else str(chunk)
            chunk_tokens = estimate_tokens(chunk_text)
            if cumulative_tokens + chunk_tokens > COMPARISON_TOKEN_BUDGET_PER_PAPER:
                break
            selected.append(chunk)
            cumulative_tokens += chunk_tokens

        context = build_context_block(selected or chunks[:20])
        paper_contexts[pid] = context

    response_text, provider = await generate_comparison(
        paper_ids=paper_ids,
        paper_contexts=paper_contexts,
        llm=llm,
        paper_titles=paper_title_map,
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

