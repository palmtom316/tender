from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tender_backend.services.pdf_document_parser import (
    PdfParseError,
    chunks_from_mineru_result,
    parse_pdf_text,
    parse_pdf_with_mineru,
)


def test_pdf_without_mineru_key_reports_required_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf_path = tmp_path / "tender.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\n%%EOF")
    monkeypatch.delenv("MINERU_API_KEY", raising=False)

    with pytest.raises(PdfParseError, match="MINERU_API_KEY"):
        parse_pdf_text(pdf_path, source_file="tender.pdf")


def test_mineru_result_converts_pages_and_tables_to_chunks() -> None:
    class _Result:
        job_id = "job-1"
        pages = [{"page_number": 1, "markdown": "OCR 文本"}]
        tables = [{"page_start": 2, "page_end": 2, "table_title": "表1", "table_html": "<table><tr><td>A</td></tr></table>", "raw_json": {}}]
        raw_payload = {"parser_version": "2.7"}

    chunks = chunks_from_mineru_result(_Result(), source_file="scan.pdf")

    assert chunks[0]["source_locator"] == "page:1:mineru"
    assert chunks[0]["metadata_json"]["parser_name"] == "mineru"
    assert chunks[1]["source_locator"] == "page:2:mineru-table:1"
    assert chunks[1]["chunk_type"] == "table"


def test_parse_pdf_with_mineru_uses_standard_mineru_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf_path = tmp_path / "tender.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\n%%EOF")
    monkeypatch.setenv("MINERU_API_KEY", "token")
    calls: list[str] = []

    class _Upload:
        batch_id = "batch-1"
        upload_url = "https://upload"

    class _Result:
        job_id = "batch-1"
        status = "completed"
        pages = [{"page_number": 1, "markdown": "MinerU 文本"}]
        tables = []
        raw_payload = {"parser_version": "2.7"}

    class _Client:
        def __init__(self, **kwargs):
            calls.append("init")
            assert kwargs["api_key"] == "token"
            assert kwargs["options"].enable_table is True
            assert kwargs["options"].is_ocr is True

        async def request_upload_url(self, filename, *, data_id):
            calls.append(f"request:{filename}:{data_id}")
            return _Upload()

        async def upload_file(self, upload_url, content, content_type=None):
            calls.append(f"upload:{upload_url}:{content_type}:{len(content)}")

    async def _poll(client, batch_id):
        calls.append(f"poll:{batch_id}")
        return _Result()

    monkeypatch.setattr("tender_backend.services.pdf_document_parser.MineruClient", _Client)
    monkeypatch.setattr("tender_backend.services.pdf_document_parser.poll_until_complete", _poll)

    chunks = asyncio.run(parse_pdf_with_mineru(pdf_path, source_file="tender.pdf"))

    assert chunks[0]["text"] == "MinerU 文本"
    assert calls == [
        "init",
        "request:tender.pdf:tender.pdf",
        "upload:https://upload:application/pdf:14",
        "poll:batch-1",
    ]
