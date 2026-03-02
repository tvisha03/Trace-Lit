"""TraceLit — Background Processing Package.

Re-exports from workers for backward compatibility.
"""

from workers.paper_worker import (
    SmartPaperQueue,
    get_paper_queue,
    init_paper_queue,
)

__all__ = [
    "SmartPaperQueue",
    "get_paper_queue",
    "init_paper_queue",
]
