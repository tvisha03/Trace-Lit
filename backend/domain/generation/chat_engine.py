import time
from dataclasses import dataclass

from domain.generation.prompts import (
    SYSTEM_PROMPT,
    CHAT_PROMPT_TEMPLATE,
    COMPARISON_PROMPT_TEMPLATE,
    SUMMARY_PROMPT_TEMPLATE,
    build_context_block,
    build_history_block,
)
from domain.retrieval.query_router import classify_query
from domain.retrieval.retriever import retrieve, RetrievedChunk
from domain.verification.havf import verify_response, VerificationResult
from infrastructure.llm.fallback_chain import FallbackChain
from infrastructure.vector_store.faiss_store import FAISSStore
from app.config import get_settings
from shared.enums import LLMProvider, QueryType
from shared.logger import get_logger
from shared.utils.text_utils import estimate_tokens
from shared.utils.time_utils import timer

logger = get_logger(__name__)


def format_evaluation_output(
    data: dict,
    paper_id_short: str = "",
    paper_title: str = "",
    skip_header: bool = False,
) -> str:
    """
    Format evaluation metrics output according to the specification.
    Returns structured, clean output with tables and source citations.

    Args:
        data: Dict with task, datasets, metrics, results, baselines, training_details
        paper_id_short: Short paper ID for source citation
        paper_title: Paper title to display
        skip_header: If True, skip the main header/footer (for multi-paper context)
    """
    task = str(data.get("task") or "N/A")
    datasets = data.get("datasets") or []
    metrics = data.get("metrics") or []
    results = data.get("results") or []
    baselines = data.get("baselines") or []
    training_details = str(data.get("training_details") or "N/A")

    if isinstance(datasets, str):
        datasets = [datasets]
    if isinstance(metrics, str):
        metrics = [metrics]
    if isinstance(results, str):
        results = [results]
    if isinstance(baselines, str):
        baselines = [baselines]

    lines = []

    # Header (skip in multi-paper context)
    if not skip_header:
        lines.append("📊 EVALUATION METRICS")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

    # Paper title/header
    if paper_title:
        lines.append(f"**Paper:** {paper_title}")
        lines.append(f"**ID:** {paper_id_short}")
        lines.append("")

    # Task
    lines.append(f"**Task:** {task}")
    lines.append("")

    # Datasets
    if datasets:
        lines.append(f"**Datasets:** {', '.join(datasets)}")
        lines.append("")

    # Results table
    if results:
        lines.append("**Results:**")

        # Build table - extract model names and values from results
        # Expected format: results is list of dicts with model, metric, value, dataset
        if isinstance(results, list) and len(results) > 0:
            if isinstance(results[0], dict):
                # Filter out useless N/A or empty rows
                filtered_results = []
                for r in results:
                    if isinstance(r, dict):
                        m = str(r.get("model", "N/A"))
                        v = str(r.get("value", "N/A"))
                        if m.strip() not in ("N/A", "") or v.strip() not in ("N/A", ""):
                            filtered_results.append(r)

                if not filtered_results:
                    lines.append("- No specific structured metrics or results found in the text.")
                    lines.append("")
                else:
                    # Group by dataset
                    from collections import defaultdict

                    datasets_map = defaultdict(list)
                    for r in filtered_results:
                        ds = r.get("dataset", "Unknown") or "Unknown"
                        datasets_map[ds].append(r)

                    for ds, items in datasets_map.items():
                        # Table header
                        lines.append(f"**Dataset: {ds}**")
                        lines.append("")
                        lines.append("┌" + "─" * 30 + "┬" + "─" * 15 + "┐")
                        lines.append(f"│ Model{' ' * 26}│ Value{' ' * 10}│")
                        lines.append("├" + "─" * 30 + "┼" + "─" * 15 + "┤")

                        for item in items:
                            model = str(item.get("model", "N/A"))
                            value = str(item.get("value", "N/A"))
                            metric = str(item.get("metric", ""))
                            metric_str = f" ({metric})" if metric else ""
                            # Trim model/value to fit width exactly
                            if len(model) > 30:
                                model = model[:27] + "..."
                            if len(value) + len(metric_str) > 15:
                                value = value[:12] + "..."
                            
                            lines.append(
                                f"│ {model}{' ' * (30 - len(model))}│ {value}{metric_str}{' ' * (15 - len(str(value)) - len(metric_str))}│"
                            )

                        lines.append("└" + "─" * 30 + "┴" + "─" * 15 + "┘")
                        lines.append("")
            else:
                # Simple list of results
                for r in results:
                    lines.append(f"- {r}")
                lines.append("")

    # Metrics
    if metrics:
        lines.append(f"**Metrics:** {', '.join(metrics)}")
        lines.append("")

    # Baselines
    if baselines:
        lines.append(f"**Baselines:** {', '.join(map(str, baselines))}")
        lines.append("")

    # Training details
    if training_details and training_details != "N/A":
        lines.append(f"**Training:** {training_details}")
        lines.append("")

    # Source citation
    cite = f"[{paper_id_short}]" if paper_id_short else "[P1]"
    lines.append(f"**Source:** {cite}")
    lines.append("")

    # Footer (skip in multi-paper context)
    if not skip_header:
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    return "\n".join(lines)


