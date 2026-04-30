from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from psycopg import Connection, errors

from tender_backend.core.config import Settings, get_settings
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.tender_document_repository import TenderDocumentRepository
from tender_backend.services.tender_document_ingestion import TenderDocumentIngestionService, UploadPayload


router = APIRouter(tags=["tender-documents"])

_repo = TenderDocumentRepository()


class TenderDocumentOut(BaseModel):
    id: UUID
    project_id: UUID
    original_filename: str
    upload_type: str
    status: str
    content_type: str
    size_bytes: int
    storage_key: str
    file_sha256: str
    error: str | None = None
    file_count: int | None = None


class TenderDocumentFileOut(BaseModel):
    id: UUID
    tender_document_id: UUID
    parent_file_id: UUID | None = None
    filename: str
    relative_path: str
    storage_key: str
    content_type: str
    size_bytes: int
    file_type: str
    classification: str
    depth: int
    is_archive: bool
    is_parsable: bool
    parse_status: str
    error: str | None = None


class TenderDocumentDetailOut(TenderDocumentOut):
    files: list[TenderDocumentFileOut]


def _document_out(row: dict) -> TenderDocumentOut:
    return TenderDocumentOut(
        id=row["id"],
        project_id=row["project_id"],
        original_filename=row["original_filename"],
        upload_type=row["upload_type"],
        status=row["status"],
        content_type=row["content_type"],
        size_bytes=row["size_bytes"],
        storage_key=row["storage_key"],
        file_sha256=row["file_sha256"],
        error=row.get("error"),
        file_count=row.get("file_count"),
    )


def _file_out(row: dict) -> TenderDocumentFileOut:
    return TenderDocumentFileOut(
        id=row["id"],
        tender_document_id=row["tender_document_id"],
        parent_file_id=row["parent_file_id"],
        filename=row["filename"],
        relative_path=row["relative_path"],
        storage_key=row["storage_key"],
        content_type=row["content_type"],
        size_bytes=row["size_bytes"],
        file_type=row["file_type"],
        classification=row["classification"],
        depth=row["depth"],
        is_archive=row["is_archive"],
        is_parsable=row["is_parsable"],
        parse_status=row["parse_status"],
        error=row.get("error"),
    )


def _service(settings: Settings) -> TenderDocumentIngestionService:
    return TenderDocumentIngestionService(storage_root=settings.tender_document_storage_root, repository=_repo)


@router.post("/projects/{project_id}/tender-documents", response_model=TenderDocumentDetailOut)
async def upload_tender_document(
    project_id: UUID,
    file: UploadFile = File(...),
    conn: Connection = Depends(get_db_conn),
    settings: Settings = Depends(get_settings),
) -> TenderDocumentDetailOut:
    filename = file.filename or "unnamed"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="file is empty")

    try:
        document = _service(settings).ingest_upload(
            conn,
            project_id=project_id,
            payload=UploadPayload(
                filename=filename,
                content_type=file.content_type or "application/octet-stream",
                content=content,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except errors.ForeignKeyViolation:
        raise HTTPException(status_code=404, detail="project not found")

    files = _repo.list_files(conn, tender_document_id=document["id"])
    return TenderDocumentDetailOut(**_document_out(document).model_dump(), files=[_file_out(row) for row in files])


@router.get("/projects/{project_id}/tender-documents", response_model=list[TenderDocumentOut])
async def list_tender_documents(project_id: UUID, conn: Connection = Depends(get_db_conn)) -> list[TenderDocumentOut]:
    return [_document_out(row) for row in _repo.list_documents(conn, project_id=project_id)]


@router.get("/tender-documents/{tender_document_id}", response_model=TenderDocumentDetailOut)
async def get_tender_document(
    tender_document_id: UUID,
    conn: Connection = Depends(get_db_conn),
) -> TenderDocumentDetailOut:
    document = _repo.get_document(conn, tender_document_id=tender_document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="tender document not found")
    files = _repo.list_files(conn, tender_document_id=tender_document_id)
    return TenderDocumentDetailOut(**_document_out(document).model_dump(), files=[_file_out(row) for row in files])


@router.get("/tender-documents/{tender_document_id}/files", response_model=list[TenderDocumentFileOut])
async def list_tender_document_files(
    tender_document_id: UUID,
    conn: Connection = Depends(get_db_conn),
) -> list[TenderDocumentFileOut]:
    if _repo.get_document(conn, tender_document_id=tender_document_id) is None:
        raise HTTPException(status_code=404, detail="tender document not found")
    return [_file_out(row) for row in _repo.list_files(conn, tender_document_id=tender_document_id)]
