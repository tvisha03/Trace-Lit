import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from domain.generation.chat_engine import generate_comparison
from domain.generation.prompts import build_context_block
from domain.extraction.contribution_extractor import extract_contributions
from infrastructure.db.crud.paper_crud import get_paper
from infrastructure.db.crud.chunk_crud import get_chunks_by_paper
from infrastructure.llm.fallback_chain import FallbackChain
from shared.enums import LLMProvider
from shared.errors import NotFoundError
from shared.logger import get_logger
from shared.utils.export_text import build_export_blocks
from shared.utils.text_utils import estimate_tokens
from shared.constants import COMPARISON_TOKEN_BUDGET_PER_PAPER

logger = get_logger(__name__)

# Conservative budget to stay safely under Groq 12K TPM
# Total prompt tokens for N papers ≈ N * per_paper_budget + ~1K system/template overhead
_GROQ_SAFE_TOTAL_TOKENS = 8_000
_FALLBACK_DIMENSION = "Comparison"


def _adaptive_token_budget(paper_count: int) -> int:
    """Scale per-paper token budget so the total prompt fits within rate limits."""
    if paper_count <= 1:
        return COMPARISON_TOKEN_BUDGET_PER_PAPER

    # Reserve ~2K tokens for system prompt + comparison template overhead
    available = _GROQ_SAFE_TOTAL_TOKENS - 2_000
    per_paper = available // paper_count
    # Clamp between 500 and the configured maximum
    return max(500, min(per_paper, COMPARISON_TOKEN_BUDGET_PER_PAPER))


async def _load_paper_context(
    pid: str, db: AsyncSession, token_budget: int,
) -> tuple[str, str, str]:
    """Load a single paper's title and context within the given token budget."""
    paper = await get_paper(db, pid)
    if not paper:
        raise NotFoundError("Paper", pid)

    title = paper.title or paper.filename
    chunks = await get_chunks_by_paper(db, pid)

    selected: list = []
    cumulative_tokens = 0
    for chunk in chunks:
        chunk_text = chunk.text if hasattr(chunk, "text") else str(chunk)
        chunk_tokens = estimate_tokens(chunk_text)
        if cumulative_tokens + chunk_tokens > token_budget:
            break
        selected.append(chunk)
        cumulative_tokens += chunk_tokens

    context = build_context_block(selected or chunks[:10])
    return pid, title, context


async def _build_paper_maps(
    paper_ids: list[str], db: AsyncSession, token_budget: int,
) -> tuple[dict[str, str], list[str], dict[str, str]]:
    results = await asyncio.gather(
        *[_load_paper_context(pid, db, token_budget) for pid in paper_ids]
    )
    contexts: dict[str, str] = {}
    titles: list[str] = []
    title_map: dict[str, str] = {}
    for pid, title, context in results:
        titles.append(title)
        title_map[pid] = title
        contexts[pid] = context
    return contexts, titles, title_map


async def _run_comparison(
    paper_ids: list[str],
    paper_contexts: dict[str, str],
    paper_title_map: dict[str, str],
    llm: FallbackChain,
    timeout: int,
) -> tuple[str, LLMProvider]:
    return await asyncio.wait_for(
        generate_comparison(
            paper_ids=paper_ids,
            paper_contexts=paper_contexts,
            llm=llm,
            paper_titles=paper_title_map,
        ),
        timeout=timeout,
    )


def _normalize_cell_text(text: str) -> str:
    return " ".join(part.strip() for part in (text or "").replace("<br>", "\n").splitlines() if part.strip())


def _build_comparison_rows(
    comparison_text: str,
    paper_ids: list[str],
    titles: list[str],
) -> list[dict]:
    for block in build_export_blocks(comparison_text):
        if block.kind != "table" or not block.rows:
            continue

        rows: list[dict] = []
        for row in block.rows:
            if not row:
                continue
            dimension = _normalize_cell_text(row[0]) or _FALLBACK_DIMENSION
            cells = []
            for idx, paper_id in enumerate(paper_ids, start=1):
                cell_text = _normalize_cell_text(row[idx] if idx < len(row) else "")
                cells.append(
                    {
                        "paper_id": paper_id,
                        "paper_title": titles[idx - 1],
                        "content": cell_text,
                    }
                )

            synthesis_index = len(paper_ids) + 1
            synthesis = _normalize_cell_text(row[synthesis_index] if synthesis_index < len(row) else "")
            rows.append(
                {
                    "dimension": dimension,
                    "cells": cells,
                    "synthesis": synthesis,
                }
            )
        if rows:
            return rows

    return [
        {
            "dimension": _FALLBACK_DIMENSION,
            "cells": [
                {
                    "paper_id": paper_id,
                    "paper_title": titles[idx],
                    "content": "",
                }
                for idx, paper_id in enumerate(paper_ids)
            ],
            "synthesis": comparison_text.strip(),
        }
    ]


async def compare_papers(
    paper_ids: list[str],
    db: AsyncSession,
    llm: FallbackChain,
) -> dict:
    settings = get_settings()
    budget = _adaptive_token_budget(len(paper_ids))
    logger.info(f"Comparing {len(paper_ids)} papers ({budget} tokens/paper)")

    contexts, titles, title_map = await _build_paper_maps(paper_ids, db, budget)

    try:
        text, provider = await _run_comparison(
            paper_ids, contexts, title_map, llm, settings.COMPARISON_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        reduced = max(300, budget // 2)
        logger.warning(f"Comparison timed out, retrying ({reduced} tok/paper)")
        contexts, _, _ = await _build_paper_maps(paper_ids, db, reduced)
        text, provider = await _run_comparison(
            paper_ids, contexts, title_map, llm, settings.COMPARISON_TIMEOUT_SECONDS,
        )

    logger.info(f"Compared {len(paper_ids)} papers using {provider.value}")
    comparison_table = _build_comparison_rows(text, paper_ids, titles)
    return {
        "comparison": text,
        "comparison_table": comparison_table,
        "paper_ids": paper_ids,
        "paper_titles": titles,
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

