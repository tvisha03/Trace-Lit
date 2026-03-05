
from pathlib import Path
from shared.logger import get_logger
from shared.errors import TraceLitError
from shared.utils.export_text import strip_markdown, format_structured_text

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
        return "ForestGreen"
    if confidence == "medium":
        return "Goldenrod"
    return "Crimson"

def _add_verification_section_latex(lines: list[str], havf_results: list) -> None:
    lines.append(r"\smallskip")
    lines.append(r"\noindent{\small\textit{Citation Verification:}}")
    lines.append(r"\begin{itemize}[leftmargin=1.5em,itemsep=1pt,parsep=0pt]")
    for r in havf_results:
        confidence = r.get("confidence", "low")
        claim = r.get("claim", "")[:200]
        paragraph_id = r.get("paragraph_id", "")
        score = r.get("score", 0)
        color = _confidence_color(confidence)

        badge = f"[{confidence.upper()}] ({score:.0%})"
        ref = f" [{_escape_latex(paragraph_id)}]" if paragraph_id else ""
        claim_text = f'``{_escape_latex(claim)}\\textquotedblright'

        line = (
            r"  \item {\footnotesize "
            r"\textcolor{" + color + r"}{\textbf{" + badge + r"}}"
            + ref
            + r" --- " + claim_text
            + r"}"
        )
        lines.append(line)
    lines.append(r"\end{itemize}")
    lines.append("")

def _render_paragraphs_latex(lines: list[str], text: str) -> None:
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        lines.append(r"\noindent " + _escape_latex(para))
        lines.append(r"\medskip")
        lines.append("")

_LATEX_PREAMBLE = r"""\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{geometry}
\geometry{margin=2.5cm}
\usepackage[dvipsnames]{xcolor}
\usepackage{hyperref}
\usepackage{longtable}
\usepackage{enumitem}
\usepackage{booktabs}
\usepackage{parskip}
\hypersetup{colorlinks=true,linkcolor=NavyBlue,urlcolor=NavyBlue}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.6em}

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

    for idx, msg in enumerate(messages):
        role = msg.get("role", "user").upper()
        content = msg.get("content", "")
        havf_results = msg.get("havf_results") or []

        if role == "ASSISTANT":
            lines.append(
                r"\subsection*{\textcolor{NavyBlue}{["
                + _escape_latex(role)
                + r"]}}"
            )
        else:
            lines.append(r"\subsection*{[" + _escape_latex(role) + "]}")
        lines.append("")

        _render_paragraphs_latex(lines, strip_markdown(content))

        if havf_results:
            _add_verification_section_latex(lines, havf_results)

        if idx < len(messages) - 1:
            lines.append(r"\vspace{0.3em}")
            lines.append(r"\noindent\textcolor{gray!50}{\rule{\linewidth}{0.4pt}}")
            lines.append(r"\vspace{0.3em}")
            lines.append("")

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
    lines.append(r"\begin{enumerate}[itemsep=2pt]")
    for pt in paper_titles:
        lines.append(r"  \item " + _escape_latex(pt))
    lines.append(r"\end{enumerate}")
    lines.append("")

    lines.append(r"\section*{Comparison Analysis}")
    cleaned = format_structured_text(comparison_content)
    _render_paragraphs_latex(lines, cleaned)

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

