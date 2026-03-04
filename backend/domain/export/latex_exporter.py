
from pathlib import Path
from shared.logger import get_logger
from shared.errors import TraceLitError
from shared.utils.export_text import strip_markdown

logger = get_logger(__name__)


def _escape_latex(text: str) -> str:
    specials = {
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    text = text.replace("\\", r"\textbackslash{}")
    for char, replacement in specials.items():
        text = text.replace(char, replacement)
    return text


def _confidence_color(confidence: str) -> str:
    if confidence == "high":
        return "green!70!black"
    if confidence == "medium":
        return "orange!80!black"
    return "red!70!black"


def _add_verification_section_latex(lines: list[str], havf_results: list) -> None:
    """Add verification items LaTeX lines to the document."""
    lines.append(r"\smallskip")
    lines.append(r"\noindent\textit{Verification:}")
    lines.append(r"\begin{itemize}[leftmargin=1.5em,itemsep=0pt]")
    for r in havf_results:
        confidence = r.get("confidence", "low")
        claim = r.get("claim", "")[:200]
        paragraph_id = r.get("paragraph_id", "")
        score = r.get("score", 0)
        label = f"{confidence.upper()} ({score:.2f})"
        if paragraph_id:
            label += f" [{_escape_latex(paragraph_id)}]"
        label += f' --- ``{_escape_latex(claim)}``'
        color = _confidence_color(confidence)
        lines.append(r"  \item \textcolor{" + color + "}{" + label + "}")
    lines.append(r"\end{itemize}")
    lines.append("")


_LATEX_PREAMBLE = r"""\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{geometry}
\geometry{margin=2.5cm}
\usepackage{xcolor}
\usepackage{hyperref}
\usepackage{longtable}
\usepackage{enumitem}
\hypersetup{colorlinks=true,linkcolor=blue,urlcolor=blue}

"""


def export_chat_to_latex(
    session_title: str,
    messages: list[dict],
    output_path: str | Path,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [_LATEX_PREAMBLE]
    lines.append(r"\title{" + _escape_latex(session_title) + "}")
    lines.append(r"\date{\today}")
    lines.append(r"\begin{document}")
    lines.append(r"\maketitle")
    lines.append("")

    for msg in messages:
        role = msg.get("role", "user").upper()
        content = msg.get("content", "")
        havf_results = msg.get("havf_results") or []

        lines.append(r"\subsection*{[" + _escape_latex(role) + "]}")
        lines.append("")

        lines.append(_escape_latex(strip_markdown(content)))
        lines.append("")

        if havf_results:
            _add_verification_section_latex(lines, havf_results)

    lines.append(r"\end{document}")
    lines.append("")

    try:
        output_path.write_text("\n".join(lines), encoding="utf-8")
    except Exception as exc:
        raise TraceLitError(
            message=f"Failed to write LaTeX file: {exc}",
            status_code=500,
        ) from exc

    logger.info(f"Exported chat LaTeX to {output_path.name}")
    return output_path


def export_comparison_to_latex(
    title: str,
    comparison_content: str,
    paper_titles: list[str],
    output_path: str | Path,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [_LATEX_PREAMBLE]
    lines.append(r"\title{" + _escape_latex(title) + "}")
    lines.append(r"\date{\today}")
    lines.append(r"\begin{document}")
    lines.append(r"\maketitle")
    lines.append("")

    lines.append(r"\section*{Papers Compared}")
    lines.append(r"\begin{enumerate}")
    for pt in paper_titles:
        lines.append(r"  \item " + _escape_latex(pt))
    lines.append(r"\end{enumerate}")
    lines.append("")

    lines.append(r"\section*{Comparison}")
    lines.append(_escape_latex(strip_markdown(comparison_content)))
    lines.append("")

    lines.append(r"\end{document}")
    lines.append("")

    try:
        output_path.write_text("\n".join(lines), encoding="utf-8")
    except Exception as exc:
        raise TraceLitError(
            message=f"Failed to write comparison LaTeX file: {exc}",
            status_code=500,
        ) from exc

    logger.info(f"Exported comparison LaTeX to {output_path.name}")
    return output_path

