
from typing import Any

from infrastructure.llm.fallback_chain import FallbackChain
from shared.logger import get_logger

logger = get_logger(__name__)

CONTRIBUTION_PROMPT = """You are an academic paper analysis assistant.
Given the following paper sections, extract the paper's contributions in this exact JSON format.
For each field, also include the paragraph_id ([P#]) from which the information was extracted.

{
  "problem": {"text": "...", "paragraph_id": "P#"},
  "method": {"text": "...", "paragraph_id": "P#"},
  "dataset": {"text": "...", "paragraph_id": "P#"},
  "metrics": {"text": "...", "paragraph_id": "P#"},
  "results": {"text": "...", "paragraph_id": "P#"}
}

If a field is not found, set text to "Not mentioned" and paragraph_id to null.
Respond ONLY with valid JSON — no markdown fences, no explanation."""

async def extract_contributions(
    context: str,
    llm: FallbackChain,
) -> dict[str, Any]:
    prompt = f"{CONTRIBUTION_PROMPT}\n\nPaper context:\n{context}"

    response_text, provider, _ = await llm.generate(
        system_prompt="You are a precise academic paper analyst. Output only valid JSON.",
        user_prompt=prompt,
        temperature=0.1,
    )

    import json
    try:
        cleaned = response_text.strip().strip("`").strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse contribution JSON from {provider.value}")
        return {
            "problem": {"text": "Extraction failed", "paragraph_id": None},
            "method": {"text": "Extraction failed", "paragraph_id": None},
            "dataset": {"text": "Extraction failed", "paragraph_id": None},
            "metrics": {"text": "Extraction failed", "paragraph_id": None},
            "results": {"text": "Extraction failed", "paragraph_id": None},
        }
