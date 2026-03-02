"""TraceLit — Domain Analysis Module.

Phase 2 analysis features:
- Keyword extraction (KeyBERT with MMR diversity)
- Paper summarization (on-demand LLM generation)
- Literature review generation (thematic, multi-paper)
- Research gap finding (limitation extraction → DBSCAN → LLM summary)
- Comparison table generation (LLM-extracted structured contributions)
"""

from domain.analysis.comparison_engine import (
    extract_paper_contributions,
    generate_comparison_table,
)
from domain.analysis.keyword_extractor import (
    extract_keywords,
    extract_paper_keywords,
)
from domain.analysis.summary_generator import generate_paper_summary
from domain.analysis.literature_review import (
    generate_literature_review,
    stream_literature_review,
)
from domain.analysis.research_gaps import find_research_gaps

__all__ = [
    "extract_paper_contributions",
    "generate_comparison_table",
    "extract_keywords",
    "extract_paper_keywords",
    "generate_paper_summary",
    "generate_literature_review",
    "stream_literature_review",
    "find_research_gaps",
]
