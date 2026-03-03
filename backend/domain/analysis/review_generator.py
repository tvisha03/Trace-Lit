
from __future__ import annotations

from typing import AsyncGenerator, Tuple

from infrastructure.llm.fallback_chain import FallbackChain
from domain.generation.prompts import SYSTEM_PROMPT, LITERATURE_REVIEW_PROMPT_TEMPLATE, build_context_block
from shared.enums import LLMProvider
from shared.logger import get_logger

logger = get_logger(__name__)


def _build_review_prompt(chunks_by_paper: dict[str, list]) -> str:
    context_parts = []
    for paper_id, chunks in chunks_by_paper.items():
        block = build_context_block(chunks)
        context_parts.append(f"--- Paper {paper_id} ---\n{block}")
    combined_context = "\n\n".join(context_parts)
    return LITERATURE_REVIEW_PROMPT_TEMPLATE.format(context=combined_context)


async def generate_review(
    chunks_by_paper: dict[str, list],
    llm: FallbackChain,
) -> tuple[str, LLMProvider]:
    user_prompt = _build_review_prompt(chunks_by_paper)

    response_text, provider, _ = await llm.generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )

    logger.info(f"Generated literature review using {provider.value}")
    return response_text, provider


async def stream_review(
    chunks_by_paper: dict[str, list],
    llm: FallbackChain,
) -> AsyncGenerator[Tuple[str, LLMProvider], None]:
    user_prompt = _build_review_prompt(chunks_by_paper)

    async for token, provider_obj in llm.generate_streaming(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
    ):
        yield (token, provider_obj)

