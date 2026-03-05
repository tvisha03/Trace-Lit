from domain.verification.havf import verify_response
from domain.retrieval.retriever import retrieve
from infrastructure.vector_store.faiss_store import FAISSStore
from app.config import get_settings
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

    settings = get_settings()
    havf_results = await verify_response(
        text,
        chunks,
        high_threshold=settings.HAVF_HIGH_THRESHOLD,
        medium_threshold=settings.HAVF_MEDIUM_THRESHOLD,
        cross_encoder_threshold=settings.HAVF_CROSS_ENCODER_THRESHOLD,
    )

    return [
        {
            "claim": r.claim,
            "confidence": r.confidence.value,
            "score": r.score,
            "source_sentence": r.source_sentence,
            "paragraph_id": r.paragraph_id,
            "paper_id": r.paper_id,
            "sentence_key": r.sentence_key,
            "verification_method": r.verification_method.value if r.verification_method else None,
            "chunk_type": r.chunk_type,
            "citation_ref": r.citation_ref,
        }
        for r in havf_results
    ]

