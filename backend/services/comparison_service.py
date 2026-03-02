"""TraceLit — Comparison Service.

Business logic for the comparison table: extraction, storage, retrieval, updates.
"""

import json
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session as DBSession

from domain.analysis.comparison_engine import (
    extract_paper_contributions,
    generate_comparison_table,
)
from infrastructure.db.models.paper import Contribution, Paper


async def get_comparison_for_session(
    session_id: str,
    db: DBSession,
) -> Dict[str, Any]:
    """Get existing comparison data for a session.

    Retrieves stored contributions for all papers in the session.
    """
    from infrastructure.db.models.session import Session as SessionModel

    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        return {"session_id": session_id, "contributions": [], "rows": []}

    paper_ids = []
    if session.paper_ids:
        try:
            paper_ids = json.loads(session.paper_ids)
        except (json.JSONDecodeError, TypeError):
            paper_ids = []

    if not paper_ids:
        return {"session_id": session_id, "contributions": [], "rows": []}

    # Fetch stored contributions
    contributions = {}
    papers_meta = []

    for pid in paper_ids:
        paper = db.query(Paper).filter(Paper.id == pid).first()
        if not paper:
            continue

        papers_meta.append({
            "id": pid,
            "paper_id": pid,
            "title": paper.title,
            "authors": json.loads(paper.authors) if paper.authors else [],
            "year": paper.year,
        })

        contrib = db.query(Contribution).filter(Contribution.paper_id == pid).first()
        if contrib:
            contributions[pid] = {
                "problem": {"value": contrib.problem or "Not specified", "source": contrib.problem_source or ""},
                "method": {"value": contrib.method or "Not specified", "source": contrib.method_source or ""},
                "dataset": {"value": contrib.dataset or "Not specified", "source": contrib.dataset_source or ""},
                "metrics": {"value": contrib.metrics or "Not specified", "source": contrib.metrics_source or ""},
                "results": {"value": contrib.results or "Not specified", "source": contrib.results_source or ""},
            }

    # Generate row format
    rows = await generate_comparison_table(contributions) if contributions else []

    return {
        "session_id": session_id,
        "papers": papers_meta,
        "contributions": contributions,
        "rows": rows,
    }


async def generate_comparison_for_session(
    session_id: str,
    db: DBSession,
) -> Dict[str, Any]:
    """Generate comparison table via LLM extraction for all papers in a session.

    Extracts contributions from each paper and stores them in the DB.
    """
    from infrastructure.db.models.session import Session as SessionModel
    from infrastructure.db.models.chunk import Paragraph

    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise ValueError(f"Session {session_id} not found")

    paper_ids = []
    if session.paper_ids:
        try:
            paper_ids = json.loads(session.paper_ids)
        except (json.JSONDecodeError, TypeError):
            paper_ids = []

    if not paper_ids:
        return {"session_id": session_id, "contributions": {}, "rows": []}

    # Create an LLM generate function
    async def _llm_generate(system_prompt: str, user_prompt: str) -> str:
        from infrastructure.llm.fallback_chain import get_llm
        llm = get_llm()
        available = llm._get_available_providers()
        for provider in available:
            try:
                return await provider.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.2,
                )
            except Exception:
                continue
        raise RuntimeError("All providers failed for comparison extraction")

    contributions = {}
    papers_meta = []

    for pid in paper_ids:
        paper = db.query(Paper).filter(Paper.id == pid).first()
        if not paper or paper.status != "ready":
            continue

        papers_meta.append({
            "id": pid,
            "paper_id": pid,
            "title": paper.title,
            "authors": json.loads(paper.authors) if paper.authors else [],
            "year": paper.year,
        })

        # Get paragraphs
        paragraphs = db.query(Paragraph).filter(Paragraph.paper_id == pid).all()
        para_dicts = []
        for p in paragraphs:
            section_title = "Unknown"
            if p.section_id:
                from infrastructure.db.models.paper import Section
                section = db.query(Section).filter(Section.id == p.section_id).first()
                if section:
                    section_title = section.title
            para_dicts.append({
                "paragraph_id": p.id.replace(f"{pid}_", "") if p.id.startswith(pid) else p.id,
                "text": p.text,
                "section": section_title,
                "page": p.page,
            })

        # Extract contributions via LLM
        paper_contribs = await extract_paper_contributions(
            paper_id=pid,
            paragraphs=para_dicts,
            llm_generate_fn=_llm_generate,
        )

        contributions[pid] = paper_contribs

        # Store in DB
        existing = db.query(Contribution).filter(Contribution.paper_id == pid).first()
        if existing:
            existing.problem = paper_contribs["problem"]["value"]
            existing.problem_source = paper_contribs["problem"]["source"]
            existing.method = paper_contribs["method"]["value"]
            existing.method_source = paper_contribs["method"]["source"]
            existing.dataset = paper_contribs["dataset"]["value"]
            existing.dataset_source = paper_contribs["dataset"]["source"]
            existing.metrics = paper_contribs["metrics"]["value"]
            existing.metrics_source = paper_contribs["metrics"]["source"]
            existing.results = paper_contribs["results"]["value"]
            existing.results_source = paper_contribs["results"]["source"]
        else:
            contrib = Contribution(
                paper_id=pid,
                problem=paper_contribs["problem"]["value"],
                problem_source=paper_contribs["problem"]["source"],
                method=paper_contribs["method"]["value"],
                method_source=paper_contribs["method"]["source"],
                dataset=paper_contribs["dataset"]["value"],
                dataset_source=paper_contribs["dataset"]["source"],
                metrics=paper_contribs["metrics"]["value"],
                metrics_source=paper_contribs["metrics"]["source"],
                results=paper_contribs["results"]["value"],
                results_source=paper_contribs["results"]["source"],
            )
            db.add(contrib)

    db.commit()

    rows = await generate_comparison_table(contributions)

    logger.info("Generated comparison for session {} ({} papers)", session_id, len(papers_meta))
    return {
        "session_id": session_id,
        "papers": papers_meta,
        "contributions": contributions,
        "rows": rows,
    }


async def update_comparison_cell(
    session_id: str,
    paper_id: str,
    field: str,
    value: str,
    db: DBSession,
) -> Dict[str, Any]:
    """Update a single cell in the comparison table.

    Args:
        session_id: Session identifier.
        paper_id: Paper identifier.
        field: Field name (problem, method, dataset, metrics, results).
        value: New value.
        db: Database session.

    Returns:
        Updated contribution data.
    """
    valid_fields = {"problem", "method", "dataset", "metrics", "results"}
    if field not in valid_fields:
        raise ValueError(f"Invalid field: {field}. Must be one of {valid_fields}")

    contrib = db.query(Contribution).filter(Contribution.paper_id == paper_id).first()
    if not contrib:
        contrib = Contribution(paper_id=paper_id)
        db.add(contrib)

    setattr(contrib, field, value)
    db.commit()

    logger.info("Updated comparison cell: paper={}, field={}", paper_id, field)
    return {
        "paper_id": paper_id,
        "field": field,
        "value": value,
        "updated": True,
    }
