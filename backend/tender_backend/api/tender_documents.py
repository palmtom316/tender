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
from tender_backend.db.repositories.scoring_repo import ScoringRepository
from tender_backend.db.repositories.tender_ai_extraction_repo import TenderAiExtractionRepository
from tender_backend.db.repositories.tender_document_repository import TenderDocumentRepository
from tender_backend.db.repositories.tender_summary_repo import TenderSummaryRepository
from tender_backend.services.extract_service.ai_extraction_planner import (
    DEFAULT_MODEL_POLICY,
    build_extraction_batch_plan,
)
from tender_backend.services.deepseek_api import (
    DEEPSEEK_V4_MAX_REASONING_EFFORT,
    DEEPSEEK_V4_PRO_MODEL,
    deepseek_v4_thinking_options,
)
from tender_backend.services.extract_service.requirements_extractor import extract_requirements_from_source_chunks
from tender_backend.services.extract_service.ai_requirements_extractor import (
    extract_requirements_with_ai,
)
from tender_backend.services.extract_service.tender_facts_extractor import extract_tender_summary_with_ai
from tender_backend.services.extract_service.scoring_extractor import extract_scoring_criteria_from_source_chunks
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
_ai_extraction_repo = TenderAiExtractionRepository()
_summary_repo = TenderSummaryRepository()
_scoring_repo = ScoringRepository()
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
    total_batches: int
    dropped_invalid: int
    failed_batches: int
    failed_batch_files: list[str]
    zero_requirement_source_files: list[str]
    total_input_tokens: int
    total_output_tokens: int
    category_counts: dict[str, int]
    extraction_method_counts: dict[str, int]
    requirements: list[dict]


class TenderDocumentAiExtractionAcceptedOut(BaseModel):
    tender_document_id: UUID
    project_id: UUID
    run_id: UUID
    status: str
    total_batches: int
    skipped_batches: int
    message: str


class TenderAiExtractionRunCreateBody(BaseModel):
    mode: str = "requirements"
    model_policy: str = DEFAULT_MODEL_POLICY
    force_replan: bool = False


class TenderAiExtractionRunOut(BaseModel):
    id: UUID
    tender_document_id: UUID
    project_id: UUID
    status: str
    mode: str
    model_policy: str
    total_batches: int
    succeeded_batches: int
    failed_batches: int
    skipped_batches: int
    total_chunks: int
    covered_chunks: int
    extracted_requirements: int
    total_input_tokens: int
    total_output_tokens: int
    error: str | None = None
    metadata_json: dict


class TenderAiExtractionBatchOut(BaseModel):
    id: UUID
    run_id: UUID
    tender_document_id: UUID
    tender_document_file_id: UUID | None = None
    source_file: str
    batch_index: int
    status: str
    chunk_ids_json: list
    chunk_count: int
    input_char_count: int
    estimated_input_tokens: int
    model: str
    reasoning_effort: str | None = None
    response_format: str
    retry_count: int
    max_retries: int
    input_tokens: int
    output_tokens: int
    latency_ms: int
    extracted_requirements: int
    dropped_invalid: int
    error_type: str | None = None
    error_message: str | None = None
    skip_reason: str | None = None
    metadata_json: dict


class TenderSummaryOut(BaseModel):
    project_id: UUID
    tender_document_id: UUID | None = None
    project_name: str | None = None
    tenderer: str | None = None
    tender_agency: str | None = None
    project_location: str | None = None
    construction_period: str | None = None
    quality_requirement: str | None = None
    control_price: str | None = None
    bid_bond: str | None = None
    bid_open_time: str | None = None
    bid_deadline: str | None = None
    raw_facts_json: dict
    source_chunk_ids_json: list
    extracted_model: str | None = None


class TenderScoringExtractionOut(BaseModel):
    tender_document_id: UUID
    project_id: UUID
    extracted_count: int
    persisted_count: int
    criteria: list[dict]


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


def _ai_run_out(row: dict) -> TenderAiExtractionRunOut:
    return TenderAiExtractionRunOut(
        id=row["id"],
        tender_document_id=row["tender_document_id"],
        project_id=row["project_id"],
        status=row["status"],
        mode=row["mode"],
        model_policy=row["model_policy"],
        total_batches=row["total_batches"],
        succeeded_batches=row["succeeded_batches"],
        failed_batches=row["failed_batches"],
        skipped_batches=row["skipped_batches"],
        total_chunks=row["total_chunks"],
        covered_chunks=row["covered_chunks"],
        extracted_requirements=row["extracted_requirements"],
        total_input_tokens=row["total_input_tokens"],
        total_output_tokens=row["total_output_tokens"],
        error=row.get("error"),
        metadata_json=row.get("metadata_json") or {},
    )


