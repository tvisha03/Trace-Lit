"""
Full pipeline diagnostic: traces query → FAISS → DB chunks → HAVF sources.
"""
import asyncio
import sys
import os

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import get_settings
from infrastructure.db.database import async_session_factory
from infrastructure.vector_store.faiss_store import FAISSStore
from domain.retrieval.indexer import encode_query
from domain.retrieval.retriever import retrieve, RetrievedChunk
from domain.retrieval.query_router import classify_query
from domain.verification.havf import build_source_sentences, _extract_chunk_sources
from infrastructure.db.crud.chunk_crud import get_chunks_by_paper

SESSION_ID = "13dac798-4080-4be8-b2b7-2d5c983070ea"
TEST_QUERY = "Explain the main idea of the paper"


async def main():
    settings = get_settings()

    # Step 1: Get paper_ids for the session
    print("=" * 70)
    print("STEP 1: Get paper_ids for session")
    print("=" * 70)
    async with async_session_factory() as db:
        from sqlalchemy import text
        result = await db.execute(
            text("SELECT id FROM papers WHERE session_id = :sid AND status = 'COMPLETED'"),
            {"sid": SESSION_ID},
        )
        rows = result.fetchall()
        paper_ids = [str(r[0]) for r in rows]
        print(f"Session {SESSION_ID} has {len(paper_ids)} papers: {paper_ids}")

        if not paper_ids:
            print("ERROR: No papers found for session!")
            return

    # Step 2: Load FAISS index
    print("\n" + "=" * 70)
    print("STEP 2: Load FAISS index")
    print("=" * 70)
    faiss_store = FAISSStore()
    faiss_store.load_or_create()
    print(f"FAISS index has {faiss_store._index.ntotal} vectors, {len(faiss_store._id_map)} ids")

    # Check which paper_ids are in FAISS
    faiss_paper_ids = set()
    for composite_id in faiss_store._id_map:
        pid = composite_id.split("::")[0]
        faiss_paper_ids.add(pid)
    print(f"FAISS contains paper_ids: {faiss_paper_ids}")
    for pid in paper_ids:
        if pid in faiss_paper_ids:
            count = sum(1 for x in faiss_store._id_map if x.startswith(pid + "::"))
            print(f"  ✅ {pid}: {count} vectors")
        else:
            print(f"  ❌ {pid}: NOT IN FAISS")

    # Step 3: Raw FAISS search
    print("\n" + "=" * 70)
    print("STEP 3: Raw FAISS search")
    print("=" * 70)
    query_vector = encode_query(TEST_QUERY)
    results = faiss_store.search(query_vector[0], paper_ids, top_k_per_paper=10)
    print(f"FAISS returned {len(results)} results:")
    for r in results[:5]:
        print(f"  paper={r['paper_id'][:8]}.. para={r['paragraph_id']} score={r['score']:.4f}")
    if not results:
        print("ERROR: FAISS returned zero results!")
        return

    # Step 4: Full retrieve() call
    print("\n" + "=" * 70)
    print("STEP 4: Full retrieve() call")
    print("=" * 70)
    async with async_session_factory() as db:
        classification = classify_query(TEST_QUERY, paper_count=len(paper_ids))
        print(f"Query classified as: {classification.query_type}")
        chunks = await retrieve(
            query=TEST_QUERY,
            paper_ids=paper_ids,
            faiss_store=faiss_store,
            db_session=db,
            classification=classification,
        )
        print(f"retrieve() returned {len(chunks)} RetrievedChunk objects")

        if not chunks:
            print("ERROR: retrieve() returned empty!")
            return

        # Step 5: Inspect RetrievedChunks
        print("\n" + "=" * 70)
        print("STEP 5: Inspect RetrievedChunks")
        print("=" * 70)
        total_sentences = 0
        empty_maps = 0
        for i, chunk in enumerate(chunks):
            smap = chunk.sentence_map
            n_sentences = len(smap) if isinstance(smap, dict) else 0
            total_sentences += n_sentences
            if n_sentences == 0:
                empty_maps += 1
            if i < 5:
                print(
                    f"  Chunk {i}: para={chunk.paragraph_id}, "
                    f"type={chunk.chunk_type}, "
                    f"sentence_map type={type(smap).__name__}, "
                    f"sentences={n_sentences}, "
                    f"score={chunk.score:.4f}, "
                    f"text[:80]={chunk.text[:80]!r}"
                )
        print(f"\nTotal sentences across {len(chunks)} chunks: {total_sentences}")
        print(f"Chunks with empty sentence_map: {empty_maps}/{len(chunks)}")

        # Step 6: Extract sources via HAVF
        print("\n" + "=" * 70)
        print("STEP 6: build_source_sentences() on retrieved chunks")
        print("=" * 70)
        sources = build_source_sentences(chunks)
        print(f"build_source_sentences() returned {len(sources)} sources")

        if not sources:
            # Dig deeper: check each chunk individually
            print("\nDEBUG: Checking each chunk individually...")
            for i, chunk in enumerate(chunks):
                chunk_sources = _extract_chunk_sources(chunk)
                smap = chunk.sentence_map
                print(
                    f"  Chunk {i} ({chunk.paragraph_id}): "
                    f"sentence_map keys={list(smap.keys())[:3] if isinstance(smap, dict) else 'N/A'}, "
                    f"extracted={len(chunk_sources)} sources"
                )
                if isinstance(smap, dict) and smap:
                    # Show first sentence details
                    first_key = next(iter(smap))
                    first_info = smap[first_key]
                    print(f"    First sentence: key={first_key}, info type={type(first_info).__name__}")
                    if isinstance(first_info, dict):
                        print(f"    Keys: {list(first_info.keys())}")
                        text = first_info.get("text", "")
                        print(f"    Text: {text[:100]!r}")
                    else:
                        print(f"    Raw value: {first_info!r}")
        else:
            print(f"First 3 sources:")
            for s in sources[:3]:
                print(f"  para={s['paragraph_id']}, text={s['text'][:100]!r}")

        # Step 7: Cross-check with direct DB lookup
        print("\n" + "=" * 70)
        print("STEP 7: Direct DB chunk comparison")
        print("=" * 70)
        for pid in paper_ids[:1]:  # Just check first paper
            db_chunks = await get_chunks_by_paper(db, pid)
            # Pick same paragraph_ids as retrieved
            retrieved_para_ids = {c.paragraph_id for c in chunks if c.paper_id == pid}
            print(f"Retrieved para_ids for paper {pid[:8]}: {retrieved_para_ids}")
            for db_chunk in db_chunks:
                if db_chunk.paragraph_id in retrieved_para_ids:
                    db_smap = db_chunk.sentence_map
                    print(
                        f"  DB chunk {db_chunk.paragraph_id}: "
                        f"sentence_map type={type(db_smap).__name__}, "
                        f"len={len(db_smap) if isinstance(db_smap, dict) else 'N/A'}"
                    )

    print("\n" + "=" * 70)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
