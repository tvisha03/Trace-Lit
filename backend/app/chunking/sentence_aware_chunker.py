"""TraceLit — Sentence-Aware Chunker. 🚨 CRITICAL COMPONENT

Chunks at paragraph level with sentence-level boundary tracking.
Every chunk contains a sentences[] array with unique sentence IDs (P#_S#).

Core principle: chunk at paragraph level for context, but track every
sentence for attribution. This enables click-to-sentence navigation
and HAVF verification at sentence granularity.

Rules from RAG_AND_CHUNKING_STRATEGY.md:
  - DO NOT chunk at sentence level — paragraph is the unit
  - DO embed the enriched_text (with paper/section prefix)
  - DO store original text for display, enriched for embedding
  - Every sentence gets a unique ID: P{para_idx}_S{sent_idx}
"""

import re
from typing import Any, Dict, List, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# Abbreviation patterns that contain periods but should NOT trigger a split
# ---------------------------------------------------------------------------

# Academic abbreviations
_ABBREVS = {
    "et al", "fig", "figs", "eq", "eqs", "ref", "refs",
    "sec", "sect", "vol", "no", "pp", "vs", "approx",
    "dept", "univ", "prof", "dr", "mr", "mrs", "ms",
    "e.g", "i.e", "cf", "etc", "al",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug",
    "sep", "oct", "nov", "dec",
}

# Pre-compiled regex: negative lookbehind for abbreviations before ". "
# Matches sentence-ending punctuation followed by whitespace
_SENTENCE_SPLIT_RE = re.compile(
    r"""
    (?<!\w\.\w)       # Not a letter.letter pattern (e.g., "e.g.")
    (?<![A-Z][a-z]\.) # Not a single capital + lowercase + dot (e.g., "Dr.")
    (?<![A-Z]\.)      # Not a single capital letter + dot (e.g., "A.")
    (?<=\.|\?|!)      # After sentence-ending punctuation
    \s+               # Followed by whitespace
    (?=[A-Z"'\(\[])   # Next char is uppercase, quote, or bracket
    """,
    re.VERBOSE,
)

# Additional patterns for academic edge cases
_DECIMAL_RE = re.compile(r"\d+\.\d+")  # 3.14, 0.001, 93.2
_CITATION_RE = re.compile(r"\[\d+(?:,\s*\d+)*\]")  # [1], [1, 2, 3]
_ABBREV_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(a) for a in _ABBREVS) + r")\.\s",
    re.IGNORECASE,
)


