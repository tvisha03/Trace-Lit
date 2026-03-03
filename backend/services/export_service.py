import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from domain.export.pdf_exporter import export_chat_to_pdf, export_comparison_to_pdf
from domain.export.excel_exporter import export_citations_to_excel, export_comparison_to_excel
from domain.export.bibtex_exporter import export_papers_to_bibtex
from infrastructure.db.crud.message_crud import get_messages_by_session
from infrastructure.db.crud.paper_crud import get_papers_by_session, get_paper
from infrastructure.db.crud.session_crud import get_session
from infrastructure.storage.file_storage import FileStorage
from shared.enums import ExportFormat
from shared.errors import NotFoundError
from shared.logger import get_logger
from workers.export_worker import run_export_in_thread

logger = get_logger(__name__)

async def export_chat(
    session_id: str,
    export_format: ExportFormat,
    db: AsyncSession,
    file_storage: FileStorage,
) -> Path:
    session = await get_session(db, session_id)
    if not session:
        raise NotFoundError("Session", session_id)

    messages_db = await get_messages_by_session(db, session_id)
    messages = [
        {
            "role": m.role.value if hasattr(m.role, "value") else m.role,
            "content": m.content,
            "havf_results": m.havf_results or [],
        }
        for m in messages_db
    ]

    filename = f"chat_{session_id[:8]}_{uuid.uuid4().hex[:6]}"

    if export_format == ExportFormat.PDF:
        output_path = file_storage.get_export_path(f"{filename}.pdf", session_id)
        return await run_export_in_thread(
            export_chat_to_pdf,
            session_title=session.title or "Chat Export",
            messages=messages,
            output_path=output_path,
        )
    elif export_format == ExportFormat.EXCEL:
        output_path = file_storage.get_export_path(f"{filename}.xlsx", session_id)
        return await run_export_in_thread(
            export_citations_to_excel,
            citations=_flatten_citations(messages),
            output_path=output_path,
        )
    elif export_format == ExportFormat.BIBTEX:
        # BibTeX export serialises paper metadata (authors, title, year,
        # abstract) for all papers in the session so researchers can cite them
        # directly from their reference managers.
        papers_db = await get_papers_by_session(db, session_id)
        paper_dicts = [
            {
                "id": p.id,
                "title": p.title,
                "authors": p.authors,
                "year": p.year,
                "abstract": p.abstract,
                "filename": p.filename,
            }
            for p in papers_db
        ]
        output_path = file_storage.get_export_path(f"{filename}.bib", session_id)
        return await run_export_in_thread(
            export_papers_to_bibtex,
            papers=paper_dicts,
            output_path=output_path,
        )
    else:
        raise ValueError(f"Unsupported export format: {export_format.value}")

async def _collect_paper_dicts(paper_ids: list[str], db: AsyncSession) -> list[dict]:
    """Fetch paper metadata dicts for BibTeX export."""
    paper_dicts = []
    for pid in paper_ids:
        paper = await get_paper(db, pid)
        if paper:
            paper_dicts.append(
                {
                    "id": paper.id,
                    "title": paper.title,
                    "authors": paper.authors,
                    "year": paper.year,
                    "abstract": paper.abstract,
                    "filename": paper.filename,
                }
            )
    return paper_dicts


async def export_comparison(
    session_id: str,
    comparison_content: str,
    paper_titles: list[str],
    export_format: ExportFormat,
    file_storage: FileStorage,
    paper_ids: Optional[list[str]] = None,
    db: Optional[AsyncSession] = None,
) -> Path:
    filename = f"comparison_{session_id[:8]}_{uuid.uuid4().hex[:6]}"

    if export_format == ExportFormat.PDF:
        output_path = file_storage.get_export_path(f"{filename}.pdf", session_id)
        return await run_export_in_thread(
            export_comparison_to_pdf,
            title="Paper Comparison",
            comparison_content=comparison_content,
            paper_titles=paper_titles,
            output_path=output_path,
        )
    elif export_format == ExportFormat.EXCEL:
        output_path = file_storage.get_export_path(f"{filename}.xlsx", session_id)
        # BUG-5 fix: populate comparison rows with actual paper metadata
        # instead of empty placeholder strings.
        paper_data = []
        for i, title in enumerate(paper_titles):
            entry: dict = {"title": title, "authors": "", "year": "", "problem": "", "method": "", "results": "", "keywords": ""}
            if paper_ids and db and i < len(paper_ids):
                paper_obj = await get_paper(db, paper_ids[i])
                if paper_obj:
                    entry["authors"] = paper_obj.authors or ""
                    entry["year"] = paper_obj.year or ""
            paper_data.append(entry)
        return await run_export_in_thread(
            export_comparison_to_excel,
            paper_data=paper_data,
            output_path=output_path,
        )
    elif export_format == ExportFormat.BIBTEX:
        if not paper_ids or not db:
            raise ValueError("paper_ids and db are required for BibTeX comparison export.")
        paper_dicts = await _collect_paper_dicts(paper_ids, db)
        output_path = file_storage.get_export_path(f"{filename}.bib", session_id)
        return await run_export_in_thread(
            export_papers_to_bibtex,
            papers=paper_dicts,
            output_path=output_path,
        )
    else:
        raise ValueError(f"Unsupported export format for comparison: {export_format.value}")

def _flatten_citations(messages: list[dict]) -> list[dict]:
    citations = []
    for msg in messages:
        raw_results = msg.get("havf_results", [])
        if not isinstance(raw_results, list):
            continue
        for result in raw_results:
            # Guard against non-dict items (e.g. null entries or malformed data)
            if isinstance(result, dict):
                citations.append(result)
    return citations
