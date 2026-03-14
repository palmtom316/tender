from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from psycopg import Connection, errors

from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.file_repository import FileRepository


router = APIRouter(tags=["files"])

_repo = FileRepository()


class ProjectFileOut(BaseModel):
    id: UUID
    project_id: UUID
    filename: str
    content_type: str
    size_bytes: int
    storage_key: str | None


@router.post("/projects/{project_id}/files")
async def upload_file(
    project_id: UUID,
    upload: UploadFile = File(...),
    conn: Connection = Depends(get_db_conn),
) -> dict:
    # v0: persist metadata only; content storage is implemented in a later task.
    upload.file.seek(0, 2)
    size_bytes = int(upload.file.tell())
    upload.file.seek(0)

    content_type = upload.content_type or "application/octet-stream"
    try:
        rec = _repo.create(
            conn,
            project_id=project_id,
            filename=upload.filename or "unnamed",
            content_type=content_type,
            size_bytes=size_bytes,
        )
    except errors.ForeignKeyViolation:
        raise HTTPException(status_code=404, detail="project not found")

    return ProjectFileOut(
        id=rec.id,
        project_id=rec.project_id,
        filename=rec.filename,
        content_type=rec.content_type,
        size_bytes=rec.size_bytes,
        storage_key=rec.storage_key,
    ).model_dump()


@router.get("/projects/{project_id}/files")
def list_files(project_id: UUID, conn: Connection = Depends(get_db_conn)) -> list[dict]:
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
