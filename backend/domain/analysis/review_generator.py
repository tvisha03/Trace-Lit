
from __future__ import annotations

from typing import AsyncGenerator, Tuple

from infrastructure.llm.fallback_chain import FallbackChain
from domain.generation.prompts import (
    SYSTEM_PROMPT,
    LITERATURE_REVIEW_PROMPT_TEMPLATE,
    GAP_ANALYSIS_PROMPT_TEMPLATE,
    build_context_block,
)
from shared.enums import LLMProvider
from shared.logger import get_logger

logger = get_logger(__name__)


def _build_paper_header(
    paper_id: str,
    paper_titles: dict[str, str] | None = None,
) -> str:
    title = (paper_titles or {}).get(paper_id)
    if title:
        return f"--- Paper: {title} ---"
    return f"--- Paper {paper_id} ---"


def _build_review_prompt(
    chunks_by_paper: dict[str, list],
    paper_titles: dict[str, str] | None = None,
) -> str:
    context_parts = []
    for paper_id, chunks in chunks_by_paper.items():
        block = build_context_block(chunks)
        header = _build_paper_header(paper_id, paper_titles)
        context_parts.append(f"{header}\n{block}")
    combined_context = "\n\n".join(context_parts)
    return LITERATURE_REVIEW_PROMPT_TEMPLATE.format(context=combined_context)


def _build_gap_prompt(
    chunks_by_paper: dict[str, list],
    paper_titles: dict[str, str] | None = None,
) -> str:
    context_parts = []
    for paper_id, chunks in chunks_by_paper.items():
        block = build_context_block(chunks)
        header = _build_paper_header(paper_id, paper_titles)
        context_parts.append(f"{header}\n{block}")
    combined_context = "\n\n".join(context_parts)
    return GAP_ANALYSIS_PROMPT_TEMPLATE.format(context=combined_context)


async def generate_review(
    chunks_by_paper: dict[str, list],
    llm: FallbackChain,
    paper_titles: dict[str, str] | None = None,
) -> tuple[str, LLMProvider]:
    user_prompt = _build_review_prompt(chunks_by_paper, paper_titles)

    response_text, provider, _ = await llm.generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )

    logger.info(f"Generated literature review using {provider.value}")
    return response_text, provider


async def generate_gap_narrative(
    chunks_by_paper: dict[str, list],
    llm: FallbackChain,
    paper_titles: dict[str, str] | None = None,
) -> tuple[str, LLMProvider]:
    user_prompt = _build_gap_prompt(chunks_by_paper, paper_titles)

    response_text, provider, _ = await llm.generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )

    logger.info(f"Generated gap analysis narrative using {provider.value}")
    return response_text, provider


async def stream_review(
    chunks_by_paper: dict[str, list],
    llm: FallbackChain,
    paper_titles: dict[str, str] | None = None,
) -> AsyncGenerator[Tuple[str, LLMProvider], None]:
    user_prompt = _build_review_prompt(chunks_by_paper, paper_titles)

    async for token, provider_obj in llm.generate_streaming(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
    ):
        yield (token, provider_obj)

