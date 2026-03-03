import re
from dataclasses import dataclass, field

from shared.logger import get_logger
from shared.utils.text_utils import split_into_sentences, estimate_tokens
from shared.constants import CHUNK_TARGET_TOKENS, CHUNK_MAX_TOKENS
from shared.enums import ChunkType

logger = get_logger(__name__)

@dataclass
class Chunk:
    paragraph_id: str
    text: str
    enriched_text: str
    section_title: str
    page_number: int | None
    token_count: int
    sentence_map: dict = field(default_factory=dict)
    chunk_type: ChunkType = ChunkType.TEXT
    image_path: str | None = None

def create_chunks(
    sections: list,
    paper_title: str | None = None,
    paper_id: str | None = None,
) -> list[Chunk]:
    if not sections:
        logger.warning(
            f"No sections provided to create_chunks for paper {paper_id or 'unknown'}. "
            "The PDF may be empty or extraction yielded no usable text."
        )
        return []

    chunks: list[Chunk] = []
    paragraph_idx = 0

    for section in sections:
        paragraphs = _split_paragraphs(section.content)

        for para_text in paragraphs:
            para_text = para_text.strip()
            if not para_text or len(para_text) < 20:
                continue

            token_count = estimate_tokens(para_text)

            if token_count > CHUNK_MAX_TOKENS:
                sub_chunks = _split_large_paragraph(
                    para_text, section.title, paper_title, paragraph_idx, paper_id
                )
                chunks.extend(sub_chunks)
                paragraph_idx += len(sub_chunks)
            else:
                chunk = _build_chunk(para_text, section.title, paper_title, paragraph_idx, paper_id)
                chunks.append(chunk)
                paragraph_idx += 1

    logger.info(f"Created {len(chunks)} chunks from {len(sections)} sections")
    return chunks

def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

def _build_chunk(
    text: str,
    section_title: str,
    paper_title: str | None,
    paragraph_idx: int,
    paper_id: str | None = None,
) -> Chunk:
    if paper_id:
        paragraph_id = f"{paper_id[:8]}_P{paragraph_idx}"
    else:
        paragraph_id = f"P{paragraph_idx}"
    sentences = split_into_sentences(text)

    if not sentences:
        logger.warning(
            f"Zero sentences extracted from chunk {paragraph_id} — "
            "falling back to full text as a single sentence."
        )
        sentences = [text]

    sentence_map = {}
    offset = 0

    for s_idx, sentence in enumerate(sentences):
        s_key = f"{paragraph_id}_S{s_idx}"
        start = text.find(sentence, offset)
        if start == -1:
            start = offset
        end = start + len(sentence)
        sentence_map[s_key] = {
            "text": sentence,
            "start": start,
            "end": end,
            "tokens": estimate_tokens(sentence),
        }
        offset = end

    prefix_parts = []
    if paper_title:
        prefix_parts.append(f"[Paper: {paper_title}]")
    if section_title:
        prefix_parts.append(f"[Section: {section_title}]")
    prefix = " ".join(prefix_parts)
    enriched_text = f"{prefix} {text}" if prefix else text

    return Chunk(
        paragraph_id=paragraph_id,
        text=text,
        enriched_text=enriched_text,
        section_title=section_title,
        page_number=None,
        token_count=estimate_tokens(text),
        sentence_map=sentence_map,
    )

def _split_large_paragraph(
    text: str,
    section_title: str,
    paper_title: str | None,
    start_idx: int,
    paper_id: str | None = None,
) -> list[Chunk]:
    sentences = split_into_sentences(text)
    chunks: list[Chunk] = []
    current_sentences: list[str] = []
    current_tokens = 0
    idx_offset = 0

    for sentence in sentences:
        s_tokens = estimate_tokens(sentence)

        if current_tokens + s_tokens > CHUNK_TARGET_TOKENS and current_sentences:
            combined = " ".join(current_sentences)
            chunk = _build_chunk(combined, section_title, paper_title, start_idx + idx_offset, paper_id)
            chunks.append(chunk)
            idx_offset += 1
            current_sentences = []
            current_tokens = 0

        current_sentences.append(sentence)
        current_tokens += s_tokens

    if current_sentences:
        combined = " ".join(current_sentences)
        chunk = _build_chunk(combined, section_title, paper_title, start_idx + idx_offset, paper_id)
        chunks.append(chunk)

    return chunks


