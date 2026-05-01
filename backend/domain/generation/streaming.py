from __future__ import annotations

import json
from typing import AsyncGenerator, Tuple

from infrastructure.llm.fallback_chain import FallbackChain
from shared.enums import LLMProvider, QueryType
from domain.generation.prompts import (
    SYSTEM_PROMPT,
    CHAT_PROMPT_TEMPLATE,
    COMPARISON_PROMPT_TEMPLATE,
    SUMMARY_PROMPT_TEMPLATE,
    build_context_block,
    build_history_block,
)
from domain.retrieval.retriever import retrieve
from domain.retrieval.query_router import classify_query, QueryClassification
from infrastructure.vector_store.faiss_store import FAISSStore
from shared.utils.streaming_utils import sse_event
from shared.logger import get_logger

logger = get_logger(__name__)

import re as _re
from shared.utils.text_utils import extract_paragraph_ids, normalize_paragraph_ids


def _validate_and_strip_citations(
    full_text: str,
    chunks: list,
    session_id: str,
) -> tuple[str, bool]:
    valid_pids = {c.paragraph_id for c in chunks}
    raw_cited = set(extract_paragraph_ids(full_text))

    cited_ids, short_to_long = normalize_paragraph_ids(raw_cited, valid_pids)
    for short_id, long_id in short_to_long.items():
        full_text = full_text.replace(f"[{short_id}]", f"[{long_id}]")

    invalid_ids = cited_ids - valid_pids
    if invalid_ids:
        logger.warning(
            f"Streaming response for session {session_id} cites non-existent "
            f"paragraphs {invalid_ids}. Stripping them before HAVF."
        )
        for bad_id in invalid_ids:
            full_text = full_text.replace(f"[{bad_id}]", "")
        full_text = _re.sub(r"  +", " ", full_text).strip()

    has_citations = bool(extract_paragraph_ids(full_text))
    if not has_citations:
        logger.warning(
            f"LLM response for session {session_id} contains no [P#]/[F#]/[T#]/[E#] citations. "
            "HAVF will have no citation targets — confidence scores may be unreliable."
        )
    return full_text, has_citations


def _clean_final_text(text: str) -> str:
    """Clean up common LLM artifacts like multiple commas or trailing separators."""
    # Remove multiple commas (e.g., ",,,")
    text = _re.sub(r",\s*,+", ", ", text)
    # Remove multiple commas before a period (e.g., ",,,.")
    text = _re.sub(r",+\s*\.", ".", text)
    # Remove multiple periods
    text = _re.sub(r"\.\.+", ".", text)
    # Clean up whitespace around commas
    text = _re.sub(r"\s+,\s+", ", ", text)
    return text.strip()


async def _emit_havf_results(full_text: str, chunks: list, paper_ids: list[str], db_session):
    from domain.verification.havf import verify_response
    from app.config import get_settings
    from infrastructure.db.crud.chunk_crud import get_chunk_by_paragraph_id
    from domain.retrieval.retriever import _chunk_to_retrieved

    # AUGMENTATION: Ensure every cited paragraph ID is present
    raw_cited = set(extract_paragraph_ids(full_text))
    existing_pids = {c.paragraph_id for c in chunks}
    missing_pids = raw_cited - existing_pids

    if missing_pids:
        logger.info(f"Streaming HAVF Augmentation: Fetching {len(missing_pids)} missing cited paragraphs")
        for pid in missing_pids:
            target_paper = next((p for p in paper_ids if pid.startswith(p[:8])), None)
            if target_paper:
                chunk = await get_chunk_by_paragraph_id(db_session, target_paper, pid)
                if chunk:
                    chunks.append(_chunk_to_retrieved(chunk, score=0.9))

    settings = get_settings()
    havf_results = await verify_response(
        full_text,
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
            "bbox": r.bbox,
            "full_context": r.full_context,
        }
        for r in havf_results
    ]


