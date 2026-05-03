from __future__ import annotations

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from psycopg import Connection, errors

from tender_backend.core.config import Settings, get_settings
from tender_backend.core.path_safety import ensure_path_within_root
from tender_backend.core.project_access import require_project_access, require_resource_project_access
from tender_backend.core.security import CurrentUser, get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.agent_config_repo import AgentConfigRepository
from tender_backend.db.repositories.requirement_repo import RequirementRepository
from tender_backend.db.repositories.tender_document_repository import TenderDocumentRepository
from tender_backend.services.deepseek_api import (
    DEEPSEEK_V4_MAX_REASONING_EFFORT,
    DEEPSEEK_V4_PRO_MODEL,
    deepseek_v4_thinking_options,
)
from tender_backend.services.extract_service.requirements_extractor import extract_requirements_from_source_chunks
from tender_backend.services.extract_service.ai_requirements_extractor import (
    extract_requirements_with_ai,
)
from tender_backend.services.office_document_parser import (
    OFFICE_PARSER_NAME,
    OFFICE_PARSER_VERSION,
    OfficeParseError,
    parse_office_file,
)
from tender_backend.services.pdf_document_parser import (
    PDF_PARSER_NAME,
    PDF_PARSER_VERSION,
    PdfParseError,
    parse_pdf_with_mineru,
)
from tender_backend.services.tender_document_ingestion import TenderDocumentIngestionService, UploadPayload


router = APIRouter(tags=["tender-documents"], dependencies=[Depends(get_current_user)])

_repo = TenderDocumentRepository()
_requirement_repo = RequirementRepository()
_agent_repo = AgentConfigRepository()
_UPLOAD_CHUNK_SIZE = 1024 * 1024
_DOCUMENT_PROJECT_QUERY = "SELECT project_id FROM tender_document WHERE id = %s"
_FILE_PROJECT_QUERY = """
    SELECT td.project_id
    FROM tender_document_file f
    JOIN tender_document td ON td.id = f.tender_document_id
    WHERE f.id = %s
"""
_SOURCE_CHUNK_PROJECT_QUERY = """
    SELECT td.project_id
    FROM source_chunk sc
    JOIN tender_document td ON td.id = sc.tender_document_id
    WHERE sc.id = %s
"""


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
    document_type: str | None = None
    section_title: str | None = None
    source_locator: str
    title: str | None = None
    text: str | None = None
    table_json: dict | None = None
    page_start: int | None = None
    page_end: int | None = None
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


class TenderDocumentParseStatusOut(BaseModel):
    tender_document_id: UUID
    document_status: str
    total_file_count: int
    pending_file_count: int
    parsing_file_count: int
    completed_file_count: int
    failed_file_count: int
    skipped_file_count: int
    chunk_count: int
    files: list[TenderDocumentFileOut]


class TenderDocumentRequirementExtractionOut(BaseModel):
    tender_document_id: UUID
    project_id: UUID
    model: str
    model_source: str
    extracted_count: int
    persisted_count: int
    category_counts: dict[str, int]
    requirements: list[dict]


class TenderDocumentAiExtractionOut(BaseModel):
    tender_document_id: UUID
    project_id: UUID
    model: str
    extracted_count: int
    persisted_count: int
    dropped_invalid: int
    failed_batches: int
    total_input_tokens: int
    total_output_tokens: int
    category_counts: dict[str, int]
    extraction_method_counts: dict[str, int]
    requirements: list[dict]


class SourceChunkUpdateBody(BaseModel):
    chunk_type: str | None = None
    document_type: str | None = None
    section_title: str | None = None
    source_locator: str | None = None
    title: str | None = None
    text: str | None = None
    table_json: dict | None = None
    page_start: int | None = None
    page_end: int | None = None
    sheet_name: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    paragraph_index: int | None = None
    sort_order: int | None = None
    confidence: float | None = None
    metadata_json: dict | None = None


class TenderDocumentFileClassificationUpdateBody(BaseModel):
    classification: str
    is_parsable: bool | None = None
    review_note: str | None = None


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
        document_type=row.get("document_type"),
        section_title=row.get("section_title"),
        source_locator=row["source_locator"],
        title=row.get("title"),
        text=row.get("text"),
        table_json=row.get("table_json"),
        page_start=row.get("page_start"),
        page_end=row.get("page_end"),
        sheet_name=row.get("sheet_name"),
        row_start=row.get("row_start"),
        row_end=row.get("row_end"),
        paragraph_index=row.get("paragraph_index"),
        sort_order=row["sort_order"],
        confidence=float(row["confidence"]),
    )


