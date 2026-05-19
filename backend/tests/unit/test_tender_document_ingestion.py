from __future__ import annotations

import zipfile
from pathlib import Path
from pathlib import PurePosixPath
from uuid import uuid4

import pytest

from tender_backend.services.tender_document_ingestion import (
    TenderDocumentIngestionService,
    UploadPayload,
    classify_tender_file,
    detect_upload_type,
    sha256_bytes,
    is_parsable_file,
    safe_zip_member_path,
)


class _FakeRepository:
    def create_document(self, _conn, **kwargs):
        return {"id": uuid4(), **kwargs}

    def create_file(self, _conn, **kwargs):
        return {"id": uuid4(), **kwargs}

    def update_document_status(self, _conn, *, tender_document_id, status, error):
        return {"id": tender_document_id, "status": status, "error": error}


class _FakeTransaction:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _FakeConn:
    def transaction(self):
        return _FakeTransaction()


def _service(tmp_path: Path, **kwargs) -> TenderDocumentIngestionService:
    return TenderDocumentIngestionService(
        storage_root=tmp_path,
        repository=_FakeRepository(),
        **kwargs,
    )


def _extract_zip(service: TenderDocumentIngestionService, archive_path: Path, output_root: Path) -> None:
    service._extract_zip(
        object(),
        tender_document_id=uuid4(),
        archive_path=archive_path,
        parent_file_id=uuid4(),
        base_relative_path=PurePosixPath(archive_path.name),
        output_root=output_root,
        depth=1,
    )


def test_detect_upload_type_accepts_zip_and_pdf() -> None:
    assert detect_upload_type("tender_package.zip", "application/octet-stream") == "zip"
    assert detect_upload_type("招标文件.pdf", "application/pdf") == "pdf"


def test_detect_upload_type_rejects_unsupported_files() -> None:
    with pytest.raises(ValueError):
        detect_upload_type("招标文件.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


def test_classify_tender_file_covers_core_sgcc_names() -> None:
    assert classify_tender_file("REDACTED公开招标采购招标公告.docx") == "tender_notice"
    assert classify_tender_file("附件2：专用资格要求.xlsx") == "qualification_requirement"
    assert classify_tender_file("附件7：技术评分细则.xlsx") == "technical_scoring"
    assert classify_tender_file("附件10：技术投标文件制作及递交要求.xlsx") == "bid_submission_requirement"
    assert classify_tender_file("附件11：发包人要求.docx") == "technical_specification"
    assert classify_tender_file("合同条款（空白）.docx") == "contract"


def test_safe_zip_member_path_rejects_unsafe_members() -> None:
    assert safe_zip_member_path("../evil.docx") is None
    assert safe_zip_member_path("/evil.docx") is None
    assert safe_zip_member_path("folder/../evil.docx") is None
    assert safe_zip_member_path("folder/\x00evil.docx") is None
    assert str(safe_zip_member_path("folder/招标公告.docx")) == "folder/招标公告.docx"


def test_zipfile_can_read_gbk_encoded_member_names(tmp_path: Path) -> None:
    archive_path = tmp_path / "gbk.zip"
    member_name = "附件2：专用资格要求.xlsx"
    with zipfile.ZipFile(archive_path, "w") as archive:
        info = zipfile.ZipInfo(member_name)
        info.flag_bits &= ~0x800
        archive.writestr(info, b"data")

    with zipfile.ZipFile(archive_path, "r", metadata_encoding="gbk") as archive:
        names = archive.namelist()

    assert member_name in names
    assert is_parsable_file(member_name)


def test_extract_zip_rejects_too_many_files(tmp_path: Path) -> None:
    archive_path = tmp_path / "many.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("a.txt", b"a")
        archive.writestr("b.txt", b"b")

    with pytest.raises(ValueError, match="too many files"):
        _extract_zip(
            _service(tmp_path, zip_max_files=1),
            archive_path,
            tmp_path / "out",
        )


def test_extract_zip_rejects_total_uncompressed_size_limit(tmp_path: Path) -> None:
    archive_path = tmp_path / "large.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("a.txt", b"12345")
        archive.writestr("b.txt", b"67890")

    with pytest.raises(ValueError, match="uncompressed size"):
        _extract_zip(
            _service(tmp_path, zip_max_uncompressed_bytes=6),
            archive_path,
            tmp_path / "out",
        )


def test_extract_zip_rejects_suspicious_compression_ratio(tmp_path: Path) -> None:
    archive_path = tmp_path / "bomb.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bomb.txt", b"0" * 4096)

    with pytest.raises(ValueError, match="compression ratio"):
        _extract_zip(
            _service(tmp_path, zip_max_compression_ratio=1.1),
            archive_path,
            tmp_path / "out",
        )


def test_ingest_upload_removes_new_document_root_after_zip_limit_failure(tmp_path: Path) -> None:
    archive_path = tmp_path / "many.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("a.txt", b"a")
        archive.writestr("b.txt", b"b")
    content = archive_path.read_bytes()
    project_id = uuid4()
    digest = sha256_bytes(content)
    storage_root = tmp_path / "storage"

    with pytest.raises(ValueError, match="too many files"):
        _service(storage_root, zip_max_files=1).ingest_upload(
            _FakeConn(),
            project_id=project_id,
            payload=UploadPayload(
                filename="many.zip",
                content_type="application/zip",
                content=content,
            ),
        )

    assert not (storage_root / str(project_id) / digest[:16]).exists()
