
from pathlib import Path
import re
from shared.logger import get_logger
from shared.errors import TraceLitError
from shared.utils.export_media import prepare_cited_assets
from shared.utils.export_text import build_export_blocks, format_structured_text, inline_tokens_to_text

logger = get_logger(__name__)
_DISPLAY_FORMULA_RE = re.compile(r"(?:\\\[|\$\$)([\s\S]+?)(?:\\\]|\$\$)|\\\(([\s\S]+?)\\\)|\$([^$\n]+)\$")

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


def _latexify_plain_text(text: str) -> str:
    normalized = text.replace("⊗", r"$\otimes$")
    normalized = normalized.replace("sigma", r"$\sigma$")
    return _escape_latex(normalized).replace(r"\$\textbackslash{}otimes\$", r"$\otimes$").replace(r"\$\textbackslash{}sigma\$", r"$\sigma$")


def _append_paragraph(lines: list[str], text: str) -> None:
    lines.append(text)
    lines.append("")

def _confidence_color(confidence: str) -> str:
    if confidence == "high":
        return "ForestGreen"
    if confidence == "medium":
        return "Goldenrod"
    return "Crimson"

def _add_verification_section_latex(lines: list[str], havf_results: list) -> None:
    lines.append(r"\subsubsection*{Citation Verification}")
    lines.append(r"\begin{itemize}[leftmargin=1.5em,itemsep=1pt,parsep=0pt]")
    for r in havf_results:
        confidence = r.get("confidence", "low")
        claim = r.get("claim", "")[:200]
        paragraph_id = r.get("paragraph_id", "")
        score = r.get("score", 0)

        badge = f"{confidence.upper()} {score:.0%}"
        ref = f" [{_escape_latex(paragraph_id)}]" if paragraph_id else ""
        claim_text = _latexify_plain_text(format_structured_text(claim))
        lines.append(r"  \item \textbf{[" + _escape_latex(badge) + r"]} " + claim_text + ref)
    lines.append(r"\end{itemize}")
    lines.append("")

def _render_paragraphs_latex(lines: list[str], text: str) -> None:
    for block in build_export_blocks(text):
        if block.kind == "heading":
            level = min(max(block.level, 1), 4)
            section_map = {1: "section", 2: "subsection", 3: "subsubsection", 4: "paragraph"}
            cmd = section_map[level]
            _append_paragraph(lines, rf"\{cmd}*{{{_latexify_plain_text(block.text)}}}")
        elif block.kind == "bullet":
            lines.append(r"\begin{itemize}[leftmargin=1.5em,itemsep=2pt,parsep=0pt]")
            lines.append(r"  \item " + _latexify_plain_text(block.text))
            _append_paragraph(lines, r"\end{itemize}")
        elif block.kind == "table":
            _render_table_latex(lines, block.headers, block.rows)
        else:
            _append_paragraph(lines, r"\noindent " + _latexify_plain_text(inline_tokens_to_text(block.tokens)))


def _render_table_latex(lines: list[str], headers: list[str], rows: list[list[str]]) -> None:
    if not headers:
        return
    colspec = "|".join([r">{\raggedright\arraybackslash}p{0.16\linewidth}"] * len(headers))
    lines.append(r"\begin{longtable}{|" + colspec + r"|}")
    lines.append(r"\hline")
    lines.append(" & ".join(_latexify_plain_text(header) for header in headers) + r" \\")
    lines.append(r"\hline")
    for row in rows:
        padded = row + [""] * max(0, len(headers) - len(row))
        lines.append(" & ".join(_latexify_plain_text(cell) for cell in padded[:len(headers)]) + r" \\")
        lines.append(r"\hline")
    lines.append(r"\end{longtable}")
    lines.append("")


def _asset_meta_line(asset: dict) -> str:
    parts = [str(asset.get("paper_title", ""))]
    if asset.get("page_number"):
        parts.append(f"page {asset.get('page_number')}")
    if asset.get("section_title"):
        parts.append(str(asset.get("section_title")))
    return " | ".join(part for part in parts if part)


def _append_asset_image_latex(lines: list[str], image_path: str | None) -> None:
    if not image_path or not Path(image_path).exists():
        return

    image_target = str(Path(image_path)).replace("\\", "/").replace("_", r"\_")
    lines.append(r"\begin{center}")
    lines.append(r"\includegraphics[width=0.9\linewidth]{" + image_target + "}")
    lines.append(r"\end{center}")
    lines.append("")


def _extract_formula_body(text: str) -> str:
    match = _DISPLAY_FORMULA_RE.search(text or "")
    if not match:
        return ""
    return next((group.strip() for group in match.groups() if group and group.strip()), "")


def _render_asset_content_latex(lines: list[str], asset: dict) -> None:
    chunk_type = str(asset.get("chunk_type", "")).lower()
    source = str(asset.get("raw_content") or asset.get("content", ""))
    if chunk_type == "formula":
        formula_body = _extract_formula_body(source)
        if formula_body:
            lines.append(r"\[")
            lines.append(formula_body)
            lines.append(r"\]")
            lines.append("")
            return
    _render_paragraphs_latex(lines, source)


def _render_cited_media_latex(lines: list[str], cited_assets: list[dict]) -> None:
    if not cited_assets:
        return

    lines.append(r"\section*{Cited Figures, Tables, and Formulas}")
    for asset in cited_assets:
        heading = f"[{asset.get('citation_id', '')}] {str(asset.get('chunk_type', '')).title()}"
        lines.append(r"\subsection*{" + _latexify_plain_text(heading) + "}")

        meta_line = _asset_meta_line(asset)
        if meta_line:
            _append_paragraph(lines, r"\textit{" + _latexify_plain_text(meta_line) + "}")

        _render_asset_content_latex(lines, asset)
        _append_asset_image_latex(lines, asset.get("image_path"))

_LATEX_PREAMBLE = r"""\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{geometry}
\geometry{margin=2.5cm}
\usepackage[dvipsnames]{xcolor}
\usepackage{hyperref}
\usepackage{longtable}
\usepackage{array}
\usepackage{enumitem}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage{parskip}
\hypersetup{colorlinks=true,linkcolor=NavyBlue,urlcolor=NavyBlue}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.6em}

"""

def export_chat_to_latex(
    session_title: str,
    messages: list[dict],
    cited_assets: list[dict] | None,
    output_path: str | Path,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cited_assets = prepare_cited_assets(cited_assets or [], output_path.parent)

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

        if role == "ASSISTANT":
            lines.append(
                r"\subsection*{\textcolor{NavyBlue}{["
                + _escape_latex(role)
                + r"]}}"
            )
        else:
            lines.append(r"\subsection*{[" + _escape_latex(role) + "]}")
        lines.append("")

        _render_paragraphs_latex(lines, content)

        if havf_results:
            _add_verification_section_latex(lines, havf_results)

    _render_cited_media_latex(lines, cited_assets)

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
    comparison_table: list[dict] | None,
    cited_assets: list[dict] | None,
    output_path: str | Path,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cited_assets = prepare_cited_assets(cited_assets or [], output_path.parent)

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
    if comparison_table:
        headers = ["Dimension", *paper_titles, "Synthesis"]
        rows = []
        for row in comparison_table:
            rows.append([
                str(row.get("dimension", "")),
                *[format_structured_text(str(cell.get("content", ""))) for cell in row.get("cells", [])],
                format_structured_text(str(row.get("synthesis", ""))),
            ])
        _render_table_latex(lines, headers, rows)
    else:
        _render_paragraphs_latex(lines, comparison_content)

    _render_cited_media_latex(lines, cited_assets)

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

