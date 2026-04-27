"""Standards management API — upload, list, detail, process, status."""

from __future__ import annotations

import asyncio
import json
import os
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from psycopg import Connection, errors

from tender_backend.core.security import CurrentUser, Role, get_current_user, require_role
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.document_repository import DocumentRepository
from tender_backend.db.repositories.file_repository import FileRepository
from tender_backend.db.repositories.skill_definition_repo import SkillDefinitionRepository
from tender_backend.db.repositories.standard_processing_job_repository import (
    StandardProcessingJobRepository,
)
from tender_backend.db.repositories.standard_repo import StandardRepository
from tender_backend.services.norm_service.document_assets import build_document_asset
from tender_backend.services.norm_service.norm_processor import _normalize_sections_for_processing
from tender_backend.services.norm_service.quality_report import build_standard_quality_report
from tender_backend.services.norm_service.standard_processing_scheduler import (
    ensure_standard_processing_scheduler_started,
)
from tender_backend.services.norm_service.validation import ValidationResult, validate_clauses
from tender_backend.services.skill_catalog import default_skill_specs
from tender_backend.services.search_service.index_manager import IndexManager
from tender_backend.services.search_service.query_service import search_standard_clauses
from tender_backend.services.storage_service.project_file_storage import ProjectFileStorage

router = APIRouter(tags=["standards"], dependencies=[Depends(get_current_user)])

_repo = StandardRepository()
_jobs = StandardProcessingJobRepository()
_files = FileRepository()
_docs = DocumentRepository()
_skills = SkillDefinitionRepository()
_storage = ProjectFileStorage()

# Sentinel project ID for standard uploads
_STANDARD_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")

# Local directory for standard PDF storage (inside container volume)
_UPLOAD_DIR = os.environ.get("STANDARD_UPLOAD_DIR", "/workspace/data/standards")


def _serialize_standard(std: dict, *, clause_count: int | None = None) -> dict:
    payload = {
        "id": str(std["id"]),
        "standard_code": std["standard_code"],
        "standard_name": std["standard_name"],
        "version_year": std.get("version_year"),
        "specialty": std.get("specialty"),
        "status": std.get("status"),
        "processing_status": std.get("processing_status", "pending"),
        "error_message": std.get("error_message"),
        "ocr_status": std.get("ocr_status"),
        "ai_status": std.get("ai_status"),
        "is_dev_artifact": bool(std.get("is_dev_artifact", False)),
        "created_at": std["created_at"].isoformat() if std.get("created_at") else None,
    }
    if std.get("document_id"):
        payload["document_id"] = str(std["document_id"])
    if std.get("processing_started_at") is not None:
        payload["processing_started_at"] = std["processing_started_at"].isoformat()
    if std.get("processing_finished_at") is not None:
        payload["processing_finished_at"] = std["processing_finished_at"].isoformat()
    if clause_count is not None:
        payload["clause_count"] = clause_count
    return payload


def _load_batch_items(raw: str) -> list[dict]:
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="items_json must be valid JSON") from exc
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="items_json must be a JSON array")
    return items


def _build_upload_items(files: list[UploadFile], items: list[dict]) -> list[tuple[UploadFile, dict]]:
    if len(files) != len(items):
        raise HTTPException(status_code=400, detail="File count does not match metadata count")

    if len({file.filename for file in files}) != len(files):
        raise HTTPException(status_code=400, detail="Duplicate filenames are not supported in one batch")

    file_by_name = {file.filename: file for file in files}
    resolved: list[tuple[UploadFile, dict]] = []
    for item in items:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="Each upload item must be an object")
        filename = str(item.get("filename") or "").strip()
        standard_code = str(item.get("standard_code") or "").strip()
        standard_name = str(item.get("standard_name") or "").strip()
        if not filename:
            raise HTTPException(status_code=400, detail="Each upload item requires filename")
        if not standard_code:
            raise HTTPException(status_code=400, detail="Each upload item requires standard_code")
        if not standard_name:
            raise HTTPException(status_code=400, detail="Each upload item requires standard_name")
        matched_file = file_by_name.get(filename)
        if matched_file is None:
            raise HTTPException(status_code=400, detail=f"No uploaded file matches filename: {filename}")
        resolved.append((matched_file, item))
    return resolved