class SentenceAwareChunker:
    """Chunks text into paragraphs with sentence-level tracking.

    Usage:
        chunker = SentenceAwareChunker()
        chunks = chunker.chunk_paper(sections, paper_metadata)
    """

    def __init__(
        self,
        min_paragraph_length: int = 30,
        max_paragraph_tokens: int = 512,
    ) -> None:
        """Initialize chunker.

        Args:
            min_paragraph_length: Minimum chars for a paragraph to be kept.
            max_paragraph_tokens: If a paragraph exceeds this, split it.
        """
        self.min_paragraph_length = min_paragraph_length
        self.max_paragraph_tokens = max_paragraph_tokens

    def chunk_paper(
        self,
        sections: List[Dict[str, Any]],
        paper_metadata: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Chunk all sections of a paper into paragraph-level chunks.

        Args:
            sections: List of section dicts from PDF extraction
                      (each has title, page_start, order, content).
            paper_metadata: Dict with paper_id, title, (authors, year).

        Returns:
            List of chunk dicts, each containing:
              - paragraph_id: "P0", "P1", etc. (global across paper)
              - text: original paragraph text (for display)
              - enriched_text: with [Paper: X] [Section: Y] prefix (for embedding)
              - sentences: [{sentence_id, text, start_char, end_char, tokens}]
              - section: section title
              - page: page number
              - paper_id: paper UUID
              - paper_title: paper title string
        """
        paper_id = paper_metadata.get("paper_id", "unknown")
        paper_title = paper_metadata.get("title", "Unknown Paper")

        all_chunks: List[Dict[str, Any]] = []
        global_para_idx = 0

        for section in sections:
            section_title = section.get("title", "Unknown Section")
            section_page = section.get("page_start", 0)
            content = section.get("content", "")

            if not content.strip():
                continue

            paragraphs = self._split_paragraphs(content)

            for para_text in paragraphs:
                if len(para_text.strip()) < self.min_paragraph_length:
                    continue

                # Split long paragraphs if needed
                sub_paragraphs = self._enforce_token_limit(para_text)

                for sub_para in sub_paragraphs:
                    sentences = self._split_sentences(sub_para)
                    sentence_map = self._build_sentence_map(
                        sentences, sub_para, global_para_idx,
                    )

                    # Context enrichment (15-20% retrieval improvement)
                    enriched_text = (
                        f"[Paper: {paper_title}] "
                        f"[Section: {section_title}] "
                        f"{sub_para}"
                    )

                    chunk = {
                        "paragraph_id": f"P{global_para_idx}",
                        "text": sub_para,
                        "enriched_text": enriched_text,
                        "sentences": sentence_map,
                        "section": section_title,
                        "page": section_page,
                        "paper_id": paper_id,
                        "paper_title": paper_title,
                        "token_count": self._estimate_tokens(sub_para),
                    }
                    all_chunks.append(chunk)
                    global_para_idx += 1

        logger.info(
            "Chunked paper '{}' → {} paragraphs with sentence tracking",
            paper_title[:50],
            len(all_chunks),
        )
        return all_chunks

    # ------------------------------------------------------------------
    # Paragraph splitting
    # ------------------------------------------------------------------

    def _split_paragraphs(self, text: str) -> List[str]:
        """Split text into paragraphs on double newlines or blank lines.

        Also handles markdown-style single newlines between logical paragraphs.
        """
        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Split on double newlines (standard paragraph break)
        raw_paragraphs = re.split(r"\n\s*\n", text)

        paragraphs: List[str] = []
        for para in raw_paragraphs:
            # Clean up internal newlines (join wrapped lines)
            cleaned = re.sub(r"\n(?!\n)", " ", para).strip()
            # Collapse multiple spaces
            cleaned = re.sub(r"  +", " ", cleaned)
            if cleaned:
                paragraphs.append(cleaned)

        return paragraphs

    def _enforce_token_limit(self, text: str) -> List[str]:
        """Split a paragraph if it exceeds max_paragraph_tokens.

        Splits at sentence boundaries when possible.
        """
        tokens = self._estimate_tokens(text)
        if tokens <= self.max_paragraph_tokens:
            return [text]

        # Split into sentences and regroup
        sentences = self._split_sentences(text)
        sub_paras: List[str] = []
        current: List[str] = []
        current_tokens = 0

        for sent in sentences:
            sent_tokens = self._estimate_tokens(sent)
            if current_tokens + sent_tokens > self.max_paragraph_tokens and current:
                sub_paras.append(" ".join(current))
                current = [sent]
                current_tokens = sent_tokens
            else:
                current.append(sent)
                current_tokens += sent_tokens

        if current:
            sub_paras.append(" ".join(current))

        return sub_paras if sub_paras else [text]

    # ------------------------------------------------------------------
    # Sentence splitting (handles academic edge cases)
    # ------------------------------------------------------------------

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences, handling academic abbreviations.

        Handles:
          - et al. / Fig. / e.g. / i.e. / Dr. → do NOT split
          - Decimal numbers: 3.14, 93.2 → do NOT split
          - Citations: "...accuracy [12]." → DO split after
          - Standard sentence endings: . ? ! → split if followed by uppercase
        """
        if not text or not text.strip():
            return []

        # Protect abbreviations by replacing their periods with a placeholder
        protected = text
        placeholder = "\x00"  # null byte as placeholder

        # Protect known abbreviations: "et al.", "Fig.", "e.g.", etc.
        for abbrev in sorted(_ABBREVS, key=len, reverse=True):
            # Match abbreviation followed by period (case-insensitive)
            pattern = re.compile(
                r"\b" + re.escape(abbrev) + r"\.",
                re.IGNORECASE,
            )
            protected = pattern.sub(
                lambda m: m.group(0).replace(".", placeholder),
                protected,
            )

        # Protect decimal numbers: 3.14, 0.001, etc.
        protected = _DECIMAL_RE.sub(
            lambda m: m.group(0).replace(".", placeholder),
            protected,
        )

        # Protect single-letter abbreviations: "A.", "B.", etc.
        protected = re.sub(
            r"\b([A-Z])\.",
            lambda m: m.group(1) + placeholder,
            protected,
        )

        # Now split on sentence boundaries
        sentences = _SENTENCE_SPLIT_RE.split(protected)

        # Restore placeholders
        sentences = [s.replace(placeholder, ".").strip() for s in sentences]

        # Filter empty strings
        sentences = [s for s in sentences if s]

        return sentences

    # ------------------------------------------------------------------
    # Sentence map builder
    # ------------------------------------------------------------------

    def _build_sentence_map(
        self,
        sentences: List[str],
        paragraph_text: str,
        para_idx: int,
    ) -> List[Dict[str, Any]]:
        """Build sentence map with unique IDs and character offsets.

        Args:
            sentences: List of sentence strings.
            paragraph_text: Original paragraph text.
            para_idx: Global paragraph index.

        Returns:
            List of dicts: {sentence_id, text, start_char, end_char, tokens}
        """
        sentence_map: List[Dict[str, Any]] = []
        search_start = 0

        for sent_idx, sent_text in enumerate(sentences):
            # Find the sentence in the original paragraph
            start_char = paragraph_text.find(sent_text, search_start)
            if start_char == -1:
                # Fallback: approximate position
                start_char = search_start
            end_char = start_char + len(sent_text)
            search_start = end_char

            sentence_map.append({
                "sentence_id": f"P{para_idx}_S{sent_idx}",
                "text": sent_text,
                "start_char": start_char,
                "end_char": end_char,
                "tokens": self._estimate_tokens(sent_text),
            })

        return sentence_map

    # ------------------------------------------------------------------
    # Token estimation
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate token count (~4 chars per token for English).

        This is a rough estimate; actual tokenization varies by model.
        """
        return max(1, len(text) // 4)
