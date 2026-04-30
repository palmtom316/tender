from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from tender_backend.services.tender_document_ingestion import (
    classify_tender_file,
    detect_upload_type,
    is_parsable_file,
    safe_zip_member_path,
)


def test_detect_upload_type_accepts_zip_and_pdf() -> None:
    assert detect_upload_type("包1_完整招标文件.zip", "application/octet-stream") == "zip"
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