def create_figure_chunks(
    analyzed_figures: list,
    paper_title: str | None = None,
    paper_id: str | None = None,
    start_idx: int = 0,
) -> list[Chunk]:
    chunks: list[Chunk] = []

    for offset, fig in enumerate(analyzed_figures):
        idx = start_idx + offset

        if paper_id:
            paragraph_id = f"{paper_id[:8]}_F{idx}"
        else:
            paragraph_id = f"F{idx}"

        text = fig.description
        fig_type = getattr(fig, "figure_type", "figure")

        prefix_parts = []
        if paper_title:
            prefix_parts.append(f"[Paper: {paper_title}]")
        prefix_parts.append(f"[Figure on page {fig.page_number}, type: {fig_type}]")
        prefix = " ".join(prefix_parts)
        enriched_text = f"{prefix} {text}"

        sentence_map = {
            f"{paragraph_id}_S0": {
                "text": text,
                "start": 0,
                "end": len(text),
                "tokens": estimate_tokens(text),
            }
        }

        chunks.append(Chunk(
            paragraph_id=paragraph_id,
            text=text,
            enriched_text=enriched_text,
            section_title=f"Figure (page {fig.page_number})",
            page_number=fig.page_number,
            token_count=estimate_tokens(text),
            sentence_map=sentence_map,
            chunk_type=ChunkType.FIGURE,
            image_path=fig.image_path,
        ))

    logger.info(f"Created {len(chunks)} figure chunks")
    return chunks


def create_table_chunks(
    tables: list,
    paper_title: str | None = None,
    paper_id: str | None = None,
    start_idx: int = 0,
) -> list[Chunk]:
    chunks: list[Chunk] = []

    for offset, table in enumerate(tables):
        idx = start_idx + offset

        if paper_id:
            paragraph_id = f"{paper_id[:8]}_T{idx}"
        else:
            paragraph_id = f"T{idx}"

        text = table.content
        caption = getattr(table, "caption", "") or ""
        rows = getattr(table, "row_count", 0)
        cols = getattr(table, "col_count", 0)

        prefix_parts = []
        if paper_title:
            prefix_parts.append(f"[Paper: {paper_title}]")
        prefix_parts.append(f"[Table on page {table.page_number}, {rows}x{cols}]")
        if caption:
            prefix_parts.append(f"[Caption: {caption}]")
        prefix = " ".join(prefix_parts)
        enriched_text = f"{prefix}\n{text}"

        display_text = f"{caption}\n{text}" if caption else text

        sentence_map = {
            f"{paragraph_id}_S0": {
                "text": display_text,
                "start": 0,
                "end": len(display_text),
                "tokens": estimate_tokens(display_text),
            }
        }

        chunks.append(Chunk(
            paragraph_id=paragraph_id,
            text=display_text,
            enriched_text=enriched_text,
            section_title=f"Table (page {table.page_number})",
            page_number=table.page_number,
            token_count=estimate_tokens(display_text),
            sentence_map=sentence_map,
            chunk_type=ChunkType.TABLE,
        ))

    logger.info(f"Created {len(chunks)} table chunks")
    return chunks


def create_formula_chunks(
    formulas: list,
    paper_title: str | None = None,
    paper_id: str | None = None,
    start_idx: int = 0,
) -> list[Chunk]:
    chunks: list[Chunk] = []

    for offset, formula in enumerate(formulas):
        idx = start_idx + offset

        if paper_id:
            paragraph_id = f"{paper_id[:8]}_E{idx}"
        else:
            paragraph_id = f"E{idx}"

        text = formula.content
        formula_type = getattr(formula, "formula_type", "unknown")
        eq_number = getattr(formula, "equation_number", None)
        context = getattr(formula, "context", "") or ""

        prefix_parts = []
        if paper_title:
            prefix_parts.append(f"[Paper: {paper_title}]")
        prefix_parts.append(f"[Equation on page {formula.page_number}, type: {formula_type}]")
        if eq_number:
            prefix_parts.append(f"[Eq. {eq_number}]")
        prefix = " ".join(prefix_parts)

        display_text = f"{context}\n{text}" if context else text
        enriched_text = f"{prefix}\n{display_text}"

        sentence_map = {
            f"{paragraph_id}_S0": {
                "text": display_text,
                "start": 0,
                "end": len(display_text),
                "tokens": estimate_tokens(display_text),
            }
        }

        chunks.append(Chunk(
            paragraph_id=paragraph_id,
            text=display_text,
            enriched_text=enriched_text,
            section_title=f"Equation (page {formula.page_number})",
            page_number=formula.page_number,
            token_count=estimate_tokens(display_text),
            sentence_map=sentence_map,
            chunk_type=ChunkType.FORMULA,
        ))

    logger.info(f"Created {len(chunks)} formula/equation chunks")
    return chunks

