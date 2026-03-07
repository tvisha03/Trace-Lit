import re
from dataclasses import dataclass, field

from shared.logger import get_logger
from shared.utils.text_utils import split_into_sentences, estimate_tokens
from shared.constants import CHUNK_TARGET_TOKENS, CHUNK_MAX_TOKENS
from shared.enums import ChunkType

logger = get_logger(__name__)

# Compiled pattern for inline image markdown: ![alt](url)
# Strips embedded image references such as ``![](data/uploads/…)`` that
# formula and figure extractor results can embed inside their text fields.
# These paths are meaningless for the HAVF verifier and the LLM.
_IMG_MD_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def _strip_image_markdown(text: str) -> str:
    """Remove ``![alt](url)`` tokens from *text*.

    Formula and figure chunks sometimes embed image paths like
    ``![](data/uploads/…)`` inside their extracted text content.  Stripping
    these keeps source sentences readable and prevents the HAVF verifier from
    treating them as meaningful claims.
    """
    return _IMG_MD_RE.sub("", text).strip()


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
    """Split oversized paragraphs into target-sized chunks with 2-sentence overlap.

    Overlap ensures boundary sentences appear in adjacent chunks, improving
    HAVF confidence scores for sentences near chunk edges.
    """
    sentences = split_into_sentences(text)
    chunks: list[Chunk] = []
    current_sentences: list[str] = []
    current_tokens = 0
    idx_offset = 0
    overlap_sentences: list[str] = []

    for sentence in sentences:
        s_tokens = estimate_tokens(sentence)

        if current_tokens + s_tokens > CHUNK_TARGET_TOKENS and current_sentences:
            combined = " ".join(current_sentences)
            chunk = _build_chunk(combined, section_title, paper_title, start_idx + idx_offset, paper_id)
            chunks.append(chunk)
            idx_offset += 1
            # Carry last 2 sentences into the next chunk for overlap
            overlap_sentences = current_sentences[-2:]
            current_sentences = list(overlap_sentences)
            current_tokens = sum(estimate_tokens(s) for s in current_sentences)

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
        caption = getattr(fig, "caption", "") or ""

        prefix_parts = []
        if paper_title:
            prefix_parts.append(f"[Paper: {paper_title}]")
        prefix_parts.append(f"[Figure on page {fig.page_number}, type: {fig_type}]")
        if caption:
            prefix_parts.append(f"[Caption: {caption}]")
        prefix = " ".join(prefix_parts)
        enriched_text = f"{prefix} {text}"

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
            section_title=f"Figure (page {fig.page_number})",
            page_number=fig.page_number,
            token_count=estimate_tokens(display_text),
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
        prefix_parts.append(f"[TABLE, page {table.page_number}, {rows} rows \u00d7 {cols} cols]")
        if caption:
            prefix_parts.append(f"[Caption: {caption}]")
        prefix = " ".join(prefix_parts)

        # Semantic description in plain English so the LLM understands what this
        # table represents and how it relates to the paper, enabling accurate
        # [T#] citations and fact-checking during HAVF verification.
        semantic_parts = []
        if paper_title:
            semantic_parts.append(f"This table is from the paper '{paper_title}'.")
        if caption:
            semantic_parts.append(f"It presents: {caption}.")
        if rows or cols:
            semantic_parts.append(f"The table contains {rows} data rows across {cols} columns.")
        semantic_desc = " ".join(semantic_parts)

        enriched_text = f"{prefix}\n{semantic_desc}\n{text}" if semantic_desc else f"{prefix}\n{text}"

        display_text = f"{caption}\n{text}" if caption else text

        # Use only the caption as the HAVF verification sentence.
        # The full markdown table body is unsuitable for embedding-based
        # similarity checks; the caption is concise and verifiable.
        havf_text = caption if caption else f"Table on page {table.page_number}"
        sentence_map = {
            f"{paragraph_id}_S0": {
                "text": havf_text,
                "start": 0,
                "end": len(havf_text),
                "tokens": estimate_tokens(havf_text),
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
        # Strip inline image markdown (e.g. ![](data/uploads/…)) so the LLM
        # context and the HAVF source sentence remain human-readable text.
        clean_text = _strip_image_markdown(display_text)
        enriched_text = f"{prefix}\n{clean_text}"

        sentence_map = {
            f"{paragraph_id}_S0": {
                "text": clean_text,
                "start": 0,
                "end": len(clean_text),
                "tokens": estimate_tokens(clean_text),
            }
        }

        chunks.append(Chunk(
            paragraph_id=paragraph_id,
            text=clean_text,
            enriched_text=enriched_text,
            section_title=f"Equation (page {formula.page_number})",
            page_number=formula.page_number,
            token_count=estimate_tokens(clean_text),
            sentence_map=sentence_map,
            chunk_type=ChunkType.FORMULA,
        ))

    logger.info(f"Created {len(chunks)} formula/equation chunks")
    return chunks

