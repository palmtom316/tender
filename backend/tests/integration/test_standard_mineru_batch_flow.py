from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
from zipfile import ZipFile

import pytest

from tender_backend.services.norm_service import norm_processor
from tender_backend.services.parse_service import parser as parse_parser


class _FakeResponse:
    def __init__(self, *, status_code: int = 200, json_data=None, content: bytes = b"") -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.content = content

    def json(self):
        if self._json_data is None:
            raise ValueError("No JSON payload configured")
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _zip_bytes(full_md: str) -> bytes:
    buf = BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("full.md", full_md)
    return buf.getvalue()


def test_parse_via_mineru_uses_batch_upload_flow(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "spec.pdf"
    pdf_bytes = b"%PDF-1.7 fake pdf"
    pdf_path.write_bytes(pdf_bytes)

    calls: list[tuple[str, str, object | None]] = []

    def fake_post(url: str, **kwargs):
        calls.append(("POST", url, kwargs.get("json")))
        if url.endswith("/file-urls/batch"):
            return _FakeResponse(json_data={
                "code": 0,
                "data": {
                    "batch_id": "batch-123",
                    "file_urls": ["https://upload.example.com/file-1"],
                },
            })
        pytest.fail(f"unexpected POST {url}")

    def fake_put(url: str, **kwargs):
        calls.append(("PUT", url, kwargs.get("data")))
        return _FakeResponse(status_code=200)

    poll_count = {"value": 0}

    def fake_get(url: str, **kwargs):
        calls.append(("GET", url, None))
        if url.endswith("/extract-results/batch/batch-123"):
            poll_count["value"] += 1
            if poll_count["value"] == 1:
                return _FakeResponse(json_data={
                    "code": 0,
                    "data": {
                        "batch_id": "batch-123",
                        "extract_result": [{
                            "file_name": "spec.pdf",
                            "state": "running",
                            "err_msg": "",
                        }],
                    },
                })
            return _FakeResponse(json_data={
                "code": 0,
                "data": {
                    "batch_id": "batch-123",
                    "extract_result": [{
                        "file_name": "spec.pdf",
                        "state": "done",
                        "err_msg": "",
                        "full_zip_url": "https://download.example.com/result.zip",
                    }],
                },
            })
        if url == "https://download.example.com/result.zip":
            return _FakeResponse(content=_zip_bytes("1 总则\n正文内容"))
        pytest.fail(f"unexpected GET {url}")

    persisted: dict[str, object] = {}

    def fake_persist_sections(conn, *, document_id: UUID, sections: list[dict]) -> int:
        persisted["document_id"] = document_id
        persisted["sections"] = sections
        return len(sections)

    monkeypatch.setattr(norm_processor._agent_repo, "get_by_key", lambda conn, key: SimpleNamespace(
        enabled=True,
        api_key="token",
        base_url="https://mineru.net/api/v4/extract/task",
    ))
    monkeypatch.setattr(norm_processor, "_get_pdf_path", lambda conn, document_id: str(pdf_path))
    monkeypatch.setattr(norm_processor.httpx, "post", fake_post)
    monkeypatch.setattr(norm_processor.httpx, "put", fake_put)
    monkeypatch.setattr(norm_processor.httpx, "get", fake_get)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)
    monkeypatch.setattr(parse_parser, "persist_sections", fake_persist_sections)

    count = norm_processor._parse_via_mineru(object(), "11111111-1111-1111-1111-111111111111")

    assert count == 1
    assert calls[0] == (
        "POST",
        "https://mineru.net/api/v4/file-urls/batch",
        {
            "files": [{"name": "spec.pdf", "data_id": "11111111-1111-1111-1111-111111111111"}],
            "model_version": "vlm",
            "is_ocr": True,
            "enable_table": True,
            "language": "ch",
        },
    )
    assert ("PUT", "https://upload.example.com/file-1", pdf_bytes) in calls
    assert ("GET", "https://mineru.net/api/v4/extract-results/batch/batch-123", None) in calls
    assert ("GET", "https://download.example.com/result.zip", None) in calls
    assert persisted["document_id"] == UUID("11111111-1111-1111-1111-111111111111")
    assert persisted["sections"] == [{
        "section_code": "1",
        "title": "总则",
        "level": 1,
        "page_start": None,
        "page_end": None,
        "text": "正文内容",
    }]
