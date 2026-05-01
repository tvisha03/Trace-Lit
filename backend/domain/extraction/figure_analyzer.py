import asyncio
import gc
from pathlib import Path
from dataclasses import dataclass

import psutil

from shared.logger import get_logger
from shared.constants import (
    FIGURE_DESCRIPTION_MAX_TOKENS,
    FIGURE_ANALYSIS_TIMEOUT,
)
from shared.enums import LLMProvider
from app.config import get_settings
from domain.extraction.pdf_processor import ExtractedFigure
from domain.generation.prompts import FIGURE_ANALYSIS_PROMPT

logger = get_logger(__name__)
_vision_semaphore: asyncio.Semaphore | None = None

# Abort the whole batch run after this many figures fail in a row.
# Protects against wasting time when every cloud provider is rate-limited.
_MAX_CONSECUTIVE_FAILURES = 3

# Gemini free-tier ceiling used to calculate the correct inter-batch sleep.
# Formula: sleep = (60s * batch_size) / RPM_limit
# e.g. batch_size=2, RPM=10 → 12s between batches to stay under 10 RPM.
_GEMINI_VISION_RPM = 10


def _get_vision_semaphore() -> asyncio.Semaphore:
    """Return (or lazily create) the global vision concurrency semaphore."""
    global _vision_semaphore
    if _vision_semaphore is None:
        _vision_semaphore = asyncio.Semaphore(get_settings().ADAPTIVE_FIGURE_CONCURRENCY)
    return _vision_semaphore


@dataclass
class AnalyzedFigure:
    image_path: str
    page_number: int
    figure_type: str
    description: str
    bbox: tuple[float, float, float, float] | None = None
    caption: str = ""

def _parse_vision_response(raw: str) -> tuple[str, str]:
    figure_type = "unknown"
    description = raw.strip()

    lines = raw.strip().split("\n")
    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("TYPE:"):
            figure_type = stripped[5:].strip().lower()
        elif stripped.upper().startswith("DESCRIPTION:"):
            description = stripped[12:].strip()

    if not description:
        description = raw.strip()

    return figure_type, description

_MIME_MAP = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}

def _read_image(img_path: Path) -> tuple[bytes, str] | None:
    if not img_path.exists():
        logger.warning(f"Figure image not found: {img_path}")
        return None
    image_data = img_path.read_bytes()
    if len(image_data) < 100:
        logger.warning(f"Figure image too small, skipping: {img_path}")
        return None
    suffix = img_path.suffix.lower().lstrip(".")
    mime_type = _MIME_MAP.get(suffix, "image/png")
    return image_data, mime_type

async def _call_vision(llm_chain, image_data: bytes, mime_type: str) -> tuple[str, object]:
    return await asyncio.wait_for(
        llm_chain.analyze_image(
            image_data=image_data,
            mime_type=mime_type,
            prompt=FIGURE_ANALYSIS_PROMPT,
            max_tokens=FIGURE_DESCRIPTION_MAX_TOKENS,
        ),
        timeout=FIGURE_ANALYSIS_TIMEOUT,
    )

async def _analyze_single_figure(
    figure: ExtractedFigure,
    llm_chain,
) -> AnalyzedFigure | None:
    async with _get_vision_semaphore():
        img_path = Path(figure.image_path)
        payload = _read_image(img_path)
        if payload is None:
            return None

        image_data, mime_type = payload
        try:
            raw_response, provider = await _call_vision(llm_chain, image_data, mime_type)
            figure_type, description = _parse_vision_response(raw_response)

            logger.info(
                f"Analyzed figure page={figure.page_number} "
                f"type={figure_type} via {provider.__class__.__name__}"
            )

            return AnalyzedFigure(
                image_path=str(img_path),
                page_number=figure.page_number,
                figure_type=figure_type,
                description=description,
                bbox=figure.bbox,
                caption=getattr(figure, "caption", "") or "",
            )

        except asyncio.TimeoutError:
            logger.warning(
                f"Figure analysis timed out for {img_path} "
                f"(limit={FIGURE_ANALYSIS_TIMEOUT}s)"
            )
            return None
        except NotImplementedError:
            logger.warning("No vision-capable LLM provider available")
            return None
        except Exception as exc:
            logger.error(f"Figure analysis failed for {img_path}: {exc}")
            return None


def _is_ram_under_pressure() -> bool:
    """Return True when system RAM usage exceeds the configured threshold."""
    try:
        used_pct = psutil.virtual_memory().percent / 100.0
        return used_pct >= get_settings().MEMORY_PRESSURE_THRESHOLD
    except Exception:
        return False


def _check_early_abort(consecutive_failures: int) -> str | None:
    """Return an abort reason if figure analysis should stop, or None to continue."""
    if _is_ram_under_pressure():
        return (
            f"RAM pressure above threshold "
            f"({psutil.virtual_memory().percent:.0f}% used)"
        )
    if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
        return (
            f"{consecutive_failures} consecutive failures — "
            "cloud providers appear rate-limited"
        )
    return None


def _process_batch_results(
    results: list,
) -> tuple[list[AnalyzedFigure], int]:
    """Split gather results into successes and a failure count."""
    successes: list[AnalyzedFigure] = []
    failures = 0
    for result in results:
        if isinstance(result, AnalyzedFigure):
            successes.append(result)
        elif isinstance(result, Exception):
            logger.error(f"Unexpected figure analysis error: {result}")
            failures += 1
        else:
            failures += 1
    return successes, failures


async def analyze_figures(
    figures: list[ExtractedFigure],
    llm_chain,
) -> list[AnalyzedFigure]:
    if not figures:
        return []

    settings = get_settings()
    batch_size = settings.ADAPTIVE_FIGURE_CONCURRENCY
    analyzed: list[AnalyzedFigure] = []
    consecutive_failures = 0

    for batch_start in range(0, len(figures), batch_size):
        abort_reason = _check_early_abort(consecutive_failures)
        if abort_reason:
            logger.warning(f"Figure analysis stopped: {abort_reason}")
            break

        batch = figures[batch_start:batch_start + batch_size]
        tasks = [_analyze_single_figure(fig, llm_chain) for fig in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        batch_analyzed, batch_failed = _process_batch_results(results)
        analyzed.extend(batch_analyzed)
        # Reset failure streak on any success; accumulate only on full-batch failures.
        consecutive_failures = 0 if batch_analyzed else (consecutive_failures + batch_failed)

        # Release image byte buffers before loading the next batch.
        del tasks, results
        gc.collect()

        remaining = len(figures) - (batch_start + len(batch))
        if remaining > 0:
            # Only throttle when Gemini is available and its rate limit applies.
            # When Gemini is in cooldown we fall back to local Ollama, which has
            # no API rate limit — adding a delay here only wastes time.
            gemini_cooldown = (
                llm_chain.rate_monitor.cooldown_remaining(LLMProvider.GEMINI)
                if hasattr(llm_chain, "rate_monitor")
                else 0.0
            )
            if gemini_cooldown <= 0:
                # sleep = (60s × batch_size) / RPM_limit
                # e.g. batch_size=2, RPM=10 → 12 s between batches
                inter_batch_sleep = (60.0 * batch_size) / _GEMINI_VISION_RPM
                await asyncio.sleep(inter_batch_sleep)

    logger.info(f"Analyzed {len(analyzed)}/{len(figures)} figures successfully")
    return analyzed