def _serialize_search_hit(hit: dict, *, fallback: dict | None = None) -> dict:
    source = fallback or {}
    standard_id = source.get("standard_id") or hit.get("standard_id")
    clause_id = hit.get("clause_id") or source.get("id")
    return {
        "standard_id": str(standard_id) if standard_id else None,
        "standard_name": source.get("standard_name") or hit.get("standard_name"),
        "specialty": source.get("specialty") if source.get("specialty") is not None else hit.get("specialty"),
        "clause_id": str(clause_id) if clause_id else None,
        "clause_no": hit.get("clause_no") or source.get("clause_no"),
        "tags": hit.get("tags") if hit.get("tags") is not None else (source.get("tags") or []),
        "summary": hit.get("summary") if hit.get("summary") is not None else source.get("summary"),
        "page_start": source.get("page_start") if source.get("page_start") is not None else hit.get("page_start"),
        "page_end": source.get("page_end") if source.get("page_end") is not None else hit.get("page_end"),
    }


def _serialize_parse_document(document: dict | None) -> dict | None:
    if not document:
        return None
    return {
        "id": str(document["id"]),
        "parser_name": document.get("parser_name"),
        "parser_version": document.get("parser_version"),
        "raw_payload": document.get("raw_payload"),
    }


def _serialize_parse_section(section: dict) -> dict:
    return {
        "id": str(section["id"]),
        "section_code": section.get("section_code"),
        "title": section.get("title"),
        "level": section.get("level"),
        "text": section.get("text"),
        "text_source": section.get("text_source"),
        "sort_order": section.get("sort_order"),
        "page_start": section.get("page_start"),
        "page_end": section.get("page_end"),
        "raw_json": section.get("raw_json"),
    }


def _serialize_parse_table(table: dict) -> dict:
    return {
        "id": str(table["id"]),
        "section_id": str(table["section_id"]) if table.get("section_id") else None,
        "page": table.get("page"),
        "page_start": table.get("page_start"),
        "page_end": table.get("page_end"),
        "table_title": table.get("table_title"),
        "table_html": table.get("table_html"),
        "raw_json": table.get("raw_json"),
    }


def _list_configured_skills(conn: Connection) -> list:
    try:
        return _skills.list_all(conn)
    except errors.UndefinedTable:
        return []


def _build_quality_report_payload(conn: Connection, standard_id: UUID) -> tuple[dict, dict]:
    std = _repo.get_standard(conn, standard_id)
    if not std:
        raise HTTPException(status_code=404, detail="Standard not found")

    file_meta = _repo.get_standard_file(conn, standard_id)
    if not file_meta:
        raise HTTPException(status_code=404, detail="Standard source PDF not found")

    document_id = file_meta["document_id"]
    document = _repo.get_document_parse_info(conn, document_id=document_id)
    raw_sections = _repo.list_document_sections(conn, document_id=document_id)
    tables = _repo.list_document_tables(conn, document_id=document_id)
    document_asset = build_document_asset(
        document_id=document_id,
        document=document,
        sections=raw_sections,
        tables=tables,
    )

    clauses = _repo.list_clauses(conn, standard_id=standard_id)
    normalized_sections = _normalize_sections_for_processing(raw_sections)
    validation = (
        validate_clauses(clauses)
        if clauses
        else ValidationResult()
    )
    report = build_standard_quality_report(
        document_asset=document_asset,
        raw_sections=raw_sections,
        normalized_sections=normalized_sections,
        tables=tables,
        clauses=clauses,
        validation=validation,
        available_skills=default_skill_specs(),
        configured_skills=_list_configured_skills(conn),
    )

    return std, report


def _search_hit_is_usable(hit: dict) -> bool:
    return bool(hit.get("standard_id") and hit.get("standard_name") and hit.get("clause_id"))


async def delete_standard_clauses_from_index(*, standard_id: str) -> None:
    manager = IndexManager()
    await manager.delete_documents_by_term("clause_index", "standard_id", standard_id)


async def delete_stale_clause_hits_from_index(clause_ids: list[str]) -> None:
    if not clause_ids:
        return
    manager = IndexManager()
    await asyncio.gather(*[
        manager.delete_documents_by_term("clause_index", "clause_id", clause_id)
        for clause_id in clause_ids
    ])


