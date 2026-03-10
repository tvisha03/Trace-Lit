import uuid
from pathlib import Path
from typing import Optional
import re

from sqlalchemy.ext.asyncio import AsyncSession

from domain.export.pdf_exporter import export_chat_to_pdf, export_comparison_to_pdf
from domain.export.excel_exporter import export_citations_to_excel, export_comparison_to_excel
from domain.export.bibtex_exporter import export_papers_to_bibtex
from domain.export.docx_exporter import export_chat_to_docx, export_comparison_to_docx
from domain.export.latex_exporter import export_chat_to_latex, export_comparison_to_latex
from infrastructure.db.crud.chunk_crud import get_chunks_by_papers
from infrastructure.db.crud.message_crud import get_messages_by_session
from infrastructure.db.crud.paper_crud import get_papers_by_session, get_paper
from infrastructure.db.crud.session_crud import get_session
from infrastructure.storage.file_storage import FileStorage
from app.config import get_settings
from shared.enums import ExportFormat
from shared.errors import NotFoundError, TraceLitError
from shared.logger import get_logger
from shared.utils.export_text import build_export_blocks, extract_citation_ids, format_structured_text
from workers.export_worker import run_export_in_thread

logger = get_logger(__name__)

_COMPARISON_SECTION_MARKERS = (
    "research problem and motivation",
    "methodology and approach",
    "key findings and results",
    "datasets used",
    "limitations acknowledged",
)
_COMPARISON_INTRO_RE = re.compile(
    r"structured comparison of the (?:three|3) academic papers|paper comparison",
    re.IGNORECASE,
)

# Strips the disclaimer note appended when attribution verification fails.
_EXPORT_DISCLAIMER_RE = re.compile(
    r"\n\n---\n_?\u26a0\ufe0f[^\n]*(?:\n[^\n]*)*?_?\s*$",
    re.DOTALL,
)

# Substrings that signal a message contains no useful answer for export.
_ERROR_CONTENT_FRAGMENTS = (
    "i apologize, but i was unable",
    "this information is not available in the",
    "could not find relevant information",
    "unable to generate a verified response",
)

