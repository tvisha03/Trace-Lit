import asyncio
import hashlib
import json
import re
from pathlib import Path
from dataclasses import dataclass

from shared.logger import get_logger
from shared.constants import (
    FIGURE_MAX_CONCURRENT_ANALYSIS,
    FIGURE_DESCRIPTION_MAX_TOKENS,
    FIGURE_ANALYSIS_TIMEOUT,
    FIGURE_BATCH_SIZE,
)
from domain.extraction.pdf_processor import ExtractedFigure
from domain.generation.prompts import FIGURE_ANALYSIS_PROMPT, FIGURE_BATCH_ANALYSIS_PROMPT

logger = get_logger(__name__)

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


def _cache_path(img_path: Path) -> Path:
    """Return the sidecar cache file path for a figure image."""
    return img_path.with_suffix(img_path.suffix + ".analysis.json")


def _image_hash(image_data: bytes) -> str:
    """Fast MD5 hash of image bytes for cache invalidation."""
    return hashlib.md5(image_data).hexdigest()


def _load_from_cache(
    img_path: Path, image_data: bytes, figure: ExtractedFigure,
) -> AnalyzedFigure | None:
    """Load a cached figure analysis result if valid."""
    cache_file = _cache_path(img_path)
    if not cache_file.exists():
        return None
    try:
        cached = json.loads(cache_file.read_text())
        if cached.get("image_hash") != _image_hash(image_data):
            return None
        logger.info(f"Figure cache hit: {img_path.name}")
        return AnalyzedFigure(
            image_path=str(img_path),
            page_number=figure.page_number,
            figure_type=cached["figure_type"],
            description=cached["description"],
            bbox=tuple(cached["bbox"]) if cached.get("bbox") else None,
            caption=cached.get("caption", ""),
        )
    except Exception:
        return None


def _save_to_cache(
    img_path: Path, image_data: bytes, analyzed: AnalyzedFigure,
) -> None:
    """Persist figure analysis result to a sidecar cache file."""
    try:
        cache_file = _cache_path(img_path)
        cache_file.write_text(json.dumps({
            "image_hash": _image_hash(image_data),
            "figure_type": analyzed.figure_type,
            "description": analyzed.description,
            "bbox": list(analyzed.bbox) if analyzed.bbox else None,
            "caption": analyzed.caption,
        }))
    except Exception as exc:
        logger.warning(f"Failed to write figure cache for {img_path}: {exc}")

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
    semaphore: asyncio.Semaphore,
) -> AnalyzedFigure | None:
    async with semaphore:
        img_path = Path(figure.image_path)
        payload = _read_image(img_path)
        if payload is None:
            return None

        image_data, mime_type = payload

        # Check file-based cache before calling expensive vision API
        cached = _load_from_cache(img_path, image_data, figure)
        if cached is not None:
            return cached

        try:
            raw_response, provider = await _call_vision(llm_chain, image_data, mime_type)
            figure_type, description = _parse_vision_response(raw_response)

            logger.info(
                f"Analyzed figure page={figure.page_number} "
                f"type={figure_type} via {provider.__class__.__name__}"
            )

            result = AnalyzedFigure(
                image_path=str(img_path),
                page_number=figure.page_number,
                figure_type=figure_type,
                description=description,
                bbox=figure.bbox,
                caption=getattr(figure, "caption", "") or "",
            )

            # Cache for re-processing scenarios — saves API calls and time
            _save_to_cache(img_path, image_data, result)

            return result

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

