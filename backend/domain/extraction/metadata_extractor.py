"""TraceLit — Metadata Extractor.

Re-exports metadata parsing from pdf_processor.
"""

from domain.extraction.pdf_processor import _parse_metadata as parse_metadata

__all__ = ["parse_metadata"]