def _check_export_size(output_path: Path) -> None:
    if not output_path.exists():
        return
    settings = get_settings()
    size_mb = output_path.stat().st_size / (1024 * 1024)
    if size_mb > settings.MAX_EXPORT_FILE_SIZE_MB:
        output_path.unlink(missing_ok=True)
        raise TraceLitError(
            message=(
                f"Generated export is too large ({size_mb:.1f} MB, "
                f"limit {settings.MAX_EXPORT_FILE_SIZE_MB} MB). Try exporting fewer messages "
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
    cited_assets: Optional[list[dict]] = None,
) -> Path:
    output_path = file_storage.get_export_path(f"{filename}.pdf", session_id)
    result = await run_export_in_thread(
        export_chat_to_pdf,
        session_title=session_title,
        messages=messages,
        cited_assets=cited_assets or [],
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
    cited_assets: Optional[list[dict]] = None,
) -> Path:
    output_path = file_storage.get_export_path(f"{filename}.xlsx", session_id)
    result = await run_export_in_thread(
        export_citations_to_excel,
        citations=_flatten_citations(messages),
        output_path=output_path,
        session_title=session_title,
        messages=messages,
        cited_assets=cited_assets or [],
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
    cited_assets: Optional[list[dict]] = None,
) -> Path:
    output_path = file_storage.get_export_path(f"{filename}.docx", session_id)
    result = await run_export_in_thread(
        export_chat_to_docx,
        session_title=session_title,
        messages=messages,
        cited_assets=cited_assets or [],
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
    cited_assets: Optional[list[dict]] = None,
) -> Path:
    output_path = file_storage.get_export_path(f"{filename}.tex", session_id)
    result = await run_export_in_thread(
        export_chat_to_latex,
        session_title=session_title,
        messages=messages,
        cited_assets=cited_assets or [],
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
    messages = _filter_chat_export_messages(messages)
    papers_db = await get_papers_by_session(db, session_id)
    paper_title_map = {
        str(p.id): p.title or p.filename or f"Paper {str(p.id)[:8]}"
        for p in papers_db
    }
    cited_assets = await _collect_chat_cited_assets(
        messages=messages,
        paper_ids=list(paper_title_map),
        paper_title_map=paper_title_map,
        db=db,
    )

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
        return await handler(
            session_id,
            session_title,
            messages,
            filename,
            file_storage,
            cited_assets,
        )

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
    comparison_table: Optional[list[dict]] = None,
    cited_assets: Optional[list[dict]] = None,
) -> Path:
    output_path = file_storage.get_export_path(f"{filename}.pdf", session_id)
    result = await run_export_in_thread(
        export_comparison_to_pdf,
        title="Paper Comparison",
        comparison_content=comparison_content,
        paper_titles=paper_titles,
        comparison_table=comparison_table or [],
        cited_assets=cited_assets or [],
        output_path=output_path,
    )
    _check_export_size(result)
    return result

def _build_contrib_map(contributions: Optional[list[dict]]) -> dict[str, dict]:
    if not contributions:
        return {}
    result: dict[str, dict] = {}
    for c in contributions:
        pid = c.get("paper_id", "")
        if pid:
            result[pid] = c.get("contributions", {})
    return result

def _apply_contributions(entry: dict, contribs: dict) -> None:
    entry["problem"] = contribs.get("problem", {}).get("text", "")
    entry["method"] = contribs.get("method", {}).get("text", "")
    entry["results"] = contribs.get("results", {}).get("text", "")
    parts = []
    for field in ("dataset", "metrics"):
        val = contribs.get(field, {}).get("text", "")
        if val and val != "Not mentioned":
            parts.append(val)
    entry["keywords"] = "; ".join(parts)

async def _enrich_from_db(entry: dict, pid: str, db: AsyncSession) -> None:
    paper_obj = await get_paper(db, pid)
    if not paper_obj:
        return
    entry["authors"] = paper_obj.authors or ""
    entry["year"] = paper_obj.year or ""
    entry["abstract"] = (paper_obj.abstract or "")[:2000]

async def _build_paper_data(
    paper_titles: list[str],
    paper_ids: Optional[list[str]],
    db: Optional[AsyncSession],
    contrib_map: dict[str, dict],
) -> list[dict]:
    paper_data: list[dict] = []
    for i, title in enumerate(paper_titles):
        entry: dict = {
            "title": title, "authors": "", "year": "",
            "abstract": "", "problem": "", "method": "",
            "results": "", "keywords": "",
        }
        pid = paper_ids[i] if paper_ids and i < len(paper_ids) else None
        if pid and db:
            await _enrich_from_db(entry, pid, db)
        if pid and pid in contrib_map:
            _apply_contributions(entry, contrib_map[pid])
        paper_data.append(entry)
    return paper_data

async def _export_comparison_as_excel(
    session_id: str,
    comparison_content: str,
    paper_titles: list[str],
    filename: str,
    file_storage: FileStorage,
    paper_ids: Optional[list[str]] = None,
    db: Optional[AsyncSession] = None,
    contributions: Optional[list[dict]] = None,
    comparison_table: Optional[list[dict]] = None,
    cited_assets: Optional[list[dict]] = None,
) -> Path:
    output_path = file_storage.get_export_path(f"{filename}.xlsx", session_id)
    contrib_map = _build_contrib_map(contributions)
    paper_data = await _build_paper_data(paper_titles, paper_ids, db, contrib_map)
    result = await run_export_in_thread(
        export_comparison_to_excel,
        paper_data=paper_data,
        output_path=output_path,
        comparison_content=comparison_content,
        comparison_table=comparison_table or [],
        cited_assets=cited_assets or [],
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
    comparison_table: Optional[list[dict]] = None,
    cited_assets: Optional[list[dict]] = None,
) -> Path:
    output_path = file_storage.get_export_path(f"{filename}.docx", session_id)
    result = await run_export_in_thread(
        export_comparison_to_docx,
        title="Paper Comparison",
        comparison_content=comparison_content,
        paper_titles=paper_titles,
        comparison_table=comparison_table or [],
        cited_assets=cited_assets or [],
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
    comparison_table: Optional[list[dict]] = None,
    cited_assets: Optional[list[dict]] = None,
) -> Path:
    output_path = file_storage.get_export_path(f"{filename}.tex", session_id)
    result = await run_export_in_thread(
        export_comparison_to_latex,
        title="Paper Comparison",
        comparison_content=comparison_content,
        paper_titles=paper_titles,
        comparison_table=comparison_table or [],
        cited_assets=cited_assets or [],
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
    contributions: Optional[list[dict]] = None,
    comparison_table: Optional[list[dict]] = None,
) -> Path:
    filename = f"comparison_{session_id[:8]}_{uuid.uuid4().hex[:6]}"
    cited_assets: list[dict] = []
    if paper_ids and db and comparison_table:
        title_map = {paper_id: paper_titles[idx] for idx, paper_id in enumerate(paper_ids) if idx < len(paper_titles)}
        cited_assets = await _collect_comparison_cited_assets(
            comparison_table=comparison_table,
            paper_ids=paper_ids,
            paper_title_map=title_map,
            db=db,
        )

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
            contributions=contributions,
            comparison_table=comparison_table,
            cited_assets=cited_assets,
        )
    else:
        return await handler(
            session_id,
            comparison_content,
            paper_titles,
            filename,
            file_storage,
            comparison_table,
            cited_assets,
        )


