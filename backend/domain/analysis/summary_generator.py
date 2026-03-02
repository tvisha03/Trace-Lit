"""TraceLit — On-Demand Paper Summary Generator.

Generates per-paper summaries on demand (not at upload time) to save compute.
Uses the existing LLM fallback chain.
"""

from typing import Dict, List, Optional

from loguru import logger


SUMMARY_SYSTEM_PROMPT = (
    "You are an expert academic paper summarizer. "
    "Create a concise, well-structured summary of the provided paper content. "
    "Focus on: the problem addressed, the proposed method/approach, key results, "
    "and main contributions. Write in third person, academic style. "
    "Cite source paragraphs with [P#] format where relevant."
)

SUMMARY_USER_TEMPLATE = """Summarize the following research paper content in 150-300 words.

Paper: {title}

Context:
{context}

Provide a clear, concise summary covering:
1. Problem/Motivation
2. Approach/Method
3. Key Results
4. Main Contribution

Use [P#] citations where appropriate."""


async def generate_paper_summary(
    title: str,
    paragraphs: List[Dict],
    llm_generate_fn=None,
) -> str:
    """Generate a summary for a single paper.

    Args:
        title: Paper title.
        paragraphs: Paper's paragraphs with paragraph_id, text, section.
        llm_generate_fn: Optional async fn(system_prompt, user_prompt) -> str.
                         If None, uses the default LLM fallback chain.

    Returns:
        Summary string.
    """
    if not paragraphs:
        return "No content available for summarization."

    # Build context from key sections
    context = _build_summary_context(paragraphs, max_paragraphs=15)

    user_prompt = SUMMARY_USER_TEMPLATE.format(title=title, context=context)

    if llm_generate_fn is None:
        llm_generate_fn = _default_llm_generate

    try:
        summary = await llm_generate_fn(SUMMARY_SYSTEM_PROMPT, user_prompt)
        logger.info("Generated summary for '{}' ({} chars)", title, len(summary))
        return summary.strip()
    except Exception as e:
        logger.error("Summary generation failed for '{}': {}", title, e)
        return "Summary generation failed. Please try again later."


async def _default_llm_generate(system_prompt: str, user_prompt: str) -> str:
    """Default LLM generation using the fallback chain."""
    from infrastructure.llm.fallback_chain import get_llm

    llm = get_llm()
    # Use generate with a minimal context to just get text back
    available = llm._get_available_providers()
    if not available:
        raise RuntimeError("No LLM providers available")

    for provider in available:
        try:
            response = await provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
            )
            return response
        except Exception:
            continue

    raise RuntimeError("All providers failed for summary generation")


def _build_summary_context(paragraphs: List[Dict], max_paragraphs: int = 15) -> str:
    """Build context prioritizing abstract, intro, method, results, conclusion."""
    priority_sections = [
        "abstract", "introduction", "method", "approach", "proposed",
        "experiment", "result", "evaluation", "conclusion", "discussion",
    ]

    def _section_priority(para: Dict) -> int:
        section = (para.get("section", "") or "").lower()
        for i, kw in enumerate(priority_sections):
            if kw in section:
                return len(priority_sections) - i
        return 0

    sorted_paras = sorted(paragraphs, key=_section_priority, reverse=True)
    selected = sorted_paras[:max_paragraphs]

    blocks = []
    for p in selected:
        pid = p.get("paragraph_id", "P?")
        section = p.get("section", "Unknown")
        text = p.get("text", "")
        blocks.append(f"[{pid}] (Section: {section})\n{text}")

    return "\n\n".join(blocks)
