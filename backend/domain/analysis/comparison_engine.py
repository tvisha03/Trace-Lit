"""TraceLit — Comparison Table Generator.

Uses LLM to extract structured contributions from each paper:
problem, method, dataset, metrics, results — each with a source paragraph_id.
"""

import json
from typing import Any, Dict, List, Optional

from loguru import logger


# ============================================================
# Extraction Prompt
# ============================================================

COMPARISON_EXTRACTION_PROMPT = """You are analyzing a research paper. Extract the following structured information from the provided context.

For each field, provide:
1. A concise description (1-3 sentences)
2. The paragraph ID [P#] that is the primary source for this information

If a field cannot be determined from the context, write "Not specified" for the value and leave source empty.

Output ONLY valid JSON matching this exact structure:
{
    "problem": {"value": "...", "source": "P#"},
    "method": {"value": "...", "source": "P#"},
    "dataset": {"value": "...", "source": "P#"},
    "metrics": {"value": "...", "source": "P#"},
    "results": {"value": "...", "source": "P#"}
}

Context from the paper:
"""


def build_extraction_context(paragraphs: List[Dict], max_paragraphs: int = 20) -> str:
    """Build context string from paper paragraphs for LLM extraction.

    Prioritizes: Abstract, Introduction, Method*, Experiment*, Results*, Conclusion.
    """
    priority_keywords = [
        "abstract", "introduction", "method", "approach", "proposed",
        "experiment", "result", "evaluation", "dataset", "conclusion",
    ]

    def _priority_score(para: Dict) -> int:
        section = (para.get("section", "") or "").lower()
        score = 0
        for i, kw in enumerate(priority_keywords):
            if kw in section:
                score = len(priority_keywords) - i
                break
        return score

    sorted_paras = sorted(paragraphs, key=_priority_score, reverse=True)
    selected = sorted_paras[:max_paragraphs]

    blocks = []
    for p in selected:
        pid = p.get("paragraph_id", "P?")
        section = p.get("section", "Unknown")
        text = p.get("text", "")
        blocks.append(f"[{pid}] (Section: {section})\n{text}")

    return "\n\n".join(blocks)


async def extract_paper_contributions(
    paper_id: str,
    paragraphs: List[Dict],
    llm_generate_fn,
) -> Dict[str, Any]:
    """Extract structured contributions from a single paper.

    Args:
        paper_id: Paper identifier.
        paragraphs: Paper's paragraphs with paragraph_id, text, section.
        llm_generate_fn: Async function(system_prompt, user_prompt) -> str.

    Returns:
        Dict with keys: problem, method, dataset, metrics, results,
        each containing 'value' and 'source'.
    """
    context = build_extraction_context(paragraphs)
    user_prompt = COMPARISON_EXTRACTION_PROMPT + context

    system_prompt = (
        "You are a precise academic paper analyzer. "
        "Extract structured information and always cite source paragraph IDs. "
        "Return ONLY valid JSON — no markdown, no explanation."
    )

    try:
        response_text = await llm_generate_fn(system_prompt, user_prompt)

        # Strip markdown code fences if present
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        result = json.loads(cleaned)

        # Validate structure
        fields = ["problem", "method", "dataset", "metrics", "results"]
        validated = {}
        for f in fields:
            entry = result.get(f, {})
            if isinstance(entry, dict):
                validated[f] = {
                    "value": entry.get("value", "Not specified"),
                    "source": entry.get("source", ""),
                }
            elif isinstance(entry, str):
                validated[f] = {"value": entry, "source": ""}
            else:
                validated[f] = {"value": "Not specified", "source": ""}

        logger.info("Extracted contributions for paper {}", paper_id)
        return validated

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse LLM extraction for {}: {}", paper_id, e)
        return _empty_contributions()
    except Exception as e:
        logger.error("Contribution extraction failed for {}: {}", paper_id, e)
        return _empty_contributions()


async def generate_comparison_table(
    paper_contributions: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Generate a comparison table from multiple papers' contributions.

    Args:
        paper_contributions: Dict mapping paper_id to contribution data.

    Returns:
        List of row dicts suitable for frontend rendering.
    """
    fields = ["problem", "method", "dataset", "metrics", "results"]
    rows = []

    for field in fields:
        row = {"field": field, "papers": {}}
        for paper_id, contributions in paper_contributions.items():
            entry = contributions.get(field, {"value": "Not specified", "source": ""})
            row["papers"][paper_id] = {
                "value": entry.get("value", "Not specified"),
                "source": entry.get("source", ""),
            }
        rows.append(row)

    return rows


def _empty_contributions() -> Dict[str, Any]:
    """Return empty contribution structure."""
    fields = ["problem", "method", "dataset", "metrics", "results"]
    return {f: {"value": "Not specified", "source": ""} for f in fields}
