"""TraceLit — Workers Package.

Background processing workers for paper ingestion pipeline.
"""

from workers.paper_worker import (
    SmartPaperQueue,
    get_paper_queue,
    init_paper_queue,
    ProcessingStage,
    PaperJob,
)

__all__ = [
    "SmartPaperQueue",
    "get_paper_queue",
    "init_paper_queue",
    "ProcessingStage",
    "PaperJob",
]
