"""Upload classification and recursive package expansion for tender documents."""

from __future__ import annotations

import hashlib
import mimetypes
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from psycopg import Connection

from tender_backend.db.repositories.tender_document_repository import TenderDocumentRepository


ZIP_MAX_DEPTH = 5
ZIP_MAX_FILES = 2000
ZIP_MAX_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
ZIP_MAX_COMPRESSION_RATIO = 100.0
PARSABLE_SUFFIXES = {".docx", ".doc", ".xlsx", ".xls", ".pdf", ".wps"}
ARCHIVE_SUFFIXES = {".zip"}


@dataclass(frozen=True)
class UploadPayload:
    filename: str
    content_type: str
    content: bytes


@dataclass
class ZipExtractionState:
    file_count: int = 0
    uncompressed_bytes: int = 0


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def detect_upload_type(filename: str, content_type: str) -> str:
    suffix = Path(filename).suffix.lower()
    normalized_content_type = content_type.lower()
    if suffix == ".zip" or normalized_content_type in {"application/zip", "application/x-zip-compressed"}:
        return "zip"
    if suffix == ".pdf" or normalized_content_type == "application/pdf":
        return "pdf"
    raise ValueError("Only ZIP and PDF tender documents are supported")


def classify_tender_file(filename: str) -> str:
    name = filename.casefold()
    suffix = Path(filename).suffix.lower()
    if suffix == ".sign":
        return "signature"
    if "招标公告" in name or "采购公告" in name:
        return "tender_notice"
    if "技术规范" in name or "技术要求" in name or "发包人要求" in name:
        return "technical_specification"
    if "资格" in name:
        return "qualification_requirement"
    if "技术评分" in name:
        return "technical_scoring"
    if "商务评分" in name:
        return "business_scoring"
    if "评分" in name:
        return "scoring"
    if "需求一览" in name or "货物清单" in name or "工程量清单" in name:
        return "demand_schedule"
    if "投标文件制作" in name or "递交要求" in name:
        return "bid_submission_requirement"
    if "合同" in name:
        return "contract"
    if "最高限价" in name or "保证金" in name or "报价" in name:
        return "pricing_reference"
    if "采购文件" in name or "招标文件" in name:
        return "tender_document"
    return "unclassified"


