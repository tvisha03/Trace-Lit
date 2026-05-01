from domain.verification.havf import verify_response
from domain.retrieval.retriever import retrieve
from domain.retrieval.query_router import QueryClassification
from shared.enums import QueryType
from shared.constants import FAISS_TOP_K_PER_PAPER
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
    # Force SIMPLE_QA classification so that query_router never skips retrieval.
    # Without this, text that looks like a metadata query (e.g. "What is the title?")
    # makes retrieve() bail early with empty results → every claim gets LOW confidence.
    forced = QueryClassification(
        query_type=QueryType.SIMPLE_QA,
        confidence=1.0,
        balanced=True,
        # Fetch more chunks per paper so HAVF has broad coverage to match against
        retrieval_top_k=FAISS_TOP_K_PER_PAPER * max(len(paper_ids), 1),
    )
    chunks = await retrieve(
        query=text,
        paper_ids=paper_ids,
        faiss_store=faiss_store,
        db_session=db_session,
        classification=forced,
    )

    # AUGMENTATION: Ensure every cited paragraph ID is present in the context
    from shared.utils.text_utils import extract_paragraph_ids
    from infrastructure.db.crud.chunk_crud import get_chunk_by_paragraph_id
    from domain.retrieval.retriever import _chunk_to_retrieved

    cited_ids = set(extract_paragraph_ids(text))
    existing_ids = {c.paragraph_id for c in chunks}
    missing_ids = cited_ids - existing_ids

    if missing_ids:
        logger.info(f"HAVF Augmentation: Fetching {len(missing_ids)} missing cited paragraphs from DB")
        for pid in missing_ids:
            target_paper = next((p for p in paper_ids if pid.startswith(p[:8])), None)
            if target_paper:
                chunk = await get_chunk_by_paragraph_id(db_session, target_paper, pid)
                if chunk:
                    chunks.append(_chunk_to_retrieved(chunk, score=0.9))

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
            "verification_method": r.verification_method.value
            if r.verification_method
            else None,
            "chunk_type": r.chunk_type,
            "citation_ref": r.citation_ref,
            "page_number": r.page_number,
        }
        for r in havf_results
    ]
