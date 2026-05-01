from __future__ import annotations

import io

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

from tender_backend.api.master_data_evidence import (
    _ALLOWED_UPLOAD_TYPES,
    _magic_media_type,
    _validate_uploaded_file,
)
from tender_backend.core.config import Settings


_PDF_MAGIC = b"%PDF-1.4\n%fake-pdf"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
_JPEG_MAGIC = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 16
_BMP_MAGIC = b"BM" + b"\x00" * 32
_GIF_MAGIC = b"GIF89a" + b"\x00" * 16
_TIFF_MAGIC = b"II*\x00" + b"\x00" * 16


def _make_settings(max_bytes: int = 1024) -> Settings:
    return Settings(evidence_upload_max_bytes=max_bytes)


def _make_upload(filename: str, content_type: str | None = None) -> UploadFile:
    headers = Headers({"content-type": content_type}) if content_type else None
    return UploadFile(file=io.BytesIO(b""), filename=filename, headers=headers)


def test_magic_media_type_recognizes_common_signatures() -> None:
    assert _magic_media_type(_PDF_MAGIC) == "application/pdf"
    assert _magic_media_type(_PNG_MAGIC) == "image/png"
    assert _magic_media_type(_JPEG_MAGIC) == "image/jpeg"
    assert _magic_media_type(_BMP_MAGIC) == "image/bmp"
    assert _magic_media_type(_GIF_MAGIC) == "image/gif"
    assert _magic_media_type(_TIFF_MAGIC) == "image/tiff"
    assert _magic_media_type(b"random binary blob") is None


def test_validate_uploaded_file_rejects_unknown_extension() -> None:
    settings = _make_settings()
    upload = _make_upload("malware.exe")

    with pytest.raises(HTTPException) as exc_info:
        _validate_uploaded_file(upload, _PDF_MAGIC, settings=settings)

    assert exc_info.value.status_code == 400
    assert "unsupported upload file type" in exc_info.value.detail


def test_validate_uploaded_file_rejects_oversized_content() -> None:
    settings = _make_settings(max_bytes=64)
    upload = _make_upload("report.pdf")

    with pytest.raises(HTTPException) as exc_info:
        _validate_uploaded_file(upload, _PDF_MAGIC + b"\x00" * 128, settings=settings)

    assert exc_info.value.status_code == 413
    assert "size limit" in exc_info.value.detail


def test_validate_uploaded_file_rejects_magic_mismatch_for_extension() -> None:
    settings = _make_settings()
    upload = _make_upload("disguised.pdf")

    with pytest.raises(HTTPException) as exc_info:
        _validate_uploaded_file(upload, _PNG_MAGIC, settings=settings)

    assert exc_info.value.status_code == 400
    assert "does not match its extension" in exc_info.value.detail


def test_validate_uploaded_file_rejects_unrecognized_magic() -> None:
    settings = _make_settings()
    upload = _make_upload("report.pdf")

    with pytest.raises(HTTPException) as exc_info:
        _validate_uploaded_file(upload, b"random binary blob", settings=settings)

    assert exc_info.value.status_code == 400
    assert "does not match its extension" in exc_info.value.detail


def test_validate_uploaded_file_rejects_content_type_mismatch() -> None:
    settings = _make_settings()
    upload = _make_upload("report.pdf", content_type="image/png")

    with pytest.raises(HTTPException) as exc_info:
        _validate_uploaded_file(upload, _PDF_MAGIC, settings=settings)

    assert exc_info.value.status_code == 400
    assert "content type is not allowed" in exc_info.value.detail


def test_validate_uploaded_file_accepts_octet_stream_content_type() -> None:
    settings = _make_settings()
    upload = _make_upload("report.pdf", content_type="application/octet-stream")

    suffix, media_type = _validate_uploaded_file(upload, _PDF_MAGIC, settings=settings)

    assert suffix == ".pdf"
    assert media_type == "application/pdf"


def test_validate_uploaded_file_accepts_matching_pdf() -> None:
    settings = _make_settings()
    upload = _make_upload("report.PDF", content_type="application/pdf")

    suffix, media_type = _validate_uploaded_file(upload, _PDF_MAGIC, settings=settings)

    assert suffix == ".pdf"
    assert media_type == "application/pdf"


def test_validate_uploaded_file_accepts_matching_png_without_content_type() -> None:
    settings = _make_settings()
    upload = _make_upload("photo.png")

    suffix, media_type = _validate_uploaded_file(upload, _PNG_MAGIC, settings=settings)

    assert suffix == ".png"
    assert media_type == "image/png"


def test_validate_uploaded_file_accepts_jpeg_with_jpg_extension() -> None:
    settings = _make_settings()
    upload = _make_upload("photo.jpg", content_type="image/jpeg")

    suffix, media_type = _validate_uploaded_file(upload, _JPEG_MAGIC, settings=settings)

    assert suffix == ".jpg"
    assert media_type == "image/jpeg"


def test_allowed_upload_types_are_lowercase() -> None:
    for suffix in _ALLOWED_UPLOAD_TYPES:
        assert suffix == suffix.lower()
        assert suffix.startswith(".")
