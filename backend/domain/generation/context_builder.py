"""TraceLit — Context Assembly & Token Budget Management."""

from typing import Dict, List

from loguru import logger


# ============================================================
# Token Budget Configuration
# ============================================================

TOKEN_BUDGETS: Dict[str, Dict[str, int]] = {
    "gemini": {"context_window": 1_000_000, "max_context": 30_000, "max_output": 4_000},
    "groq":   {"context_window": 131_072,   "max_context": 20_000, "max_output": 4_000},
    "ollama": {"context_window": 8_192,      "max_context": 4_000,  "max_output": 2_000},
}

BUDGET_ALLOCATION = {
    "system_prompt": 500,
    "context": 2000,
    "history": 800,
    "response": 700,
}


def estimate_tokens(text: str) -> int:
    """Rough token estimate — 1 token ≈ 4 chars for English text."""
    return len(text) // 4


# ============================================================
# Context Formatting
# ============================================================

def format_context_block(paragraphs: List[Dict]) -> str:
    """Format retrieved paragraphs into an LLM-ready context block.

    Args:
        paragraphs: List of dicts with keys:
            paragraph_id, text, paper_title, section, page

    Returns:
        Formatted context string with [P#] identifiers.
    """
    if not paragraphs:
        return "No relevant context found in the provided papers."

    blocks = []
    for para in paragraphs:
        pid = para.get("paragraph_id", "P?")
        title = para.get("paper_title", "Unknown Paper")
        section = para.get("section", "Unknown Section")
        page = para.get("page", 0)
        text = para.get("text", "")
        block = (
            f"[{pid}] (Paper: {title}, Section: {section}, Page: {page})\n"
            f"{text}"
        )
        blocks.append(block)

    return "Context:\n" + "\n\n".join(blocks)


def trim_context_to_budget(paragraphs: List[Dict], provider: str) -> List[Dict]:
    """Keep only top-k paragraphs that fit within provider's token budget.

    Args:
        paragraphs: Relevance-ranked paragraph dicts.
        provider: Provider name ('gemini', 'groq', 'ollama').

    Returns:
        Trimmed list within budget.
    """
    budget = TOKEN_BUDGETS.get(provider, TOKEN_BUDGETS["gemini"])["max_context"]
    context_budget = budget - (
        BUDGET_ALLOCATION["system_prompt"]
        + BUDGET_ALLOCATION["history"]
        + BUDGET_ALLOCATION["response"]
    )

    selected: List[Dict] = []
    total_tokens = 0
    for para in paragraphs:
        chunk_tokens = estimate_tokens(para.get("text", ""))
        if total_tokens + chunk_tokens > context_budget:
            break
        selected.append(para)
        total_tokens += chunk_tokens

    if len(selected) < len(paragraphs):
        logger.debug(
            "Trimmed context from {} to {} paragraphs for {} (budget: {} tokens)",
            len(paragraphs), len(selected), provider, context_budget,
        )
    return selected


# ============================================================
# Conversation History
# ============================================================

def format_conversation_history(messages: List[Dict], max_turns: int = 5) -> str:
    """Format recent conversation history for LLM context.

    Args:
        messages: List of dicts with 'role' and 'content'.
        max_turns: Maximum recent exchanges to include.

    Returns:
        Formatted history string, or empty string if no history.
    """
    if not messages:
        return ""

    recent = messages[-(max_turns * 2):]
    lines = ["Previous conversation:"]
    for msg in recent:
        role = msg.get("role", "user").capitalize()
        content = msg.get("content", "")
        if role == "Assistant" and len(content) > 500:
            content = content[:500] + "..."
        lines.append(f"{role}: {content}")

    return "\n".join(lines)
