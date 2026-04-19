"""Unit tests for the v4 batch-contract MinerU client.

All HTTP traffic is stubbed via `httpx.MockTransport`. Tests drive async
methods with `asyncio.run` to match the project's existing async-test
convention (see `backend/tests/integration/test_parse_pipeline.py`).
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from tender_backend.services.parse_service.mineru_client import (
    MineruClient,
    MineruParseResult,
    MineruUploadInfo,
)
from tests.unit._mineru_fixtures import make_result_zip, make_simple_middle_json


def _build_client(handler) -> MineruClient:
    return MineruClient(
        base_url="https://mineru.net/api/v4/extract/task",
        api_key="token",
        transport=httpx.MockTransport(handler),
    )


def test_request_upload_url_posts_to_file_urls_batch_and_returns_info() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode("utf-8"))
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={
                "data": {
                    "batch_id": "batch-123",
                    "file_urls": ["https://upload.example.com/file-1"],
                }
            },
        )

    client = _build_client(handler)
    info = asyncio.run(client.request_upload_url("spec.pdf", data_id="doc-1"))

    assert captured["method"] == "POST"
    assert captured["url"] == "https://mineru.net/api/v4/file-urls/batch"
    assert captured["body"] == {
        "files": [{"name": "spec.pdf", "data_id": "doc-1", "is_ocr": True}]
    }
    assert captured["auth"] == "Bearer token"
    assert isinstance(info, MineruUploadInfo)
    assert info.batch_id == "batch-123"
    assert info.upload_url == "https://upload.example.com/file-1"
    assert info.data_id == "doc-1"


def test_request_upload_url_raises_when_response_missing_batch_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"file_urls": []}})

    client = _build_client(handler)
    with pytest.raises(RuntimeError, match="batch_id"):
        asyncio.run(client.request_upload_url("spec.pdf", data_id="doc-1"))


def test_upload_file_puts_bytes_to_signed_url_without_auth_header() -> None:
    """PUT goes to the pre-signed URL, which does NOT accept our API auth."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["content"] = request.content
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(200)

    client = _build_client(handler)
    asyncio.run(client.upload_file("https://upload.example.com/file-1", b"%PDF-1.7 fake"))

    assert captured["method"] == "PUT"
    assert captured["url"] == "https://upload.example.com/file-1"
    assert captured["content"] == b"%PDF-1.7 fake"
    assert captured["auth"] is None  # signed URL is keyless


def test_get_parse_status_returns_processing_while_running() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url).endswith("/extract-results/batch/batch-123")
        return httpx.Response(200, json={
            "data": {"extract_result": [{"state": "running"}]},
        })

    client = _build_client(handler)
    result = asyncio.run(client.get_parse_status("batch-123"))

    assert isinstance(result, MineruParseResult)
    assert result.job_id == "batch-123"
    assert result.status == "processing"
    assert result.pages == []
    assert result.tables == []
    assert result.raw_payload == {}


def test_get_parse_status_downloads_and_normalizes_zip_when_done() -> None:
    zip_bytes = make_result_zip(make_simple_middle_json(), full_md="1 总则\n正文内容")

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/extract-results/batch/batch-123"):
            return httpx.Response(200, json={
                "data": {
                    "extract_result": [{
                        "state": "done",
                        "full_zip_url": "https://download.example.com/result.zip",
                    }],
                },
            })
        if str(request.url) == "https://download.example.com/result.zip":
            return httpx.Response(200, content=zip_bytes)
        return httpx.Response(404)

    client = _build_client(handler)
    result = asyncio.run(client.get_parse_status("batch-123"))

    assert result.status == "completed"
    assert result.pages == [{"page_number": 1, "markdown": "1 总则\n正文内容"}]
    assert result.tables == []
    assert result.raw_payload["parser_version"] == "2.7.6"
    assert result.raw_payload["pages"] == result.pages
    assert result.raw_payload["tables"] == []
    assert result.raw_payload["full_markdown"] == "1 总则\n正文内容"


def test_get_parse_status_returns_failed_with_error_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "data": {"extract_result": [{"state": "failed", "err_msg": "quota exceeded"}]},
        })

    client = _build_client(handler)
    result = asyncio.run(client.get_parse_status("batch-xyz"))

    assert result.status == "failed"
    assert result.raw_payload == {"error": "quota exceeded"}


def test_client_normalizes_base_url_with_legacy_parse_suffix() -> None:
    """Legacy config using `/parse` root should still hit the v4 root."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={
            "data": {
                "batch_id": "batch-legacy",
                "file_urls": ["https://upload.example.com/file-legacy"],
            },
        })

    client = MineruClient(
        base_url="https://mineru.net/api/v4/parse",
        api_key="token",
        transport=httpx.MockTransport(handler),
    )
    asyncio.run(client.request_upload_url("spec.pdf", data_id="doc-legacy"))

    assert captured["url"] == "https://mineru.net/api/v4/file-urls/batch"