def _serialize_cited_asset(chunk, paper_title: str) -> dict:
    chunk_type = getattr(chunk, "chunk_type", "text")
    display_content = getattr(chunk, "text", None) or getattr(chunk, "enriched_text", "")
    enriched_content = getattr(chunk, "enriched_text", None) or display_content
    return {
        "citation_id": str(getattr(chunk, "paragraph_id", "")),
        "chunk_type": str(chunk_type),
        "paper_title": paper_title,
        "section_title": getattr(chunk, "section_title", None),
        "page_number": getattr(chunk, "page_number", None),
        "raw_content": display_content,
        "content": format_structured_text(display_content),
        "enriched_content": enriched_content,
        "image_path": getattr(chunk, "image_path", None),
    }


async def _build_chunk_lookup(
    paper_ids: list[str],
    paper_title_map: dict[str, str],
    db: AsyncSession,
) -> dict[tuple[str, str], dict]:
    chunks_by_paper = await get_chunks_by_papers(db, paper_ids)
    lookup: dict[tuple[str, str], dict] = {}
    for paper_id, chunks in chunks_by_paper.items():
        for chunk in chunks:
            citation_id = str(getattr(chunk, "paragraph_id", ""))
            if not citation_id:
                continue
            asset = _serialize_cited_asset(
                chunk,
                paper_title_map.get(paper_id, f"Paper {paper_id[:8]}"),
            )
            for candidate in _citation_candidates(citation_id):
                lookup[(paper_id, candidate)] = asset
    return lookup


def _citation_candidates(citation_id: str | None, citation_ref: str | None = None) -> list[str]:
    candidates: list[str] = []
    for value in (citation_id, citation_ref):
        normalized = str(value or "").strip().strip("[]")
        if not normalized:
            continue
        if normalized not in candidates:
            candidates.append(normalized)
        if "_" in normalized:
            suffix = normalized.rsplit("_", 1)[-1]
            if suffix and suffix not in candidates:
                candidates.append(suffix)
    return candidates


def _is_media_citation(citation_id: str) -> bool:
    return any(candidate.startswith(("F", "T", "E")) for candidate in _citation_candidates(citation_id))