def _standard_exists(conn: Connection, standard_id: str | None) -> bool:
    if not standard_id:
        return False
    try:
        parsed_id = UUID(str(standard_id))
    except ValueError:
        return False
    return _repo.get_standard(conn, parsed_id) is not None


def _build_search_payload(
    *,
    conn: Connection,
    hits: list[dict],
) -> tuple[list[dict], list[str], list[str]]:
    payload: list[dict] = []
    fallback_clause_ids: list[UUID] = []
    stale_clause_ids: set[str] = set()
    stale_standard_ids: set[str] = set()

    for hit in hits:
        if not hit.get("clause_id"):
            continue
        try:
            fallback_clause_ids.append(UUID(str(hit["clause_id"])))
        except ValueError:
            continue

    fallback_by_id = _repo.get_clauses_by_ids(conn, fallback_clause_ids)

    for hit in hits:
        fallback = None
        clause_id = hit.get("clause_id")
        if clause_id is not None:
            fallback = fallback_by_id.get(str(clause_id))
            if fallback is None:
                if _standard_exists(conn, hit.get("standard_id")):
                    stale_clause_ids.add(str(clause_id))
                elif hit.get("standard_id"):
                    stale_standard_ids.add(str(hit["standard_id"]))
                else:
                    stale_clause_ids.add(str(clause_id))
                continue
        serialized = _serialize_search_hit(hit, fallback=fallback)
        if _search_hit_is_usable(serialized):
            payload.append(serialized)

    return payload, sorted(stale_clause_ids), sorted(stale_standard_ids)


@router.post("/standards/upload")
async def upload_standard(
    files: list[UploadFile] = File(...),
    items_json: str = Form(...),
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(require_role(Role.EDITOR, Role.ADMIN)),
) -> list[dict]:
    """Upload multiple standard PDFs and enqueue them for OCR."""
    items = _load_batch_items(items_json)
    uploads = _build_upload_items(files, items)
    created: list[dict] = []

    os.makedirs(_UPLOAD_DIR, exist_ok=True)

    for file, item in uploads:
        content = await file.read()
        size_bytes = len(content)
        file_id = uuid4()
        content_type = file.content_type or "application/pdf"

        local_path = os.path.join(_UPLOAD_DIR, f"{file_id}.pdf")
        with open(local_path, "wb") as f:
            f.write(content)

        try:
            file_rec = _files.create(
                conn,
                file_id=file_id,
                project_id=_STANDARD_PROJECT_ID,
                filename=file.filename or "unnamed",
                content_type=content_type,
                size_bytes=size_bytes,
                storage_key=local_path,
            )
        except errors.ForeignKeyViolation:
            raise HTTPException(
                status_code=500,
                detail="Sentinel project not found. Run migration 0006.",
            )

        doc = _docs.create(conn, project_file_id=file_rec.id)
        std = _repo.create_standard(
            conn,
            standard_code=str(item["standard_code"]).strip(),
            standard_name=str(item["standard_name"]).strip(),
            version_year=str(item.get("version_year") or "").strip() or None,
            specialty=str(item.get("specialty") or "").strip() or None,
            document_id=doc.id,
        )
        _jobs.create(conn, standard_id=std["id"], document_id=doc.id)
        _repo.update_processing_status(conn, std["id"], "queued_ocr")
        created.append(_serialize_standard({
            **std,
            "document_id": doc.id,
            "processing_status": "queued_ocr",
            "ocr_status": "queued",
            "ai_status": "blocked",
        }))

    scheduler = ensure_standard_processing_scheduler_started()
    scheduler.wake()
    return created


@router.get("/standards/search")
async def search_standards(
    q: str = Query(..., min_length=1),
    specialty: str | None = Query(None),
    top_k: int = Query(10, ge=1, le=50),
    conn: Connection = Depends(get_db_conn),
) -> list[dict]:
    """Search indexed standard clauses and backfill viewer fields from PostgreSQL when needed."""
    for attempt in range(2):
        hits = await search_standard_clauses(q, specialty=specialty, top_k=top_k)
        payload, stale_clause_ids, stale_standard_ids = _build_search_payload(conn=conn, hits=hits)
        if not stale_clause_ids and not stale_standard_ids:
            return payload

        await asyncio.gather(
            delete_stale_clause_hits_from_index(stale_clause_ids),
            *[
                delete_standard_clauses_from_index(standard_id=standard_id)
                for standard_id in stale_standard_ids
            ],
        )
        if attempt == 1 or not stale_standard_ids:
            return payload

    return []