def _service(settings: Settings) -> TenderDocumentIngestionService:
    return TenderDocumentIngestionService(storage_root=settings.tender_document_storage_root, repository=_repo)


def _parse_status_out(document: dict, files: list[dict], chunk_count: int) -> TenderDocumentParseStatusOut:
    counts = {
        "pending": 0,
        "parsing": 0,
        "completed": 0,
        "failed": 0,
        "skipped": 0,
    }
    for row in files:
        status = str(row.get("parse_status") or "pending")
        counts[status] = counts.get(status, 0) + 1
    return TenderDocumentParseStatusOut(
        tender_document_id=document["id"],
        document_status=document["status"],
        total_file_count=len(files),
        pending_file_count=counts.get("pending", 0),
        parsing_file_count=counts.get("parsing", 0),
        completed_file_count=counts.get("completed", 0),
        failed_file_count=counts.get("failed", 0),
        skipped_file_count=counts.get("skipped", 0),
        chunk_count=chunk_count,
        files=[_file_out(row) for row in files],
    )


async def _read_upload_with_limit(file: UploadFile, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail=f"file exceeds {max_bytes} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


async def _parse_file(conn: Connection, file_row: dict, *, settings: Settings) -> tuple[str, int]:
    if not file_row["is_parsable"] or file_row["is_archive"]:
        _repo.update_file_parse_status(conn, tender_document_file_id=file_row["id"], parse_status="skipped", error=None)
        return "skipped", 0
    if file_row["file_type"] not in {"doc", "docx", "xls", "xlsx", "pdf", "wps"}:
        _repo.update_file_parse_status(conn, tender_document_file_id=file_row["id"], parse_status="skipped", error=None)
        return "skipped", 0

    try:
        path = ensure_path_within_root(
            file_row["storage_key"],
            settings.tender_document_storage_root,
            label="tender document file path",
        )
    except ValueError:
        _repo.update_file_parse_status(
            conn,
            tender_document_file_id=file_row["id"],
            parse_status="failed",
            error="source file path is outside tender document storage root",
        )
        return "failed", 0
    if not path.is_file():
        _repo.update_file_parse_status(
            conn,
            tender_document_file_id=file_row["id"],
            parse_status="failed",
            error="source file not found",
        )
        return "failed", 0

    _repo.update_file_parse_status(conn, tender_document_file_id=file_row["id"], parse_status="parsing", error=None)
    parser_name: str
    parser_version: str
    parser_file_type: str
    try:
        if file_row["file_type"] == "pdf":
            parser_name = PDF_PARSER_NAME
            parser_version = PDF_PARSER_VERSION
            parser_file_type = "pdf"
            chunks = await parse_pdf_with_mineru(path, source_file=file_row["relative_path"])
        else:
            parser_name = OFFICE_PARSER_NAME
            parser_version = OFFICE_PARSER_VERSION
            parser_file_type, chunks = await asyncio.to_thread(
                parse_office_file,
                path,
                source_file=file_row["relative_path"],
            )
    except (OfficeParseError, PdfParseError) as exc:
        _repo.update_file_parse_status(
            conn,
            tender_document_file_id=file_row["id"],
            parse_status="failed",
            error=str(exc),
        )
        return "failed", 0

    document_type = file_row.get("classification")
    for chunk in chunks:
        chunk.setdefault("document_type", document_type)
        chunk.setdefault("section_title", chunk.get("title"))

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
            "parser_name": parser_name,
            "parser_version": parser_version,
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
    user: CurrentUser = Depends(get_current_user),
) -> TenderDocumentDetailOut:
    require_project_access(conn, project_id=project_id, user=user)
    filename = file.filename or "unnamed"
    content = await _read_upload_with_limit(file, max_bytes=settings.tender_document_upload_max_bytes)
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
async def list_tender_documents(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[TenderDocumentOut]:
    require_project_access(conn, project_id=project_id, user=user)
    return [_document_out(row) for row in _repo.list_documents(conn, project_id=project_id)]


@router.get("/tender-documents/{tender_document_id}", response_model=TenderDocumentDetailOut)
async def get_tender_document(
    tender_document_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> TenderDocumentDetailOut:
    require_resource_project_access(
        conn,
        resource_id=tender_document_id,
        query=_DOCUMENT_PROJECT_QUERY,
        not_found_detail="tender document not found",
        user=user,
    )
    document = _repo.get_document(conn, tender_document_id=tender_document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="tender document not found")
    files = _repo.list_files(conn, tender_document_id=tender_document_id)
    return TenderDocumentDetailOut(**_document_out(document).model_dump(), files=[_file_out(row) for row in files])


@router.get("/tender-documents/{tender_document_id}/files", response_model=list[TenderDocumentFileOut])
async def list_tender_document_files(
    tender_document_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[TenderDocumentFileOut]:
    require_resource_project_access(
        conn,
        resource_id=tender_document_id,
        query=_DOCUMENT_PROJECT_QUERY,
        not_found_detail="tender document not found",
        user=user,
    )
    if _repo.get_document(conn, tender_document_id=tender_document_id) is None:
        raise HTTPException(status_code=404, detail="tender document not found")
    return [_file_out(row) for row in _repo.list_files(conn, tender_document_id=tender_document_id)]


@router.patch("/tender-document-files/{tender_document_file_id}/classification", response_model=TenderDocumentFileOut)
async def update_tender_document_file_classification(
    tender_document_file_id: UUID,
    payload: TenderDocumentFileClassificationUpdateBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> TenderDocumentFileOut:
    require_resource_project_access(
        conn,
        resource_id=tender_document_file_id,
        query=_FILE_PROJECT_QUERY,
        not_found_detail="tender document file not found",
        user=user,
    )
    existing = _repo.get_file(conn, tender_document_file_id=tender_document_file_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="tender document file not found")
    metadata = dict(existing.get("metadata_json") or {})
    metadata["classification_review"] = {
        "previous_classification": existing.get("classification"),
        "review_note": payload.review_note,
    }
    row = _repo.update_file_classification(
        conn,
        tender_document_file_id=tender_document_file_id,
        classification=payload.classification,
        is_parsable=payload.is_parsable,
        metadata_json=metadata,
    )
    conn.commit()
    if row is None:
        raise HTTPException(status_code=500, detail="failed to update tender document file")
    return _file_out(row)


@router.post("/tender-documents/{tender_document_id}/parse", response_model=TenderDocumentParseOut)
async def parse_tender_document(
    tender_document_id: UUID,
    conn: Connection = Depends(get_db_conn),
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(get_current_user),
) -> TenderDocumentParseOut:
    require_resource_project_access(
        conn,
        resource_id=tender_document_id,
        query=_DOCUMENT_PROJECT_QUERY,
        not_found_detail="tender document not found",
        user=user,
    )
    if _repo.get_document(conn, tender_document_id=tender_document_id) is None:
        raise HTTPException(status_code=404, detail="tender document not found")

    parsed = 0
    failed = 0
    skipped = 0
    chunk_count = 0
    files = _repo.list_files(conn, tender_document_id=tender_document_id)
    for file_row in files:
        status, count = await _parse_file(conn, file_row, settings=settings)
        chunk_count += count
        if status == "parsed":
            parsed += 1
        elif status == "failed":
            failed += 1
        else:
            skipped += 1
    conn.commit()

    updated_files = _repo.list_files(conn, tender_document_id=tender_document_id)
    return TenderDocumentParseOut(
        tender_document_id=tender_document_id,
        parsed_file_count=parsed,
        failed_file_count=failed,
        skipped_file_count=skipped,
        chunk_count=chunk_count,
        files=[_file_out(row) for row in updated_files],
    )


@router.get("/tender-documents/{tender_document_id}/parse-status", response_model=TenderDocumentParseStatusOut)
async def get_tender_document_parse_status(
    tender_document_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> TenderDocumentParseStatusOut:
    require_resource_project_access(
        conn,
        resource_id=tender_document_id,
        query=_DOCUMENT_PROJECT_QUERY,
        not_found_detail="tender document not found",
        user=user,
    )
    document = _repo.get_document(conn, tender_document_id=tender_document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="tender document not found")
    files = _repo.list_files(conn, tender_document_id=tender_document_id)
    chunk_count = len(_repo.list_source_chunks(conn, tender_document_id=tender_document_id))
    return _parse_status_out(document, files, chunk_count)


@router.post("/tender-document-files/{tender_document_file_id}/parse", response_model=TenderDocumentFileOut)
async def parse_tender_document_file(
    tender_document_file_id: UUID,
    conn: Connection = Depends(get_db_conn),
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(get_current_user),
) -> TenderDocumentFileOut:
    require_resource_project_access(
        conn,
        resource_id=tender_document_file_id,
        query=_FILE_PROJECT_QUERY,
        not_found_detail="tender document file not found",
        user=user,
    )
    file_row = _repo.get_file(conn, tender_document_file_id=tender_document_file_id)
    if file_row is None:
        raise HTTPException(status_code=404, detail="tender document file not found")
    status, _ = await _parse_file(conn, file_row, settings=settings)
    conn.commit()
    updated = _repo.get_file(conn, tender_document_file_id=tender_document_file_id)
    assert updated is not None
    if status == "skipped":
        raise HTTPException(status_code=400, detail="file is not a supported tender source document")
    return _file_out(updated)


@router.get("/tender-documents/{tender_document_id}/source-chunks", response_model=list[SourceChunkOut])
async def list_tender_source_chunks(
    tender_document_id: UUID,
    tender_document_file_id: UUID | None = None,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[SourceChunkOut]:
    require_resource_project_access(
        conn,
        resource_id=tender_document_id,
        query=_DOCUMENT_PROJECT_QUERY,
        not_found_detail="tender document not found",
        user=user,
    )
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


@router.get("/tender-documents/{tender_document_id}/source-chunks/download")
async def download_tender_source_chunks(
    tender_document_id: UUID,
    tender_document_file_id: UUID | None = None,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> Response:
    require_resource_project_access(
        conn,
        resource_id=tender_document_id,
        query=_DOCUMENT_PROJECT_QUERY,
        not_found_detail="tender document not found",
        user=user,
    )
    document = _repo.get_document(conn, tender_document_id=tender_document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="tender document not found")
    rows = _repo.list_source_chunks(
        conn,
        tender_document_id=tender_document_id,
        tender_document_file_id=tender_document_file_id,
    )
    payload = {
        "tender_document_id": str(tender_document_id),
        "project_id": str(document["project_id"]),
        "count": len(rows),
        "chunks": rows,
    }
    content = json.dumps(payload, ensure_ascii=False, default=str, indent=2)
    return Response(
        content=content,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="tender-document-{tender_document_id}-source-chunks.json"'},
    )


@router.patch("/source-chunks/{source_chunk_id}", response_model=SourceChunkOut)
async def update_source_chunk(
    source_chunk_id: UUID,
    payload: SourceChunkUpdateBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> SourceChunkOut:
    require_resource_project_access(
        conn,
        resource_id=source_chunk_id,
        query=_SOURCE_CHUNK_PROJECT_QUERY,
        not_found_detail="source chunk not found",
        user=user,
    )
    row = _repo.update_source_chunk(
        conn,
        source_chunk_id=source_chunk_id,
        fields=payload.model_dump(exclude_unset=True),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="source chunk not found")
    conn.commit()
    return _chunk_out(row)


@router.post(
    "/tender-documents/{tender_document_id}/extract-requirements",
    response_model=TenderDocumentRequirementExtractionOut,
)
@router.post(
    "/tender-documents/{tender_document_id}/extract-constraints",
    response_model=TenderDocumentRequirementExtractionOut,
)
async def extract_tender_document_requirements(
    tender_document_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> TenderDocumentRequirementExtractionOut:
    require_resource_project_access(
        conn,
        resource_id=tender_document_id,
        query=_DOCUMENT_PROJECT_QUERY,
        not_found_detail="tender document not found",
        user=user,
    )
    document = _repo.get_document(conn, tender_document_id=tender_document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="tender document not found")

    chunks = _repo.list_source_chunks(conn, tender_document_id=tender_document_id)
    if not chunks:
        raise HTTPException(status_code=400, detail="no source chunks found; parse the tender document first")

    extracted = extract_requirements_from_source_chunks(chunks)
    payload = [item.to_dict() for item in extracted]
    config = _agent_repo.get_by_key(conn, "extract")
    model = (config.primary_model if config and config.primary_model else DEEPSEEK_V4_PRO_MODEL)
    model_source = "agent_config.extract" if config else "default"
    thinking_options = deepseek_v4_thinking_options(reasoning_effort=DEEPSEEK_V4_MAX_REASONING_EFFORT)
    for item in payload:
        source_metadata = item.get("source_metadata") if isinstance(item.get("source_metadata"), dict) else {}
        source_metadata["ai_parse_default_model"] = model
        source_metadata["ai_parse_model_source"] = model_source
        source_metadata["ai_parse_thinking"] = thinking_options["thinking"]
        source_metadata["ai_parse_reasoning_effort"] = thinking_options["reasoning_effort"]
        item["source_metadata"] = source_metadata
    persisted = _requirement_repo.create_many(
        conn,
        project_id=document["project_id"],
        requirements=payload,
    )

    category_counts: dict[str, int] = {}
    for item in persisted:
        category = str(item["category"])
        category_counts[category] = category_counts.get(category, 0) + 1

    return TenderDocumentRequirementExtractionOut(
        tender_document_id=tender_document_id,
        project_id=document["project_id"],
        model=model,
        model_source=model_source,
        extracted_count=len(extracted),
        persisted_count=len(persisted),
        category_counts=category_counts,
        requirements=persisted,
    )


@router.post(
    "/tender-documents/{tender_document_id}/ai-extract-requirements",
    response_model=TenderDocumentAiExtractionOut,
)
async def ai_extract_tender_document_requirements(
    tender_document_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> TenderDocumentAiExtractionOut:
    """Run AI-powered requirement extraction over the tender document.

    Calls the AI Gateway with `task_type=extract_tender_requirements`
    (deepseek-v4-pro + reasoning_effort=max). Persists results into
    project_requirement and conflicts on (project_id, category, source_chunk_id,
    source_locator) — when a prior keyword candidate exists for the same chunk
    and category the row is upgraded to extraction_method='merged'.
    """
    require_resource_project_access(
        conn,
        resource_id=tender_document_id,
        query=_DOCUMENT_PROJECT_QUERY,
        not_found_detail="tender document not found",
        user=user,
    )
    document = _repo.get_document(conn, tender_document_id=tender_document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="tender document not found")

    chunks = _repo.list_source_chunks(conn, tender_document_id=tender_document_id)
    if not chunks:
        raise HTTPException(
            status_code=400,
            detail="no source chunks found; parse the tender document first",
        )

    persist_lock = asyncio.Lock()
    persisted: list[dict] = []

    async def _persist(batch_requirements):
        if not batch_requirements:
            return
        payload = [item.to_repository_dict() for item in batch_requirements]
        async with persist_lock:
            rows = await asyncio.to_thread(
                _requirement_repo.create_many,
                conn,
                project_id=document["project_id"],
                requirements=payload,
            )
        persisted.extend(rows)

    summary = await extract_requirements_with_ai(
        chunks,
        conn=conn,
        on_batch_persisted=_persist,
    )

    category_counts: dict[str, int] = {}
    method_counts: dict[str, int] = {}
    for item in persisted:
        category = str(item["category"])
        category_counts[category] = category_counts.get(category, 0) + 1
        method = str(item.get("extraction_method") or "ai")
        method_counts[method] = method_counts.get(method, 0) + 1

    failed_batches = sum(1 for b in summary.batches if b.extracted == 0 and b.input_tokens == 0)
    dropped_invalid = sum(b.dropped_invalid for b in summary.batches)
    resolved_models = {b.resolved_model for b in summary.batches if b.resolved_model}
    model_label = ", ".join(sorted(resolved_models)) or DEEPSEEK_V4_PRO_MODEL

    return TenderDocumentAiExtractionOut(
        tender_document_id=tender_document_id,
        project_id=document["project_id"],
        model=model_label,
        extracted_count=len(summary.requirements),
        persisted_count=len(persisted),
        dropped_invalid=dropped_invalid,
        failed_batches=failed_batches,
        total_input_tokens=summary.total_input_tokens,
        total_output_tokens=summary.total_output_tokens,
        category_counts=category_counts,
        extraction_method_counts=method_counts,
        requirements=persisted,
    )
