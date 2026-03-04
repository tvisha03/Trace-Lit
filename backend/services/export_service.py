import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from domain.export.pdf_exporter import export_chat_to_pdf, export_comparison_to_pdf
from domain.export.excel_exporter import export_citations_to_excel, export_comparison_to_excel
from domain.export.bibtex_exporter import export_papers_to_bibtex
from domain.export.docx_exporter import export_chat_to_docx, export_comparison_to_docx
from domain.export.latex_exporter import export_chat_to_latex, export_comparison_to_latex
from infrastructure.db.crud.message_crud import get_messages_by_session
from infrastructure.db.crud.paper_crud import get_papers_by_session, get_paper
from infrastructure.db.crud.session_crud import get_session
from infrastructure.storage.file_storage import FileStorage
from shared.constants import MAX_EXPORT_FILE_SIZE_MB
from shared.enums import ExportFormat
from shared.errors import NotFoundError, TraceLitError
from shared.logger import get_logger
from workers.export_worker import run_export_in_thread

logger = get_logger(__name__)


def _check_export_size(output_path: Path) -> None:
    if not output_path.exists():
        return
    size_mb = output_path.stat().st_size / (1024 * 1024)
    if size_mb > MAX_EXPORT_FILE_SIZE_MB:
        output_path.unlink(missing_ok=True)
        raise TraceLitError(
            message=(
                f"Generated export is too large ({size_mb:.1f} MB, "
                f"limit {MAX_EXPORT_FILE_SIZE_MB} MB). Try exporting fewer messages "
                "or a smaller range."
            ),
            status_code=413,
        )

async def _export_chat_as_pdf(
    session_id: str,
    session_title: str,
    messages: list[dict],
    filename: str,
    file_storage: FileStorage,
) -> Path:
    output_path = file_storage.get_export_path(f"{filename}.pdf", session_id)
    result = await run_export_in_thread(
        export_chat_to_pdf,
        session_title=session_title,
        messages=messages,
        output_path=output_path,
    )
    _check_export_size(result)
    return result


async def _export_chat_as_excel(
    session_id: str,
    session_title: str,
    messages: list[dict],
    filename: str,
    file_storage: FileStorage,
) -> Path:
    output_path = file_storage.get_export_path(f"{filename}.xlsx", session_id)
    result = await run_export_in_thread(
        export_citations_to_excel,
        citations=_flatten_citations(messages),
        output_path=output_path,
        session_title=session_title,
        messages=messages,
    )
    _check_export_size(result)
    return result


async def _export_chat_as_bibtex(
    session_id: str,
    filename: str,
    file_storage: FileStorage,
    db: AsyncSession,
) -> Path:
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
    result = await run_export_in_thread(
        export_papers_to_bibtex,
        papers=paper_dicts,
        output_path=output_path,
    )
    _check_export_size(result)
    return result


async def _export_chat_as_docx(
    session_id: str,
    session_title: str,
    messages: list[dict],
    filename: str,
    file_storage: FileStorage,
) -> Path:
    output_path = file_storage.get_export_path(f"{filename}.docx", session_id)
    result = await run_export_in_thread(
        export_chat_to_docx,
        session_title=session_title,
        messages=messages,
        output_path=output_path,
    )
    _check_export_size(result)
    return result


async def _export_chat_as_latex(
    session_id: str,
    session_title: str,
    messages: list[dict],
    filename: str,
    file_storage: FileStorage,
) -> Path:
    output_path = file_storage.get_export_path(f"{filename}.tex", session_id)
    result = await run_export_in_thread(
        export_chat_to_latex,
        session_title=session_title,
        messages=messages,
        output_path=output_path,
    )
    _check_export_size(result)
    return result


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
    session_title = session.title or "Chat Export"

    handlers = {
        ExportFormat.PDF: _export_chat_as_pdf,
        ExportFormat.EXCEL: _export_chat_as_excel,
        ExportFormat.BIBTEX: _export_chat_as_bibtex,
        ExportFormat.DOCX: _export_chat_as_docx,
        ExportFormat.LATEX: _export_chat_as_latex,
    }

    if export_format not in handlers:
        raise ValueError(f"Unsupported export format: {export_format.value}")

    handler = handlers[export_format]
    if export_format == ExportFormat.BIBTEX:
        return await handler(session_id, filename, file_storage, db)
    else:
        return await handler(session_id, session_title, messages, filename, file_storage)

