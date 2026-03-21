from __future__ import annotations

from uuid import uuid4
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from psycopg import Connection, errors

from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.document_repository import DocumentRepository
from tender_backend.db.repositories.file_repository import FileRepository


router = APIRouter(tags=["files"])

_repo = FileRepository()
_docs = DocumentRepository()


@router.post("/projects/{project_id}/files")
async def upload_file(
    project_id: UUID,
    file: UploadFile | None = File(None),
    upload: UploadFile | None = File(None),  # backward-compat for early internal clients
    conn: Connection = Depends(get_db_conn),
) -> dict:
    upload = file or upload
    if upload is None:
        raise HTTPException(status_code=422, detail="file is required")

    # v0: persist metadata only; content storage is implemented in a later task.
    upload.file.seek(0, 2)
    size_bytes = int(upload.file.tell())
    upload.file.seek(0)

    file_id = uuid4()
    storage_key = f"tender-raw/{project_id}/{file_id}/{upload.filename or 'unnamed'}"
    content_type = upload.content_type or "application/octet-stream"
    try:
        rec = _repo.create(
            conn,
            file_id=file_id,
            project_id=project_id,
            filename=upload.filename or "unnamed",
            content_type=content_type,
            size_bytes=size_bytes,
            storage_key=storage_key,
        )
    except errors.ForeignKeyViolation:
        raise HTTPException(status_code=404, detail="project not found")

    doc = _docs.create(conn, project_file_id=rec.id)
    return {
        "file_id": str(rec.id),
        "document_id": str(doc.id),
        "file_name": rec.filename,
        "storage_path": rec.storage_key,
        "parsed": False,
        "content_type": rec.content_type,
        "size_bytes": rec.size_bytes,
    }


@router.get("/projects/{project_id}/files")
async def list_files(project_id: UUID, conn: Connection = Depends(get_db_conn)) -> list[dict]:
    rows = _repo.list(conn, project_id=project_id)
    return [
        {
            "id": str(r.id),
            "project_id": str(r.project_id),
            "filename": r.filename,
            "content_type": r.content_type,
            "size_bytes": r.size_bytes,
            "storage_key": r.storage_key,
        }
        for r in rows
    ]
