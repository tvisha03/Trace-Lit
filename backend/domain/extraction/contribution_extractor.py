import json
import re
from typing import Any

from infrastructure.llm.fallback_chain import FallbackChain
from domain.generation.prompts import CONTRIBUTION_PROMPT
from shared.logger import get_logger

logger = get_logger(__name__)

_JSON_BLOCK_RE = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", re.DOTALL)

_REQUIRED_FIELDS = ("problem", "method", "dataset", "metrics", "results")

_EMPTY_FIELD: dict[str, Any] = {"text": "Not mentioned", "paragraph_id": None}

def _parse_json_response(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    match = _JSON_BLOCK_RE.search(text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None

def _validate_contributions(data: dict[str, Any]) -> dict[str, Any]:
    validated: dict[str, Any] = {}
    for field in _REQUIRED_FIELDS:
        value = data.get(field)
        if isinstance(value, dict) and "text" in value:
            validated[field] = {
                "text": str(value["text"]),
                "paragraph_id": value.get("paragraph_id"),
            }
        elif isinstance(value, str):
            validated[field] = {"text": value, "paragraph_id": None}
        else:
            validated[field] = dict(_EMPTY_FIELD)
    return validated

async def extract_contributions(
    context: str,
    llm: FallbackChain,
) -> dict[str, Any]:
    prompt = f"{CONTRIBUTION_PROMPT}\n\nPaper context:\n{context}"

    max_attempts = 2
    last_raw = ""

    for attempt in range(1, max_attempts + 1):
        response_text, provider, _ = await llm.generate(
            system_prompt="You are a precise academic paper analyst. Output only valid JSON.",
            user_prompt=prompt,
            temperature=0.1,
            max_tokens=2048,
        )
        last_raw = response_text

        parsed = _parse_json_response(response_text)
        if parsed and isinstance(parsed, dict):
            result = _validate_contributions(parsed)
            has_content = any(
                result[f]["text"] not in ("Not mentioned", "Extraction failed")
                for f in _REQUIRED_FIELDS
            )
            if has_content:
                logger.info(
                    f"Extracted contributions from {provider.value} "
                    f"(attempt {attempt})"
                )
                return result

        if attempt < max_attempts:
            logger.warning(
                f"Contribution JSON parse attempt {attempt} failed "
                f"from {provider.value}, retrying..."
            )

    logger.warning(
        f"Failed to parse contribution JSON after {max_attempts} attempts. "
        f"Raw response (first 300 chars): {last_raw[:300]}"
    )
    return {field: dict(_EMPTY_FIELD) for field in _REQUIRED_FIELDS}

