"""TraceLit — Paper Service (re-export for backward compatibility).

Business logic is split across:
  - paper_upload : process_uploads, _process_single_paper
  - paper_query  : get_all_papers, get_paper_by_id, get_paper_content, delete_paper
"""

from services.paper_query import (  # noqa: F401
    delete_paper,
    get_all_papers,
    get_paper_by_id,
    get_paper_content,
)
from services.paper_upload import process_uploads  # noqa: F401

