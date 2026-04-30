from __future__ import annotations

from uuid import UUID
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from psycopg import Connection, errors

from tender_backend.core.config import Settings, get_settings
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.tender_document_repository import TenderDocumentRepository
from tender_backend.services.office_document_parser import (
    OFFICE_PARSER_NAME,
    OFFICE_PARSER_VERSION,
    OfficeParseError,
    parse_office_file,
)
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


class SourceChunkOut(BaseModel):
    id: UUID
    tender_document_id: UUID
    tender_document_file_id: UUID
    chunk_type: str
    source_file: str
    source_locator: str
    title: str | None = None
    text: str | None = None
    table_json: dict | None = None
    sheet_name: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    paragraph_index: int | None = None
    sort_order: int
    confidence: float


class TenderDocumentParseOut(BaseModel):
    tender_document_id: UUID
    parsed_file_count: int
    failed_file_count: int
    skipped_file_count: int
    chunk_count: int
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


def _chunk_out(row: dict) -> SourceChunkOut:
    return SourceChunkOut(
        id=row["id"],
        tender_document_id=row["tender_document_id"],
        tender_document_file_id=row["tender_document_file_id"],
        chunk_type=row["chunk_type"],
        source_file=row["source_file"],
        source_locator=row["source_locator"],
        title=row.get("title"),
        text=row.get("text"),
        table_json=row.get("table_json"),
        sheet_name=row.get("sheet_name"),
        row_start=row.get("row_start"),
        row_end=row.get("row_end"),
        paragraph_index=row.get("paragraph_index"),
        sort_order=row["sort_order"],
        confidence=float(row["confidence"]),
    )


def _service(settings: Settings) -> TenderDocumentIngestionService:
    return TenderDocumentIngestionService(storage_root=settings.tender_document_storage_root, repository=_repo)


def _parse_file(conn: Connection, file_row: dict) -> tuple[str, int]:
    if not file_row["is_parsable"] or file_row["is_archive"]:
        return "skipped", 0
    if file_row["file_type"] not in {"doc", "docx", "xls", "xlsx"}:
        return "skipped", 0

    path = Path(file_row["storage_key"])
    if not path.is_file():
        _repo.update_file_parse_status(
            conn,
            tender_document_file_id=file_row["id"],
            parse_status="failed",
            error="source file not found",
        )
        return "failed", 0

    _repo.update_file_parse_status(conn, tender_document_file_id=file_row["id"], parse_status="parsing", error=None)
    try:
        parser_file_type, chunks = parse_office_file(path, source_file=file_row["relative_path"])
    except OfficeParseError as exc:
        _repo.update_file_parse_status(
            conn,
            tender_document_file_id=file_row["id"],
            parse_status="failed",
            error=str(exc),
        )
        return "failed", 0

    _repo.replace_source_chunks(
        conn,
        tender_document_id=file_row["tender_document_id"],
        tender_document_file_id=file_row["id"],
        chunks=chunks,
    )
    _repo.update_file_parse_status(
        conn,
        tender_document_file_id=file_row["id"],
        parse_status="completed",
        error=None,
        metadata_json={
            "parser_name": OFFICE_PARSER_NAME,
            "parser_version": OFFICE_PARSER_VERSION,
            "parser_file_type": parser_file_type,
            "chunk_count": len(chunks),
        },
    )
    return "parsed", len(chunks)


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


@router.post("/tender-documents/{tender_document_id}/parse", response_model=TenderDocumentParseOut)
async def parse_tender_document(
    tender_document_id: UUID,
    conn: Connection = Depends(get_db_conn),
) -> TenderDocumentParseOut:
    if _repo.get_document(conn, tender_document_id=tender_document_id) is None:
        raise HTTPException(status_code=404, detail="tender document not found")

    parsed = 0
    failed = 0
    skipped = 0
    chunk_count = 0
    files = _repo.list_files(conn, tender_document_id=tender_document_id)
    for file_row in files:
        status, count = _parse_file(conn, file_row)
        chunk_count += count
        if status == "parsed":
            parsed += 1
        elif status == "failed":
            failed += 1
        else:
            skipped += 1

    updated_files = _repo.list_files(conn, tender_document_id=tender_document_id)
    return TenderDocumentParseOut(
        tender_document_id=tender_document_id,
        parsed_file_count=parsed,
        failed_file_count=failed,
        skipped_file_count=skipped,
        chunk_count=chunk_count,
        files=[_file_out(row) for row in updated_files],
    )


@router.post("/tender-document-files/{tender_document_file_id}/parse", response_model=TenderDocumentFileOut)
async def parse_tender_document_file(
    tender_document_file_id: UUID,
    conn: Connection = Depends(get_db_conn),
) -> TenderDocumentFileOut:
    file_row = _repo.get_file(conn, tender_document_file_id=tender_document_file_id)
    if file_row is None:
        raise HTTPException(status_code=404, detail="tender document file not found")
    status, _ = _parse_file(conn, file_row)
    updated = _repo.get_file(conn, tender_document_file_id=tender_document_file_id)
    assert updated is not None
    if status == "skipped":
        raise HTTPException(status_code=400, detail="file is not a supported Office document")
    return _file_out(updated)


@router.get("/tender-documents/{tender_document_id}/source-chunks", response_model=list[SourceChunkOut])
async def list_tender_source_chunks(
    tender_document_id: UUID,
    tender_document_file_id: UUID | None = None,
    conn: Connection = Depends(get_db_conn),
) -> list[SourceChunkOut]:
    if _repo.get_document(conn, tender_document_id=tender_document_id) is None:
        raise HTTPException(status_code=404, detail="tender document not found")
    return [
        _chunk_out(row)
        for row in _repo.list_source_chunks(
            conn,
            tender_document_id=tender_document_id,
            tender_document_file_id=tender_document_file_id,
        )
    ]
