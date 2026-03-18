"""Standards management API — upload, list, detail, process, status."""

from __future__ import annotations

import os
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from psycopg import Connection, errors

from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.document_repository import DocumentRepository
from tender_backend.db.repositories.file_repository import FileRepository
from tender_backend.db.repositories.standard_repo import StandardRepository

router = APIRouter(tags=["standards"])

_repo = StandardRepository()
_files = FileRepository()
_docs = DocumentRepository()

# Sentinel project ID for standard uploads
_STANDARD_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")

# Local directory for standard PDF storage (inside container volume)
_UPLOAD_DIR = os.environ.get("STANDARD_UPLOAD_DIR", "/workspace/data/standards")


@router.post("/standards/upload")
async def upload_standard(
    file: UploadFile = File(...),
    standard_code: str = Form(...),
    standard_name: str = Form(...),
    version_year: str | None = Form(None),
    specialty: str | None = Form(None),
    conn: Connection = Depends(get_db_conn),
) -> dict:
    """Upload a standard PDF and create standard + file + document records."""
    # Read file content
    content = await file.read()
    size_bytes = len(content)

    file_id = uuid4()
    filename = file.filename or "unnamed.pdf"
    content_type = file.content_type or "application/pdf"

    # Persist PDF to local filesystem
    os.makedirs(_UPLOAD_DIR, exist_ok=True)
    local_path = os.path.join(_UPLOAD_DIR, f"{file_id}.pdf")
    with open(local_path, "wb") as f:
        f.write(content)

    storage_key = local_path

    try:
        file_rec = _files.create(
            conn,
            file_id=file_id,
            project_id=_STANDARD_PROJECT_ID,
            filename=file.filename or "unnamed",
            content_type=content_type,
            size_bytes=size_bytes,
            storage_key=storage_key,
        )
    except errors.ForeignKeyViolation:
        raise HTTPException(
            status_code=500,
            detail="Sentinel project not found. Run migration 0006.",
        )

    # Create document record
    doc = _docs.create(conn, project_file_id=file_rec.id)

    # Create standard record linked to document
    std = _repo.create_standard(
        conn,
        standard_code=standard_code.strip(),
        standard_name=standard_name.strip(),
        version_year=version_year.strip() if version_year else None,
        specialty=specialty.strip() if specialty else None,
        document_id=doc.id,
    )

    return {
        "id": str(std["id"]),
        "standard_code": std["standard_code"],
        "standard_name": std["standard_name"],
        "document_id": str(doc.id),
        "processing_status": std.get("processing_status", "pending"),
    }


@router.get("/standards")
def list_standards(
    conn: Connection = Depends(get_db_conn),
) -> list[dict]:
    """List all standards with processing status and clause count."""
    standards = _repo.list_standards(conn)
    result = []
    for s in standards:
        clause_count = _repo.get_clause_count(conn, s["id"])
        result.append({
            "id": str(s["id"]),
            "standard_code": s["standard_code"],
            "standard_name": s["standard_name"],
            "version_year": s.get("version_year"),
            "specialty": s.get("specialty"),
            "status": s.get("status"),
            "processing_status": s.get("processing_status", "pending"),
            "clause_count": clause_count,
            "created_at": s["created_at"].isoformat() if s.get("created_at") else None,
        })
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
        "id": str(std["id"]),
        "standard_code": std["standard_code"],
        "standard_name": std["standard_name"],
        "version_year": std.get("version_year"),
        "specialty": std.get("specialty"),
        "status": std.get("status"),
        "processing_status": std.get("processing_status", "pending"),
        "error_message": std.get("error_message"),
        "processing_started_at": std["processing_started_at"].isoformat() if std.get("processing_started_at") else None,
        "processing_finished_at": std["processing_finished_at"].isoformat() if std.get("processing_finished_at") else None,
        "clause_count": clause_count,
        "clause_tree": tree,
        "created_at": std["created_at"].isoformat() if std.get("created_at") else None,
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
    """Trigger AI processing for a standard.

    Tries Celery first; falls back to in-process background thread
    when the broker is unreachable (e.g. no Celery worker running).
    """
    import threading

    import structlog

    logger = structlog.stdlib.get_logger(__name__)

    std = _repo.get_standard(conn, standard_id)
    if not std:
        raise HTTPException(status_code=404, detail="Standard not found")

    if std.get("processing_status") == "processing":
        raise HTTPException(status_code=409, detail="Already processing")

    if not std.get("document_id"):
        raise HTTPException(status_code=400, detail="No document linked to standard")

    # Mark as processing immediately so the frontend sees the change
    _repo.update_processing_status(conn, standard_id, "processing")

    document_id = str(std["document_id"])
    sid = str(standard_id)

    def _run_in_thread() -> None:
        from tender_backend.core.config import get_settings
        from tender_backend.db.pool import get_pool
        from tender_backend.services.norm_service.norm_processor import process_standard

        try:
            settings = get_settings()
            pool = get_pool(database_url=settings.database_url)
            with pool.connection() as bg_conn:
                process_standard(bg_conn, UUID(sid), document_id)
        except Exception:
            logger.exception("background_processing_failed", standard_id=sid)
            # Ensure status is set to failed even if process_standard didn't
            try:
                settings = get_settings()
                pool = get_pool(database_url=settings.database_url)
                with pool.connection() as bg_conn:
                    _repo.update_processing_status(
                        bg_conn, UUID(sid), "failed",
                        error_message="Background processing crashed",
                    )
            except Exception:
                logger.exception("failed_to_set_error_status", standard_id=sid)

    thread = threading.Thread(target=_run_in_thread, daemon=True)
    thread.start()
    logger.info("processing_thread_started", standard_id=sid, document_id=document_id)

    return {
        "standard_id": sid,
        "processing_status": "processing",
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
        "clause_count": clause_count,
        "processing_started_at": std["processing_started_at"].isoformat() if std.get("processing_started_at") else None,
        "processing_finished_at": std["processing_finished_at"].isoformat() if std.get("processing_finished_at") else None,
    }
