from domain.verification.havf import verify_response
from domain.retrieval.retriever import retrieve
from infrastructure.vector_store.faiss_store import FAISSStore
from shared.logger import get_logger

logger = get_logger(__name__)

async def verify_text_against_papers(
    text: str,
    paper_ids: list[str],
    faiss_store: FAISSStore,
    db_session,
) -> list[dict]:
    chunks = await retrieve(
        query=text,
        paper_ids=paper_ids,
        faiss_store=faiss_store,
        db_session=db_session,
    )

    havf_results = await verify_response(text, chunks)

    return [
        {
            "claim": r.claim,
            "confidence": r.confidence.value,
            "score": r.score,
            "source_sentence": r.source_sentence,
            "paragraph_id": r.paragraph_id,
            "sentence_key": r.sentence_key,
        }
        for r in havf_results
    ]
