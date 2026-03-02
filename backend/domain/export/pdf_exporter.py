"""TraceLit — PDF Export via WeasyPrint + Jinja2.

Generates professional PDF documents from chat sessions with:
- Cover page
- Messages with citations and confidence indicators
- Source reference list
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


def generate_session_pdf(
    session_data: Dict[str, Any],
    output_dir: str = None,
) -> str:
    """Generate a PDF export of a chat session.

    Args:
        session_data: Dict with keys:
            - session_id, session_name
            - messages: list of message dicts
            - papers: list of paper metadata dicts
            - export_options: optional dict with formatting prefs

    Returns:
        Path to generated PDF file.
    """
    from jinja2 import Environment, FileSystemLoader, BaseLoader

    if output_dir is None:
        from app.config import settings
        output_dir = settings.export_dir

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    session_id = session_data.get("session_id", "unknown")
    session_name = session_data.get("session_name", "TraceLit Session")
    messages = session_data.get("messages", [])
    papers = session_data.get("papers", [])

    # Build HTML
    html_content = _render_pdf_html(
        session_name=session_name,
        messages=messages,
        papers=papers,
    )

    # Generate PDF
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"tracelit_export_{session_id[:8]}_{timestamp}.pdf"
    output_path = os.path.join(output_dir, filename)

    try:
        from weasyprint import HTML
        HTML(string=html_content).write_pdf(output_path)
        logger.info("PDF generated: {} ({} messages)", output_path, len(messages))
        return output_path
    except ImportError:
        logger.error("WeasyPrint not installed — PDF export unavailable")
        raise RuntimeError("WeasyPrint is required for PDF export")
    except Exception as e:
        logger.error("PDF generation failed: {}", e)
        raise


def _render_pdf_html(
    session_name: str,
    messages: List[Dict],
    papers: List[Dict],
) -> str:
    """Render the PDF HTML template."""

    paper_refs = ""
    for p in papers:
        authors = p.get("authors", [])
        if isinstance(authors, str):
            import json
            try:
                authors = json.loads(authors)
            except Exception:
                authors = [authors]
        author_str = ", ".join(authors[:3])
        if len(authors) > 3:
            author_str += " et al."
        year = p.get("year", "")
        year_str = f" ({year})" if year else ""
        paper_refs += f"""
        <div class="paper-ref">
            <strong>{p.get('title', 'Unknown')}</strong>{year_str}<br/>
            <em>{author_str}</em>
        </div>"""

    message_blocks = ""
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        metadata = msg.get("metadata", {})

        if role == "user":
            message_blocks += f"""
            <div class="message user-message">
                <div class="role-label">Question</div>
                <div class="content">{_escape_html(content)}</div>
            </div>"""
        else:
            confidence = metadata.get("overall_confidence", 0)
            provider = metadata.get("provider", "unknown")
            conf_class = _confidence_class(confidence)

            message_blocks += f"""
            <div class="message assistant-message">
                <div class="role-label">
                    TraceLit Response
                    <span class="confidence-badge {conf_class}">
                        Confidence: {confidence:.0%}
                    </span>
                    <span class="provider-badge">{provider}</span>
                </div>
                <div class="content">{_format_citations_html(content)}</div>
            </div>"""

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        @page {{
            size: A4;
            margin: 2cm;
        }}
        body {{
            font-family: 'Helvetica Neue', Arial, sans-serif;
            font-size: 11pt;
            line-height: 1.6;
            color: #1a1a1a;
        }}
        .cover {{
            text-align: center;
            padding-top: 8cm;
            page-break-after: always;
        }}
        .cover h1 {{
            font-size: 28pt;
            color: #2563eb;
            margin-bottom: 0.5em;
        }}
        .cover .subtitle {{
            font-size: 14pt;
            color: #64748b;
        }}
        .cover .date {{
            margin-top: 2em;
            color: #94a3b8;
        }}
        h2 {{
            color: #1e40af;
            border-bottom: 2px solid #dbeafe;
            padding-bottom: 0.3em;
            margin-top: 1.5em;
        }}
        .message {{
            margin: 1em 0;
            padding: 1em;
            border-radius: 8px;
        }}
        .user-message {{
            background: #eff6ff;
            border-left: 4px solid #3b82f6;
        }}
        .assistant-message {{
            background: #f8fafc;
            border-left: 4px solid #10b981;
        }}
        .role-label {{
            font-weight: 600;
            font-size: 10pt;
            color: #475569;
            margin-bottom: 0.5em;
        }}
        .confidence-badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 9pt;
            font-weight: 500;
            margin-left: 0.5em;
        }}
        .confidence-high {{ background: #dcfce7; color: #166534; }}
        .confidence-medium {{ background: #fef3c7; color: #92400e; }}
        .confidence-low {{ background: #fee2e2; color: #991b1b; }}
        .provider-badge {{
            display: inline-block;
            padding: 2px 8px;
            background: #e2e8f0;
            border-radius: 12px;
            font-size: 9pt;
            color: #475569;
            margin-left: 0.5em;
        }}
        .citation {{
            color: #2563eb;
            font-weight: 600;
            font-size: 9pt;
            vertical-align: super;
        }}
        .paper-ref {{
            padding: 0.5em 0;
            border-bottom: 1px solid #e2e8f0;
        }}
        .footer {{
            text-align: center;
            font-size: 9pt;
            color: #94a3b8;
            margin-top: 3em;
        }}
    </style>
</head>
<body>
    <div class="cover">
        <h1>TraceLit</h1>
        <div class="subtitle">{_escape_html(session_name)}</div>
        <div class="date">Generated on {datetime.now().strftime("%B %d, %Y at %H:%M")}</div>
        <div class="date">AI-Powered Research Paper Analysis</div>
    </div>

    <h2>Conversation</h2>
    {message_blocks}

    <h2>Paper References</h2>
    {paper_refs if paper_refs else "<p>No papers referenced.</p>"}

    <div class="footer">
        Generated by TraceLit — Sentence-Level Attribution for Research Papers
    </div>
</body>
</html>"""


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _format_citations_html(text: str) -> str:
    """Convert [P#] citations to styled superscript HTML."""
    import re
    escaped = _escape_html(text)
    return re.sub(
        r'\[P(\d+)\]',
        r'<span class="citation">[P\1]</span>',
        escaped,
    )


def _confidence_class(confidence: float) -> str:
    """Map confidence to CSS class."""
    if confidence >= 0.85:
        return "confidence-high"
    elif confidence >= 0.65:
        return "confidence-medium"
    return "confidence-low"