def _strip_duplicate_prefix(accumulated: str, new_chunk: str) -> str:
    if not accumulated or not new_chunk:
        return new_chunk

    if new_chunk.startswith(accumulated):
        stripped = new_chunk[len(accumulated) :]
        if stripped:
            logger.info(
                f"Duplicate token detection: stripped {len(accumulated)} chars "
                f"of duplicate prefix after provider switch"
            )
        return stripped

    max_overlap = min(len(accumulated), len(new_chunk))
    for overlap_len in range(max_overlap, 0, -1):
        if accumulated.endswith(new_chunk[:overlap_len]):
            stripped = new_chunk[overlap_len:]
            logger.info(
                f"Duplicate token detection: stripped {overlap_len} chars "
                f"of overlapping prefix after provider switch"
            )
            return stripped

    return new_chunk


async def _stream_tokens(
    llm: FallbackChain, user_prompt: str
) -> AsyncGenerator[Tuple[str, LLMProvider], None]:
    full_text = ""
    current_provider: LLMProvider | None = None

    async for token, provider_obj in llm.generate_streaming(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
    ):
        if current_provider is not None and provider_obj != current_provider:
            logger.info(
                f"Provider switch mid-stream: {current_provider.value} → {provider_obj.value}"
            )
            token = _strip_duplicate_prefix(full_text, token)
            if not token:
                current_provider = provider_obj
                continue

        current_provider = provider_obj
        full_text += token
        yield (token, provider_obj)


async def _classify_and_validate_query(
    query: str,
    paper_count: int,
    history: list,
) -> QueryClassification:
    try:
        return classify_query(query, history=history, paper_count=paper_count)
    except Exception as exc:
        logger.error(f"Query classification failed: {exc}")
        raise


def _apply_keyword_filter(chunks: list, keywords: list[str] | None) -> list:
    """Return *chunks* filtered to those mentioning any keyword.

    Falls back to the full unfiltered list when the filter would eliminate
    everything (e.g. a Swagger UI placeholder keyword like ``"string"``).
    """
    if not keywords or not chunks:
        return chunks
    lower_kw = [kw.lower() for kw in keywords]
    filtered = [c for c in chunks if any(kw in c.text.lower() for kw in lower_kw)]
    return filtered if filtered else chunks


async def _retrieve_and_filter_chunks(
    query: str,
    paper_ids: list[str],
    faiss_store: FAISSStore,
    db_session,
    classification,
    keywords: list[str] | None = None,
) -> list:
    try:
        chunks = await retrieve(
            query=query,
            paper_ids=paper_ids,
            faiss_store=faiss_store,
            db_session=db_session,
            classification=classification,
        )
    except Exception as exc:
        logger.error(f"Retrieval failed during streaming: {exc}")
        raise

    return _apply_keyword_filter(chunks, keywords)


async def _persist_response(
    session_id: str,
    full_text: str,
    provider: str,
    havf_data: list,
) -> None:
    try:
        from infrastructure.db.database import async_session_factory
        from infrastructure.db.crud.message_crud import create_message
        from shared.enums import MessageRole

        async with async_session_factory() as db:
            await create_message(
                db,
                session_id=session_id,
                role=MessageRole.ASSISTANT,
                content=full_text,
                provider=provider,
                havf_results=havf_data,
            )
            await db.commit()
    except Exception as exc:
        logger.error(
            f"Failed to persist streaming assistant message for session {session_id}: {exc}"
        )


async def _build_streaming_prompt(
    classification: QueryClassification,
    query: str,
    chunks: list,
    history: list,
    paper_ids: list[str],
    db_session,
) -> str:
    context_block = build_context_block(chunks)
    history_block = build_history_block(history)
    query_type = classification.query_type

    if query_type == QueryType.COMPARISON:
        from infrastructure.db.crud.paper_crud import get_paper
        paper_titles = {}
        for pid in paper_ids:
            p = await get_paper(db_session, pid)
            paper_titles[pid] = p.title if p and p.title else f"Paper {pid[:8]}"
        
        paper_count = len(paper_ids)
        paper_listing_lines = [f"  {i+1}. {paper_titles[pid]}" for i, pid in enumerate(paper_ids)]
        paper_listing = "\n".join(paper_listing_lines)
        
        header_cols = ["Dimension"]
        for i, pid in enumerate(paper_ids):
            header_cols.append(f"Paper {i+1}: {paper_titles[pid]}")
        header_cols.append("Synthesis")
        
        table_header = " | ".join(header_cols)
        table_separator = " | ".join(["---"] * len(header_cols))

        return COMPARISON_PROMPT_TEMPLATE.format(
            paper_count=paper_count,
            paper_listing=paper_listing,
            table_header=table_header,
            table_separator=table_separator,
            paper_contexts=context_block,
            question=query,
        )
    
    if query_type == QueryType.SUMMARY:
        return SUMMARY_PROMPT_TEMPLATE.format(
            context=context_block,
            question=query,
        )
        
    return CHAT_PROMPT_TEMPLATE.format(
        context=context_block,
        history=history_block,
        question=query,
    )