@router.get("/standards")
async def list_standards(
    conn: Connection = Depends(get_db_conn),
) -> list[dict]:
    """List all standards with processing status and clause count."""
    standards = _repo.list_standards(conn)
    result = []
    for s in standards:
        clause_count = _repo.get_clause_count(conn, s["id"])
        result.append(_serialize_standard(s, clause_count=clause_count))
    return result


@router.get("/standards/{standard_id}")
async def get_standard_detail(
    standard_id: UUID,
    conn: Connection = Depends(get_db_conn),
) -> dict:
    """Get standard detail with nested clause tree."""
    std = _repo.get_standard(conn, standard_id)
    if not std:
        raise HTTPException(status_code=404, detail="Standard not found")

    tree = _repo.get_clause_tree(conn, standard_id)
    clause_count = _repo.get_clause_count(conn, standard_id)

    return {
        **_serialize_standard(std, clause_count=clause_count),
        "clause_tree": tree,
    }


@router.get("/standards/{standard_id}/parse-assets")
async def get_standard_parse_assets(
    standard_id: UUID,
    conn: Connection = Depends(get_db_conn),
) -> dict:
    std = _repo.get_standard(conn, standard_id)
    if not std:
        raise HTTPException(status_code=404, detail="Standard not found")

    assets = _repo.get_standard_parse_assets(conn, standard_id=standard_id)
    if assets is None:
        raise HTTPException(status_code=404, detail="Standard source PDF not found")

    return {
        "standard_id": str(standard_id),
        "document": _serialize_parse_document(assets.get("document")),
        "sections": [_serialize_parse_section(section) for section in assets.get("sections", [])],
        "tables": [_serialize_parse_table(table) for table in assets.get("tables", [])],
    }


@router.get("/standards/{standard_id}/quality-report")
async def get_standard_quality_report(
    standard_id: UUID,
    conn: Connection = Depends(get_db_conn),
) -> dict:
    std, report = _build_quality_report_payload(conn, standard_id)
    return {
        "standard_id": str(standard_id),
        "standard_code": std["standard_code"],
        "standard_name": std["standard_name"],
        "processing_status": std.get("processing_status", "pending"),
        "ocr_status": std.get("ocr_status"),
        "ai_status": std.get("ai_status"),
        "report": report,
    }


@router.get("/standards/{standard_id}/viewer")
async def get_standard_viewer(
    standard_id: UUID,
    conn: Connection = Depends(get_db_conn),
) -> dict:
    """Get standard detail enriched with the source PDF URL for split-view browsing."""
    std = _repo.get_standard(conn, standard_id)
    if not std:
        raise HTTPException(status_code=404, detail="Standard not found")

    file_meta = _repo.get_standard_file(conn, standard_id)
    if not file_meta:
        raise HTTPException(status_code=404, detail="Standard source PDF not found")

    clause_count = _repo.get_clause_count(conn, standard_id)
    return {
        **_serialize_standard(std, clause_count=clause_count),
        "document_id": str(file_meta["document_id"]),
        "pdf_url": f"/api/standards/{standard_id}/pdf",
        "clause_tree": _repo.get_viewer_tree(conn, standard_id),
    }


@router.get("/standards/{standard_id}/pdf")
async def get_standard_pdf(
    standard_id: UUID,
    conn: Connection = Depends(get_db_conn),
) -> FileResponse:
    """Stream the uploaded source PDF for viewer-side preview."""
    std = _repo.get_standard(conn, standard_id)
    if not std:
        raise HTTPException(status_code=404, detail="Standard not found")

    file_meta = _repo.get_standard_file(conn, standard_id)
    if not file_meta or not file_meta.get("storage_key"):
        raise HTTPException(status_code=404, detail="Standard source PDF not found")

    file_path = _storage.resolve_local_path(
        str(file_meta["storage_key"]),
        filename=file_meta.get("filename"),
    )
    if file_path is None:
        raise HTTPException(status_code=404, detail="Standard source PDF not found")

    return FileResponse(
        str(file_path),
        media_type=file_meta.get("content_type") or "application/pdf",
        filename=file_meta.get("filename") or f"{standard_id}.pdf",
    )


