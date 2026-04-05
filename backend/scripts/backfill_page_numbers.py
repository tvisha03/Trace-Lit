"""
Backfill page_number for existing chunks.

For each paper, re-extracts the PDF to get per-page text, then maps
each chunk's text back to the page it came from.

Usage:
    cd backend
    python scripts/backfill_page_numbers.py              # All papers
    python scripts/backfill_page_numbers.py <paper_id>   # Specific paper
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from infrastructure.db.database import async_session_factory
from infrastructure.db.models.chunk import Chunk
from infrastructure.db.models.paper import Paper
from domain.extraction.pdf_processor import extract_pdf
from shared.logger import get_logger

logger = get_logger(__name__)


def find_page_for_text(text: str, page_texts: list[tuple[int, int, str]]) -> int | None:
    """Find which page a chunk's text belongs to.

    page_texts: list of (offset, page_number, page_text)
    """
    if not text or len(text) < 20:
        return None

    combined = "".join(pt[2] for pt in page_texts)

    # Try exact match
    pos = combined.find(text)
    if pos >= 0:
        for offset, page_num, ptext in page_texts:
            if offset <= pos < offset + len(ptext):
                return page_num

    # Try first 200 chars
    snippet = text[:200].strip()
    if len(snippet) > 50:
        pos = combined.find(snippet)
        if pos >= 0:
            for offset, page_num, ptext in page_texts:
                if offset <= pos < offset + len(ptext):
                    return page_num

    # Try matching first sentence
    sentences = text.split(". ")
    if sentences:
        first_sentence = sentences[0].strip()
        if len(first_sentence) > 30:
            pos = combined.find(first_sentence)
            if pos >= 0:
                for offset, page_num, ptext in page_texts:
                    if offset <= pos < offset + len(ptext):
                        return page_num

    return None


async def backfill_paper(paper_id: str, file_path: str) -> int:
    """Backfill page_number for all chunks of a single paper."""
    logger.info(f"Backfilling page_number for paper {paper_id} ({file_path})")

    try:
        extracted = extract_pdf(file_path)
    except Exception as e:
        logger.error(f"Failed to extract PDF {file_path}: {e}")
        return 0

    # Build per-page text mapping
    page_texts = []
    cumulative = 0
    for page in extracted.pages:
        page_text = getattr(page, "text", "") or ""
        page_num = getattr(page, "page_number", None)
        if page_num is not None and page_text.strip():
            page_texts.append((cumulative, page_num, page_text.strip()))
            cumulative += len(page_text)

    if not page_texts:
        logger.warning(f"No page texts found for paper {paper_id}")
        return 0

    async with async_session_factory() as session:
        result = await session.execute(select(Chunk).where(Chunk.paper_id == paper_id))
        chunks = result.scalars().all()

        updated = 0
        for chunk in chunks:
            if chunk.page_number is not None:
                continue

            page_num = find_page_for_text(chunk.text, page_texts)
            if page_num is not None:
                chunk.page_number = page_num
                updated += 1

        if updated > 0:
            await session.commit()
            logger.info(f"Updated {updated}/{len(chunks)} chunks for paper {paper_id}")
        else:
            logger.info(f"No chunks needed updating for paper {paper_id}")

        return updated


async def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"

    async with async_session_factory() as session:
        if arg == "all":
            result = await session.execute(select(Paper))
            papers = result.scalars().all()
        else:
            result = await session.execute(select(Paper).where(Paper.id == arg))
            papers = result.scalars().all()

    if not papers:
        print("No papers found.")
        return

    total_updated = 0
    for paper in papers:
        file_path = getattr(paper, "file_path", None)
        if not file_path or not Path(file_path).exists():
            logger.warning(f"File not found for paper {paper.id}: {file_path}")
            continue

        updated = await backfill_paper(paper.id, file_path)
        total_updated += updated

    print(f"\nTotal chunks updated: {total_updated}")


if __name__ == "__main__":
    asyncio.run(main())
