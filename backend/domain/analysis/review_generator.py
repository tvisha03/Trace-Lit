
from infrastructure.llm.fallback_chain import FallbackChain
from domain.generation.prompts import SYSTEM_PROMPT, GAP_ANALYSIS_PROMPT_TEMPLATE, build_context_block
from shared.enums import LLMProvider
from shared.logger import get_logger

logger = get_logger(__name__)

async def generate_review(
    chunks_by_paper: dict[str, list],
    llm: FallbackChain,
) -> tuple[str, LLMProvider]:
    context_parts = []
    for paper_id, chunks in chunks_by_paper.items():
        block = build_context_block(chunks)
        context_parts.append(f"--- Paper {paper_id} ---\n{block}")

    combined_context = "\n\n".join(context_parts)
    user_prompt = GAP_ANALYSIS_PROMPT_TEMPLATE.format(context=combined_context)

    response_text, provider, _ = await llm.generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )

    logger.info(f"Generated review using {provider.value}")
    return response_text, provider