@router.get("/standards/{standard_id}/clauses")
async def list_clauses(
    standard_id: UUID,
    clause_type: str | None = Query(None),
    conn: Connection = Depends(get_db_conn),
) -> list[dict]:
    """List flat clauses for a standard, optionally filtered by clause_type."""
    std = _repo.get_standard(conn, standard_id)
    if not std:
        raise HTTPException(status_code=404, detail="Standard not found")

    clauses = _repo.list_clauses(conn, standard_id=standard_id)

    if clause_type:
        clauses = [c for c in clauses if c.get("clause_type") == clause_type]

    return [
        {
            "id": str(c["id"]),
            "clause_no": c.get("clause_no"),
            "clause_title": c.get("clause_title"),
            "clause_text": c.get("clause_text"),
            "summary": c.get("summary"),
            "tags": c.get("tags", []),
            "clause_type": c.get("clause_type", "normative"),
            "page_start": c.get("page_start"),
            "page_end": c.get("page_end"),
            "sort_order": c.get("sort_order"),
            "parent_id": str(c["parent_id"]) if c.get("parent_id") else None,
            "source_type": c.get("source_type", "text"),
            "source_label": c.get("source_label"),
        }
        for c in clauses
    ]


@router.delete("/standards/{standard_id}")
async def delete_standard(
    standard_id: UUID,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(require_role(Role.EDITOR, Role.ADMIN)),
) -> dict:
    """Delete a standard aggregate once it is no longer actively processing."""
    std = _repo.get_standard(conn, standard_id)
    if not std:
        raise HTTPException(status_code=404, detail="Standard not found")

    if std.get("processing_status") in {"queued_ocr", "parsing", "queued_ai", "processing"}:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a standard while processing is active",
        )

    await delete_standard_clauses_from_index(standard_id=str(standard_id))
    file_meta = _repo.get_standard_file(conn, standard_id)
    deleted = _repo.delete_standard(conn, standard_id=standard_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Standard not found")

    _storage.delete_managed_file(file_meta.get("storage_key") if file_meta else None)

    return {"standard_id": str(standard_id), "deleted": True}

@router.post("/standards/{standard_id}/process")
async def trigger_processing(
    standard_id: UUID,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(require_role(Role.EDITOR, Role.ADMIN)),
) -> dict:
    """Retry a failed standard processing job by re-queuing the failed stage."""

    std = _repo.get_standard(conn, standard_id)
    if not std:
        raise HTTPException(status_code=404, detail="Standard not found")

    try:
        job = _jobs.retry(conn, standard_id=standard_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    next_status = "queued_ai" if job.ai_status == "queued" else "queued_ocr"
    _repo.update_processing_status(conn, standard_id, next_status)
    scheduler = ensure_standard_processing_scheduler_started()
    scheduler.wake()

    return {
        "standard_id": str(standard_id),
        "processing_status": next_status,
        "ocr_status": job.ocr_status,
        "ai_status": job.ai_status,
    }


@router.get("/standards/{standard_id}/status")
async def get_processing_status(
    standard_id: UUID,
    conn: Connection = Depends(get_db_conn),
) -> dict:
    """Get processing status, error info, and clause count."""
    std = _repo.get_standard(conn, standard_id)
    if not std:
        raise HTTPException(status_code=404, detail="Standard not found")

    clause_count = _repo.get_clause_count(conn, standard_id)

    return {
        "standard_id": str(standard_id),
        "processing_status": std.get("processing_status", "pending"),
        "error_message": std.get("error_message"),
        "ocr_status": std.get("ocr_status"),
        "ai_status": std.get("ai_status"),
        "clause_count": clause_count,
        "processing_started_at": std["processing_started_at"].isoformat() if std.get("processing_started_at") else None,
        "processing_finished_at": std["processing_finished_at"].isoformat() if std.get("processing_finished_at") else None,
    }
