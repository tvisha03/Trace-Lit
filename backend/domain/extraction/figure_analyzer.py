import asyncio
from pathlib import Path
from dataclasses import dataclass

from shared.logger import get_logger
from shared.constants import (
    FIGURE_MAX_CONCURRENT_ANALYSIS,
    FIGURE_DESCRIPTION_MAX_TOKENS,
    FIGURE_ANALYSIS_TIMEOUT,
)
from domain.extraction.pdf_processor import ExtractedFigure

logger = get_logger(__name__)

FIGURE_ANALYSIS_PROMPT = (
    "You are an expert academic research analyst. "
    "Analyze this figure/chart from a research paper. Provide:\n"
    "1. A concise description of what the figure shows\n"
    "2. The type of visualization (bar chart, line graph, scatter plot, "
    "flowchart, diagram, table, photograph, etc.)\n"
    "3. Key data points, trends, or relationships visible\n"
    "4. Any axis labels, legends, or annotations present\n\n"
    "Format your response as:\n"
    "TYPE: <figure_type>\n"
    "DESCRIPTION: <detailed_description>\n"
    "Keep the description under 200 words and focused on factual observations."
)


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
    semaphore: asyncio.Semaphore,
) -> AnalyzedFigure | None:
    async with semaphore:
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


async def analyze_figures(
    figures: list[ExtractedFigure],
    llm_chain,
) -> list[AnalyzedFigure]:
    if not figures:
        return []

    semaphore = asyncio.Semaphore(FIGURE_MAX_CONCURRENT_ANALYSIS)

    tasks = [
        _analyze_single_figure(fig, llm_chain, semaphore)
        for fig in figures
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    analyzed: list[AnalyzedFigure] = []
    for result in results:
        if isinstance(result, AnalyzedFigure):
            analyzed.append(result)
        elif isinstance(result, Exception):
            logger.error(f"Unexpected figure analysis error: {result}")

    logger.info(f"Analyzed {len(analyzed)}/{len(figures)} figures successfully")
    return analyzed