async def stream_chat_response(
    query: str,
    paper_ids: list[str],
    history: list,
    faiss_store: FAISSStore,
    llm: FallbackChain,
    db_session,
    session_id: str,
    keywords: list[str] | None = None,
) -> AsyncGenerator[str, None]:
    try:
        EVAL_KEYWORDS = {
            "accuracy", "bleu", "f1", "precision", "recall", "perplexity", "auc",
            "rouge", "benchmark", "dataset", "evaluation", "performance", "score",
            "results", "compared", "achieved"
        }
        is_eval_query = any(kw in query.lower() for kw in EVAL_KEYWORDS)

        classification = await _classify_and_validate_query(
            query, len(paper_ids), history
        )
        yield sse_event(
            "query_type", json.dumps({"type": classification.query_type.value})
        )

        chunks = await _retrieve_and_filter_chunks(
            query, paper_ids, faiss_store, db_session, classification, keywords
        )

        if is_eval_query:
            try:
                from sqlalchemy import select
                from infrastructure.db.models.evaluation import EvaluationCache

                pids_str = ",".join(sorted(paper_ids))
                stmt = select(EvaluationCache).where(
                    EvaluationCache.query == query,
                    EvaluationCache.paper_ids == pids_str
                )
                res = await db_session.execute(stmt)
                cache_item = res.scalars().first()

                if cache_item:
                    logger.info(f"Using cached evaluation metrics in stream for query: {query}")
                    yield sse_event(
                        "sources",
                        json.dumps([
                            {
                                "paragraph_id": c.paragraph_id,
                                "paper_id": c.paper_id,
                                "score": c.score,
                                "page_number": c.page_number,
                                "bbox": list(c.bbox) if getattr(c, "bbox", None) and isinstance(c.bbox, (list, tuple)) else None,
                                "chunk_type": getattr(c, "chunk_type", "text"),
                            }
                            for c in chunks
                        ]),
                    )
                    # Emit tokens and HAVF data
                    for token in cache_item.results:
                        yield sse_event("token", {"token": token})
                    
                    havf_data = await _emit_havf_results(cache_item.results, chunks, paper_ids, db_session)
                    yield sse_event("havf", json.dumps(havf_data))
                    yield sse_event(
                        "done", json.dumps({"provider": "ollama", "full_text": cache_item.results})
                    )
                    await _persist_response(session_id, cache_item.results, "ollama", havf_data)
                    return
            except Exception as e:
                logger.warning(f"Error in streaming evaluation cache lookup: {e}")

        # If not cached but is an eval query, perform extraction
        if is_eval_query:
            try:
                from domain.generation.chat_engine import format_evaluation_output
                from app.config import get_settings
                context_text = "\n".join([c.text for c in chunks])
                extract_prompt = f"""You are an expert academic reviewer extracting experimental evaluation details.
Analyze the following retrieved context from the paper:
{context_text}

Extract the following details from the paper as a clean JSON object:
- task: What problem/task the paper evaluates.
- datasets: The datasets used.
- metrics: The evaluation metrics used (e.g., BLEU, accuracy, perplexity).
- results: The main experimental results achieved by the paper's method.
- baselines: What baselines/previous models the paper compares against.
- training_details: Training parameters, compute, or hardware mentioned.

Your response MUST be ONLY valid JSON with keys: 'task', 'datasets', 'metrics', 'results', 'baselines', 'training_details'. Do NOT add extra text.
"""
                settings = get_settings()
                res_text, provider, _ = await llm.generate(
                    system_prompt="You are a JSON extractor. Return ONLY valid JSON.",
                    user_prompt=extract_prompt,
                    max_tokens=settings.OLLAMA_CLOUD_MAX_TOKENS,
                )

                import re
                match = re.search(r'\{.*\}', res_text, re.DOTALL)
                if match:
                    res_text = match.group(0)

                data = json.loads(res_text)
                p_short = paper_ids[0][:8] if paper_ids else "P1"
                formatted_out = format_evaluation_output(data, p_short)

                # Cache extraction results
                try:
                    from infrastructure.db.models.evaluation import EvaluationCache
                    pids_str = ",".join(sorted(paper_ids))
                    cache_entry = EvaluationCache(
                        query=query,
                        paper_ids=pids_str,
                        results=formatted_out
                    )
                    db_session.add(cache_entry)
                    await db_session.commit()
                except Exception as e:
                    logger.warning(f"Could not save evaluation cache entry: {e}")

                yield sse_event(
                    "sources",
                    json.dumps([
                        {
                            "paragraph_id": c.paragraph_id,
                            "paper_id": c.paper_id,
                            "score": c.score,
                            "page_number": c.page_number,
                            "bbox": list(c.bbox) if getattr(c, "bbox", None) and isinstance(c.bbox, (list, tuple)) else None,
                            "chunk_type": getattr(c, "chunk_type", "text"),
                        }
                        for c in chunks
                    ]),
                )
                for token in formatted_out:
                    yield sse_event("token", {"token": token})

                havf_data = await _emit_havf_results(formatted_out, chunks, paper_ids, db_session)
                yield sse_event("havf", json.dumps(havf_data))
                yield sse_event(
                    "done", json.dumps({"provider": provider.value, "full_text": formatted_out})
                )
                await _persist_response(session_id, formatted_out, provider.value, havf_data)
                return
            except Exception as e:
                logger.warning(f"Error in streaming extraction pass. Falling back: {e}")

        yield sse_event(
            "sources",
            json.dumps(
                [
                    {
                        "paragraph_id": c.paragraph_id,
                        "paper_id": c.paper_id,
                        "score": c.score,
                        "page_number": c.page_number,
                        "bbox": list(c.bbox) if getattr(c, "bbox", None) and isinstance(c.bbox, (list, tuple)) else None,
                        "chunk_type": getattr(c, "chunk_type", "text"),
                    }
                    for c in chunks

                ]
            ),
        )

        user_prompt = await _build_streaming_prompt(
            classification, query, chunks, history, paper_ids, db_session
        )

        full_text = ""
        provider = ""
        async for token, provider_obj in _stream_tokens(llm, user_prompt):
            full_text += token
            provider = provider_obj.value
            yield sse_event("token", {"token": token})

        resolved_provider = provider or "unknown"
        full_text, has_citations = _validate_and_strip_citations(
            full_text, chunks, session_id
        )

        if not has_citations:
            # Keep the LLM's actual answer — appending a disclaimer is far more
            # useful than replacing the whole response with an opaque apology.
            disclaimer = (
                "\n\n---\n"
                "_⚠️ Note: This response could not be automatically attributed to specific "
                "sections of the uploaded papers. Please verify the information independently._"
            )
            full_text = full_text.strip() + disclaimer
            yield sse_event(
                "warning",
                json.dumps(
                    {
                        "detail": "Citations absent or invalid — answer shown with unverified disclaimer."
                    }
                ),
            )

        havf_data = await _emit_havf_results(full_text, chunks, paper_ids, db_session)
        
        # FINAL CLEANUP: strip artifacts before finalizing
        full_text = _clean_final_text(full_text)
        
        yield sse_event("havf", json.dumps(havf_data))
        yield sse_event(
            "done", json.dumps({"provider": resolved_provider, "full_text": full_text})
        )

        await _persist_response(
            session_id, full_text, resolved_provider, havf_data
        )

    except Exception as exc:
        logger.error(f"Streaming error: {exc}")
        yield sse_event("error", str(exc))
        yield sse_event(
            "done", json.dumps({"provider": "", "full_text": "", "error": True})
        )
