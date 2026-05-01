"""
Fast backfill page_number for existing chunks.

Uses pymupdf (fast) instead of pymupdf4llm (slow) to extract per-page text,
then maps each chunk's text to the correct page.

Usage:
    cd backend
    python scripts/backfill_page_numbers_fast.py              # All papers
    python scripts/backfill_page_numbers_fast.py <paper_id>   # Specific paper
"""

import sys
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pymupdf
from shared.logger import get_logger

logger = get_logger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "trace_lit.db"


def get_papers(db_path):
    """Get all papers with their file paths."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT id, file_path, page_count FROM papers WHERE UPPER(status) = 'COMPLETED'"
    )
    papers = [dict(row) for row in cur.fetchall()]
    conn.close()
    return papers


def build_page_text_map(pdf_path):
    """Extract text per page using pymupdf (fast).

    Returns:
        combined_text: full document text with \n\n separators
        offset_to_page: list of (char_offset, page_number) tuples
        page_texts: list of (offset, page_number, text) tuples
    """
    doc = pymupdf.open(str(pdf_path))
    combined_parts = []
    offset_to_page = []
    page_texts = []
    cumulative = 0

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        page_number = page_num + 1  # 1-indexed

        offset_to_page.append((cumulative, page_number))
        page_texts.append((cumulative, page_number, text))
        combined_parts.append(text)
        cumulative += len(text) + 2  # \n\n separator

    doc.close()

    combined_text = "\n\n".join(combined_parts)
    return combined_text, offset_to_page, page_texts


def offset_to_page_number(offset, offset_to_page):
    """Binary search for the page containing a character offset."""
    lo, hi = 0, len(offset_to_page) - 1
    result = offset_to_page[0][1]
    while lo <= hi:
        mid = (lo + hi) // 2
        if offset_to_page[mid][0] <= offset:
            result = offset_to_page[mid][1]
            lo = mid + 1
        else:
            hi = mid - 1
    return result


def find_page_for_chunk(chunk_text, combined_text, offset_to_page):
    """Find the page number for a chunk's text."""
    if not chunk_text or len(chunk_text) < 20:
        return None

    # Try exact match
    pos = combined_text.find(chunk_text)
    if pos >= 0:
        return offset_to_page_number(pos, offset_to_page)

    # Try first 200 chars
    snippet = chunk_text[:200].strip()
    if len(snippet) > 50:
        pos = combined_text.find(snippet)
        if pos >= 0:
            return offset_to_page_number(pos, offset_to_page)

    # Try first sentence
    sentences = chunk_text.split(". ")
    if sentences:
        first_sentence = sentences[0].strip()
        if len(first_sentence) > 30:
            pos = combined_text.find(first_sentence)
            if pos >= 0:
                return offset_to_page_number(pos, offset_to_page)

    return None


def backfill_paper(paper_id, file_path, db_path):
    """Backfill page_number for all chunks of a single paper."""
    pdf_path = Path(file_path)
    if not pdf_path.exists():
        logger.warning(f"PDF not found: {file_path}")
        return 0, 0

    logger.info(f"Backfilling {paper_id} ({pdf_path.name})...")

    # Extract page texts
    combined_text, offset_to_page, page_texts = build_page_text_map(pdf_path)
    total_pages = len(page_texts)
    logger.info(f"  Extracted {total_pages} pages, {len(combined_text)} chars")

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # Get all chunks for this paper
    cur.execute(
        "SELECT id, paragraph_id, text, page_number FROM chunks WHERE paper_id = ?",
        (paper_id,),
    )
    chunks = cur.fetchall()

    updated = 0
    skipped = 0

    for chunk_id, paragraph_id, text, existing_page in chunks:
        if existing_page is not None:
            skipped += 1
            continue

        page_num = find_page_for_chunk(text, combined_text, offset_to_page)
        if page_num is not None:
            cur.execute(
                "UPDATE chunks SET page_number = ? WHERE id = ?", (page_num, chunk_id)
            )
            updated += 1
        else:
            # Assign based on paragraph index as fallback
            # P0, P1, P2... are sequential paragraphs - distribute across pages
            try:
                para_idx = int(paragraph_id.split("_P")[-1])
                # Rough estimate: paragraphs per page
                if total_pages > 0:
                    page_num = min(
                        (para_idx * total_pages) // max(len(chunks), 1) + 1, total_pages
                    )
                    cur.execute(
                        "UPDATE chunks SET page_number = ? WHERE id = ?",
                        (page_num, chunk_id),
                    )
                    updated += 1
            except (ValueError, IndexError):
                pass

    conn.commit()
    conn.close()

    logger.info(f"  Updated {updated}/{len(chunks)} chunks, skipped {skipped}")
    return updated, len(chunks)


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"

    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        return

    papers = get_papers(DB_PATH)
    if not papers:
        print("No papers found.")
        return

    if arg != "all":
        papers = [p for p in papers if p["id"] == arg]
        if not papers:
            print(f"Paper {arg} not found.")
            return

    total_updated = 0
    total_chunks = 0

    for paper in papers:
        updated, count = backfill_paper(paper["id"], paper["file_path"], DB_PATH)
        total_updated += updated
        total_chunks += count

    print(f"\nTotal: {total_updated}/{total_chunks} chunks updated with page numbers")


if __name__ == "__main__":
    main()
