"""TraceLit — Literature Review Generator.

Generates structured literature reviews from multiple papers with
proper citations and thematic organization.
"""

from typing import AsyncIterator, Dict, List, Optional

from loguru import logger


LIT_REVIEW_SYSTEM_PROMPT = """You are an expert academic literature review writer.
Write a comprehensive literature review based on the provided research papers.
Follow these guidelines:

1. **Thematic Organization**: Group related findings across papers by theme, not paper-by-paper.
2. **Critical Analysis**: Compare and contrast approaches, methods, and findings.
3. **Citations**: ALWAYS cite every factual claim with [P#] paragraph IDs from the context.
4. **Academic Tone**: Third person, formal academic writing style.
5. **Transitions**: Smooth transitions between themes and papers.
6. **Structure**: Include clear topic sentences and logical flow.

Format the review with clear section headings using markdown ## syntax."""


LIT_REVIEW_USER_TEMPLATE = """Write a literature review covering the following papers and their content.

Papers included:
{paper_list}

Context from all papers:
{context}

Focus the review on:
{focus_area}

Write a well-structured literature review of approximately 500-800 words. 
Cite every factual claim with [P#] format. Group findings thematically."""


async def generate_literature_review(
    papers_data: List[Dict],
    focus_area: str = "the main contributions, methods, and findings of these papers",
    llm_generate_fn=None,
) -> str:
    """Generate a literature review from multiple papers.

    Args:
        papers_data: List of dicts with keys:
            - paper_id, title, paragraphs (list of paragraph dicts)
        focus_area: Optional focus/theme for the review.
        llm_generate_fn: Optional async fn(system_prompt, user_prompt) -> str.

    Returns:
        Literature review text with citations.
    """
    if not papers_data:
        return "No papers available for literature review generation."

    paper_list = "\n".join(
        f"- {pd.get('title', 'Unknown')} (ID: {pd.get('paper_id', '?')})"
        for pd in papers_data
    )

    context = _build_multi_paper_context(papers_data, max_per_paper=10)

    user_prompt = LIT_REVIEW_USER_TEMPLATE.format(
        paper_list=paper_list,
        context=context,
        focus_area=focus_area,
    )

    if llm_generate_fn is None:
        llm_generate_fn = _default_llm_generate

    try:
        review = await llm_generate_fn(LIT_REVIEW_SYSTEM_PROMPT, user_prompt)
        logger.info("Generated literature review ({} chars, {} papers)", len(review), len(papers_data))
        return review.strip()
    except Exception as e:
        logger.error("Literature review generation failed: {}", e)
        return "Literature review generation failed. Please try again later."


async def stream_literature_review(
    papers_data: List[Dict],
    focus_area: str = "the main contributions, methods, and findings of these papers",
    llm_stream_fn=None,
) -> AsyncIterator[str]:
    """Stream a literature review for SSE endpoints.

    Args:
        papers_data: List of dicts with paper_id, title, paragraphs.
        focus_area: Optional focus/theme.
        llm_stream_fn: Optional async generator fn(system_prompt, user_prompt).

    Yields:
        Text chunks of the literature review.
    """
    if not papers_data:
        yield "No papers available for literature review generation."
        return

    paper_list = "\n".join(
        f"- {pd.get('title', 'Unknown')} (ID: {pd.get('paper_id', '?')})"
        for pd in papers_data
    )

    context = _build_multi_paper_context(papers_data, max_per_paper=10)

    user_prompt = LIT_REVIEW_USER_TEMPLATE.format(
        paper_list=paper_list,
        context=context,
        focus_area=focus_area,
    )

    if llm_stream_fn is None:
        llm_stream_fn = _default_llm_stream

    try:
        async for chunk in llm_stream_fn(LIT_REVIEW_SYSTEM_PROMPT, user_prompt):
            yield chunk
    except Exception as e:
        logger.error("Literature review streaming failed: {}", e)
        yield "\n\n[Error: Literature review generation failed]"


def _build_multi_paper_context(papers_data: List[Dict], max_per_paper: int = 10) -> str:
    """Build context from multiple papers."""
    blocks = []

    for pd in papers_data:
        paper_id = pd.get("paper_id", "?")
        title = pd.get("title", "Unknown")
        paragraphs = pd.get("paragraphs", [])

        # Prioritize key sections
        priority_sections = [
            "abstract", "introduction", "method", "approach",
            "experiment", "result", "evaluation", "conclusion",
        ]

        def _priority(para):
            section = (para.get("section", "") or "").lower()
            for i, kw in enumerate(priority_sections):
                if kw in section:
                    return len(priority_sections) - i
            return 0

        sorted_paras = sorted(paragraphs, key=_priority, reverse=True)
        selected = sorted_paras[:max_per_paper]

        blocks.append(f"=== Paper: {title} (ID: {paper_id}) ===")
        for p in selected:
            pid = p.get("paragraph_id", "P?")
            section = p.get("section", "Unknown")
            text = p.get("text", "")
            blocks.append(f"[{pid}] (Section: {section})\n{text}")
        blocks.append("")

    return "\n\n".join(blocks)


async def _default_llm_generate(system_prompt: str, user_prompt: str) -> str:
    """Default LLM generation using the fallback chain."""
    from infrastructure.llm.fallback_chain import get_llm

    llm = get_llm()
    available = llm._get_available_providers()
    if not available:
        raise RuntimeError("No LLM providers available")

    for provider in available:
        try:
            response = await provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.4,
            )
            return response
        except Exception:
            continue

    raise RuntimeError("All providers failed for literature review")


async def _default_llm_stream(system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
    """Default LLM streaming using the fallback chain."""
    from infrastructure.llm.fallback_chain import get_llm

    llm = get_llm()
    available = llm._get_available_providers()
    if not available:
        raise RuntimeError("No LLM providers available")

    for provider in available:
        try:
            async for chunk in provider.stream(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.4,
            ):
                yield chunk
            return
        except Exception:
            continue

    raise RuntimeError("All providers failed for streaming literature review")