def _ai_batch_out(row: dict) -> TenderAiExtractionBatchOut:
    return TenderAiExtractionBatchOut(
        id=row["id"],
        run_id=row["run_id"],
        tender_document_id=row["tender_document_id"],
        tender_document_file_id=row.get("tender_document_file_id"),
        source_file=row["source_file"],
        batch_index=row["batch_index"],
        status=row["status"],
        chunk_ids_json=row.get("chunk_ids_json") or [],
        chunk_count=row["chunk_count"],
        input_char_count=row["input_char_count"],
        estimated_input_tokens=row["estimated_input_tokens"],
        model=row["model"],
        reasoning_effort=row.get("reasoning_effort"),
        response_format=row["response_format"],
        retry_count=row["retry_count"],
        max_retries=row["max_retries"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        latency_ms=row["latency_ms"],
        extracted_requirements=row["extracted_requirements"],
        dropped_invalid=row["dropped_invalid"],
        error_type=row.get("error_type"),
        error_message=row.get("error_message"),
        skip_reason=row.get("skip_reason"),
        metadata_json=row.get("metadata_json") or {},
    )


def _summary_out(row: dict) -> TenderSummaryOut:
    return TenderSummaryOut(
        project_id=row["project_id"],
        tender_document_id=row.get("tender_document_id"),
        project_name=row.get("project_name"),
        tenderer=row.get("tenderer"),
        tender_agency=row.get("tender_agency"),
        project_location=row.get("project_location"),
        construction_period=row.get("construction_period"),
        quality_requirement=row.get("quality_requirement"),
        control_price=row.get("control_price"),
        bid_bond=row.get("bid_bond"),
        bid_open_time=row.get("bid_open_time"),
        bid_deadline=row.get("bid_deadline"),
        raw_facts_json=row.get("raw_facts_json") or {},
        source_chunk_ids_json=row.get("source_chunk_ids_json") or [],
        extracted_model=row.get("extracted_model"),
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


@router.get("/source-chunks/{source_chunk_id}", response_model=SourceChunkOut)
async def get_tender_source_chunk(
    source_chunk_id: UUID,
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
    row = _repo.get_source_chunk(conn, source_chunk_id=source_chunk_id)
    if row is None:
        raise HTTPException(status_code=404, detail="source chunk not found")
    return _chunk_out(row)


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


def _enqueue_ai_extraction_run(run_id: UUID) -> None:
    from tender_backend.workers.tasks_extract import run_tender_ai_extraction

    run_tender_ai_extraction.delay(run_id=str(run_id))


def _create_ai_extraction_run(
    conn: Connection,
    *,
    document: dict,
    mode: str,
    model_policy: str,
    enqueue: bool = True,
) -> dict:
    chunks = _repo.list_source_chunks(conn, tender_document_id=document["id"])
    if not chunks:
        raise HTTPException(status_code=400, detail="no source chunks found; parse the tender document first")
    run = _ai_extraction_repo.create_run(
        conn,
        tender_document_id=document["id"],
        project_id=document["project_id"],
        mode=mode,
        model_policy=model_policy,
        metadata_json={"planner": "token_aware_v1"},
    )
    plans = build_extraction_batch_plan(chunks, model_policy=model_policy)
    _ai_extraction_repo.create_batches(
        conn,
        run_id=run["id"],
        tender_document_id=document["id"],
        batches=[plan.to_repository_dict() for plan in plans],
    )
    run = _ai_extraction_repo.refresh_run_progress(conn, run_id=run["id"]) or run
    conn.commit()
    if enqueue:
        _enqueue_ai_extraction_run(run["id"])
    return run


@router.post(
    "/tender-documents/{tender_document_id}/ai-extraction-runs",
    response_model=TenderAiExtractionRunOut,
)
async def create_tender_ai_extraction_run(
    tender_document_id: UUID,
    payload: TenderAiExtractionRunCreateBody | None = None,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> TenderAiExtractionRunOut:
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
    body = payload or TenderAiExtractionRunCreateBody()
    run = _create_ai_extraction_run(
        conn,
        document=document,
        mode=body.mode,
        model_policy=body.model_policy,
        enqueue=True,
    )
    return _ai_run_out(run)


@router.get("/tender-ai-extraction-runs/{run_id}", response_model=TenderAiExtractionRunOut)
async def get_tender_ai_extraction_run(
    run_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> TenderAiExtractionRunOut:
    run = _ai_extraction_repo.get_run(conn, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="tender ai extraction run not found")
    require_resource_project_access(
        conn,
        resource_id=run["tender_document_id"],
        query=_DOCUMENT_PROJECT_QUERY,
        not_found_detail="tender document not found",
        user=user,
    )
    refreshed = _ai_extraction_repo.refresh_run_progress(conn, run_id=run_id) or run
    conn.commit()
    return _ai_run_out(refreshed)


@router.get("/tender-ai-extraction-runs/{run_id}/batches", response_model=list[TenderAiExtractionBatchOut])
async def list_tender_ai_extraction_batches(
    run_id: UUID,
    status: str | None = None,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[TenderAiExtractionBatchOut]:
    run = _ai_extraction_repo.get_run(conn, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="tender ai extraction run not found")
    require_resource_project_access(
        conn,
        resource_id=run["tender_document_id"],
        query=_DOCUMENT_PROJECT_QUERY,
        not_found_detail="tender document not found",
        user=user,
    )
    return [_ai_batch_out(row) for row in _ai_extraction_repo.list_batches(conn, run_id=run_id, status=status)]


@router.post("/tender-ai-extraction-runs/{run_id}/retry-failed", response_model=TenderAiExtractionRunOut)
async def retry_failed_tender_ai_extraction_batches(
    run_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> TenderAiExtractionRunOut:
    run = _ai_extraction_repo.get_run(conn, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="tender ai extraction run not found")
    require_resource_project_access(
        conn,
        resource_id=run["tender_document_id"],
        query=_DOCUMENT_PROJECT_QUERY,
        not_found_detail="tender document not found",
        user=user,
    )
    reset_count = _ai_extraction_repo.reset_failed_batches(conn, run_id=run_id)
    refreshed = _ai_extraction_repo.refresh_run_progress(conn, run_id=run_id) or run
    conn.commit()
    if reset_count:
        _enqueue_ai_extraction_run(run_id)
    return _ai_run_out(refreshed)


@router.post("/tender-ai-extraction-runs/{run_id}/cancel", response_model=TenderAiExtractionRunOut)
async def cancel_tender_ai_extraction_run(
    run_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> TenderAiExtractionRunOut:
    run = _ai_extraction_repo.get_run(conn, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="tender ai extraction run not found")
    require_resource_project_access(
        conn,
        resource_id=run["tender_document_id"],
        query=_DOCUMENT_PROJECT_QUERY,
        not_found_detail="tender document not found",
        user=user,
    )
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tender_ai_extraction_batch
            SET status = 'skipped', skip_reason = 'run_cancelled', updated_at = now()
            WHERE run_id = %s AND status = 'pending'
            """,
            (run_id,),
        )
        cur.execute(
            """
            UPDATE tender_ai_extraction_run
            SET status = 'cancelled', finished_at = now(), updated_at = now()
            WHERE id = %s
            """,
            (run_id,),
        )
    conn.commit()
    cancelled = _ai_extraction_repo.get_run(conn, run_id=run_id) or run
    return _ai_run_out(cancelled)


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
        source_metadata["ai_parse_reasoning_effort"] = thinking_options.get("reasoning_effort")
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


@router.post("/tender-documents/{tender_document_id}/extract-facts", response_model=TenderSummaryOut)
async def extract_tender_document_facts(
    tender_document_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> TenderSummaryOut:
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

    extraction = await extract_tender_summary_with_ai(chunks, conn=conn)
    row = _summary_repo.upsert(
        conn,
        project_id=document["project_id"],
        tender_document_id=tender_document_id,
        summary=extraction.summary,
        raw_facts_json=extraction.raw_facts,
        source_chunk_ids=extraction.source_chunk_ids,
        extracted_model=extraction.model,
    )
    conn.commit()
    return _summary_out(row)


@router.get("/projects/{project_id}/tender-summary", response_model=TenderSummaryOut)
async def get_project_tender_summary(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> TenderSummaryOut:
    require_project_access(conn, project_id=project_id, user=user)
    row = _summary_repo.get_by_project(conn, project_id=project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="tender summary not found")
    return _summary_out(row)


@router.post(
    "/tender-documents/{tender_document_id}/extract-scoring-criteria",
    response_model=TenderScoringExtractionOut,
)
async def extract_tender_document_scoring_criteria(
    tender_document_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> TenderScoringExtractionOut:
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

    extracted = await extract_scoring_criteria_from_source_chunks(chunks)
    payload = [item.to_repository_dict() for item in extracted]
    persisted = _scoring_repo.create_many(conn, project_id=document["project_id"], criteria=payload)
    return TenderScoringExtractionOut(
        tender_document_id=tender_document_id,
        project_id=document["project_id"],
        extracted_count=len(extracted),
        persisted_count=len(persisted),
        criteria=persisted,
    )


@router.post(
    "/tender-documents/{tender_document_id}/ai-extract-requirements",
    response_model=TenderDocumentAiExtractionAcceptedOut,
)
async def ai_extract_tender_document_requirements(
    tender_document_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> TenderDocumentAiExtractionAcceptedOut:
    """Compatibility entry point: create an async AI extraction run.

    Full-package AI extraction is intentionally not executed inside this HTTP
    request. The run/batch worker pipeline provides progress, retry and
    completion gates for large tender packages.
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

    run = _create_ai_extraction_run(
        conn,
        document=document,
        mode="requirements",
        model_policy=DEFAULT_MODEL_POLICY,
        enqueue=True,
    )
    return TenderDocumentAiExtractionAcceptedOut(
        tender_document_id=tender_document_id,
        project_id=document["project_id"],
        run_id=run["id"],
        status=run["status"],
        total_batches=run["total_batches"],
        skipped_batches=run["skipped_batches"],
        message="AI extraction accepted; poll /api/tender-ai-extraction-runs/{run_id}",
    )