def file_type_for(filename: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    return suffix or "unknown"


def is_parsable_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in PARSABLE_SUFFIXES


def is_archive_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ARCHIVE_SUFFIXES


def content_type_for(filename: str, fallback: str = "application/octet-stream") -> str:
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or fallback


def safe_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    if not name:
        return "unnamed"
    cleaned = "".join("_" if ord(ch) < 32 else ch for ch in name)
    return cleaned[:180] or "unnamed"


def safe_zip_member_path(name: str) -> PurePosixPath | None:
    normalized = name.replace("\\", "/").strip()
    if not normalized or normalized.endswith("/"):
        return None
    path = PurePosixPath(normalized)
    if path.is_absolute():
        return None
    if any(part in {"", ".", ".."} for part in path.parts):
        return None
    if any(any(ord(ch) < 32 for ch in part) for part in path.parts):
        return None
    return path


class TenderDocumentIngestionService:
    def __init__(
        self,
        *,
        storage_root: Path,
        repository: TenderDocumentRepository | None = None,
        zip_max_depth: int = ZIP_MAX_DEPTH,
        zip_max_files: int = ZIP_MAX_FILES,
        zip_max_uncompressed_bytes: int = ZIP_MAX_UNCOMPRESSED_BYTES,
        zip_max_compression_ratio: float = ZIP_MAX_COMPRESSION_RATIO,
    ) -> None:
        self.storage_root = storage_root
        self.repository = repository or TenderDocumentRepository()
        self.zip_max_depth = zip_max_depth
        self.zip_max_files = zip_max_files
        self.zip_max_uncompressed_bytes = zip_max_uncompressed_bytes
        self.zip_max_compression_ratio = zip_max_compression_ratio

    def ingest_upload(self, conn: Connection, *, project_id: UUID, payload: UploadPayload) -> dict[str, Any]:
        upload_type = detect_upload_type(payload.filename, payload.content_type)
        digest = sha256_bytes(payload.content)
        document_root = self.storage_root / str(project_id) / digest[:16]
        created_document_root = not document_root.exists()
        original_dir = document_root / "original"
        original_dir.mkdir(parents=True, exist_ok=True)

        original_filename = safe_filename(payload.filename)
        original_path = original_dir / original_filename
        original_path.write_bytes(payload.content)

        try:
            with conn.transaction():
                document = self.repository.create_document(
                    conn,
                    project_id=project_id,
                    original_filename=original_filename,
                    upload_type=upload_type,
                    status="extracting" if upload_type == "zip" else "uploaded",
                    content_type=payload.content_type or content_type_for(original_filename),
                    size_bytes=len(payload.content),
                    storage_key=str(original_path),
                    file_sha256=digest,
                    metadata_json={"storage_root": str(document_root)},
                )

                original_file = self.repository.create_file(
                    conn,
                    tender_document_id=document["id"],
                    parent_file_id=None,
                    filename=original_filename,
                    relative_path=original_filename,
                    storage_key=str(original_path),
                    content_type=payload.content_type or content_type_for(original_filename),
                    size_bytes=len(payload.content),
                    file_type=file_type_for(original_filename),
                    classification="uploaded_package" if upload_type == "zip" else "uploaded_pdf",
                    depth=0,
                    is_archive=upload_type == "zip",
                    is_parsable=upload_type == "pdf",
                    parse_status="pending",
                    metadata_json={"sha256": digest},
                )

                if upload_type == "zip":
                    self._extract_zip(
                        conn,
                        tender_document_id=document["id"],
                        archive_path=original_path,
                        parent_file_id=original_file["id"],
                        base_relative_path=PurePosixPath(original_filename),
                        output_root=document_root / "extracted",
                        depth=1,
                        state=ZipExtractionState(),
                    )
                    document = self.repository.update_document_status(
                        conn,
                        tender_document_id=document["id"],
                        status="completed",
                        error=None,
                    ) or document
        except Exception:
            if created_document_root:
                try:
                    shutil.rmtree(document_root)
                except FileNotFoundError:
                    pass
            raise

        return document

    def _extract_zip(
        self,
        conn: Connection,
        *,
        tender_document_id: UUID,
        archive_path: Path,
        parent_file_id: UUID,
        base_relative_path: PurePosixPath,
        output_root: Path,
        depth: int,
        state: ZipExtractionState | None = None,
    ) -> None:
        state = state or ZipExtractionState()
        if depth > self.zip_max_depth:
            return

        output_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path, "r", metadata_encoding="gbk") as archive:
            for member in archive.infolist():
                member_path = safe_zip_member_path(member.filename)
                if member_path is None:
                    continue
                self._validate_zip_member(member, state=state)

                filename = safe_filename(member_path.name)
                relative_path = base_relative_path / member_path
                stored_path = output_root / str(member_path)
                stored_path.parent.mkdir(parents=True, exist_ok=True)

                with archive.open(member) as source, stored_path.open("wb") as target:
                    self._copy_zip_member(source, target, member.file_size, state=state)

                size_bytes = stored_path.stat().st_size
                classification = classify_tender_file(filename)
                archive_child = is_archive_file(filename)
                file_row = self.repository.create_file(
                    conn,
                    tender_document_id=tender_document_id,
                    parent_file_id=parent_file_id,
                    filename=filename,
                    relative_path=str(relative_path),
                    storage_key=str(stored_path),
                    content_type=content_type_for(filename),
                    size_bytes=size_bytes,
                    file_type=file_type_for(filename),
                    classification=classification,
                    depth=depth,
                    is_archive=archive_child,
                    is_parsable=is_parsable_file(filename),
                    parse_status="pending",
                    metadata_json={"zip_member": member.filename},
                )

                if archive_child:
                    self._extract_zip(
                        conn,
                        tender_document_id=tender_document_id,
                        archive_path=stored_path,
                        parent_file_id=file_row["id"],
                        base_relative_path=relative_path,
                        output_root=stored_path.with_name(f"{stored_path.name}.contents"),
                        depth=depth + 1,
                        state=state,
                    )

    def _validate_zip_member(self, member: zipfile.ZipInfo, *, state: ZipExtractionState) -> None:
        if state.file_count + 1 > self.zip_max_files:
            raise ValueError("ZIP archive has too many files")
        next_total = state.uncompressed_bytes + max(member.file_size, 0)
        if next_total > self.zip_max_uncompressed_bytes:
            raise ValueError("ZIP archive uncompressed size exceeds limit")
        if member.compress_size > 0 and member.file_size > 0:
            ratio = member.file_size / member.compress_size
            if ratio > self.zip_max_compression_ratio:
                raise ValueError("ZIP member compression ratio exceeds limit")

    def _copy_zip_member(self, source, target, expected_size: int, *, state: ZipExtractionState) -> None:
        copied = 0
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            copied += len(chunk)
            if state.uncompressed_bytes + copied > self.zip_max_uncompressed_bytes:
                raise ValueError("ZIP archive uncompressed size exceeds limit")
            target.write(chunk)
        if expected_size >= 0 and copied != expected_size:
            raise ValueError("ZIP member size changed while extracting")
        state.file_count += 1
        state.uncompressed_bytes += copied
