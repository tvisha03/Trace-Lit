"""
PDF Exporter — renders chat sessions and comparisons to PDF using WeasyPrint + Jinja2.
"""

from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from shared.logger import get_logger
from shared.utils.time_utils import timer

logger = get_logger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _get_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )


def export_chat_to_pdf(
    session_title: str,
    messages: list[dict],
    output_path: str | Path,
) -> Path:
    """
    Render a chat session to a styled PDF.

    Args:
        session_title: title shown at the top of the export.
        messages: list of dicts with ``role``, ``content``, optional ``havf_results``.
        output_path: filesystem path for the output PDF.

    Returns:
        Path to the written PDF file.
    """
    output_path = Path(output_path)
    env = _get_jinja_env()
    template = env.get_template("chat_export.html")

    html = template.render(
        title=session_title,
        messages=messages,
    )

    with timer("WeasyPrint PDF render"):
        from weasyprint import HTML
        HTML(string=html).write_pdf(str(output_path))

    logger.info(f"Exported chat PDF to {output_path.name}")
    return output_path


def export_comparison_to_pdf(
    title: str,
    comparison_content: str,
    paper_titles: list[str],
    output_path: str | Path,
) -> Path:
    """Render a paper comparison to a styled PDF."""
    output_path = Path(output_path)
    env = _get_jinja_env()
    template = env.get_template("comparison_export.html")

    html = template.render(
        title=title,
        comparison=comparison_content,
        papers=paper_titles,
    )

    from weasyprint import HTML
    HTML(string=html).write_pdf(str(output_path))

    logger.info(f"Exported comparison PDF to {output_path.name}")
    return output_path