async def _collect_paper_dicts(paper_ids: list[str], db: AsyncSession) -> list[dict]:
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


async def _export_comparison_as_pdf(
    session_id: str,
    comparison_content: str,
    paper_titles: list[str],
    filename: str,
    file_storage: FileStorage,
) -> Path:
    output_path = file_storage.get_export_path(f"{filename}.pdf", session_id)
    result = await run_export_in_thread(
        export_comparison_to_pdf,
        title="Paper Comparison",
        comparison_content=comparison_content,
        paper_titles=paper_titles,
        output_path=output_path,
    )
    _check_export_size(result)
    return result


async def _export_comparison_as_excel(
    session_id: str,
    comparison_content: str,
    paper_titles: list[str],
    filename: str,
    file_storage: FileStorage,
    paper_ids: Optional[list[str]] = None,
    db: Optional[AsyncSession] = None,
) -> Path:
    output_path = file_storage.get_export_path(f"{filename}.xlsx", session_id)
    paper_data = []
    for i, title in enumerate(paper_titles):
        entry: dict = {"title": title, "authors": "", "year": "", "problem": "", "method": "", "results": "", "keywords": ""}
        if paper_ids and db and i < len(paper_ids):
            paper_obj = await get_paper(db, paper_ids[i])
            if paper_obj:
                entry["authors"] = paper_obj.authors or ""
                entry["year"] = paper_obj.year or ""
        paper_data.append(entry)
    result = await run_export_in_thread(
        export_comparison_to_excel,
        paper_data=paper_data,
        output_path=output_path,
        comparison_content=comparison_content,
    )
    _check_export_size(result)
    return result


async def _export_comparison_as_bibtex(
    session_id: str,
    filename: str,
    file_storage: FileStorage,
    paper_ids: list[str],
    db: AsyncSession,
) -> Path:
    paper_dicts = await _collect_paper_dicts(paper_ids, db)
    output_path = file_storage.get_export_path(f"{filename}.bib", session_id)
    result = await run_export_in_thread(
        export_papers_to_bibtex,
        papers=paper_dicts,
        output_path=output_path,
    )
    _check_export_size(result)
    return result


async def _export_comparison_as_docx(
    session_id: str,
    comparison_content: str,
    paper_titles: list[str],
    filename: str,
    file_storage: FileStorage,
) -> Path:
    output_path = file_storage.get_export_path(f"{filename}.docx", session_id)
    result = await run_export_in_thread(
        export_comparison_to_docx,
        title="Paper Comparison",
        comparison_content=comparison_content,
        paper_titles=paper_titles,
        output_path=output_path,
    )
    _check_export_size(result)
    return result


async def _export_comparison_as_latex(
    session_id: str,
    comparison_content: str,
    paper_titles: list[str],
    filename: str,
    file_storage: FileStorage,
) -> Path:
    output_path = file_storage.get_export_path(f"{filename}.tex", session_id)
    result = await run_export_in_thread(
        export_comparison_to_latex,
        title="Paper Comparison",
        comparison_content=comparison_content,
        paper_titles=paper_titles,
        output_path=output_path,
    )
    _check_export_size(result)
    return result


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

    if export_format == ExportFormat.BIBTEX:
        if not paper_ids or not db:
            raise ValueError("paper_ids and db are required for BibTeX comparison export.")
        return await _export_comparison_as_bibtex(session_id, filename, file_storage, paper_ids, db)

    handlers = {
        ExportFormat.PDF: _export_comparison_as_pdf,
        ExportFormat.EXCEL: _export_comparison_as_excel,
        ExportFormat.DOCX: _export_comparison_as_docx,
        ExportFormat.LATEX: _export_comparison_as_latex,
    }

    if export_format not in handlers:
        raise ValueError(f"Unsupported export format for comparison: {export_format.value}")

    handler = handlers[export_format]
    if export_format == ExportFormat.EXCEL:
        return await handler(
            session_id=session_id,
            comparison_content=comparison_content,
            paper_titles=paper_titles,
            filename=filename,
            file_storage=file_storage,
            paper_ids=paper_ids,
            db=db,
        )
    else:
        return await handler(session_id, comparison_content, paper_titles, filename, file_storage)

def _flatten_citations(messages: list[dict]) -> list[dict]:
    citations = []
    for msg in messages:
        raw_results = msg.get("havf_results", [])
        if not isinstance(raw_results, list):
            continue
        for result in raw_results:
            if isinstance(result, dict):
                citations.append(result)
    return citations

