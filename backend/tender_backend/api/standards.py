"""Standards management API — upload, list, detail, process, status."""

from __future__ import annotations

import json
import os
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from psycopg import Connection, errors

from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.document_repository import DocumentRepository
from tender_backend.db.repositories.file_repository import FileRepository
from tender_backend.db.repositories.standard_processing_job_repository import (
    StandardProcessingJobRepository,
)
from tender_backend.db.repositories.standard_repo import StandardRepository
from tender_backend.services.norm_service.standard_processing_scheduler import (
    ensure_standard_processing_scheduler_started,
)

router = APIRouter(tags=["standards"])

_repo = StandardRepository()
_jobs = StandardProcessingJobRepository()
_files = FileRepository()
_docs = DocumentRepository()

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


@router.post("/standards/upload")
async def upload_standard(
    files: list[UploadFile] = File(...),
    items_json: str = Form(...),
    conn: Connection = Depends(get_db_conn),
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


@router.get("/standards")
def list_standards(
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
def get_standard_detail(
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


@router.get("/standards/{standard_id}/clauses")
def list_clauses(
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
        }
        for c in clauses
    ]


@router.post("/standards/{standard_id}/process")
def trigger_processing(
    standard_id: UUID,
    conn: Connection = Depends(get_db_conn),
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
def get_processing_status(
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