@dataclass
class ChatResponse:
    content: str
    provider: LLMProvider
    havf_results: list[VerificationResult]
    retrieved_chunks: list[RetrievedChunk]
    token_count: int
    latency_ms: float


def _filter_chunks_by_keywords(
    chunks: list[RetrievedChunk],
    keywords: list[str] | None,
) -> list[RetrievedChunk]:
    if not keywords or not chunks:
        return chunks
    lower_kw = [kw.lower() for kw in keywords]
    filtered = [c for c in chunks if any(kw in c.text.lower() for kw in lower_kw)]
    # If the filter eliminates all chunks (e.g. a placeholder keyword like "string"
    # sent from Swagger UI), ignore the filter so the LLM still gets context.
    return filtered if filtered else chunks


def _build_user_prompt(
    query_type: QueryType,
    query: str,
    chunks: list[RetrievedChunk],
    history: list,
) -> str:
    context_block = build_context_block(chunks)
    history_block = build_history_block(history)

    if query_type == QueryType.COMPARISON:
        return CHAT_PROMPT_TEMPLATE.format(
            context=context_block,
            history=history_block,
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


async def _retrieve_and_filter_chunks(
    query: str,
    paper_ids: list[str],
    faiss_store: FAISSStore,
    db_session,
    classification,
    keywords: list[str] | None,
) -> list[RetrievedChunk]:
    chunks = await retrieve(
        query=query,
        paper_ids=paper_ids,
        faiss_store=faiss_store,
        db_session=db_session,
        classification=classification,
    )
    return _filter_chunks_by_keywords(chunks, keywords)


async def _verify_response_with_settings(
    response_text: str,
    chunks: list[RetrievedChunk],
) -> list[VerificationResult]:
    settings = get_settings()
    return await verify_response(
        response_text,
        chunks,
        high_threshold=settings.HAVF_HIGH_THRESHOLD,
        medium_threshold=settings.HAVF_MEDIUM_THRESHOLD,
        cross_encoder_threshold=settings.HAVF_CROSS_ENCODER_THRESHOLD,
    )


def _build_response(
    response_text: str,
    provider: LLMProvider,
    havf_results: list[VerificationResult],
    chunks: list[RetrievedChunk],
    latency_ms: float,
) -> ChatResponse:
    return ChatResponse(
        content=response_text,
        provider=provider,
        havf_results=havf_results,
        retrieved_chunks=chunks,
        token_count=estimate_tokens(response_text),
        latency_ms=latency_ms,
    )


async def generate_response(
    query: str,
    paper_ids: list[str],
    history: list,
    faiss_store: FAISSStore,
    llm: FallbackChain,
    db_session,
    keywords: list[str] | None = None,
) -> ChatResponse:
    start = time.perf_counter()

    classification = classify_query(
        query,
        history=history,
        paper_count=len(paper_ids),
    )

    if classification.query_type == QueryType.METADATA:
        return await _handle_metadata_query(
            query,
            paper_ids,
            history,
            llm,
            db_session,
            start,
        )

    query_lower = query.lower().strip()
    is_eval_query = (
        "evaluation metrics" in query_lower or 
        "experimental evaluation" in query_lower or 
        "extract evaluation" in query_lower or 
        ("metrics" in query_lower and "evaluation" in query_lower) or
        ("extract" in query_lower and "metrics" in query_lower) or
        ("summarize" in query_lower and "metrics" in query_lower) or
        ("summary" in query_lower and "evaluation" in query_lower)
    )

    if is_eval_query:
        try:
            from sqlalchemy import select
            from infrastructure.db.models.evaluation import EvaluationCache

            pids_str = ",".join(sorted(paper_ids))
            stmt = select(EvaluationCache).where(
                EvaluationCache.query == query, EvaluationCache.paper_ids == pids_str
            )
            res = await db_session.execute(stmt)
            cache_item = res.scalars().first()

            if cache_item:
                logger.info(f"Using cached evaluation metrics for query: {query}")
                chunks = await _retrieve_and_filter_chunks(
                    query,
                    paper_ids,
                    faiss_store,
                    db_session,
                    classification,
                    keywords,
                )
                havf_results = await _verify_response_with_settings(
                    cache_item.results, chunks
                )
                return _build_response(
                    cache_item.results,
                    LLMProvider.OLLAMA,
                    havf_results,
                    chunks,
                    (time.perf_counter() - start) * 1000,
                )
        except Exception as exc:
            logger.warning(f"Error reading evaluation cache: {exc}")

    chunks = await _retrieve_and_filter_chunks(
        query,
        paper_ids,
        faiss_store,
        db_session,
        classification,
        keywords,
    )

    if is_eval_query:
        try:
            # Build context from all papers
            context_text = "\n\n---\n\n".join(
                [
                    f"[Paper {i + 1}: {paper_ids[i][:8]}]\n{c.text}"
                    for i, c in enumerate(chunks)
                ]
            )

            # Get all paper titles
            paper_titles = {}
            try:
                from infrastructure.db.crud.paper_crud import get_paper

                for pid in paper_ids:
                    paper = await get_paper(db_session, pid)
                    if paper and paper.title:
                        paper_titles[pid] = paper.title
            except Exception:
                pass

            extract_prompt = f"""You are an expert academic reviewer extracting experimental evaluation details.
Analyze the following retrieved context from the paper(s):
{context_text}

For each paper, extract the following details as a JSON array:
[
  {{
    "paper_id": "paper identifier like P1, P2",
    "task": "What problem/task the paper evaluates.",
    "datasets": ["dataset1", "dataset2"],
    "metrics": ["metric1", "metric2"],
    "results": [
      {{"model": "model name", "metric": "BLEU", "dataset": "WMT14", "value": "27.3"}},
      ...
    ],
    "baselines": ["baseline1", "baseline2"],
    "training_details": "Training parameters, compute, or hardware."
  }},
  ...
]

Your response MUST be ONLY valid JSON array. Do NOT add extra text.
"""
            settings = get_settings()
            res_text, provider, _ = await llm.generate(
                system_prompt="You are a JSON extractor. Return ONLY valid JSON array.",
                user_prompt=extract_prompt,
                max_tokens=settings.OLLAMA_CLOUD_MAX_TOKENS,
            )

            import json
            import re

            match = re.search(r"\[.*\]", res_text, re.DOTALL)
            if not match:
                match = re.search(r"\{.*\}", res_text, re.DOTALL)
            if match:
                res_text = match.group(0)

            papers_data = json.loads(res_text)
            if isinstance(papers_data, dict):
                papers_data = [papers_data]

            # Format output for all papers
            formatted_parts = []
            formatted_parts.append("📊 EVALUATION METRICS ACROSS PAPERS")
            formatted_parts.append(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            formatted_parts.append("")

            for idx, data in enumerate(papers_data):
                p_id = data.get("paper_id", f"P{idx + 1}")
                p_short = p_id[:8] if len(p_id) > 8 else p_id
                paper_title = ""
                if idx < len(paper_ids):
                    paper_title = paper_titles.get(paper_ids[idx], "")

                # Paper header
                formatted_parts.append(f"PAPER {idx + 1}: {paper_title or p_short}")
                formatted_parts.append("─" * 40)

                # Use format_evaluation_output for consistent formatting
                single_paper_data = {
                    "task": data.get("task", "N/A"),
                    "datasets": data.get("datasets", []),
                    "metrics": data.get("metrics", []),
                    "results": data.get("results", []),
                    "baselines": data.get("baselines", []),
                    "training_details": data.get("training_details", "N/A"),
                }
                paper_output = format_evaluation_output(
                    single_paper_data, p_short, paper_title, skip_header=True
                )
                formatted_parts.append(paper_output)
                formatted_parts.append("")

            # Cross-paper comparison
            if len(papers_data) > 1:
                formatted_parts.append("CROSS-PAPER COMPARISON")
                formatted_parts.append("─" * 40)

                # Check for common metrics/datasets
                all_metrics_set = [set(data.get("metrics", [])) for data in papers_data]
                all_datasets_set = [
                    set(data.get("datasets", [])) for data in papers_data
                ]

                common_metrics = (
                    set.intersection(*all_metrics_set) if all_metrics_set else set()
                )
                common_datasets = (
                    set.intersection(*all_datasets_set) if all_datasets_set else set()
                )

                if common_metrics and common_datasets:
                    formatted_parts.append(
                        f"**Common metrics:** {', '.join(common_metrics)}"
                    )
                    formatted_parts.append(
                        f"**Common datasets:** {', '.join(common_datasets)}"
                    )
                    formatted_parts.append("")
                    formatted_parts.append("Direct comparison possible:")

                    # Build comparison table
                    # Get all unique models across papers
                    all_models = []
                    for data in papers_data:
                        for r in data.get("results", []):
                            m = r.get("model", "N/A")
                            if m not in all_models:
                                all_models.append(m)

                    if all_models:
                        # Header: Model | Paper 1 | Paper 2 | ...
                        header = (
                            "| Model | "
                            + " | ".join(
                                [f"Paper {i + 1}" for i in range(len(papers_data))]
                            )
                            + " |"
                        )
                        formatted_parts.append(header)
                        sep = "|---" + "|---" * len(papers_data) + "|"
                        formatted_parts.append(sep)

                        for model in all_models:
                            row = [model]
                            for data in papers_data:
                                # Find value for this model in this paper
                                val = next(
                                    (
                                        r.get("value", "N/A")
                                        for r in data.get("results", [])
                                        if r.get("model") == model
                                    ),
                                    "N/A",
                                )
                                row.append(val)
                            formatted_parts.append("| " + " | ".join(row) + " |")
                        formatted_parts.append("")
                else:
                    formatted_parts.append("**No common benchmarks across papers.**")
                    formatted_parts.append(
                        "Direct numerical comparison not meaningful."
                    )

                formatted_parts.append("")
                formatted_parts.append(
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )

            formatted_out = "\n".join(formatted_parts)

            try:
                from infrastructure.db.models.evaluation import EvaluationCache

                pids_str = ",".join(sorted(paper_ids))
                cache_entry = EvaluationCache(
                    query=query, paper_ids=pids_str, results=formatted_out
                )
                db_session.add(cache_entry)
                await db_session.commit()
            except Exception as e:
                logger.warning(f"Could not save evaluation cache entry: {e}")

            havf_results = await _verify_response_with_settings(formatted_out, chunks)
            return _build_response(
                formatted_out,
                provider,
                havf_results,
                chunks,
                (time.perf_counter() - start) * 1000,
            )
        except Exception as exc:
            logger.warning(
                f"Error in extraction pass or invalid JSON response. Falling back to regular chat generation: {exc}"
            )

    user_prompt = _build_user_prompt(
        classification.query_type,
        query,
        chunks,
        history,
    )

    with timer("LLM generation"):
        settings = get_settings()
        chat_max_tokens = settings.OLLAMA_CLOUD_MAX_TOKENS
        prompt_tokens = estimate_tokens(SYSTEM_PROMPT + user_prompt)
        estimated_total = prompt_tokens + chat_max_tokens
        response_text, provider, _ = await llm.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=chat_max_tokens,
            estimated_tokens=estimated_total,
        )

    if not response_text or not response_text.strip():
        from shared.errors import EmptyResponseError

        raise EmptyResponseError(provider.value)

    havf_results = await _verify_response_with_settings(response_text, chunks)
    latency_ms = (time.perf_counter() - start) * 1000

    return _build_response(response_text, provider, havf_results, chunks, latency_ms)


async def _gather_paper_metadata(paper_ids: list[str], db_session) -> str:
    from infrastructure.db.crud.paper_crud import get_paper

    meta_lines: list[str] = []
    for pid in paper_ids:
        paper = await get_paper(db_session, pid)
        if paper is None:
            continue
        parts = [f"[Paper {pid[:8]}]"]
        if paper.title:
            parts.append(f"Title: {paper.title}")
        if paper.authors:
            parts.append(f"Authors: {paper.authors}")
        if paper.year:
            parts.append(f"Year: {paper.year}")
        if paper.abstract:
            parts.append(f"Abstract: {paper.abstract[:500]}")
        meta_lines.append("\n".join(parts))

    return (
        "\n\n---\n\n".join(meta_lines)
        if meta_lines
        else "(No paper metadata available)"
    )


async def _handle_metadata_query(
    query: str,
    paper_ids: list[str],
    history: list,
    llm: FallbackChain,
    db_session,
    start_time: float,
) -> ChatResponse:
    meta_context = await _gather_paper_metadata(paper_ids, db_session)

    user_prompt = CHAT_PROMPT_TEMPLATE.format(
        context=meta_context,
        history=build_history_block(history),
        question=query,
    )

    with timer("LLM generation (metadata)"):
        response_text, provider, _ = await llm.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

    latency_ms = (time.perf_counter() - start_time) * 1000

    return ChatResponse(
        content=response_text,
        provider=provider,
        havf_results=[],
        retrieved_chunks=[],
        token_count=estimate_tokens(response_text),
        latency_ms=latency_ms,
    )


async def generate_comparison(
    paper_ids: list[str],
    paper_contexts: dict[str, str],
    llm: FallbackChain,
    question: str = "Compare these papers across all dimensions.",
    paper_titles: dict[str, str] | None = None,
) -> tuple[str, LLMProvider]:
    titles = paper_titles or {}
    paper_count = len(paper_ids)

    paper_listing_lines = []
    header_cols = ["Dimension"]
    for i, pid in enumerate(paper_ids, start=1):
        name = titles.get(pid, f"Paper {pid[:8]}")
        paper_listing_lines.append(f"  {i}. {name}")
        header_cols.append(f"Paper {i}: {name}")
    header_cols.append("Synthesis")
    paper_listing = "\n".join(paper_listing_lines)
    table_header = " | ".join(header_cols)
    table_separator = " | ".join(["---"] * len(header_cols))

    formatted_contexts = "\n\n---\n\n".join(
        f"Paper {i}: {titles.get(pid, pid[:8])}\n{ctx}"
        for i, (pid, ctx) in enumerate(paper_contexts.items(), start=1)
    )

    user_prompt = COMPARISON_PROMPT_TEMPLATE.format(
        paper_count=paper_count,
        paper_listing=paper_listing,
        table_header=table_header,
        table_separator=table_separator,
        paper_contexts=formatted_contexts,
        question=question,
    )

    settings = get_settings()
    prompt_tokens = estimate_tokens(SYSTEM_PROMPT + user_prompt)
    estimated_total = prompt_tokens + settings.COMPARISON_MAX_TOKENS
    response_text, provider, _ = await llm.generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        max_tokens=settings.COMPARISON_MAX_TOKENS,
        estimated_tokens=estimated_total,
    )
    return response_text, provider


async def generate_summary(
    context: str,
    llm: FallbackChain,
    question: str = "Summarize this paper.",
) -> tuple[str, LLMProvider]:
    user_prompt = SUMMARY_PROMPT_TEMPLATE.format(
        context=context,
        question=question,
    )

    settings = get_settings()
    response_text, provider, _ = await llm.generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        max_tokens=settings.OLLAMA_CLOUD_MAX_TOKENS,
    )
    return response_text, provider
