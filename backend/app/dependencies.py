"""TraceLit — Shared FastAPI Dependencies.

Centralises database session injection and other cross-cutting dependencies
so every router imports from one place.
"""

from sqlalchemy.orm import Session

from infrastructure.db.database import SessionLocal


def get_db() -> Session:
    """Yield a database session; auto-closes on request completion.

    Usage::

        @router.get("/items")
        def read_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