def _deduplicate_assets(assets: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for asset in assets:
        key = (asset.get("paper_title", ""), asset.get("citation_id", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(asset)
    return deduped


async def _collect_chat_cited_assets(
    messages: list[dict],
    paper_ids: list[str],
    paper_title_map: dict[str, str],
    db: AsyncSession,
) -> list[dict]:
    if not paper_ids:
        return []

    lookup = await _build_chunk_lookup(paper_ids, paper_title_map, db)
    assets: list[dict] = []
    for msg in messages:
        for result in msg.get("havf_results") or []:
            paper_id = result.get("paper_id")
            citation_id = result.get("paragraph_id")
            if not paper_id or not citation_id or not _is_media_citation(str(citation_id)):
                continue
            for candidate in _citation_candidates(citation_id, result.get("citation_ref")):
                asset = lookup.get((str(paper_id), candidate))
                if asset:
                    assets.append(asset)
                    break
    return _deduplicate_assets(assets)


async def _collect_comparison_cited_assets(
    comparison_table: list[dict],
    paper_ids: list[str],
    paper_title_map: dict[str, str],
    db: AsyncSession,
) -> list[dict]:
    if not paper_ids or not comparison_table:
        return []

    lookup = await _build_chunk_lookup(paper_ids, paper_title_map, db)
    assets: list[dict] = []
    for row in comparison_table:
        for cell in row.get("cells", []):
            paper_id = cell.get("paper_id")
            if not paper_id:
                continue
            for citation_id in extract_citation_ids(cell.get("content", "")):
                if not _is_media_citation(citation_id):
                    continue
                for candidate in _citation_candidates(citation_id):
                    asset = lookup.get((str(paper_id), candidate))
                    if asset:
                        assets.append(asset)
                        break
    return _deduplicate_assets(assets)

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


def _looks_like_comparison_table(content: str) -> bool:
    for block in build_export_blocks(content or ""):
        if block.kind != "table" or not block.headers:
            continue
        headers = [format_structured_text(header).strip().lower() for header in block.headers]
        if not headers:
            continue
        if headers[0] == "dimension" and "synthesis" in headers and any(
            header.startswith("paper 1") for header in headers[1:]
        ):
            return True
    return False


def _looks_like_comparison_message(message: dict) -> bool:
    if str(message.get("role", "")).lower() != "assistant":
        return False

    content = str(message.get("content", "") or "")
    if not content.strip():
        return False

    normalized = format_structured_text(content).lower()
    if _COMPARISON_INTRO_RE.search(normalized):
        return True
    if _looks_like_comparison_table(content):
        return True

    marker_hits = sum(1 for marker in _COMPARISON_SECTION_MARKERS if marker in normalized)
    return marker_hits >= 3 and "paper 1" in normalized and "paper 2" in normalized


def _looks_like_error_message(message: dict) -> bool:
    """Return True for assistant messages that contain only an error/apology fallback.

    These messages add no scholarly value to an exported document.  We look for
    the well-known error fragments after stripping the trailing disclaimer note
    so that the check is not confused by the ``⚠️ Note`` suffix that the system
    appends to otherwise valid (but unattributed) answers.
    """
    if str(message.get("role", "")).lower() != "assistant":
        return False

    content = str(message.get("content", "") or "")
    # Strip the disclaimer suffix, then inspect what remains.
    real_content = _EXPORT_DISCLAIMER_RE.sub("", content).strip()
    if not real_content:
        # Nothing left after removing the disclaimer — pure error message.
        return True

    normalised = real_content.lower()
    return any(fragment in normalised for fragment in _ERROR_CONTENT_FRAGMENTS)


def _filter_chat_export_messages(messages: list[dict]) -> list[dict]:
    filtered = [
        message
        for message in messages
        if not _looks_like_comparison_message(message)
        and not _looks_like_error_message(message)
    ]
    removed = len(messages) - len(filtered)
    if removed:
        logger.info("Filtered %s low-quality message(s) from chat export", removed)
    return filtered

