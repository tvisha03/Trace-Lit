"""TraceLit — Section Parser.

Thin wrapper re-exporting section detection from pdf_processor
for callers that only need the section layer (no full PDF extraction).
"""

from domain.extraction.pdf_processor import _detect_sections as detect_sections, _detect_heading as detect_heading

__all__ = ["detect_sections", "detect_heading"]