async def analyze_figures(
    figures: list[ExtractedFigure],
    llm_chain,
) -> list[AnalyzedFigure]:
    if not figures:
        return []

    # ------------------------------------------------------------------
    # Phase 1: Resolve cache hits — no API calls needed for these
    # ------------------------------------------------------------------
    cached_results: dict[int, AnalyzedFigure] = {}
    uncached: list[tuple[int, ExtractedFigure, bytes, str]] = []

    for idx, fig in enumerate(figures):
        img_path = Path(fig.image_path)
        payload = _read_image(img_path)
        if payload is None:
            continue
        image_data, mime_type = payload
        hit = _load_from_cache(img_path, image_data, fig)
        if hit is not None:
            cached_results[idx] = hit
        else:
            uncached.append((idx, fig, image_data, mime_type))

    # ------------------------------------------------------------------
    # Phase 2: Process uncached figures — batch when beneficial
    # ------------------------------------------------------------------
    api_results: dict[int, AnalyzedFigure] = {}

    if len(uncached) > FIGURE_BATCH_SIZE:
        # Batch mode: group figures and send multi-image API calls
        api_results = await _analyze_figures_batched(uncached, llm_chain)
    elif uncached:
        # Few figures: use individual analysis (simpler, more reliable)
        semaphore = asyncio.Semaphore(FIGURE_MAX_CONCURRENT_ANALYSIS)
        tasks = [
            _analyze_single_figure(fig, llm_chain, semaphore)
            for _, fig, _, _ in uncached
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for (idx, _fig, _data, _mime), result in zip(uncached, results):
            if isinstance(result, AnalyzedFigure):
                api_results[idx] = result
            elif isinstance(result, Exception):
                logger.error(f"Unexpected figure analysis error: {result}")

    # ------------------------------------------------------------------
    # Phase 3: Merge and return in original order
    # ------------------------------------------------------------------
    all_results = {**cached_results, **api_results}
    analyzed = [all_results[i] for i in sorted(all_results.keys())]

    logger.info(
        f"Analyzed {len(analyzed)}/{len(figures)} figures "
        f"(cache={len(cached_results)}, api={len(api_results)})"
    )
    return analyzed


def _parse_batch_response(
    raw: str, count: int,
) -> list[tuple[str, str]]:
    """Parse a multi-figure batch response into per-figure (type, description) pairs.

    Expected format:
        ---FIGURE 1---
        TYPE: bar chart
        DESCRIPTION: Shows the trend ...
        ---FIGURE 2---
        ...

    Returns a list of (figure_type, description) tuples, one per figure.
    Falls back gracefully if parsing fails.
    """
    # Split on ---FIGURE N--- markers (case insensitive)
    blocks = re.split(r"---\s*FIGURE\s+\d+\s*---", raw, flags=re.IGNORECASE)
    # First element is any text before the first marker (usually empty)
    blocks = [b.strip() for b in blocks if b.strip()]

    results: list[tuple[str, str]] = []
    for block in blocks:
        fig_type, desc = _parse_vision_response(block)
        results.append((fig_type, desc))

    return results


async def _analyze_figures_batched(
    uncached: list[tuple[int, ExtractedFigure, bytes, str]],
    llm_chain,
) -> dict[int, AnalyzedFigure]:
    """Analyze uncached figures in batches of FIGURE_BATCH_SIZE.

    Sends multi-image prompts to reduce API calls from N to ceil(N/batch_size).
    Falls back to individual analysis if batch parsing yields wrong count.
    """
    results: dict[int, AnalyzedFigure] = {}

    # Group into batches
    batches: list[list[tuple[int, ExtractedFigure, bytes, str]]] = []
    for i in range(0, len(uncached), FIGURE_BATCH_SIZE):
        batches.append(uncached[i : i + FIGURE_BATCH_SIZE])

    semaphore = asyncio.Semaphore(FIGURE_MAX_CONCURRENT_ANALYSIS)

    for batch in batches:
        batch_results = await _analyze_batch(batch, llm_chain, semaphore)
        results.update(batch_results)

    return results


async def _analyze_batch(
    batch: list[tuple[int, ExtractedFigure, bytes, str]],
    llm_chain,
    semaphore: asyncio.Semaphore,
) -> dict[int, AnalyzedFigure]:
    """Attempt a single batch API call; fall back to individual on failure."""
    async with semaphore:
        count = len(batch)
        images = [(img_data, mime) for _, _, img_data, mime in batch]
        prompt = FIGURE_BATCH_ANALYSIS_PROMPT.format(count=count)

        try:
            # Scale token budget with batch size
            max_tokens = FIGURE_DESCRIPTION_MAX_TOKENS * count
            raw_response, provider = await asyncio.wait_for(
                llm_chain.analyze_images_batch(
                    images=images,
                    prompt=prompt,
                    max_tokens=max_tokens,
                ),
                timeout=FIGURE_ANALYSIS_TIMEOUT * 1.5,
            )

            parsed = _parse_batch_response(raw_response, count)

            if len(parsed) == count:
                # Batch parse succeeded — build results
                batch_results: dict[int, AnalyzedFigure] = {}
                for (idx, fig, img_data, _mime), (fig_type, desc) in zip(batch, parsed):
                    img_path = Path(fig.image_path)
                    result = AnalyzedFigure(
                        image_path=str(img_path),
                        page_number=fig.page_number,
                        figure_type=fig_type,
                        description=desc,
                        bbox=fig.bbox,
                        caption=getattr(fig, "caption", "") or "",
                    )
                    _save_to_cache(img_path, img_data, result)
                    batch_results[idx] = result

                logger.info(
                    f"Batch analyzed {count} figures via {provider}"
                )
                return batch_results
            else:
                logger.warning(
                    f"Batch parse mismatch: expected {count}, got {len(parsed)}. "
                    f"Falling back to individual analysis."
                )

        except NotImplementedError:
            logger.info("No batch vision support — falling back to individual analysis")
        except asyncio.TimeoutError:
            logger.warning("Batch figure analysis timed out — falling back to individual")
        except Exception as exc:
            logger.warning(f"Batch figure analysis failed: {exc} — falling back")

    # Fallback: analyze individually
    return await _fallback_individual(batch, llm_chain, semaphore)


async def _fallback_individual(
    batch: list[tuple[int, ExtractedFigure, bytes, str]],
    llm_chain,
    semaphore: asyncio.Semaphore,
) -> dict[int, AnalyzedFigure]:
    """Analyze figures one-by-one as a fallback when batching fails."""
    results: dict[int, AnalyzedFigure] = {}
    tasks = [
        _analyze_single_figure(fig, llm_chain, semaphore)
        for _, fig, _, _ in batch
    ]
    outcomes = await asyncio.gather(*tasks, return_exceptions=True)
    for (idx, _fig, _data, _mime), outcome in zip(batch, outcomes):
        if isinstance(outcome, AnalyzedFigure):
            results[idx] = outcome
        elif isinstance(outcome, Exception):
            logger.error(f"Individual fallback figure error: {outcome}")
    return results
