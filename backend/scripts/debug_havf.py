"""Diagnostic script to check why HAVF reports no source sentences."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.db.database import async_session_factory
from sqlalchemy import text


async def check():
    async with async_session_factory() as db:
        # Get sessions
        result = await db.execute(text("SELECT id FROM sessions"))
        sessions = result.fetchall()
        print(f"Sessions: {[str(s[0]) for s in sessions]}")

        if not sessions:
            print("No sessions found!")
            return

        # Use the session from the logs that had papers
        session_id = "13dac798-4080-4be8-b2b7-2d5c983070ea"
        print(f"\nUsing session: {session_id}")

        # Get papers
        result = await db.execute(
            text(f"SELECT id, filename, status FROM papers WHERE session_id = :sid"),
            {"sid": session_id},
        )
        papers = result.fetchall()
        print(f"Papers: {[(str(p[0])[:8], p[1], p[2]) for p in papers]}")

        if not papers:
            print("No papers!")
            return

        for paper in papers:
            paper_id = str(paper[0])
            print(f"\n--- Paper: {paper[1]} ({paper_id[:8]}...) status={paper[2]}")

            result = await db.execute(
                text(
                    "SELECT paragraph_id, chunk_type, sentence_map, "
                    "length(text) as text_len, sentence_embeddings IS NOT NULL as has_emb "
                    "FROM chunks WHERE paper_id = :pid LIMIT 5"
                ),
                {"pid": paper_id},
            )
            chunks = result.fetchall()
            print(f"  Total sample chunks: {len(chunks)}")

            for c in chunks:
                para_id, ctype, smap, text_len, has_emb = c
                print(f"\n  Chunk: paragraph_id={para_id}, type={ctype}, text_len={text_len}, has_embeddings={has_emb}")
                print(f"    sentence_map raw type: {type(smap)}")
                if smap is None:
                    print("    sentence_map is NULL!")
                elif isinstance(smap, str):
                    print(f"    sentence_map is STRING (len={len(smap)}): {smap[:200]}")
                elif isinstance(smap, dict):
                    keys = list(smap.keys())
                    print(f"    sentence_map has {len(keys)} keys: {keys[:3]}")
                    if keys:
                        first = smap[keys[0]]
                        print(f"    First entry: {first}")
                else:
                    print(f"    sentence_map is {type(smap)}: {str(smap)[:200]}")

        # Now test the HAVF pipeline directly
        print("\n\n=== Testing HAVF source extraction ===")
        from infrastructure.db.crud.chunk_crud import get_chunks_by_paper
        from domain.verification.havf import build_source_sentences, _extract_chunk_sources

        paper_id = str(papers[0][0])
        db_chunks = await get_chunks_by_paper(db, paper_id)
        print(f"\nDB chunks loaded: {len(db_chunks)}")

        if db_chunks:
            chunk = db_chunks[0]
            print(f"\nFirst chunk details:")
            print(f"  type(chunk): {type(chunk)}")
            print(f"  paragraph_id: {chunk.paragraph_id}")
            print(f"  chunk_type: {chunk.chunk_type}")
            smap = chunk.sentence_map
            print(f"  sentence_map type: {type(smap)}")
            print(f"  sentence_map is None: {smap is None}")
            if isinstance(smap, dict):
                print(f"  sentence_map keys: {len(smap)}")
            elif isinstance(smap, str):
                print(f"  sentence_map is string (len={len(smap)}): {smap[:200]}")

            # Test extraction
            sources = _extract_chunk_sources(chunk)
            print(f"  Extracted sources: {len(sources)}")
            if sources:
                print(f"  First source: {sources[0]}")

        # Test full pipeline
        all_sources = build_source_sentences(db_chunks)
        print(f"\nTotal source sentences from all chunks: {len(all_sources)}")
        if all_sources:
            print(f"  Sample: {all_sources[0]}")
        else:
            print("  NO SOURCES! This is the bug.")
            # Debug deeper
            for i, chunk in enumerate(db_chunks[:5]):
                smap = chunk.sentence_map
                raw_paper_id = getattr(chunk, "paper_id", None)
                print(f"\n  Debug chunk {i}: paragraph_id={chunk.paragraph_id}")
                print(f"    paper_id type: {type(raw_paper_id)}, val: {raw_paper_id}")
                print(f"    sentence_map: type={type(smap)}, truthy={bool(smap)}")
                if isinstance(smap, dict) and smap:
                    for sk, sv in list(smap.items())[:2]:
                        print(f"    sentence '{sk}': {sv}")


if __name__ == "__main__":
    asyncio.run(check())
