"""TraceLit — HAVF Runner.

Async facade over HAVFVerifier.verify_response,
shared by chat endpoints (non-streaming and streaming).
"""

from typing import Any, Dict, List

from loguru import logger

from api.v1.schemas import CitationSource, SentenceVerification
from domain.verification.havf import (
    HAVFVerifier,
    build_cited_paragraphs_map,
    get_havf,
    parse_response_into_sentences,
)


async def run_havf_verification(
    response_text: str,
    context_paragraphs: List[Dict[str, Any]],
) -> List[SentenceVerification]:
    """Verify every sentence in a generated response.

    Args:
        response_text: Complete LLM response string.
        context_paragraphs: Context paragraphs used for this query.

    Returns:
        List of SentenceVerification with sentence-level confidence scores.
    """
    para_map = build_cited_paragraphs_map(context_paragraphs)
    parsed = parse_response_into_sentences(response_text)
    if not parsed:
        return []

    havf = get_havf()

    try:
        havf_results = await havf.verify_response(parsed, para_map)
    except Exception as exc:
        logger.error("HAVF verification failed: {}", exc, exc_info=True)
        return _build_placeholder_verifications(parsed, para_map)

    return _havf_results_to_verifications(havf_results, para_map)


def _havf_results_to_verifications(
    havf_results: List[Dict],
    para_map: Dict[str, Dict],
) -> List[SentenceVerification]:
    import re
    citation_pattern = re.compile(r"\[P(\d+)\]")
    results = []
    for hr in havf_results:
        pid = hr.get("paragraph_id", "")
        sid = hr.get("sentence_id", "")
        para = para_map.get(pid, {})
        sources = []
        if pid and para:
            sources.append(CitationSource(
                paragraph_id=pid,
                sentence_id=sid or f"{pid}_S0",
                paper_id=para.get("paper_id", ""),
                paper_title=para.get("paper_title", ""),
                section=para.get("section", ""),
                page=para.get("page", 0),
                matched_text=hr.get("matched_text", "")[:300],
            ))
        sent_text = hr.get("text", "")
        cited_ids = [f"P{m}" for m in citation_pattern.findall(sent_text)]
        results.append(SentenceVerification(
            text=sent_text,
            citations=cited_ids,
            confidence=hr.get("confidence", 0.0),
            level=hr.get("level", "low"),
            method=hr.get("method", "unknown"),
            sources=sources,
        ))
    return results


def _build_placeholder_verifications(
    parsed_sentences: List[Dict],
    para_map: Dict[str, Dict],
) -> List[SentenceVerification]:
    """Graceful degradation when HAVF is unavailable."""
    import re
    citation_pattern = re.compile(r"\[P(\d+)\]")
    results = []
    for sent in parsed_sentences:
        cited_ids = sent.get("citations", [])
        sources = []
        for pid in cited_ids:
            para = para_map.get(pid, {})
            if para:
                sources.append(CitationSource(
                    paragraph_id=pid,
                    sentence_id=f"{pid}_S0",
                    paper_id=para.get("paper_id", ""),
                    paper_title=para.get("paper_title", ""),
                    section=para.get("section", ""),
                    page=para.get("page", 0),
                    matched_text=para.get("text", "")[:200],
                ))
        if cited_ids and all(pid in para_map for pid in cited_ids):
            confidence, level, method = 0.7, "medium", "citation_present"
        elif cited_ids:
            confidence, level, method = 0.4, "low", "citation_unmatched"
        else:
            confidence, level, method = 0.3, "low", "no_citation"

        results.append(SentenceVerification(
            text=sent.get("text", ""),
            citations=[f"P{m}" for m in citation_pattern.findall(sent.get("text", ""))],
            confidence=confidence,
            level=level,
            method=method,
            sources=sources,
        ))
    return results
