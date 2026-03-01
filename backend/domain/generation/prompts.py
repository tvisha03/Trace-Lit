"""TraceLit — Prompt Assembly (main entry point).

Composes system + user prompts from modular sub-components:
  - system_prompts  : constants, sanitize_user_input
  - context_builder : format_context_block, trim_context_to_budget,
                      format_conversation_history, estimate_tokens
  - citation_utils  : extract_citations, validate_citations,
                      remove_invalid_citations
"""

from typing import Dict, List, Optional, Tuple

from loguru import logger

# Re-export the full public API for backward compatibility
from domain.generation.citation_utils import (  # noqa: F401
    extract_citations,
    remove_invalid_citations,
    validate_citations,
)
from domain.generation.context_builder import (  # noqa: F401
    TOKEN_BUDGETS,
    BUDGET_ALLOCATION,
    estimate_tokens,
    format_context_block,
    format_conversation_history,
    trim_context_to_budget,
)
from domain.generation.system_prompts import (  # noqa: F401
    COMPARISON_PROMPT_ADDITION,
    REINFORCEMENT,
    SYSTEM_PROMPT,
    sanitize_user_input,
)


def assemble_prompt(
    query: str,
    context_paragraphs: List[Dict],
    conversation_history: Optional[List[Dict]] = None,
    provider: str = "gemini",
    is_comparison: bool = False,
    max_turns: int = 5,
) -> Tuple[str, str]:
    """Build the complete (system_prompt, user_prompt) tuple for the LLM.

    Args:
        query: Sanitized user question.
        context_paragraphs: Relevance-ranked paragraph dicts from retrieval.
        conversation_history: Previous messages in this session.
        provider: LLM provider name for budget trimming.
        is_comparison: Whether this is a multi-paper comparison query.
        max_turns: Max conversation turns to include.

    Returns:
        Tuple of (system_prompt, user_prompt).
    """
    system = SYSTEM_PROMPT
    if is_comparison:
        system += COMPARISON_PROMPT_ADDITION
    system += REINFORCEMENT

    trimmed = trim_context_to_budget(context_paragraphs, provider)
    context_block = format_context_block(trimmed)

    history = ""
    if conversation_history:
        history = format_conversation_history(conversation_history, max_turns)

    parts = [context_block]
    if history:
        parts.append(history)
    parts.append(f"Question: {query}")
    parts.append(
        "Answer the question using ONLY the context above. "
        "Cite every factual sentence with [P#] format."
    )

    user_prompt = "\n\n".join(parts)

    logger.debug(
        "Prompt assembled: system={} tokens, user={} tokens, provider={}, paragraphs={}",
        estimate_tokens(system),
        estimate_tokens(user_prompt),
        provider,
        len(trimmed),
    )

    return system, user_prompt

