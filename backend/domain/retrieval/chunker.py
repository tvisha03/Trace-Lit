"""TraceLit — Sentence-Aware Chunker. 🚨 CRITICAL COMPONENT

Chunks at paragraph level with sentence-level boundary tracking.
Every chunk contains a sentences[] array with unique sentence IDs (P#_S#).

Rules from RAG_AND_CHUNKING_STRATEGY.md:
  - DO NOT chunk at sentence level — paragraph is the unit
  - DO embed the enriched_text (paper/section prefix)
  - DO store original text for display, enriched for embedding
  - Every sentence gets a unique ID: P{para_idx}_S{sent_idx}
"""

import re
from typing import Any, Dict, List, Optional

from loguru import logger


_ABBREVS = {
    "et al", "fig", "figs", "eq", "eqs", "ref", "refs",
    "sec", "sect", "vol", "no", "pp", "vs", "approx",
    "dept", "univ", "prof", "dr", "mr", "mrs", "ms",
    "e.g", "i.e", "cf", "etc", "al",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug",
    "sep", "oct", "nov", "dec",
}

_SENTENCE_SPLIT_RE = re.compile(
    r"""
    (?<!\w\.\w)
    (?<![A-Z][a-z]\.)
    (?<![A-Z]\.)
    (?<=\.|\?|!)
    \s+
    (?=[A-Z"'\(\[])
    """,
    re.VERBOSE,
)

_DECIMAL_RE = re.compile(r"\d+\.\d+")
_CITATION_RE = re.compile(r"\[\d+(?:,\s*\d+)*\]")
_ABBREV_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(a) for a in _ABBREVS) + r")\.\s",
    re.IGNORECASE,
)


class SentenceAwareChunker:
    """Chunks text into paragraphs with sentence-level tracking."""

    def __init__(
        self,
        min_paragraph_length: int = 30,
        max_paragraph_tokens: int = 512,
    ) -> None:
        self.min_paragraph_length = min_paragraph_length
        self.max_paragraph_tokens = max_paragraph_tokens

    def chunk_paper(
        self,
        sections: List[Dict[str, Any]],
        paper_metadata: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Chunk all sections of a paper into paragraph-level chunks."""
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

            for para_text in self._split_paragraphs(content):
                if len(para_text.strip()) < self.min_paragraph_length:
                    continue

                for sub_para in self._enforce_token_limit(para_text):
                    sentences = self._split_sentences(sub_para)
                    sentence_map = self._build_sentence_map(sentences, sub_para, global_para_idx)
                    enriched_text = f"[Paper: {paper_title}] [Section: {section_title}] {sub_para}"

                    all_chunks.append({
                        "paragraph_id": f"P{global_para_idx}",
                        "text": sub_para,
                        "enriched_text": enriched_text,
                        "sentences": sentence_map,
                        "section": section_title,
                        "page": section_page,
                        "paper_id": paper_id,
                        "paper_title": paper_title,
                        "token_count": self._estimate_tokens(sub_para),
                    })
                    global_para_idx += 1

        logger.info("Chunked '{}' → {} paragraphs", paper_title[:50], len(all_chunks))
        return all_chunks

    # ------------------------------------------------------------------

    def _split_paragraphs(self, text: str) -> List[str]:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        raw = re.split(r"\n\s*\n", text)
        result = []
        for para in raw:
            cleaned = re.sub(r"\n(?!\n)", " ", para).strip()
            cleaned = re.sub(r"  +", " ", cleaned)
            if cleaned:
                result.append(cleaned)
        return result

    def _enforce_token_limit(self, text: str) -> List[str]:
        if self._estimate_tokens(text) <= self.max_paragraph_tokens:
            return [text]
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

    def _split_sentences(self, text: str) -> List[str]:
        protected = text
        protected = _DECIMAL_RE.sub(lambda m: m.group().replace(".", "DECIMAL"), protected)
        protected = _CITATION_RE.sub(lambda m: m.group().replace(",", "COMMA"), protected)
        abbrev_positions = [(m.start(), m.end()) for m in _ABBREV_RE.finditer(protected)]
        for start, end in reversed(abbrev_positions):
            protected = protected[:start] + protected[start:end].replace(". ", "ABBREVDOT ") + protected[end:]

        raw_sentences = _SENTENCE_SPLIT_RE.split(protected)
        sentences = []
        for sent in raw_sentences:
            restored = (sent
                .replace("DECIMAL", ".")
                .replace("COMMA", ",")
                .replace("ABBREVDOT", ".")
                .strip())
            if restored:
                sentences.append(restored)
        return sentences

    def _build_sentence_map(
        self,
        sentences: List[str],
        para_text: str,
        para_idx: int,
    ) -> List[Dict[str, Any]]:
        result = []
        search_start = 0
        for sent_idx, sent in enumerate(sentences):
            start = para_text.find(sent, search_start)
            if start == -1:
                start = search_start
            end = start + len(sent)
            result.append({
                "sentence_id": f"P{para_idx}_S{sent_idx}",
                "text": sent,
                "start_char": start,
                "end_char": end,
                "tokens": self._estimate_tokens(sent),
            })
            search_start = end
        return result

    def _estimate_tokens(self, text: str) -> int:
        return len(text) // 4
