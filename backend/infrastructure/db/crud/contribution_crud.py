"""TraceLit — Contribution CRUD operations."""

from typing import Dict, Optional

from sqlalchemy.orm import Session

from infrastructure.db.models.paper import Contribution


def get_contribution(db: Session, paper_id: str) -> Optional[Contribution]:
    """Get contribution for a paper."""
    return db.query(Contribution).filter(Contribution.paper_id == paper_id).first()


def upsert_contribution(db: Session, paper_id: str, data: Dict[str, Dict[str, str]]) -> Contribution:
    """Create or update a contribution record.

    Args:
        db: Database session.
        paper_id: Paper identifier.
        data: Dict with keys (problem, method, dataset, metrics, results),
              each mapping to {"value": str, "source": str}.

    Returns:
        The Contribution record.
    """
    existing = get_contribution(db, paper_id)

    if existing:
        for field in ("problem", "method", "dataset", "metrics", "results"):
            if field in data:
                setattr(existing, field, data[field].get("value", ""))
                setattr(existing, f"{field}_source", data[field].get("source", ""))
        return existing

    contrib = Contribution(
        paper_id=paper_id,
        problem=data.get("problem", {}).get("value", ""),
        problem_source=data.get("problem", {}).get("source", ""),
        method=data.get("method", {}).get("value", ""),
        method_source=data.get("method", {}).get("source", ""),
        dataset=data.get("dataset", {}).get("value", ""),
        dataset_source=data.get("dataset", {}).get("source", ""),
        metrics=data.get("metrics", {}).get("value", ""),
        metrics_source=data.get("metrics", {}).get("source", ""),
        results=data.get("results", {}).get("value", ""),
        results_source=data.get("results", {}).get("source", ""),
    )
    db.add(contrib)
    return contrib


def delete_contribution(db: Session, paper_id: str) -> bool:
    """Delete contribution for a paper. Returns True if a record was deleted."""
    n = db.query(Contribution).filter(Contribution.paper_id == paper_id).delete()
    return n > 0
