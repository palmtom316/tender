from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest

from tender_backend.services.norm_service import norm_processor
from tender_backend.services.norm_service.block_segments import BlockSegment, build_single_standard_blocks
from tender_backend.services.norm_service.document_assets import DocumentAsset, PageAsset, TableAsset
from tender_backend.services.norm_service.layout_compressor import PageWindow, compress_sections
from tender_backend.services.norm_service.prompt_builder import build_prompt
from tender_backend.services.norm_service.scope_splitter import ProcessingScope, rebalance_scopes, split_into_scopes
from tender_backend.services.norm_service.tree_builder import validate_tree
from tender_backend.services.parse_service import parser as parse_parser
from tests.unit._mineru_fixtures import (
    make_middle_json,
    make_pdf_info_page,
    make_result_zip,
    make_table_block,
    make_text_block,
)


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


def test_parse_via_mineru_uses_batch_upload_flow(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "spec.pdf"
    pdf_bytes = b"%PDF-1.7 fake pdf"
    pdf_path.write_bytes(pdf_bytes)

    calls: list[tuple[str, str, object | None, object | None]] = []

    def fake_post(url: str, **kwargs):
        calls.append(("POST", url, kwargs.get("json"), kwargs.get("headers")))
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
        calls.append(("PUT", url, kwargs.get("data"), kwargs.get("headers")))
        return _FakeResponse(status_code=200)

    poll_count = {"value": 0}

    def fake_get(url: str, **kwargs):
        calls.append(("GET", url, None, kwargs.get("headers")))
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
            return _FakeResponse(content=make_result_zip(
                make_middle_json([
                    make_pdf_info_page(6, [
                        make_text_block("1 总则", block_type="title"),
                        make_text_block("正文内容"),
                    ]),
                    make_pdf_info_page(7, [
                        make_text_block("2 术语", block_type="title"),
                        make_text_block("术语正文"),
                    ]),
                ]),
                full_md="1 总则\n正文内容\n\n2 术语\n术语正文",
            ))
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
    monkeypatch.setattr(parse_parser, "update_document_parse_assets", lambda *args, **kwargs: None)

    count = norm_processor._parse_via_mineru(object(), "11111111-1111-1111-1111-111111111111")

    assert count == 2
    assert calls[0] == (
        "POST",
        "https://mineru.net/api/v4/file-urls/batch",
        {
            "files": [{
                "name": "spec.pdf",
                "data_id": "11111111-1111-1111-1111-111111111111",
                "is_ocr": True,
            }],
            "model_version": "vlm",
            "language": "ch",
            "enable_table": True,
            "enable_formula": False,
        },
        {"Authorization": "Bearer token", "token": "token"},
    )
    assert ("PUT", "https://upload.example.com/file-1", pdf_bytes, None) in calls
    assert (
        "GET",
        "https://mineru.net/api/v4/extract-results/batch/batch-123",
        None,
        {"Authorization": "Bearer token", "token": "token"},
    ) in calls
    assert ("GET", "https://download.example.com/result.zip", None, None) in calls
    assert persisted["document_id"] == UUID("11111111-1111-1111-1111-111111111111")
    assert persisted["sections"] == [
        {
            "section_code": "1",
            "title": "总则",
            "level": 1,
            "page_start": 7,
            "page_end": 7,
            "text": "正文内容",
            "text_source": "mineru_markdown",
            "sort_order": 0,
            "raw_json": {
                "page_number": 7,
                "markdown": "1 总则\n正文内容",
            },
        },
        {
            "section_code": "2",
            "title": "术语",
            "level": 1,
            "page_start": 8,
            "page_end": 8,
            "text": "术语正文",
            "text_source": "mineru_markdown",
            "sort_order": 1,
            "raw_json": {
                "page_number": 8,
                "markdown": "2 术语\n术语正文",
            },
        },
    ]


def test_parse_via_mineru_persists_canonical_payload_from_pdf_info(
    monkeypatch, tmp_path: Path
) -> None:
    """`_parse_via_mineru` must ship only the canonical `{parser_version, pages,
    tables, full_markdown}` payload to `update_document_parse_assets`.

    Legacy keys such as `batch_id` or `result_item` must not leak into
    `raw_payload`, and the pages/tables must come straight from the normalizer.
    """
    pdf_path = tmp_path / "spec.pdf"
    pdf_path.write_bytes(b"%PDF-1.7 fake pdf")

    def fake_post(url: str, **kwargs):
        if url.endswith("/file-urls/batch"):
            return _FakeResponse(json_data={
                "data": {
                    "batch_id": "batch-canonical",
                    "file_urls": ["https://upload.example.com/file-canonical"],
                },
            })
        pytest.fail(f"unexpected POST {url}")

    def fake_put(url: str, **kwargs):
        return _FakeResponse(status_code=200)

    def fake_get(url: str, **kwargs):
        if url.endswith("/extract-results/batch/batch-canonical"):
            return _FakeResponse(json_data={
                "data": {
                    "extract_result": [{
                        "state": "done",
                        "full_zip_url": "https://download.example.com/result-canonical.zip",
                    }],
                },
            })
        if url == "https://download.example.com/result-canonical.zip":
            return _FakeResponse(content=make_result_zip(
                make_middle_json([
                    make_pdf_info_page(0, [
                        make_text_block("1 总则", block_type="title"),
                        make_text_block("正文内容"),
                    ]),
                ]),
                full_md="1 总则\n正文内容",
            ))
        pytest.fail(f"unexpected GET {url}")

    captured: dict[str, object] = {}

    def fake_update_document_parse_assets(conn, **kwargs):
        captured.update(kwargs)

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
    monkeypatch.setattr(parse_parser, "persist_sections", lambda *args, **kwargs: 1)
    monkeypatch.setattr(parse_parser, "persist_tables", lambda *args, **kwargs: 0)
    monkeypatch.setattr(parse_parser, "update_document_parse_assets", fake_update_document_parse_assets)

    norm_processor._parse_via_mineru(object(), "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

    assert captured["parser_name"] == "mineru"
    assert captured["parser_version"] == "2.7.6"
    assert captured["raw_payload"] == {
        "parser_version": "2.7.6",
        "pages": [{"page_number": 1, "markdown": "1 总则\n正文内容"}],
        "tables": [],
        "full_markdown": "1 总则\n正文内容",
    }


def test_parse_via_mineru_cleans_toc_noise_before_persisting_sections(
    monkeypatch, tmp_path: Path
) -> None:
    pdf_path = tmp_path / "spec.pdf"
    pdf_path.write_bytes(b"%PDF-1.7 fake pdf")

    def fake_post(url: str, **kwargs):
        if url.endswith("/file-urls/batch"):
            return _FakeResponse(json_data={
                "data": {
                    "batch_id": "batch-clean",
                    "file_urls": ["https://upload.example.com/file-clean"],
                },
            })
        pytest.fail(f"unexpected POST {url}")

    def fake_put(url: str, **kwargs):
        return _FakeResponse(status_code=200)

    def fake_get(url: str, **kwargs):
        if url.endswith("/extract-results/batch/batch-clean"):
            return _FakeResponse(json_data={
                "data": {
                    "extract_result": [{
                        "state": "done",
                        "full_zip_url": "https://download.example.com/result-clean.zip",
                    }],
                },
            })
        if url == "https://download.example.com/result-clean.zip":
            return _FakeResponse(content=make_result_zip(
                make_middle_json([
                    make_pdf_info_page(0, [
                        make_text_block("目次", block_type="title"),
                        make_text_block("1 总则 (1)"),
                    ]),
                    make_pdf_info_page(1, [
                        make_text_block("1 总则", block_type="title"),
                        make_text_block("正文内容"),
                    ]),
                ]),
                full_md="目次\n1 总则 (1)\n\n1 总则\n正文内容",
            ))
        pytest.fail(f"unexpected GET {url}")

    persisted: dict[str, object] = {}

    def fake_persist_sections(conn, *, document_id: UUID, sections: list[dict]) -> int:
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
    monkeypatch.setattr(parse_parser, "persist_tables", lambda *args, **kwargs: 0)
    monkeypatch.setattr(parse_parser, "update_document_parse_assets", lambda *args, **kwargs: None)

    count = norm_processor._parse_via_mineru(object(), "dddddddd-dddd-dddd-dddd-dddddddddddd")

    assert count == 1
    assert persisted["sections"] == [
        {
            "section_code": "1",
            "title": "总则",
            "level": 1,
            "page_start": 2,
            "page_end": 2,
            "text": "正文内容",
            "text_source": "mineru_markdown",
            "sort_order": 0,
            "raw_json": {
                "page_number": 2,
                "markdown": "1 总则\n正文内容",
            },
        },
    ]


def test_parse_via_mineru_uses_uuid_token_header_for_jwt_api_key(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "spec.pdf"
    pdf_path.write_bytes(b"%PDF-1.7 fake pdf")
    jwt = (
        "eyJ0eXBlIjoiSldUIiwiYWxnIjoiSFM1MTIifQ."
        "eyJ1dWlkIjoiZWU1ZGUyZTItYzJjMC00ZTBkLTliODEtMGU1OWUzMWEzOGI1IiwiZXhwIjoxNzgwMTEwOTc1fQ."
        "sig"
    )
    captured_headers: list[tuple[str, dict[str, str] | None]] = []

    def fake_post(url: str, **kwargs):
        captured_headers.append(("POST", kwargs.get("headers")))
        if url.endswith("/file-urls/batch"):
            return _FakeResponse(json_data={
                "data": {
                    "batch_id": "batch-jwt",
                    "file_urls": ["https://upload.example.com/file-jwt"],
                },
            })
        pytest.fail(f"unexpected POST {url}")

    def fake_put(url: str, **kwargs):
        return _FakeResponse(status_code=200)

    def fake_get(url: str, **kwargs):
        captured_headers.append(("GET", kwargs.get("headers")))
        if url.endswith("/extract-results/batch/batch-jwt"):
            return _FakeResponse(json_data={
                "data": {
                    "extract_result": [{
                        "state": "done",
                        "full_zip_url": "https://download.example.com/result-jwt.zip",
                    }],
                },
            })
        if url == "https://download.example.com/result-jwt.zip":
            return _FakeResponse(content=make_result_zip(
                make_middle_json([
                    make_pdf_info_page(0, [
                        make_text_block("1 总则", block_type="title"),
                        make_text_block("正文内容"),
                    ]),
                ]),
                full_md="1 总则\n正文内容",
            ))
        pytest.fail(f"unexpected GET {url}")

    monkeypatch.setattr(norm_processor._agent_repo, "get_by_key", lambda conn, key: SimpleNamespace(
        enabled=True,
        api_key=jwt,
        base_url="https://mineru.net/api/v4/extract/task",
    ))
    monkeypatch.setattr(norm_processor, "_get_pdf_path", lambda conn, document_id: str(pdf_path))
    monkeypatch.setattr(norm_processor.httpx, "post", fake_post)
    monkeypatch.setattr(norm_processor.httpx, "put", fake_put)
    monkeypatch.setattr(norm_processor.httpx, "get", fake_get)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)
    monkeypatch.setattr(parse_parser, "persist_sections", lambda *args, **kwargs: 1)
    monkeypatch.setattr(parse_parser, "persist_tables", lambda *args, **kwargs: 0)
    monkeypatch.setattr(parse_parser, "update_document_parse_assets", lambda *args, **kwargs: None)

    norm_processor._parse_via_mineru(object(), "cccccccc-cccc-cccc-cccc-cccccccccccc")

    assert captured_headers[0] == (
        "POST",
        {
            "Authorization": f"Bearer {jwt}",
            "token": "ee5de2e2-c2c0-4e0d-9b81-0e59e31a38b5",
        },
    )
    assert captured_headers[1] == (
        "GET",
        {
            "Authorization": f"Bearer {jwt}",
            "token": "ee5de2e2-c2c0-4e0d-9b81-0e59e31a38b5",
        },
    )
    assert captured_headers[2] == ("GET", None)


def test_parse_via_mineru_uses_configured_batch_options(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "spec.pdf"
    pdf_path.write_bytes(b"%PDF-1.7 fake pdf")

    calls: list[tuple[str, str, object | None, object | None]] = []

    def fake_post(url: str, **kwargs):
        calls.append(("POST", url, kwargs.get("json"), kwargs.get("headers")))
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
        calls.append(("PUT", url, kwargs.get("data"), kwargs.get("headers")))
        return _FakeResponse(status_code=200)

    def fake_get(url: str, **kwargs):
        calls.append(("GET", url, None, kwargs.get("headers")))
        if url.endswith("/extract-results/batch/batch-123"):
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
            return _FakeResponse(content=make_result_zip(
                make_middle_json([
                    make_pdf_info_page(0, [
                        make_text_block("1 总则", block_type="title"),
                        make_text_block("正文内容"),
                    ]),
                ]),
                full_md="1 总则\n正文内容",
            ))
        pytest.fail(f"unexpected GET {url}")

    monkeypatch.setattr(norm_processor._agent_repo, "get_by_key", lambda conn, key: SimpleNamespace(
        enabled=True,
        api_key="token",
        base_url="https://mineru.net/api/v4/extract/task",
    ))
    monkeypatch.setattr(norm_processor, "_get_pdf_path", lambda conn, document_id: str(pdf_path))
    monkeypatch.setattr(norm_processor, "get_settings", lambda: SimpleNamespace(
        standard_mineru_model_version="pipeline",
        standard_mineru_language="en",
        standard_mineru_enable_table=False,
        standard_mineru_enable_formula=True,
        standard_mineru_is_ocr=False,
        standard_mineru_page_ranges="1-10",
    ))
    monkeypatch.setattr(norm_processor.httpx, "post", fake_post)
    monkeypatch.setattr(norm_processor.httpx, "put", fake_put)
    monkeypatch.setattr(norm_processor.httpx, "get", fake_get)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)
    monkeypatch.setattr(parse_parser, "persist_sections", lambda conn, *, document_id, sections: len(sections))
    monkeypatch.setattr(parse_parser, "persist_tables", lambda conn, *, document_id, tables: len(tables))
    monkeypatch.setattr(parse_parser, "update_document_parse_assets", lambda *args, **kwargs: None)

    norm_processor._parse_via_mineru(object(), "22222222-2222-2222-2222-222222222222")

    assert calls[0] == (
        "POST",
        "https://mineru.net/api/v4/file-urls/batch",
        {
            "files": [{
                "name": "spec.pdf",
                "data_id": "22222222-2222-2222-2222-222222222222",
                "is_ocr": False,
                "page_ranges": "1-10",
            }],
            "model_version": "pipeline",
            "language": "en",
            "enable_table": False,
            "enable_formula": True,
        },
        {"Authorization": "Bearer token", "token": "token"},
    )


def test_mineru_to_sections_uses_page_markdown_to_anchor_headings() -> None:
    sections = norm_processor._mineru_to_sections(
        "1 总则\n正文内容\n\n2 术语\n术语正文",
        [
            {"page_number": 3, "markdown": "1 总则\n正文内容"},
            {"page_number": 4, "markdown": "2 术语\n术语正文"},
        ],
    )

    assert sections == [
        {
            "section_code": "1",
            "title": "总则",
            "level": 1,
            "page_start": 3,
            "page_end": 3,
            "text": "正文内容",
            "text_source": "mineru_markdown",
            "sort_order": 0,
            "raw_json": {
                "page_number": 3,
                "markdown": "1 总则\n正文内容",
            },
        },
        {
            "section_code": "2",
            "title": "术语",
            "level": 1,
            "page_start": 4,
            "page_end": 4,
            "text": "术语正文",
            "text_source": "mineru_markdown",
            "sort_order": 1,
            "raw_json": {
                "page_number": 4,
                "markdown": "2 术语\n术语正文",
            },
        },
    ]

def test_mineru_to_sections_promotes_inline_clause_heading_text() -> None:
    sections = norm_processor._mineru_to_sections(
        "1.0.1 为保证施工安装质量，制定本规范。\n\n1.0.2 本规范适用于交流3kV~750kV电气装置安装工程。",
        [
            {"page_number": 10, "markdown": "1.0.1 为保证施工安装质量，制定本规范。"},
            {"page_number": 10, "markdown": "1.0.2 本规范适用于交流3kV~750kV电气装置安装工程。"},
        ],
    )

    assert sections == [
        {
            "section_code": "1.0.1",
            "title": "为保证施工安装质量，制定本规范。",
            "level": 3,
            "page_start": 10,
            "page_end": 10,
            "text": "为保证施工安装质量，制定本规范。",
            "text_source": "mineru_markdown",
            "sort_order": 0,
            "raw_json": {
                "page_number": 10,
                "markdown": "1.0.1 为保证施工安装质量，制定本规范。",
            },
        },
        {
            "section_code": "1.0.2",
            "title": "本规范适用于交流3kV~750kV电气装置安装工程。",
            "level": 3,
            "page_start": 10,
            "page_end": 10,
            "text": "本规范适用于交流3kV~750kV电气装置安装工程。",
            "text_source": "mineru_markdown",
            "sort_order": 1,
            "raw_json": {
                "page_number": 10,
                "markdown": "1.0.2 本规范适用于交流3kV~750kV电气装置安装工程。",
            },
        },
    ]
def test_parse_llm_json_extracts_object_with_trailing_text() -> None:
    raw = '{"clause_no":"1.0.1","clause_text":"正文"}\n以上为提取结果。'

    parsed = norm_processor._parse_llm_json(raw)

    assert parsed == [{"clause_no": "1.0.1", "clause_text": "正文"}]


def test_parse_llm_json_extracts_fenced_object_with_leading_text() -> None:
    raw = '提取结果如下：\n```json\n{"clause_no":"1.0.2","clause_text":"条文"}\n```\n请核对。'

    parsed = norm_processor._parse_llm_json(raw)

    assert parsed == [{"clause_no": "1.0.2", "clause_text": "条文"}]


def test_parse_llm_json_prefers_array_over_leading_example_object() -> None:
    raw = (
        '以下是格式示例：{"clause_no":"0.0.0","clause_text":"示例"}\n'
        '实际提取结果：'
        '[{"clause_no":"1.0.1","clause_text":"第一条"},'
        '{"clause_no":"1.0.2","clause_text":"第二条"}]'
    )

    parsed = norm_processor._parse_llm_json(raw)

    assert parsed == [
        {"clause_no": "1.0.1", "clause_text": "第一条"},
        {"clause_no": "1.0.2", "clause_text": "第二条"},
    ]


def test_parse_llm_json_accepts_empty_array_without_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    warnings: list[tuple[tuple, dict]] = []

    monkeypatch.setattr(
        norm_processor.logger,
        "warning",
        lambda *args, **kwargs: warnings.append((args, kwargs)),
    )

    parsed = norm_processor._parse_llm_json("[]")

    assert parsed == []
    assert warnings == []


def test_extract_pages_from_payload_skips_layout_blocks_and_keeps_real_page_payloads() -> None:
    payload = {
        "pages": [
            {"type": "text", "content": "中华人民共和国国家标准"},
            {"type": "title", "content": "电气装置安装工程"},
        ],
        "result": {
            "pages": [
                {"page_number": 7, "markdown": "1 总则\n正文内容"},
                {"page_number": 8, "markdown": "2 术语\n术语正文"},
            ],
        },
    }

    pages = norm_processor._extract_pages_from_payload(payload)

    assert pages == [
        {"page_number": 7, "markdown": "1 总则\n正文内容"},
        {"page_number": 8, "markdown": "2 术语\n术语正文"},
    ]


def test_extract_pages_from_payload_aggregates_layout_blocks_by_page_index() -> None:
    payload = [
        {"type": "header", "text": "中华人民共和国国家标准", "page_idx": 0, "bbox": [0, 10, 100, 20]},
        {"type": "text", "text": "1 总则", "page_idx": 0, "bbox": [0, 100, 100, 120]},
        {"type": "text", "text": "正文内容", "page_idx": 0, "bbox": [0, 140, 100, 180]},
        {"type": "text", "text": "2 术语", "page_idx": 1, "bbox": [0, 100, 100, 120]},
        {"type": "text", "text": "术语正文", "page_idx": 1, "bbox": [0, 140, 100, 180]},
    ]

    pages = norm_processor._extract_pages_from_payload(payload)

    assert pages == [
        {
            "page_number": 1,
            "markdown": "中华人民共和国国家标准\n1 总则\n正文内容",
        },
        {
            "page_number": 2,
            "markdown": "2 术语\n术语正文",
        },
    ]


def test_extract_pages_from_payload_aggregates_per_page_block_lists() -> None:
    payload = [
        [
            {"type": "title", "content": {"title_content": [{"type": "text", "content": "1 总则"}]}, "bbox": [0, 100, 100, 120]},
            {"type": "paragraph", "content": {"paragraph_content": [{"type": "text", "content": "正文内容"}]}, "bbox": [0, 140, 100, 180]},
        ],
        [
            {"type": "title", "content": {"title_content": [{"type": "text", "content": "2 术语"}]}, "bbox": [0, 100, 100, 120]},
            {"type": "paragraph", "content": {"paragraph_content": [{"type": "text", "content": "术语正文"}]}, "bbox": [0, 140, 100, 180]},
        ],
    ]

    pages = norm_processor._extract_pages_from_payload(payload)

    assert pages == [
        {
            "page_number": 1,
            "markdown": "1 总则\n正文内容",
        },
        {
            "page_number": 2,
            "markdown": "2 术语\n术语正文",
        },
    ]


def test_parse_via_mineru_persists_tables_from_structured_payload(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "spec.pdf"
    pdf_path.write_bytes(b"%PDF-1.7 fake pdf")

    def fake_post(url: str, **kwargs):
        if url.endswith("/file-urls/batch"):
            return _FakeResponse(json_data={
                "data": {
                    "batch_id": "batch-456",
                    "file_urls": ["https://upload.example.com/file-2"],
                },
            })
        pytest.fail(f"unexpected POST {url}")

    def fake_put(url: str, **kwargs):
        return _FakeResponse(status_code=200)

    poll_count = {"value": 0}

    def fake_get(url: str, **kwargs):
        if url.endswith("/extract-results/batch/batch-456"):
            poll_count["value"] += 1
            if poll_count["value"] == 1:
                return _FakeResponse(json_data={"data": {"extract_result": [{"state": "running"}]}})
            return _FakeResponse(json_data={
                "data": {
                    "extract_result": [{
                        "state": "done",
                        "full_zip_url": "https://download.example.com/result-table.zip",
                    }],
                },
            })
        if url == "https://download.example.com/result-table.zip":
            return _FakeResponse(content=make_result_zip(
                make_middle_json([
                    make_pdf_info_page(6, [
                        make_text_block("1 总则", block_type="title"),
                        make_text_block("正文内容"),
                    ]),
                    make_pdf_info_page(7, [
                        make_table_block(
                            caption="主要参数",
                            html="<table><tr><td>额定电压</td><td>10kV</td></tr></table>",
                            bbox=[0, 0, 10, 10],
                        ),
                    ]),
                ]),
                full_md="1 总则\n正文内容",
            ))
        pytest.fail(f"unexpected GET {url}")

    persisted: dict[str, object] = {}

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
    monkeypatch.setattr(parse_parser, "persist_sections", lambda *args, **kwargs: 1)
    monkeypatch.setattr(parse_parser, "update_document_parse_assets", lambda *args, **kwargs: None)
    monkeypatch.setattr(parse_parser, "persist_tables", lambda conn, *, document_id, tables: persisted.setdefault("tables", tables) or len(tables))

    norm_processor._parse_via_mineru(object(), "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert persisted["tables"] == [
        {
            "page": 8,
            "page_start": 8,
            "page_end": 8,
            "table_title": "主要参数",
            "table_html": "<table><tr><td>额定电压</td><td>10kV</td></tr></table>",
            "data": {
                "page_start": 8,
                "page_end": 8,
                "table_title": "主要参数",
                "table_html": "<table><tr><td>额定电压</td><td>10kV</td></tr></table>",
                "table_image_path": None,
                "raw_json": {
                    "type": "table",
                    "bbox": [0, 0, 10, 10],
                    "blocks": [
                        {
                            "type": "table_caption",
                            "lines": [{"spans": [{"content": "主要参数", "type": "text"}]}],
                        },
                        {
                            "type": "table_body",
                            "lines": [{"spans": [{
                                "type": "table",
                                "html": "<table><tr><td>额定电压</td><td>10kV</td></tr></table>",
                            }]}],
                        },
                    ],
                },
            },
        }
    ]


def test_call_ai_gateway_uses_api_prefix(monkeypatch) -> None:
    called: dict[str, object] = {}

    class _ChatResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "content": "[]",
                "resolved_model": "deepseek-chat",
                "input_tokens": 1,
                "output_tokens": 1,
                "used_fallback": False,
            }

    def fake_post(url: str, **kwargs):
        called["url"] = url
        called["json"] = kwargs.get("json")
        called["timeout"] = kwargs.get("timeout")
        return _ChatResponse()

    monkeypatch.setattr(norm_processor._agent_repo, "get_by_key", lambda conn, key: SimpleNamespace(
        enabled=True,
        base_url="https://api.deepseek.com/v1",
        api_key="primary-key",
        primary_model="deepseek-v4-flash",
        fallback_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        fallback_api_key="fallback-key",
        fallback_model="qwen-plus",
    ))
    monkeypatch.setattr(norm_processor, "AI_GATEWAY_URL", "http://ai-gateway:8100")
    monkeypatch.setattr(norm_processor.httpx, "post", fake_post)

    raw = norm_processor._call_ai_gateway(object(), "prompt text", "第1章")

    assert raw == "[]"
    assert called["url"] == "http://ai-gateway:8100/api/ai/chat"
    assert called["timeout"] == 120.0


def test_call_ai_gateway_uses_longer_timeout_for_reasoner(monkeypatch) -> None:
    called: dict[str, object] = {}

    class _ChatResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "content": "[]",
                "resolved_model": "deepseek-v4-pro",
                "input_tokens": 1,
                "output_tokens": 1,
                "used_fallback": False,
            }

    def fake_post(url: str, **kwargs):
        called["timeout"] = kwargs.get("timeout")
        return _ChatResponse()

    monkeypatch.setattr(norm_processor._agent_repo, "get_by_key", lambda conn, key: SimpleNamespace(
        enabled=True,
        base_url="https://api.deepseek.com/v1",
        api_key="primary-key",
        primary_model="deepseek-v4-pro",
        fallback_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        fallback_api_key="fallback-key",
        fallback_model="qwen-plus",
    ))
    monkeypatch.setattr(norm_processor.httpx, "post", fake_post)

    norm_processor._call_ai_gateway(object(), "prompt text", "第1章")

    assert called["timeout"] == 300.0


def test_call_ai_gateway_uses_configured_backend_timeout(monkeypatch) -> None:
    called: dict[str, object] = {}

    class _ChatResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "content": "[]",
                "resolved_model": "deepseek-ai/DeepSeek-V3.2",
                "input_tokens": 1,
                "output_tokens": 1,
                "used_fallback": False,
            }

    def fake_post(url: str, **kwargs):
        called["timeout"] = kwargs.get("timeout")
        return _ChatResponse()

    monkeypatch.setattr(norm_processor._agent_repo, "get_by_key", lambda conn, key: SimpleNamespace(
        enabled=True,
        base_url="https://api.siliconflow.cn/v1",
        api_key="primary-key",
        primary_model="deepseek-ai/DeepSeek-V3.2",
        fallback_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        fallback_api_key="fallback-key",
        fallback_model="qwen-plus",
    ))
    monkeypatch.setattr(
        norm_processor,
        "get_settings",
        lambda: SimpleNamespace(standard_ai_gateway_timeout_seconds=120.0),
        raising=False,
    )
    monkeypatch.setattr(norm_processor.httpx, "post", fake_post)

    norm_processor._call_ai_gateway(object(), "prompt text", "第1章")

    assert called["timeout"] == 120.0


def test_process_scope_with_retries_rebalances_on_timeout(monkeypatch) -> None:
    calls: list[str] = []
    seen_scope_meta: dict[str, tuple[list[str], dict | None]] = {}
    scope = ProcessingScope(
        scope_type="normative",
        chapter_label="8 电力变压器",
        text=(
            "8 电力变压器\n\n"
            "8.0.1 第一条正文\n\n"
            "8.0.2 第二条正文\n\n"
            "8.0.3 第三条正文\n\n"
            "8.0.4 第四条正文"
        ),
        page_start=1,
        page_end=2,
        section_ids=["s1"],
        source_refs=["document_section:s1"],
        context={"document_id": "doc-1", "source_refs": ["document_section:s1"]},
    )

    def fake_call_ai_gateway(conn, prompt: str, scope_label: str) -> str:
        calls.append(scope_label)
        if scope_label == "8 电力变压器":
            raise httpx.ReadTimeout("timed out")
        return "[]"

    monkeypatch.setattr(norm_processor, "_call_ai_gateway", fake_call_ai_gateway)
    monkeypatch.setattr(norm_processor, "_parse_llm_json", lambda raw: [])
    def fake_build_prompt(current_scope):
        seen_scope_meta[current_scope.chapter_label] = (
            list(current_scope.source_refs),
            current_scope.context,
        )
        return current_scope.text

    monkeypatch.setattr(norm_processor, "build_prompt", fake_build_prompt)

    entries = norm_processor._process_scope_with_retries(object(), scope)

    assert entries == []
    assert calls[:3] == ["8 电力变压器", "8 电力变压器", "8 电力变压器"]
    assert calls[3:] == ["8 电力变压器 (1/2)", "8 电力变压器 (2/2)"]
    assert seen_scope_meta["8 电力变压器 (1/2)"] == (
        ["document_section:s1"],
        {"document_id": "doc-1", "source_refs": ["document_section:s1"]},
    )
    assert seen_scope_meta["8 电力变压器 (2/2)"] == (
        ["document_section:s1"],
        {"document_id": "doc-1", "source_refs": ["document_section:s1"]},
    )


def test_process_scope_with_retries_rebalances_on_ai_gateway_timeout_502(monkeypatch) -> None:
    calls: list[str] = []
    scope = ProcessingScope(
        scope_type="normative",
        chapter_label="4 电力变压器",
        text=(
            "4 电力变压器\n\n"
            "4.0.1 第一条正文\n\n"
            "4.0.2 第二条正文\n\n"
            "4.0.3 第三条正文\n\n"
            "4.0.4 第四条正文"
        ),
        page_start=1,
        page_end=3,
        section_ids=["s1"],
    )

    def fake_call_ai_gateway(conn, prompt: str, scope_label: str) -> str:
        calls.append(scope_label)
        if scope_label == "4 电力变压器":
            request = httpx.Request("POST", "http://ai-gateway:8100/api/ai/chat")
            response = httpx.Response(
                502,
                request=request,
                json={"detail": "All providers failed: Request timed out."},
            )
            raise httpx.HTTPStatusError("502 timeout", request=request, response=response)
        return "[]"

    monkeypatch.setattr(norm_processor, "_call_ai_gateway", fake_call_ai_gateway)
    monkeypatch.setattr(norm_processor, "_parse_llm_json", lambda raw: [])
    monkeypatch.setattr(norm_processor, "build_prompt", lambda current_scope: current_scope.text)

    entries = norm_processor._process_scope_with_retries(object(), scope)

    assert entries == []
    assert calls[:3] == ["4 电力变压器", "4 电力变压器", "4 电力变压器"]
    assert calls[3:] == ["4 电力变压器 (1/2)", "4 电力变压器 (2/2)"]


def test_process_scope_with_retries_retries_unsplittable_scope_before_failing(monkeypatch) -> None:
    calls: list[str] = []
    scope = ProcessingScope(
        scope_type="normative",
        chapter_label="1 总则",
        text="1.0.1 条文正文",
        page_start=1,
        page_end=1,
        section_ids=["s1"],
        source_refs=["document_section:s1"],
    )

    def fake_call_ai_gateway(conn, prompt: str, scope_label: str) -> str:
        calls.append(scope_label)
        if len(calls) == 1:
            raise httpx.ReadTimeout("timed out")
        return "[]"

    monkeypatch.setattr(norm_processor, "_call_ai_gateway", fake_call_ai_gateway)
    monkeypatch.setattr(norm_processor, "_parse_llm_json", lambda raw: [])
    monkeypatch.setattr(norm_processor, "build_prompt", lambda current_scope: current_scope.text)

    entries = norm_processor._process_scope_with_retries(object(), scope)

    assert entries == []
    assert calls == ["1 总则", "1 总则"]


def test_process_scope_with_retries_marks_table_entries_with_table_source(monkeypatch) -> None:
    scope = ProcessingScope(
        scope_type="table",
        chapter_label="表格: 主要参数",
        text="<table><tr><td>额定电压</td><td>10kV</td></tr></table>",
        page_start=8,
        page_end=8,
        section_ids=["t1"],
    )

    monkeypatch.setattr(norm_processor, "_call_ai_gateway", lambda conn, prompt, scope_label: '[{"clause_text":"额定电压不应低于10kV。"}]')
    monkeypatch.setattr(norm_processor, "build_prompt", lambda current_scope: current_scope.text)

    entries = norm_processor._process_scope_with_retries(object(), scope)

    assert entries == [
        {
            "clause_text": "额定电压不应低于10kV。",
            "clause_type": "normative",
            "page_start": 8,
            "page_end": 8,
            "source_type": "table",
            "source_label": "表格: 主要参数",
        }
    ]


def test_process_scope_with_retries_records_raw_ai_response_artifact(monkeypatch) -> None:
    scope = ProcessingScope(
        scope_type="normative",
        chapter_label="3.1 一般规定",
        text="3.1.1 设备安装应牢固。",
        page_start=12,
        page_end=12,
        source_refs=["document_section:s1"],
    )
    artifacts = []

    monkeypatch.setattr(
        norm_processor,
        "_call_ai_gateway",
        lambda conn, prompt, scope_label: '[{"clause_no":"3.1.1","clause_text":"设备安装应牢固。"}]',
    )

    entries = norm_processor._process_scope_with_retries(
        object(),
        scope,
        ai_artifacts=artifacts,
    )

    assert entries[0]["clause_no"] == "3.1.1"
    assert len(artifacts) == 1
    assert artifacts[0].task_type == "tag_clauses"
    assert artifacts[0].prompt_mode == "legacy_extract"
    assert artifacts[0].scope_label == "3.1 一般规定"
    assert artifacts[0].raw_response == '[{"clause_no":"3.1.1","clause_text":"设备安装应牢固。"}]'
    assert artifacts[0].parsed_count == 1
    assert artifacts[0].source_refs == ["document_section:s1"]


def test_process_scope_with_retries_skips_non_dict_llm_entries(monkeypatch) -> None:
    scope = ProcessingScope(
        scope_type="normative",
        chapter_label="3 基本规定",
        text="3.0.1 条文正文",
        page_start=5,
        page_end=5,
        section_ids=["s3"],
        source_refs=["document_section:s3"],
    )

    monkeypatch.setattr(
        norm_processor,
        "_call_ai_gateway",
        lambda conn, prompt, scope_label: '[{"clause_no":"3.0.1","clause_text":"有效条文"},"附加说明文本"]',
    )
    monkeypatch.setattr(norm_processor, "build_prompt", lambda current_scope: current_scope.text)

    entries = norm_processor._process_scope_with_retries(object(), scope)

    assert entries == [
        {
            "clause_no": "3.0.1",
            "clause_text": "有效条文",
            "clause_type": "normative",
            "page_start": 5,
            "page_end": 5,
            "source_ref": "document_section:s3",
            "source_refs": ["document_section:s3"],
            "source_type": "text",
            "source_label": "3 基本规定",
        }
    ]


def test_process_scope_with_retries_backfills_scope_metadata_recursively(monkeypatch) -> None:
    scope = ProcessingScope(
        scope_type="normative",
        chapter_label="4 电力变压器",
        text="4.8.1 220kV 及以上变压器本体露空安装附件应符合下列规定：",
        page_start=11,
        page_end=12,
        section_ids=["s1", "s2"],
        source_refs=["document_section:s1", "document_section:s2"],
    )

    monkeypatch.setattr(
        norm_processor,
        "_call_ai_gateway",
        lambda conn, prompt, scope_label: (
            '[{"clause_no":"4.8.1","clause_text":"主条文","children":'
            '[{"node_type":"item","node_label":"1","clause_text":"子项"}]}]'
        ),
    )
    monkeypatch.setattr(norm_processor, "build_prompt", lambda current_scope: current_scope.text)

    entries = norm_processor._process_scope_with_retries(object(), scope)

    assert entries == [
        {
            "clause_no": "4.8.1",
            "clause_text": "主条文",
            "children": [
                {
                    "node_type": "item",
                    "node_label": "1",
                    "clause_text": "子项",
                    "clause_type": "normative",
                    "page_start": 11,
                    "page_end": 12,
                    "source_ref": "document_section:s1",
                    "source_refs": ["document_section:s1", "document_section:s2"],
                    "source_type": "text",
                    "source_label": "4 电力变压器",
                }
            ],
            "clause_type": "normative",
            "page_start": 11,
            "page_end": 12,
            "source_ref": "document_section:s1",
            "source_refs": ["document_section:s1", "document_section:s2"],
            "source_type": "text",
            "source_label": "4 电力变压器",
        }
    ]


def test_process_scope_with_retries_replaces_non_positive_page_anchors_from_scope(monkeypatch) -> None:
    scope = ProcessingScope(
        scope_type="normative",
        chapter_label="5 互感器",
        text="5.2.1 互感器可不进行器身检查。",
        page_start=21,
        page_end=22,
        section_ids=["s1"],
        source_refs=["document_section:s1"],
    )

    monkeypatch.setattr(
        norm_processor,
        "_call_ai_gateway",
        lambda conn, prompt, scope_label: '[{"clause_no":"5.2.1","clause_text":"主条文","page_start":0,"page_end":0}]',
    )
    monkeypatch.setattr(norm_processor, "build_prompt", lambda current_scope: current_scope.text)

    entries = norm_processor._process_scope_with_retries(object(), scope)

    assert entries[0]["page_start"] == 21
    assert entries[0]["page_end"] == 22


def test_backfill_clause_page_anchors_recovers_page_from_raw_page_text_and_parent() -> None:
    asset = DocumentAsset(
        document_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        parser_name="mineru",
        parser_version="2.7.6",
        raw_payload={},
        pages=[
            PageAsset(
                page_number=18,
                normalized_text=(
                    "4.2.4设备在保管期间，应经常检查。充油保管时应每隔10天对变压器外观进行一次检查。"
                    "每隔30天应从变压器内抽取油样进行试验，其变压器内油样性能应符合表4.2.4的规定：\n"
                    "1 外观应无渗油。"
                ),
                raw_page={"page_number": 18},
                source_ref="document.raw_payload.pages[17]",
            )
        ],
        tables=[],
        full_markdown="",
    )
    clauses = [
        {
            "id": uuid4(),
            "clause_no": "4.2.4",
            "node_type": "clause",
            "source_type": "text",
            "source_label": "4.2.4 设备在保管期间，应经常检查。充油保管时应每隔10天对变压器外观进行一次检查。",
            "source_ref": "document_section:raw-section#4",
            "source_refs": ["document_section:raw-section#4"],
            "clause_text": "设备在保管期间，应经常检查。充油保管时应每隔10天对变压器外观进行一次检查。",
            "page_start": None,
            "page_end": None,
            "parent_id": None,
        },
        {
            "id": uuid4(),
            "clause_no": "4.2.4",
            "node_type": "item",
            "source_type": "text",
            "source_label": "4.2.4 设备在保管期间，应经常检查。充油保管时应每隔10天对变压器外观进行一次检查。",
            "source_ref": "document_section:raw-section#4",
            "source_refs": ["document_section:raw-section#4"],
            "clause_text": "外观应无渗油。",
            "page_start": None,
            "page_end": None,
            "parent_id": None,  # filled below to keep UUID stable in fixture
        },
    ]
    clauses[1]["parent_id"] = clauses[0]["id"]

    norm_processor._backfill_clause_page_anchors_from_asset(clauses, asset)

    assert clauses[0]["page_start"] == 18
    assert clauses[0]["page_end"] == 18
    assert clauses[1]["page_start"] == 18
    assert clauses[1]["page_end"] == 18


def test_backfill_clause_page_anchors_uses_table_source_refs() -> None:
    asset = DocumentAsset(
        document_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        parser_name="mineru",
        parser_version="2.7.6",
        raw_payload={},
        pages=[],
        tables=[
            TableAsset(
                source_ref="table:t1",
                page_start=32,
                page_end=32,
                table_title="表4.10.2热油循环后施加电压前变压器油标准",
                table_html="<table><tr><td>项目</td><td>标准</td></tr></table>",
                raw_json={"id": "t1"},
            )
        ],
        full_markdown="",
    )
    clauses = [
        {
            "id": uuid4(),
            "clause_no": None,
            "node_type": "clause",
            "source_type": "table",
            "source_label": "表格: 表4.10.2热油循环后施加电压前变压器油标准",
            "source_ref": "table:t1",
            "source_refs": ["table:t1"],
            "clause_text": "击穿电压：不应低于60kV。",
            "page_start": None,
            "page_end": None,
            "parent_id": None,
        }
    ]

    norm_processor._backfill_clause_page_anchors_from_asset(clauses, asset)

    assert clauses[0]["page_start"] == 32
    assert clauses[0]["page_end"] == 32


def test_backfill_clause_page_anchors_matches_table_title_when_source_ref_is_missing() -> None:
    asset = DocumentAsset(
        document_id=UUID("bcbcbcbc-bcbc-bcbc-bcbc-bcbcbcbcbcbc"),
        parser_name="mineru",
        parser_version="2.7.6",
        raw_payload={},
        pages=[],
        tables=[
            TableAsset(
                source_ref="table:unknown",
                page_start=70,
                page_end=70,
                table_title="续表D.0.23",
                table_html="<table><tr><td>序号</td></tr></table>",
                raw_json={},
            )
        ],
        full_markdown="",
    )
    clauses = [
        {
            "id": uuid4(),
            "clause_no": "D.0.23",
            "node_type": "clause",
            "source_type": "text",
            "source_label": "D.0.23 10kV线路导线架设检查记录表应按本规范表D.0.23填写。",
            "source_ref": "document_section:d023#34",
            "source_refs": ["document_section:d023#34"],
            "clause_text": "10kV线路导线架设检查记录表应按本规范表D.0.23填写。",
            "page_start": None,
            "page_end": None,
            "parent_id": None,
        }
    ]

    norm_processor._backfill_clause_page_anchors_from_asset(clauses, asset)

    assert clauses[0]["page_start"] == 70
    assert clauses[0]["page_end"] == 70


def test_backfill_clause_page_anchors_ignores_toc_page_matches() -> None:
    asset = DocumentAsset(
        document_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        parser_name="mineru",
        parser_version="2.7.6",
        raw_payload={},
        pages=[
            PageAsset(
                page_number=7,
                normalized_text="目次\n附录A 新装电力变压器及油浸电抗器不需干燥的条件（29）\nA.0.2 （30）",
                raw_page={"page_number": 7},
                source_ref="document.raw_payload.pages[6]",
            ),
            PageAsset(
                page_number=38,
                normalized_text=(
                    "附录A 新装电力变压器及油浸电抗器不需干燥的条件\n"
                    "A.0.2 变压器及电抗器注入合格绝缘油后应符合下列规定：\n"
                    "1 绝缘油电气强度及含水量应合格。"
                ),
                raw_page={"page_number": 38},
                source_ref="document.raw_payload.pages[37]",
            ),
        ],
        tables=[],
        full_markdown="",
    )
    clauses = [
        {
            "id": uuid4(),
            "clause_no": "A.0.2",
            "node_type": "clause",
            "source_type": "text",
            "source_label": "A.0.2 变压器及电抗器注人合格绝缘油后应符合下列规定：",
            "source_ref": "document_section:appendix-a",
            "source_refs": ["document_section:appendix-a"],
            "clause_text": "器身内压力在出厂至安装前均应保持正压。",
            "page_start": None,
            "page_end": None,
            "parent_id": None,
        }
    ]

    norm_processor._backfill_clause_page_anchors_from_asset(clauses, asset)

    assert clauses[0]["page_start"] == 38
    assert clauses[0]["page_end"] == 38


def test_build_processing_scopes_appends_table_segments() -> None:
    sections = [
        {
            "id": "s1",
            "section_code": "1",
            "title": "总则",
            "level": 1,
            "page_start": 1,
            "page_end": 1,
            "text": "1.0.1 正文",
        }
    ]
    tables = [
        {
            "id": "t1",
            "page": 2,
            "page_start": 2,
            "page_end": 2,
            "table_title": "主要参数",
            "table_html": "<table><tr><td>额定电压</td><td>10kV</td></tr></table>",
        }
    ]

    scopes = norm_processor._build_processing_scopes(sections, tables)

    assert [scope.scope_type for scope in scopes] == ["normative", "table"]
    assert scopes[0].chapter_label == "1 总则"
    assert scopes[0].source_refs == ["document_section:s1"]
    assert scopes[0].context == {
        "document_id": "00000000-0000-0000-0000-000000000000",
        "source_refs": ["document_section:s1"],
        "node_types": ["page"],
    }
    assert scopes[1].chapter_label == "表格: 主要参数"
    assert scopes[1].text == "<table><tr><td>额定电压</td><td>10kV</td></tr></table>"
    assert scopes[1].page_start == 2
    assert scopes[1].source_refs == ["table:t1"]


def test_build_processing_scopes_ignores_raw_front_matter_before_normalized_sections() -> None:
    document_id = UUID("11111111-2222-3333-4444-555555555555")
    sections = [
        {
            "id": "s1",
            "section_code": "1.0.1",
            "title": "为保证施工安装质量，制定本规范。",
            "level": 3,
            "page_start": 10,
            "page_end": 10,
            "text": "",
            "raw_json": {"page_number": 10},
        },
        {
            "id": "s2",
            "section_code": None,
            "title": "2.0.1 电力变压器 power transformer",
            "level": 3,
            "page_start": 11,
            "page_end": 11,
            "text": "",
            "raw_json": {"page_number": 11},
        },
    ]

    document = {
        "id": document_id,
        "raw_payload": {
            "pages": [
                {"page_number": 1, "markdown": "中华人民共和国国家标准\n2010 北京"},
                {"page_number": 7, "markdown": "1 总 则 ………………………………………… (1)\n2 术语 (2)"},
                {"page_number": 10, "markdown": "1 总则\n1.0.1 为保证施工安装质量，制定本规范。"},
                {"page_number": 11, "markdown": "2 术语\n2.0.1 电力变压器 power transformer"},
            ]
        },
    }

    scopes = norm_processor._build_processing_scopes(
        sections,
        [],
        document=document,
        document_id=str(document_id),
    )

    assert [scope.scope_type for scope in scopes] == ["normative", "normative"]
    assert [scope.chapter_label for scope in scopes] == ["1 总则", "2 术语"]
    assert scopes[0].page_start == 10
    assert scopes[0].page_end == 10
    assert scopes[1].page_start == 11
    assert scopes[1].page_end == 11


def test_build_processing_scopes_uses_rebuilt_leaf_outline_when_sections_are_polluted() -> None:
    document_id = UUID("99999999-2222-3333-4444-555555555555")
    sections = [
        {
            "id": "bad-1",
            "section_code": "4",
            "title": "电力变压器、油浸电抗器",
            "level": 1,
            "page_start": 15,
            "page_end": 38,
            "text": "",
            "raw_json": None,
        },
        {
            "id": "bad-2",
            "section_code": "5",
            "title": "内部枚举污染行",
            "level": 1,
            "page_start": 15,
            "page_end": 38,
            "text": "",
            "raw_json": None,
        },
        {
            "id": "bad-3",
            "section_code": "6",
            "title": "内部枚举污染行",
            "level": 1,
            "page_start": 15,
            "page_end": 38,
            "text": "",
            "raw_json": None,
        },
    ]

    document = {
        "id": document_id,
        "raw_payload": {
            "pages": [
                {
                    "page_number": 15,
                    "markdown": (
                        "4 电力变压器、油浸电抗器\n"
                        "4.1 装卸、运输与就位\n"
                        "4.1.1 条文正文\n"
                        "1 水路运输时，应做好下列工作："
                    ),
                },
                {
                    "page_number": 17,
                    "markdown": (
                        "4.2 交接与保管\n"
                        "4.2.1 设备到达现场后，应及时按下列规定进行外观检查："
                    ),
                },
                {
                    "page_number": 35,
                    "markdown": (
                        "5 互感器\n"
                        "5.1 一般规定\n"
                        "5.1.1 互感器运输和保管应符合产品技术文件的规定。"
                    ),
                },
                {
                    "page_number": 38,
                    "markdown": (
                        "附录A 新装电力变压器及油浸电抗器不需干燥的条件\n"
                        "A.0.1 带油运输的变压器及电抗器应符合下列规定："
                    ),
                },
                {
                    "page_number": 39,
                    "markdown": (
                        "本规范用词说明\n"
                        "为便于在执行本规范条文时区别对待，对要求严格程度不同的用词说明如下："
                    ),
                },
            ]
        },
    }

    scopes = norm_processor._build_processing_scopes(
        sections,
        [],
        document=document,
        document_id=str(document_id),
    )

    assert [scope.scope_type for scope in scopes] == ["normative", "normative", "normative", "normative"]
    assert [scope.chapter_label for scope in scopes] == [
        "4.1 装卸、运输与就位",
        "4.2 交接与保管",
        "5.1 一般规定",
        "附录A 新装电力变压器及油浸电抗器不需干燥的条件",
    ]
    assert scopes[0].page_start == 15
    assert scopes[0].page_end == 15
    assert scopes[1].page_start == 17
    assert scopes[1].page_end == 17
    assert scopes[2].page_start == 35
    assert scopes[2].page_end == 35
    assert scopes[3].page_start == 38
    assert scopes[3].page_end == 38


def test_build_prompt_uses_table_specific_prompt() -> None:
    prompt = build_prompt(ProcessingScope(
        scope_type="table",
        chapter_label="表格: 主要参数",
        text="<table><tr><td>额定电压</td><td>10kV</td></tr></table>",
        page_start=8,
        page_end=8,
        section_ids=["t1"],
        source_refs=["table:t1"],
        context={"node_type": "table", "source_ref": "table:t1"},
    ))

    assert "规范表格" in prompt


def test_build_block_processing_scopes_routes_three_channels() -> None:
    blocks = [
        BlockSegment(
            segment_type="normative_clause_block",
            chapter_label="4.1.2 变压器或电抗器的装卸",
            text="变压器或电抗器的装卸应符合下列规定：",
            clause_no="4.1.2",
            page_start=6,
            page_end=6,
            section_ids=["s1"],
            source_refs=["document_section:s1"],
        ),
        BlockSegment(
            segment_type="commentary_block",
            chapter_label="4.1.2 条文说明",
            text="本条说明变压器装卸控制要求。",
            clause_no="4.1.2",
            page_start=7,
            page_end=7,
            section_ids=["s2"],
            source_refs=["document_section:s2"],
        ),
        BlockSegment(
            segment_type="table_requirement_block",
            chapter_label="表格: 表 4.2.4 变压器内油样性能",
            text="表 4.2.4 变压器内油样性能\n含水量 ≤10μL/L",
            table_title="表 4.2.4 变压器内油样性能",
            page_start=18,
            page_end=18,
            source_refs=["table:t1"],
        ),
    ]

    scopes = norm_processor._build_block_processing_scopes(blocks)

    assert [scope.scope_type for scope in scopes] == ["normative", "commentary", "table"]
    assert scopes[0].chapter_label == "4.1.2 变压器或电抗器的装卸"
    assert scopes[1].chapter_label == "4.1.2 条文说明"
    assert scopes[2].source_refs == ["table:t1"]


def test_build_block_processing_scopes_keeps_table_prompt_on_table_channel() -> None:
    block = BlockSegment(
        segment_type="table_requirement_block",
        chapter_label="表格: 表 4.2.4 变压器内油样性能",
        text="表 4.2.4 变压器内油样性能\n含水量 ≤10μL/L",
        table_title="表 4.2.4 变压器内油样性能",
        page_start=18,
        page_end=18,
        source_refs=["table:t1"],
    )

    [scope] = norm_processor._build_block_processing_scopes([block])
    prompt = build_prompt(scope)

    assert scope.scope_type == "table"
    assert "规范表格" in prompt
    assert "来源引用: table:t1" in prompt
    assert "表 4.2.4 变压器内油样性能" in prompt


def test_validate_tree_ignores_empty_structural_parent_clause() -> None:
    parent_id = UUID("11111111-1111-1111-1111-111111111111")
    child_id = UUID("22222222-2222-2222-2222-222222222222")
    clauses = [
        {
            "id": parent_id,
            "parent_id": None,
            "clause_no": "15",
            "clause_title": "套管",
            "clause_text": "",
        },
        {
            "id": child_id,
            "parent_id": parent_id,
            "clause_no": "15.0.1",
            "clause_title": None,
            "clause_text": "说明正文",
        },
    ]

    warnings = validate_tree(clauses)

    assert warnings == []


def test_validate_tree_still_warns_for_empty_leaf_clause() -> None:
    clause_id = UUID("33333333-3333-3333-3333-333333333333")
    clauses = [
        {
            "id": clause_id,
            "parent_id": None,
            "clause_no": "10",
            "clause_title": "互感器",
            "clause_text": "",
        }
    ]

    warnings = validate_tree(clauses)

    assert warnings == ["Clause 10: empty clause_text"]


def test_split_into_scopes_uses_top_level_chapters_only() -> None:
    windows = [
        PageWindow(
            page_start=1,
            page_end=2,
            section_ids=["s1"],
            text=(
                "前言内容\n\n"
                "1 总则\n"
                "1.0.1 第一条内容\n"
                "1.0.2 第二条内容\n\n"
                "2 术语\n"
                "2.0.1 第三条内容\n"
            ),
        )
    ]

    scopes = split_into_scopes(windows)

    assert [scope.chapter_label for scope in scopes] == ["前言", "1 总则", "2 术语"]


def test_split_into_scopes_does_not_treat_clause_sentences_as_chapters() -> None:
    windows = [
        PageWindow(
            page_start=1,
            page_end=3,
            section_ids=["s1"],
            text=(
                "3 基本规定\n\n"
                "1 交流耐压试验时加至试验标准电压后的持续时间，无特殊说明时应为 1min。\n"
                "2 耐压试验电压值以额定电压的倍数计算时，应按铭牌额定电压计算。\n\n"
                "4 同步发电机及调相机\n"
                "1 测量定子绕组的绝缘电阻和吸收比或极化指数；\n"
            ),
        )
    ]

    scopes = split_into_scopes(windows)

    assert [scope.chapter_label for scope in scopes] == ["3 基本规定", "4 同步发电机及调相机"]


def test_split_into_scopes_ignores_stray_commentary_heading_inside_normative_flow() -> None:
    windows = [
        PageWindow(
            page_start=1,
            page_end=4,
            section_ids=["s1", "s2", "s3"],
            text=(
                "1 总则\n"
                "1.0.1 第一条内容\n\n"
                "条文说明\n\n"
                "2 术语\n"
                "2.0.1 第二条内容\n"
            ),
        )
    ]

    scopes = split_into_scopes(windows)

    assert [scope.scope_type for scope in scopes] == ["normative", "normative"]
    assert [scope.chapter_label for scope in scopes] == ["1 总则", "2 术语"]
    assert all("条文说明" not in scope.text for scope in scopes)


def test_split_into_scopes_does_not_treat_standalone_page_numbers_as_chapters() -> None:
    windows = [
        PageWindow(
            page_start=13,
            page_end=14,
            section_ids=["s1", "s2"],
            text=(
                "3 基本规定\n"
                "3.0.1 第一条内容\n\n"
                "4\n"
                "text_list\n"
                "text\n"
                "3.0.2 第二条内容\n\n"
                "4 电力变压器、油浸电抗器\n"
                "4.1.1 第三条内容\n"
            ),
        )
    ]

    scopes = split_into_scopes(windows)

    assert [scope.chapter_label for scope in scopes] == ["3 基本规定", "4 电力变压器、油浸电抗器"]


def test_split_into_scopes_ignores_toc_heavy_commentary_pages() -> None:
    windows = [
        PageWindow(
            page_start=39,
            page_end=39,
            section_ids=["s1"],
            text=(
                "本规范用词说明\n"
                "1 为便于在执行本规范条文时区别对待，对要求严格程度不同的用词说明如下：\n"
            ),
        ),
        PageWindow(
            page_start=44,
            page_end=44,
            section_ids=["s2"],
            text=(
                "2 术语 ………………………………………… (39)\n"
                "text_list\n"
                "text\n"
                "4 电力变压器、油浸电抗器 (40)\n"
                "text\n"
                "4.1 装卸、运输与就位 (40)\n"
                "text\n"
                "4.2 交接与保管 (41)\n"
            ),
        ),
        PageWindow(
            page_start=45,
            page_end=45,
            section_ids=["s3"],
            text=(
                "1 总则\n"
                "1.0.1 第一条说明\n\n"
                "2 术语\n"
                "2.0.1 第二条说明\n"
            ),
        ),
    ]

    scopes = split_into_scopes(windows)

    assert [scope.scope_type for scope in scopes] == ["commentary", "commentary", "commentary"]
    assert [scope.chapter_label for scope in scopes] == ["前言", "1 总则", "2 术语"]


def test_compress_sections_preserves_input_order_without_page_numbers() -> None:
    sections = [
        {
            "id": "sec-2",
            "section_code": "2",
            "title": "术语",
            "level": 1,
            "page_start": None,
            "page_end": None,
            "text": "第二章正文内容足够长",
        },
        {
            "id": "sec-1",
            "section_code": "1",
            "title": "总则",
            "level": 1,
            "page_start": None,
            "page_end": None,
            "text": "第一章正文内容足够长",
        },
    ]

    windows = compress_sections(sections)

    assert len(windows) == 1
    assert windows[0].text == (
        "2 术语\n第二章正文内容足够长\n\n"
        "1 总则\n第一章正文内容足够长"
    )


def test_compress_sections_keeps_heading_only_sections() -> None:
    sections = [
        {
            "id": "chapter-1",
            "section_code": "1",
            "title": "总则",
            "level": 1,
            "page_start": 1,
            "page_end": 1,
            "text": "",
        },
        {
            "id": "clause-1",
            "section_code": None,
            "title": "适用范围",
            "level": 3,
            "page_start": 1,
            "page_end": 1,
            "text": "本条正文内容足够长，不能被当成噪声过滤。",
        },
    ]

    windows = compress_sections(sections)

    assert len(windows) == 1
    assert windows[0].text.startswith("1 总则\n\n适用范围\n本条正文内容足够长")


def test_fetch_sections_uses_ctid_fallback_order_for_legacy_rows() -> None:
    captured: dict[str, object] = {}

    class _FakeCursor:
        def __init__(self) -> None:
            self.rows = [{
                "id": "sec-1",
                "section_code": None,
                "title": "标题",
                "level": 1,
                "text": "正文",
                "page_start": None,
                "page_end": None,
            }]

        def execute(self, query: str, params: tuple[str]) -> "_FakeCursor":
            captured["query"] = query
            captured["params"] = params
            return self

        def fetchall(self) -> list[dict]:
            return self.rows

        def __enter__(self) -> "_FakeCursor":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class _FakeConn:
        def cursor(self, **kwargs) -> _FakeCursor:
            captured["cursor_kwargs"] = kwargs
            return _FakeCursor()

    rows = norm_processor._fetch_sections(
        _FakeConn(),
        "2784a326-9811-4fb4-972b-a1efe8a39d62",
    )

    assert rows[0]["title"] == "标题"
    assert captured["params"] == ("2784a326-9811-4fb4-972b-a1efe8a39d62",)
    assert "ctid" in str(captured["query"])


def test_normalize_sections_for_processing_drops_toc_and_front_matter() -> None:
    sections = [
        {"title": "电气装置安装工程电气设备交接试验标准", "text": "", "level": 1},
        {"title": "总 则 (1)", "text": "", "level": 1},
        {"title": "Contents", "text": "", "level": 1},
        {"title": "1 General provisions (1)", "text": "", "level": 1},
        {"title": "1 总 则", "text": "", "level": 1},
        {"title": "为适应电气装置安装工程电气设备交接试验的需要，制定本标准。", "text": "", "level": 3},
        {"title": "2 术语", "text": "", "level": 1},
        {"title": "1 总 则 ………………………………………… (97)", "text": "", "level": 1},
        {"title": "条文说明", "text": "", "level": 1},
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert [section["title"] for section in normalized] == [
        "1 总 则",
        "为适应电气装置安装工程电气设备交接试验的需要，制定本标准。",
        "2 术语",
        "条文说明",
    ]


def test_normalize_sections_for_processing_drops_toc_anchored_heading_noise_from_page_markdown() -> None:
    sections = [
        {
            "id": "toc-heading",
            "section_code": "1",
            "title": "总则",
            "text": "",
            "level": 1,
            "page_start": 7,
            "page_end": 7,
            "raw_json": {
                "page_number": 7,
                "markdown": "目次\n1 总则 (1)",
            },
        },
        {
            "id": "real-heading",
            "section_code": "1",
            "title": "总则",
            "text": "",
            "level": 1,
            "page_start": 10,
            "page_end": 10,
            "raw_json": {
                "page_number": 10,
                "markdown": "1 总则\n1.0.1 为保证施工安装质量，制定本规范。",
            },
        },
        {
            "id": "clause",
            "section_code": "1.0.1",
            "title": "为保证施工安装质量，制定本规范。",
            "text": "",
            "level": 3,
            "page_start": 10,
            "page_end": 10,
            "raw_json": {
                "page_number": 10,
                "markdown": "1 总则\n1.0.1 为保证施工安装质量，制定本规范。",
            },
        },
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert [(section.get("section_code"), section.get("page_start")) for section in normalized] == [
        ("1", 10),
        ("1.0.1", 10),
    ]


def test_normalize_sections_for_processing_keeps_first_clause_when_chapter_heading_missing() -> None:
    sections = [
        {"title": "中华人民共和国国家标准", "text": "", "level": 1, "page_start": 1},
        {"title": "目次", "text": "", "level": 1, "page_start": 7},
        {"title": "1 总 则 ………………………………………… (1)", "text": "", "level": 1, "page_start": 7},
        {"title": "1 General provisions (1)", "text": "", "level": 1, "page_start": 8},
        {"title": "1.0.1 为保证施工安装质量，制定本规范。", "text": "", "level": 2, "page_start": 10},
        {"title": "1.0.2 本规范适用于交流3kV~750kV。", "text": "", "level": 2, "page_start": 10},
        {"title": "2 术语", "text": "", "level": 1, "page_start": 11},
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert [section["title"] for section in normalized] == [
        "1.0.1 为保证施工安装质量，制定本规范。",
        "1.0.2 本规范适用于交流3kV~750kV。",
        "2 术语",
    ]


def test_normalize_sections_for_processing_drops_toc_rows_even_when_they_carry_tail_text() -> None:
    sections = [
        {"section_code": "5.4", "title": "工程交接验收 (28)", "text": "附录A 新装电力变压器及油浸电抗器不需干燥的条件 …… (29)", "level": 2, "page_start": 7},
        {"section_code": "1.0.1", "title": "为保证施工安装质量，制定本规范。", "text": "", "level": 3, "page_start": 10},
        {"section_code": None, "title": "2.0.1 电力变压器 power transformer", "text": "", "level": 3, "page_start": 11},
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert [f'{section.get("section_code") or ""} {section["title"]}'.strip() for section in normalized] == [
        "1.0.1 为保证施工安装质量，制定本规范。",
        "2.0.1 电力变压器 power transformer",
    ]


def test_normalize_sections_for_processing_drops_toc_heading_even_when_body_contains_catalog_rows() -> None:
    sections = [
        {
            "section_code": None,
            "title": "目次",
            "text": "1 总则 ………………………………………… (1)\n2 术语 ………………………………………… (2)",
            "level": 1,
            "page_start": 7,
        },
        {
            "section_code": "1",
            "title": "总则",
            "text": "",
            "level": 1,
            "page_start": 10,
        },
        {
            "section_code": "1.0.1",
            "title": "为保证施工安装质量，制定本规范。",
            "text": "",
            "level": 2,
            "page_start": 10,
        },
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert [f'{section.get("section_code") or ""} {section["title"]}'.strip() for section in normalized] == [
        "1 总则",
        "1.0.1 为保证施工安装质量，制定本规范。",
    ]


def test_normalize_sections_for_processing_backfills_missing_heading_anchor_from_page_markdown() -> None:
    sections = [
        {
            "id": "chapter",
            "section_code": "1",
            "title": "总则",
            "text": "",
            "level": 1,
            "page_start": None,
            "page_end": None,
            "raw_json": None,
        },
        {
            "id": "clause",
            "section_code": "1.0.1",
            "title": "为保证施工安装质量，制定本规范。",
            "text": "",
            "level": 3,
            "page_start": 10,
            "page_end": 10,
            "raw_json": {
                "page_number": 10,
                "markdown": "1 总则\n1.0.1 为保证施工安装质量，制定本规范。",
            },
        },
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert normalized[0]["section_code"] == "1"
    assert normalized[0]["page_start"] == 10
    assert normalized[0]["page_end"] == 10
    assert normalized[0]["raw_json"]["page_number"] == 10


def test_normalize_sections_for_processing_drops_suspicious_year_code_and_unanchored_heading_noise() -> None:
    sections = [
        {
            "id": "chapter",
            "section_code": "1",
            "title": "总则",
            "text": "",
            "level": 1,
            "page_start": 10,
            "page_end": 10,
            "raw_json": {
                "page_number": 10,
                "markdown": "1 总则\n1.0.1 为保证施工安装质量，制定本规范。",
            },
        },
        {
            "id": "year-noise",
            "section_code": "2014",
            "title": "2014",
            "text": "",
            "level": 1,
            "page_start": None,
            "page_end": None,
            "raw_json": {
                "page_number": 1,
                "markdown": "2014\n中华人民共和国住房和城乡建设部公告",
            },
        },
        {
            "id": "heading-noise",
            "section_code": None,
            "title": "4.2 安装与调整",
            "text": "",
            "level": 2,
            "page_start": None,
            "page_end": None,
            "raw_json": None,
        },
        {
            "id": "clause",
            "section_code": "1.0.1",
            "title": "为保证施工安装质量，制定本规范。",
            "text": "",
            "level": 3,
            "page_start": 10,
            "page_end": 10,
            "raw_json": {
                "page_number": 10,
                "markdown": "1 总则\n1.0.1 为保证施工安装质量，制定本规范。",
            },
        },
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert [section["id"] for section in normalized] == ["chapter", "clause"]


def test_normalize_sections_for_processing_promotes_inline_clause_title_to_text() -> None:
    sections = [
        {"section_code": "1.0.1", "title": "为保证施工安装质量，制定本规范。", "text": "", "level": 3, "page_start": 10},
        {"section_code": "1.0.2", "title": "本规范适用于交流3kV~750kV电气装置安装工程。", "text": "", "level": 3, "page_start": 10},
        {"section_code": "2", "title": "术语", "text": "", "level": 1, "page_start": 11},
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert normalized[0]["text"] == "为保证施工安装质量，制定本规范。"
    assert normalized[1]["text"] == "本规范适用于交流3kV~750kV电气装置安装工程。"
    assert normalized[2]["text"] == ""


def test_normalize_sections_for_processing_splits_embedded_subclauses_from_chapter_body() -> None:
    sections = [
        {
            "id": "s4",
            "section_code": "4",
            "title": "电力变压器、油浸电抗器",
            "text": (
                "4.1 装卸、运输与就位\n"
                "4.1.1 31.5MV·A及以上变压器和40MVar及以上的电抗器的装卸及运输，应符合下列规定：\n"
                "1 水路运输时，应做好准备工作。\n"
                "4.1.2 变压器或电抗器的装卸应符合下列规定：\n"
                "1 装卸站台、码头等地点的地面应坚实。\n"
            ),
            "level": 1,
            "page_start": 15,
            "page_end": 15,
        }
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert [(section.get("section_code"), section.get("title")) for section in normalized] == [
        ("4", "电力变压器、油浸电抗器"),
        ("4.1", "装卸、运输与就位"),
        ("4.1.1", "31.5MV·A及以上变压器和40MVar及以上的电抗器的装卸及运输，应符合下列规定："),
        ("1", "水路运输时，应做好准备工作。"),
        ("4.1.2", "变压器或电抗器的装卸应符合下列规定："),
        ("1", "装卸站台、码头等地点的地面应坚实。"),
    ]
    assert normalized[2]["text"] == "31.5MV·A及以上变压器和40MVar及以上的电抗器的装卸及运输，应符合下列规定："
    assert normalized[4]["text"] == "变压器或电抗器的装卸应符合下列规定："


def test_normalize_sections_for_processing_splits_embedded_subclauses_from_continuation_rows() -> None:
    sections = [
        {
            "id": "s4b",
            "section_code": None,
            "title": "运输过程中，冲击加速度应符合制造厂及合同的规定。",
            "text": (
                "4.1.3 运输过程中，冲击加速度应符合制造厂及合同的规定。\n"
                "4.1.4 当产品有特殊要求时，尚应符合产品技术文件的规定。\n"
                "1 运输倾斜角不得超过15°。\n"
            ),
            "level": 2,
            "page_start": 16,
            "page_end": 16,
        }
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert [(section.get("section_code"), section.get("title")) for section in normalized] == [
        ("4.1.3", "运输过程中，冲击加速度应符合制造厂及合同的规定。"),
        ("4.1.4", "当产品有特殊要求时，尚应符合产品技术文件的规定。"),
    ]
    assert normalized[0]["text"] == "运输过程中，冲击加速度应符合制造厂及合同的规定。"
    assert normalized[1]["text"] == "当产品有特殊要求时，尚应符合产品技术文件的规定。\n1 运输倾斜角不得超过15°。"


def test_normalize_sections_for_processing_expands_text_list_body_into_numbered_item_sections() -> None:
    sections = [
        {
            "id": "s412",
            "section_code": "4.1.2",
            "title": "变压器或电抗器的装卸应符合下列规定：",
            "text": (
                "text_list\n"
                "text\n"
                "1 装卸站台、码头等地点的地面应坚实。\n"
                "text\n"
                "2 装卸时应设专人观测车辆、平台的升降或船只的沉浮情况，防止超过允许范围的倾斜。\n"
                "·6·\n"
            ),
            "level": 3,
            "page_start": 15,
            "page_end": 15,
        }
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert [(section.get("section_code"), section.get("title")) for section in normalized] == [
        ("4.1.2", "变压器或电抗器的装卸应符合下列规定："),
        ("1", "装卸站台、码头等地点的地面应坚实。"),
        ("2", "装卸时应设专人观测车辆、平台的升降或船只的沉浮情况，防止超过允许范围的倾斜。"),
    ]
    assert normalized[0]["text"] == "变压器或电抗器的装卸应符合下列规定："
    assert normalized[1]["text"] == ""
    assert normalized[2]["text"] == ""


def test_normalize_sections_for_processing_expands_parenthesized_text_list_items() -> None:
    sections = [
        {
            "id": "s8013",
            "section_code": "8.0.13",
            "title": "局部放电测量应符合下列规定：",
            "text": (
                "text_list\n"
                "text\n"
                "（3）在施加试验电压的整个期间，应监测局部放电量。\n"
                "text\n"
                "(4) 在施加试验电压的前后，应测量所有测量通道上的背景噪声水平。\n"
            ),
            "level": 3,
            "page_start": 95,
            "page_end": 95,
        }
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert [(section.get("section_code"), section.get("title")) for section in normalized] == [
        ("8.0.13", "局部放电测量应符合下列规定："),
        ("3", "在施加试验电压的整个期间，应监测局部放电量。"),
        ("4", "在施加试验电压的前后，应测量所有测量通道上的背景噪声水平。"),
    ]
    assert normalized[0]["text"] == "局部放电测量应符合下列规定："
    assert normalized[1]["text"] == ""
    assert normalized[2]["text"] == ""


def test_normalize_sections_for_processing_expands_text_list_continuations_and_following_clauses() -> None:
    sections = [
        {
            "id": "s4121",
            "section_code": "4.12.1",
            "title": "变压器、电抗器在试运行前，应进行全面检查，确认其符合运行条件时，方可投入试运行。检查项目应包含以下内容和要求：",
            "text": (
                "text_list\n"
                "text\n"
                "1 本体、冷却装置及所有附件应无缺陷，且不渗油。\n"
            ),
            "level": 3,
            "page_start": 33,
            "page_end": 33,
        },
        {
            "id": "s4121b",
            "section_code": None,
            "title": "text_list",
            "text": (
                "text\n"
                "12 变压器、电抗器的全部电气试验应合格；保护装置整定值应符合规定；操作及联动试验应正确。\n"
                "text\n"
                "13 局部放电测量前、后本体绝缘油色谱试验比对结果应合格。\n"
                "4.12.2 变压器、电抗器试运行时应按下列规定项目进行检查：\n"
                "text_list\n"
                "text\n"
                "1 中性点接地系统的变压器，在进行冲击合闸时，其中性点必须接地。\n"
            ),
            "level": 3,
            "page_start": 34,
            "page_end": 34,
        },
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert [(section.get("section_code"), section.get("title")) for section in normalized] == [
        ("4.12.1", "变压器、电抗器在试运行前，应进行全面检查，确认其符合运行条件时，方可投入试运行。检查项目应包含以下内容和要求："),
        ("1", "本体、冷却装置及所有附件应无缺陷，且不渗油。"),
        ("12", "变压器、电抗器的全部电气试验应合格；保护装置整定值应符合规定；操作及联动试验应正确。"),
        ("13", "局部放电测量前、后本体绝缘油色谱试验比对结果应合格。"),
        ("4.12.2", "变压器、电抗器试运行时应按下列规定项目进行检查："),
        ("1", "中性点接地系统的变压器，在进行冲击合闸时，其中性点必须接地。"),
    ]
    assert normalized[4]["text"] == "变压器、电抗器试运行时应按下列规定项目进行检查："


def test_normalize_sections_for_processing_splits_sibling_clauses_after_numbered_items() -> None:
    sections = [
        {
            "id": "s485",
            "section_code": "4.8.5",
            "title": "储油柜的安装应符合下列规定：",
            "text": (
                "得\n"
                "text_list\n"
                "1 储油柜应按照产品技术文件要求进行检查、安装。\n"
                "2 油位表动作应灵活，指示应与储油柜内的真实油位对应。\n"
                "3 储油柜安装方向正确并进行位置复核。\n"
                "4.8.6 所有导气管应清拭干净，其连接应密封严密。\n"
                "4.8.7 升高座的安装应符合下列规定：\n"
                "text_list\n"
                "1 安装前，应进行检查。\n"
                "4.8.8 套管安装后，顶部结构应密封良好。\n"
            ),
            "level": 3,
            "page_start": 28,
            "page_end": 28,
        }
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert [(section.get("section_code"), section.get("title")) for section in normalized] == [
        ("4.8.5", "储油柜的安装应符合下列规定："),
        ("1", "储油柜应按照产品技术文件要求进行检查、安装。"),
        ("2", "油位表动作应灵活，指示应与储油柜内的真实油位对应。"),
        ("3", "储油柜安装方向正确并进行位置复核。"),
        ("4.8.6", "所有导气管应清拭干净，其连接应密封严密。"),
        ("4.8.7", "升高座的安装应符合下列规定："),
        ("1", "安装前，应进行检查。"),
        ("4.8.8", "套管安装后，顶部结构应密封良好。"),
    ]
    assert normalized[3]["text"] == ""
    assert normalized[4]["text"] == "所有导气管应清拭干净，其连接应密封严密。"
    assert normalized[5]["text"] == "升高座的安装应符合下列规定："


def test_normalize_sections_for_processing_keeps_wrapped_embedded_clause_title_in_text() -> None:
    sections = [
        {
            "id": "s3",
            "section_code": "3",
            "title": "基本规定",
            "text": (
                "3.0.8 变压器、电抗器、互感器的瓷件质量，应符合现行国家标准《高压绝缘子瓷件技术条件》GB/T772、《标称电压高于\n"
                "1000\\\\mathrm{V}\n"
                "系统用户内和户外支柱绝缘子第1部分：瓷或玻璃绝缘子的试验》GB/T8287.1的有关规定。\n"
            ),
            "level": 1,
            "page_start": 14,
            "page_end": 14,
        }
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert [(section.get("section_code"), section.get("title")) for section in normalized] == [
        ("3", "基本规定"),
        ("3.0.8", "变压器、电抗器、互感器的瓷件质量，应符合现行国家标准《高压绝缘子瓷件技术条件》GB/T772、《标称电压高于"),
    ]
    assert normalized[1]["text"].startswith("变压器、电抗器、互感器的瓷件质量，应符合现行国家标准")
    assert "1000\\\\mathrm{V}" in normalized[1]["text"]


def test_normalize_sections_for_processing_splits_inline_sibling_clause_from_same_line_body() -> None:
    sections = [
        {
            "id": "s843",
            "section_code": "8.4.3",
            "title": "导线或架空地线，应使用合格的电力金具配套接续管及耐张线夹进行连接。",
            "text": (
                "对小截面导线采用螺栓式耐张线夹及钳压管连接时，其试件应分别制作。"
                "应。8.4.4采用液压连接，工期相近的不同工程，当采用同制造厂、同批量的导线、"
                "架空地线、接续管、耐张线夹及钢模完全没有变化时，可免做重复性试验。"
            ),
            "level": 3,
            "page_start": 40,
            "page_end": 40,
        }
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert [(section.get("section_code"), section.get("title")) for section in normalized] == [
        ("8.4.3", "导线或架空地线，应使用合格的电力金具配套接续管及耐张线夹进行连接。"),
        ("8.4.4", "采用液压连接，工期相近的不同工程，当采用同制造厂、同批量的导线、架空地线、接续管、耐张线夹及钢模完全没有变化时，可免做重复性试验。"),
    ]
    assert normalized[0]["text"] == "对小截面导线采用螺栓式耐张线夹及钳压管连接时，其试件应分别制作。应。"
    assert normalized[1]["text"] == "采用液压连接，工期相近的不同工程，当采用同制造厂、同批量的导线、架空地线、接续管、耐张线夹及钢模完全没有变化时，可免做重复性试验。"


def test_normalize_sections_for_processing_repairs_compact_voltage_embedded_sibling_clauses() -> None:
    sections = [
        {
            "id": "s353",
            "section_code": "3.5.3",
            "title": "金具的质量应符合国家现行标准的规定。",
            "text": (
                "3.5.435kV及以下架空电力线路金具还应符合现行行业标准的规定。\n"
                "3.5.510kV及以下架空绝缘导线金具，应符合现行行业标准的有关规定。"
            ),
            "level": 3,
            "page_start": 7,
            "page_end": 7,
        }
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert [(section.get("section_code"), section.get("title")) for section in normalized] == [
        ("3.5.3", "金具的质量应符合国家现行标准的规定。"),
        ("3.5.4", "35kV及以下架空电力线路金具还应符合现行行业标准的规定。"),
        ("3.5.5", "10kV及以下架空绝缘导线金具，应符合现行行业标准的有关规定。"),
    ]


def test_normalize_sections_for_processing_repairs_compact_first_embedded_clause_before_next_sibling() -> None:
    sections = [
        {
            "id": "s41",
            "section_code": "4.1",
            "title": "装卸、运输与就位",
            "text": (
                "4.1.131.5MV·A及以上变压器和40MVar及以上的电抗器的装卸及运输，应对运输路径及两端装卸条件作充分调查，制定施工安全技术措施，并应符合下列规定：\n"
                "1水路运输时，应做好下列工作：\n"
                "4.1.2变压器或电抗器的装卸应符合下列规定：\n"
                "1装卸站台、码头等地点的地面应坚实。\n"
            ),
            "level": 2,
            "page_start": 15,
            "page_end": 15,
        }
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert [(section.get("section_code"), section.get("title")) for section in normalized[:5]] == [
        ("4.1", "装卸、运输与就位"),
        ("4.1.1", "31.5MV·A及以上变压器和40MVar及以上的电抗器的装卸及运输，应对运输路径及两端装卸条件作充分调查，制定施工安全技术措施，并应符合下列规定："),
        ("1", "水路运输时，应做好下列工作："),
        ("4.1.2", "变压器或电抗器的装卸应符合下列规定："),
        ("1", "装卸站台、码头等地点的地面应坚实。"),
    ]
    assert normalized[1]["text"].startswith("31.5MV·A及以上变压器和40MVar及以上的电抗器的装卸及运输")


def test_normalize_sections_for_processing_repairs_prefixed_embedded_first_clause() -> None:
    sections = [
        {
            "id": "s66",
            "section_code": "6.6",
            "title": "岩石基础",
            "text": "16.6.1岩石基础施工时,应逐基逐腿与设计地质资料核对。",
            "level": 2,
            "page_start": 21,
            "page_end": 21,
        }
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert [(section.get("section_code"), section.get("title")) for section in normalized] == [
        ("6.6", "岩石基础"),
        ("6.6.1", "岩石基础施工时,应逐基逐腿与设计地质资料核对。"),
    ]


def test_normalize_sections_for_processing_rejects_front_matter_noise_as_embedded_clauses() -> None:
    sections = [
        {
            "id": "frontmatter",
            "title": "中华人民共和国住房和城乡建设部公告",
            "text": (
                "第409号\n"
                "住房城乡建设部关于发布国家标准《电气装置安装工程66kV及以下架空电力线路施工及验收规范》的公告\n"
                "中华人民共和国国家标准\n"
                "电气装置安装工程66kV及以下架空电力线路施工及验收规范\n"
                "GB50173-2014\n"
                "地址：北京市西城区木樨地北里甲11号国宏大厦C座3层\n"
                "5.5印张140千字\n"
                "定价：33.00元\n"
                "本规范第6.1.1(1)条(款)为强制性条文，必须严格执行。\n"
            ),
            "level": 1,
            "page_start": 2,
            "page_end": 2,
        }
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert [(section.get("section_code"), section.get("title")) for section in normalized] == [
        (None, "中华人民共和国住房和城乡建设部公告"),
    ]
    assert "66kV及以下架空电力线路施工及验收规范" in normalized[0]["text"]
    assert "GB50173-2014" in normalized[0]["text"]
    assert "33.00元" in normalized[0]["text"]
    assert "第6.1.1(1)条" in normalized[0]["text"]


def test_normalize_sections_for_processing_repairs_compact_voltage_after_multi_clause_host() -> None:
    sections = [
        {
            "id": "s102",
            "title": "10.2电气设备的试验",
            "text": (
                "10.2.7金属氧化物避雷器试验项目，应包括下列内容：\n"
                "1测量金属氧化物避雷器及基座绝缘电阻。\n"
                "10.2.866kV及以下架空电力线路杆塔上电气设备交接试验报告统一格式，应符合本规范附录B的规定。"
            ),
            "level": 1,
            "page_start": 34,
            "page_end": 34,
        }
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert ("10.2.8", "66kV及以下架空电力线路杆塔上电气设备交接试验报告统一格式，应符合本规范附录B的规定。") in [
        (section.get("section_code"), section.get("title"))
        for section in normalized
    ]
    assert all(section.get("section_code") != "10.2.86" for section in normalized)


def test_normalize_sections_for_processing_repairs_missing_chapter_prefix_for_embedded_clause() -> None:
    sections = [
        {
            "id": "s86",
            "title": "8.6附件安装",
            "text": (
                "6.3：10kV～66kV架空电力线路当采用并沟线夹连接引流线时，线夹数量不应少于2个。\n"
                "1.6.410kV及以下架空电力线路的引流线（或跨接线)之间、引流线与主干线之间的连接，应符合下列规定：\n"
            ),
            "level": 2,
            "page_start": 29,
            "page_end": 29,
        }
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert [(section.get("section_code"), section.get("title")) for section in normalized] == [
        (None, "8.6附件安装"),
        ("8.6.3", "10kV～66kV架空电力线路当采用并沟线夹连接引流线时，线夹数量不应少于2个。"),
        ("8.6.4", "10kV及以下架空电力线路的引流线（或跨接线)之间、引流线与主干线之间的连接，应符合下列规定："),
    ]


def test_normalize_sections_for_processing_recovers_missing_clause_before_following_sibling() -> None:
    sections = [
        {
            "id": "s87",
            "title": "8.7光缆架设",
            "text": (
                "8.7.2 光缆应直立装卸、运输及存放，不得平放。\n"
                "应直立装卸、运输及存放，不得平放 8.7v..\n"
                "）元现的架线施工应符合下列规定：T ，定：\n"
                "1 光缆架线施工应采用张力放线方法。\n"
                "2 选择放线区段长度应与线盘长度相适应，不宜两盘及以上连接后展放。\n"
                "8.7.4 除设计另有要求外，张力放线机主卷筒槽底直径不应小于光缆直径的70倍，且不得小于1m。\n"
            ),
            "level": 2,
            "page_start": 31,
            "page_end": 31,
        }
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert [(section.get("section_code"), section.get("title")) for section in normalized] == [
        (None, "8.7光缆架设"),
        ("8.7.2", "光缆应直立装卸、运输及存放，不得平放。"),
        ("8.7.3", "光缆架线施工应符合下列规定："),
        ("1", "光缆架线施工应采用张力放线方法。"),
        ("2", "选择放线区段长度应与线盘长度相适应，不宜两盘及以上连接后展放。"),
        ("8.7.4", "除设计另有要求外，张力放线机主卷筒槽底直径不应小于光缆直径的70倍，且不得小于1m。"),
    ]
    assert "不得平放" in normalized[1]["text"]


def test_normalize_sections_for_processing_does_not_promote_decimal_threshold_to_clause_no() -> None:
    sections = [
        {
            "id": "s81",
            "title": "8.1一般规定",
            "text": (
                "8.1.4 放线滑轮的使用应符合下列规定：\n"
                "3 张力展放导线用的滑轮，轮槽的磨阻系数不应大于1.01。\n"
                "4 对严重上扬、下压或垂直档距很大处的放线滑轮应进行验算，必要时应采用特制的结构。\n"
                "5 应采用滚动轴承滑轮，使用前应进行检查并确保转动灵活。\n"
                "8.1.5 架空绝缘导线的架设应选择在干燥的天气进行。\n"
            ),
            "level": 2,
            "page_start": 23,
            "page_end": 23,
        }
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)
    codes = [section.get("section_code") for section in normalized]

    assert "8.1.01" not in codes
    assert "8.1.5" in codes


def test_normalize_sections_for_processing_recovers_following_clauses_from_numbered_item_continuation_page() -> None:
    sections = [
        {
            "id": "s8616",
            "section_code": "8.6.16",
            "title": "绝缘子串、导线及架空地线上的各种金具上的螺栓、穿钉及弹簧销子，除有固定的穿向外，其余穿向应统一，并应符合下列规定：",
            "text": (
                "1 单、双悬垂串上的弹簧销子应一律由电源侧向受电侧穿入。\n"
                "2 耐张串上的弹簧销子、螺栓及穿钉应一律由上向下穿入。\n"
            ),
            "level": 3,
            "page_start": 29,
            "page_end": 30,
        },
        {
            "id": "s8616b",
            "section_code": "3",
            "title": "当穿入方向与当地运行单位要求不一致时，可按运行单位的要求安装，但应在开工前明确规定。",
            "text": (
                ".6.17 金具上所用的闭口销的直径应与孔径相配合，且弹力应适度。\n"
                "8.6.18 各种类型的铝质绞线，在与金具的线夹夹紧时，除并沟线夹及使用预绞丝护线条外，安装时应在铝股外缠绕铝包带，缠绕时应符合下列规定：\n"
                "1 铝包带应缠绕紧密，其缠绕方向应与外层铝股的绞制方向一致。\n"
                "2 所缠铝包带应露出线夹，但不应超过10mm，其端头应回缠绕于线夹内压住。\n"
                "8.6.19 安装预绞丝护线条时，每条的中心与线夹中心应重合，对导线包裹应紧固。\n"
                "8.6.20 防振锤及阻尼线与被连接的导线或架空地线应在同一铅垂面内，设计有特殊要求时应按设计要求安装。其安装距离偏差应为±30mm。\n"
            ),
            "level": 4,
            "page_start": 30,
            "page_end": 30,
        },
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert [(section.get("section_code"), section.get("title")) for section in normalized] == [
        ("8.6.16", "绝缘子串、导线及架空地线上的各种金具上的螺栓、穿钉及弹簧销子，除有固定的穿向外，其余穿向应统一，并应符合下列规定："),
        ("1", "单、双悬垂串上的弹簧销子应一律由电源侧向受电侧穿入。"),
        ("2", "耐张串上的弹簧销子、螺栓及穿钉应一律由上向下穿入。"),
        ("3", "当穿入方向与当地运行单位要求不一致时，可按运行单位的要求安装，但应在开工前明确规定。"),
        ("8.6.17", "金具上所用的闭口销的直径应与孔径相配合，且弹力应适度。"),
        ("8.6.18", "各种类型的铝质绞线，在与金具的线夹夹紧时，除并沟线夹及使用预绞丝护线条外，安装时应在铝股外缠绕铝包带，缠绕时应符合下列规定："),
        ("1", "铝包带应缠绕紧密，其缠绕方向应与外层铝股的绞制方向一致。"),
        ("2", "所缠铝包带应露出线夹，但不应超过10mm，其端头应回缠绕于线夹内压住。"),
        ("8.6.19", "安装预绞丝护线条时，每条的中心与线夹中心应重合，对导线包裹应紧固。"),
        ("8.6.20", "防振锤及阻尼线与被连接的导线或架空地线应在同一铅垂面内，设计有特殊要求时应按设计要求安装。其安装距离偏差应为±30mm。"),
    ]
    assert normalized[3]["text"] == ""
    assert normalized[5]["text"] == "各种类型的铝质绞线，在与金具的线夹夹紧时，除并沟线夹及使用预绞丝护线条外，安装时应在铝股外缠绕铝包带，缠绕时应符合下列规定："


def test_normalize_sections_for_processing_removes_polluted_inline_reference_and_synthesizes_missing_clause_before_table() -> None:
    sections = [
        {
            "id": "s62",
            "title": "6.2现场浇筑基础",
            "text": (
                "6.2.12现场浇筑混凝土的养护应符合下列规定：\n"
                "1浇筑后应在12h内开始浇水养护。\n"
                "2对普通硅酸盐和矿渣硅酸盐水泥拌制的混凝土浇水养护，不得少于7d。\n"
                "外露部分加遮盖物，应按规定期限继续浇水养护，养护时应使遮盖6.2.16的规定。物及基础周围的土始终保持湿润。\n"
                "4采用养护剂养护时，应在拆模并经表面检查合格后立即涂刷，涂刷后不得浇水。\n"
                "5日平均温度低于5℃时，不得浇水养护。\n"
                "6.2.13基础拆模时的混凝土强度，应保证其表面及棱角不损坏。\n"
                "6.2.15浇筑拉线基础的允许偏差应符合表6.2.15的规定。\n"
                "表6.2.16整基基础尺寸施工允许偏差\n"
                "<table><tr><td>项 目</td></tr></table>\n"
                "6.2.17现场浇筑混凝土强度应以试块强度为依据。试块强度应符合设计要求。\n"
            ),
            "level": 2,
            "page_start": 13,
            "page_end": 13,
        }
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)
    clause_rows = [
        (section.get("section_code"), section.get("title"), str(section.get("text") or ""))
        for section in normalized
    ]

    assert ("6.2.16", "整基基础尺寸施工允许偏差应符合表6.2.16的规定。", "整基基础尺寸施工允许偏差应符合表6.2.16的规定。\n<table><tr><td>项 目</td></tr></table>") in clause_rows
    assert all(not (code == "6.2.16" and title.startswith("的规定")) for code, title, _ in clause_rows)
    assert any("使遮盖物及基础周围的土始终保持湿润" in text for _, _, text in clause_rows)


def test_normalize_sections_for_processing_does_not_synthesize_duplicate_clause_before_table_when_clause_already_exists() -> None:
    sections = [
        {
            "id": "s675",
            "title": "6.7冬期施工",
            "text": (
                "6.7.5 冬期拌制混凝土时应采用加热水的方法，拌和水及骨料的最高温度不得超过表6.7.5的规定。\n"
                "表6.7.5拌和水及骨料的最高温度（℃）\n"
                "<table><tr><td>项 目</td></tr></table>\n"
                "6.7.6 水泥不应直接加热。\n"
            ),
            "level": 2,
            "page_start": 17,
            "page_end": 17,
        }
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert [section.get("section_code") for section in normalized].count("6.7.5") == 1


def test_normalize_sections_for_processing_repairs_grounding_chapter_out_of_order_duplicates() -> None:
    sections = [
        {
            "id": "s90",
            "title": "9接地工程",
            "text": (
                "9.0.1 接地体埋设深度和防腐应符合设计要求。\n"
                "受地质地形条件限制时可作局部修改，但不论修改与否均应在施工质量验收记录中绘制接地装置敷设简图并标示相对位置和尺寸。\n"
                "9.0.9 接施由阻值应符合设计要求。和尽士从重验收记录中绘制接地。\n"
                "9.0.9 架空线路杆塔的每一腿均应与接地体引下线连接。\n"
                "9.0.9 架空线路杆塔的每一腿均应与接地体引下线连接。环形。\n"
                "9.0.10 接地电阻值应符合设计要求。\n"
                "9.0.3 接地装置的连接应可靠。\n"
                "9.0.4 采用水平敷设的接地体，应符合下列规定。\n"
            ),
            "level": 1,
            "page_start": 32,
            "page_end": 32,
        }
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)
    codes = [section.get("section_code") for section in normalized]

    assert codes == [None, "9.0.1", "9.0.2", "9.0.3", "9.0.4", "9.0.9", "9.0.10"]
    assert codes.count("9.0.9") == 1


def test_ensure_standard_ocr_reuses_existing_sections(monkeypatch) -> None:
    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: [
        {"id": "s1", "title": "1 总则", "text": "正文", "level": 1},
    ])
    monkeypatch.setattr(
        norm_processor,
        "_parse_via_mineru",
        lambda conn, document_id: pytest.fail("should not call mineru when sections already exist"),
    )

    count = norm_processor.ensure_standard_ocr(
        object(),
        document_id="11111111-1111-1111-1111-111111111111",
    )

    assert count == 1


def test_process_standard_ai_uses_existing_ocr_sections(monkeypatch) -> None:
    standard_id = UUID("11111111-1111-1111-1111-111111111111")
    captured: dict[str, object] = {}

    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: [
        {"id": "s1", "title": "1 总则", "text": "正文", "level": 1, "page_start": 1, "page_end": 1},
    ])
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, document_id: [])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, document_id: {
        "id": UUID(document_id),
        "parser_name": "mineru",
        "parser_version": "v4",
        "raw_payload": {
            "pages": [
                {
                    "page_number": 1,
                    "markdown": "1 总则\n1.0.1 正文",
                }
            ],
            "tables": [],
            "full_markdown": "1 总则\n1.0.1 正文",
        },
    })
    monkeypatch.setattr(norm_processor, "_normalize_sections_for_processing", lambda sections: sections)
    monkeypatch.setattr(norm_processor, "rebalance_scopes", lambda scopes, **kwargs: scopes)
    def fake_process_scope(conn, scope):
        captured["scope_source_refs"] = scope.source_refs
        captured["scope_context"] = scope.context
        return [
            {
                "id": uuid4(),
                "standard_id": standard_id,
                "parent_id": None,
                "clause_no": "1.0.1",
                "clause_title": "总则条款",
                "clause_text": "正文",
                "summary": "摘要",
                "tags": [],
                "page_start": 1,
                "page_end": 1,
                "sort_order": 1,
                "clause_type": "normative",
                "commentary_clause_id": None,
            }
        ]

    monkeypatch.setattr(norm_processor, "_process_scope_with_retries", fake_process_scope)
    monkeypatch.setattr(norm_processor, "build_tree", lambda entries, current_standard_id: entries)
    monkeypatch.setattr(norm_processor, "link_commentary", lambda clauses: clauses)
    monkeypatch.setattr(norm_processor, "validate_tree", lambda clauses: [])
    monkeypatch.setattr(norm_processor._std_repo, "delete_clauses", lambda conn, current_standard_id: 0)
    monkeypatch.setattr(norm_processor._std_repo, "bulk_create_clauses", lambda conn, clauses: len(clauses))
    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: {
        "id": standard_id,
        "standard_code": "GB 1",
        "specialty": "结构",
    })
    monkeypatch.setattr(norm_processor, "_index_clauses", lambda standard, clauses: captured.setdefault("indexed", len(clauses)))
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)

    summary = norm_processor.process_standard_ai(
        object(),
        standard_id=standard_id,
        document_id="22222222-2222-2222-2222-222222222222",
    )

    assert summary["status"] == "completed"
    assert summary["total_clauses"] == 1
    assert summary["scopes_processed"] == 1
    assert summary["quality_report"]["overview"]["status"] == "pass"
    assert summary["quality_report"]["metrics"]["clause_count"] == 1
    assert captured["indexed"] == 1
    assert captured["scope_source_refs"] == ["document_section:s1"]
    assert captured["scope_context"] == {
        "document_id": "22222222-2222-2222-2222-222222222222",
        "source_refs": ["document_section:s1"],
        "node_types": ["page"],
    }


def test_process_standard_ai_processes_text_and_table_scopes(monkeypatch) -> None:
    standard_id = UUID("12121212-1212-1212-1212-121212121212")
    processed_scopes: list[str] = []

    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: [
        {"id": "s1", "title": "1 总则", "text": "正文", "level": 1, "page_start": 1, "page_end": 1},
    ])
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, document_id: [
        {
            "id": "t1",
            "table_title": "主要参数",
            "table_html": "<table><tr><td>额定电压</td><td>10kV</td></tr></table>",
            "page_start": 2,
            "page_end": 2,
        }
    ])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, document_id: None)
    monkeypatch.setattr(norm_processor, "_normalize_sections_for_processing", lambda sections: sections)
    monkeypatch.setattr(norm_processor, "_build_processing_scopes", lambda sections, tables, document=None, document_id=None: [
        ProcessingScope(
            scope_type="normative",
            chapter_label="1 总则",
            text="1.0.1 正文",
            page_start=1,
            page_end=1,
            section_ids=["s1"],
        ),
        ProcessingScope(
            scope_type="table",
            chapter_label="表格: 主要参数",
            text="<table><tr><td>额定电压</td><td>10kV</td></tr></table>",
            page_start=2,
            page_end=2,
            section_ids=["t1"],
        ),
    ])
    monkeypatch.setattr(norm_processor, "rebalance_scopes", lambda scopes, **kwargs: scopes)
    monkeypatch.setattr(norm_processor, "_process_scope_with_retries", lambda conn, scope: processed_scopes.append(scope.chapter_label) or [])
    monkeypatch.setattr(norm_processor, "build_tree", lambda entries, current_standard_id: [])
    monkeypatch.setattr(norm_processor, "link_commentary", lambda clauses: clauses)
    monkeypatch.setattr(norm_processor, "validate_tree", lambda clauses: [])
    monkeypatch.setattr(norm_processor._std_repo, "delete_clauses", lambda conn, current_standard_id: 0)
    monkeypatch.setattr(norm_processor._std_repo, "bulk_create_clauses", lambda conn, clauses: 0)
    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: {
        "id": standard_id,
        "standard_code": "GB 1",
        "specialty": "结构",
    })
    monkeypatch.setattr(norm_processor, "_index_clauses", lambda standard, clauses: None)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)

    summary = norm_processor.process_standard_ai(
        object(),
        standard_id=standard_id,
        document_id="34343434-3434-3434-3434-343434343434",
    )

    assert summary["status"] == "completed"
    assert processed_scopes == ["1 总则", "表格: 主要参数"]


def test_process_standard_ai_includes_structured_validation(monkeypatch) -> None:
    standard_id = UUID("56565656-5656-5656-5656-565656565656")

    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: [
        {"id": "s1", "title": "1 总则", "text": "正文", "level": 1, "page_start": 1, "page_end": 1},
    ])
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, document_id: [])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, document_id: None)
    monkeypatch.setattr(norm_processor, "_normalize_sections_for_processing", lambda sections: sections)
    monkeypatch.setattr(norm_processor, "_build_processing_scopes", lambda sections, tables, document=None, document_id=None: [
        ProcessingScope(
            scope_type="normative",
            chapter_label="1 总则",
            text="1.0.1 正文",
            page_start=1,
            page_end=1,
            section_ids=["s1"],
        )
    ])
    monkeypatch.setattr(norm_processor, "rebalance_scopes", lambda scopes, **kwargs: scopes)
    monkeypatch.setattr(norm_processor, "_process_scope_with_retries", lambda conn, scope: [])
    monkeypatch.setattr(norm_processor, "build_tree", lambda entries, current_standard_id: [])
    monkeypatch.setattr(norm_processor, "link_commentary", lambda clauses: clauses)
    monkeypatch.setattr(norm_processor, "validate_tree", lambda clauses: [])
    monkeypatch.setattr(
        norm_processor,
        "validate_clauses",
        lambda clauses, *, outline_clause_nos=None: SimpleNamespace(
            issues=[SimpleNamespace(code="page.missing_anchor", severity="warning", message="缺少页码锚点")],
            phrase_flags=[SimpleNamespace(phrase="必须", category="mandatory", clause_no="1.0.1")],
            to_dict=lambda: {
                "issue_count": 1,
                "phrase_flag_count": 1,
                "issues": [{"code": "page.missing_anchor", "severity": "warning", "message": "缺少页码锚点"}],
                "phrase_flags": [{"phrase": "必须", "category": "mandatory", "clause_no": "1.0.1"}],
            },
            warning_messages=lambda limit=None: ["缺少页码锚点"],
        ),
        raising=False,
    )
    monkeypatch.setattr(norm_processor._std_repo, "delete_clauses", lambda conn, current_standard_id: 0)
    monkeypatch.setattr(norm_processor._std_repo, "bulk_create_clauses", lambda conn, clauses: 0)
    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: {
        "id": standard_id,
        "standard_code": "GB 1",
        "specialty": "结构",
    })
    monkeypatch.setattr(norm_processor, "_index_clauses", lambda standard, clauses: None)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)

    summary = norm_processor.process_standard_ai(
        object(),
        standard_id=standard_id,
        document_id="67676767-6767-6767-6767-676767676767",
    )

    assert summary["status"] == "completed"
    assert summary["validation"]["issue_count"] == 1
    assert summary["validation"]["phrase_flag_count"] == 1
    assert summary["validation"]["phrase_flags"][0]["phrase"] == "必须"
    assert summary["validation"]["issues"][0]["code"] == "page.missing_anchor"


def test_process_standard_ai_passes_outline_codes_into_validation(monkeypatch) -> None:
    standard_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    captured: dict[str, object] = {}

    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: [
        {"id": "s1", "section_code": "4.8", "title": "附件安装", "text": "", "level": 2, "page_start": 11, "page_end": 12},
        {"id": "s2", "section_code": None, "title": "4.8.8", "text": "正文", "level": 3, "page_start": 12, "page_end": 12},
    ])
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, document_id: [])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, document_id: None)
    monkeypatch.setattr(norm_processor, "_normalize_sections_for_processing", lambda sections: sections)
    monkeypatch.setattr(norm_processor, "_build_processing_scopes", lambda sections, tables, document=None, document_id=None: [
        ProcessingScope(
            scope_type="normative",
            chapter_label="4.8 附件安装",
            text="4.8.8 正文",
            page_start=11,
            page_end=12,
            section_ids=["s1", "s2"],
        )
    ])
    monkeypatch.setattr(norm_processor, "rebalance_scopes", lambda scopes, **kwargs: scopes)
    monkeypatch.setattr(norm_processor, "_process_scope_with_retries", lambda conn, scope: [])
    monkeypatch.setattr(norm_processor, "build_tree", lambda entries, current_standard_id: [
        {
            "id": uuid4(),
            "standard_id": current_standard_id,
            "parent_id": None,
            "clause_no": "4.8.8",
            "node_type": "clause",
            "node_key": "4.8.8",
            "node_label": None,
            "clause_title": None,
            "clause_text": "正文",
            "summary": None,
            "tags": [],
            "page_start": 12,
            "page_end": 12,
            "clause_type": "normative",
            "source_type": "text",
            "source_label": "4.8 附件安装",
            "source_ref": "document_section:s2",
            "source_refs": ["document_section:s2"],
        }
    ])
    monkeypatch.setattr(norm_processor, "link_commentary", lambda clauses: clauses)
    monkeypatch.setattr(norm_processor, "validate_tree", lambda clauses: [])

    def fake_validate_clauses(clauses, *, outline_clause_nos=None):
        captured.setdefault("outline_clause_nos", outline_clause_nos)
        return SimpleNamespace(
            issues=[],
            phrase_flags=[],
            to_dict=lambda: {"issue_count": 0, "phrase_flag_count": 0, "issues": [], "phrase_flags": []},
            warning_messages=lambda limit=None: [],
        )

    monkeypatch.setattr(norm_processor, "validate_clauses", fake_validate_clauses)
    monkeypatch.setattr(norm_processor._std_repo, "delete_clauses", lambda conn, current_standard_id: 0)
    monkeypatch.setattr(norm_processor._std_repo, "bulk_create_clauses", lambda conn, clauses: len(clauses))
    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: {
        "id": standard_id,
        "standard_code": "GB 1",
        "specialty": "结构",
    })
    monkeypatch.setattr(norm_processor, "_index_clauses", lambda standard, clauses: None)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)

    summary = norm_processor.process_standard_ai(
        object(),
        standard_id=standard_id,
        document_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    )

    assert summary["status"] == "completed"
    assert captured["outline_clause_nos"] == {"4.8"}


def test_process_standard_ai_uses_pre_normalization_outline_codes_for_validation(monkeypatch) -> None:
    standard_id = UUID("acacacac-acac-acac-acac-acacacacacac")
    captured: dict[str, object] = {}

    raw_sections = [
        {"id": "toc-1", "section_code": "4.2", "title": "交接与保管 (8)", "text": "", "level": 2, "page_start": 7, "page_end": 7},
        {"id": "body-1", "section_code": "4.2.1", "title": "设备到达现场后，应及时按下列规定进行外观检查：", "text": "", "level": 3, "page_start": 15, "page_end": 15},
    ]

    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: raw_sections)
    monkeypatch.setattr(norm_processor, "_normalize_sections_for_processing", lambda sections: sections[1:])
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, document_id: [])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, document_id: None)
    monkeypatch.setattr(norm_processor, "_build_processing_scopes", lambda sections, tables, document=None, document_id=None: [
        ProcessingScope(
            scope_type="normative",
            chapter_label="4.2 交接与保管",
            text="4.2.1 设备到达现场后，应及时按下列规定进行外观检查：",
            page_start=15,
            page_end=15,
            section_ids=["body-1"],
        )
    ])
    monkeypatch.setattr(norm_processor, "rebalance_scopes", lambda scopes, **kwargs: scopes)
    monkeypatch.setattr(norm_processor, "_process_scope_with_retries", lambda conn, scope: [])
    monkeypatch.setattr(norm_processor, "build_tree", lambda entries, current_standard_id: [
        {
            "id": uuid4(),
            "standard_id": current_standard_id,
            "parent_id": None,
            "clause_no": "4.2.1",
            "node_type": "clause",
            "node_key": "4.2.1",
            "node_label": None,
            "clause_title": None,
            "clause_text": "正文",
            "summary": None,
            "tags": [],
            "page_start": 15,
            "page_end": 15,
            "clause_type": "normative",
            "source_type": "text",
            "source_label": "4.2 交接与保管",
        }
    ])
    monkeypatch.setattr(norm_processor, "link_commentary", lambda clauses: clauses)
    monkeypatch.setattr(norm_processor, "validate_tree", lambda clauses: [])

    def fake_validate_clauses(clauses, *, outline_clause_nos=None):
        captured.setdefault("outline_clause_nos", outline_clause_nos)
        return SimpleNamespace(
            issues=[],
            phrase_flags=[],
            to_dict=lambda: {"issue_count": 0, "phrase_flag_count": 0, "issues": [], "phrase_flags": []},
            warning_messages=lambda limit=None: [],
        )

    monkeypatch.setattr(norm_processor, "validate_clauses", fake_validate_clauses)
    monkeypatch.setattr(norm_processor._std_repo, "delete_clauses", lambda conn, current_standard_id: 0)
    monkeypatch.setattr(norm_processor._std_repo, "bulk_create_clauses", lambda conn, clauses: len(clauses))
    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: {
        "id": standard_id,
        "standard_code": "GB 2",
        "specialty": "电气",
    })
    monkeypatch.setattr(norm_processor, "_index_clauses", lambda standard, clauses: None)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)

    summary = norm_processor.process_standard_ai(
        object(),
        standard_id=standard_id,
        document_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    )

    assert summary["status"] == "completed"
    assert captured["outline_clause_nos"] == {"4.2", "4.2.1"}

def test_apply_scope_defaults_clamps_out_of_scope_page_numbers() -> None:
    scope = ProcessingScope(
        scope_type="normative",
        chapter_label="2 术语",
        text="2.0.1 电力变压器",
        page_start=11,
        page_end=12,
        section_ids=["s2"],
        source_refs=["document_section:s2"],
    )
    entry = {
        "clause_no": "2.0.9",
        "clause_text": "密封试验 sealing test",
        "page_start": 2,
        "page_end": 2,
    }

    norm_processor._apply_scope_defaults(entry, scope)

    assert entry["page_start"] == 11
    assert entry["page_end"] == 12


def test_process_standard_ai_prefers_rebuilt_outline_codes_from_page_text(monkeypatch) -> None:
    standard_id = UUID("cdcdcdcd-cdcd-cdcd-cdcd-cdcdcdcdcdcd")
    captured: dict[str, object] = {}

    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: [
        {"id": "toc", "section_code": None, "title": "本体及附件安装 (17)", "text": "", "level": 2, "page_start": 7, "page_end": 7},
        {"id": "body", "section_code": None, "title": "4.8.1", "text": "正文", "level": 3, "page_start": 26, "page_end": 26},
    ])
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, document_id: [])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, document_id: {
        "id": UUID(document_id),
        "parser_name": "mineru",
        "parser_version": "v4",
        "raw_payload": {
            "pages": [
                {"page_number": 7, "markdown": "目次\n4.8 本体及附件安装 ………………………………………… (17)"},
                {"page_number": 26, "markdown": "4.8 本体及附件安装\n4.8.1 220kV及以上变压器本体露空安装附件应符合下列规定："},
            ],
            "tables": [],
            "full_markdown": "4.8 本体及附件安装\n4.8.1 220kV及以上变压器本体露空安装附件应符合下列规定：",
        },
    })
    monkeypatch.setattr(norm_processor, "_normalize_sections_for_processing", lambda sections: sections)
    monkeypatch.setattr(norm_processor, "_build_processing_scopes", lambda sections, tables, document=None, document_id=None: [
        ProcessingScope(
            scope_type="normative",
            chapter_label="4 电力变压器、油浸电抗器",
            text="4.8.1 正文",
            page_start=26,
            page_end=26,
            section_ids=["body"],
        )
    ])
    monkeypatch.setattr(norm_processor, "rebalance_scopes", lambda scopes, **kwargs: scopes)
    monkeypatch.setattr(norm_processor, "_process_scope_with_retries", lambda conn, scope: [])
    monkeypatch.setattr(norm_processor, "build_tree", lambda entries, current_standard_id: [])
    monkeypatch.setattr(norm_processor, "link_commentary", lambda clauses: clauses)
    monkeypatch.setattr(norm_processor, "validate_tree", lambda clauses: [])

    def fake_validate_clauses(clauses, *, outline_clause_nos=None):
        captured["outline_clause_nos"] = outline_clause_nos
        return SimpleNamespace(
            issues=[],
            phrase_flags=[],
            to_dict=lambda: {"issue_count": 0, "phrase_flag_count": 0, "issues": [], "phrase_flags": []},
            warning_messages=lambda limit=None: [],
        )

    monkeypatch.setattr(norm_processor, "validate_clauses", fake_validate_clauses)
    monkeypatch.setattr(norm_processor._std_repo, "delete_clauses", lambda conn, current_standard_id: 0)
    monkeypatch.setattr(norm_processor._std_repo, "bulk_create_clauses", lambda conn, clauses: 0)
    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: {
        "id": standard_id,
        "standard_code": "GB 4",
        "specialty": "电气",
    })


def test_process_standard_ai_uses_block_scopes_for_single_standard_experiment(monkeypatch) -> None:
    standard_id = UUID("ff2ddb6c-ba8e-4e42-862f-e75d5824437a")
    captured: dict[str, object] = {}

    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: [
        {"id": "s1", "section_code": "4.1.2", "title": "变压器装卸", "text": "正文", "level": 1, "page_start": 6, "page_end": 6},
    ])
    monkeypatch.setattr(norm_processor, "_normalize_sections_for_processing", lambda sections: sections)
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, document_id: [])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, document_id: None)
    monkeypatch.setattr(norm_processor, "_build_processing_scopes", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("legacy structural scope builder should not be used for the single-standard experiment")
    ))
    monkeypatch.setattr(norm_processor, "build_single_standard_blocks", lambda sections, tables: [
        BlockSegment(
            segment_type="normative_clause_block",
            chapter_label="4.1.2 变压器装卸",
            text="变压器装卸应符合规定。",
            clause_no="4.1.2",
            page_start=6,
            page_end=6,
            section_ids=["s1"],
            source_refs=["document_section:s1"],
            confidence="high",
        ),
        BlockSegment(
            segment_type="non_clause_block",
            chapter_label="本规范用词说明",
            text="1 为便于在执行本规范条文时区别对待。",
            page_start=39,
            page_end=39,
            section_ids=["s2"],
            source_refs=["document_section:s2"],
            confidence="low",
        ),
        BlockSegment(
            segment_type="commentary_block",
            chapter_label="4.1.7 条文说明",
            text="为确保运输安全此条规定为强制性条文。",
            clause_no="4.1.7",
            page_start=46,
            page_end=46,
            section_ids=["s3"],
            source_refs=["document_section:s3"],
            confidence="high",
        ),
    ])

    def fake_process_scope_with_retries(conn, scope):
        captured.setdefault("scope_types", []).append(scope.scope_type)
        if scope.scope_type == "normative":
            return [{
                "clause_no": "4.1.2",
                "clause_text": "变压器装卸应符合规定。",
                "clause_type": "normative",
                "source_type": "text",
                "source_ref": "document_section:s1",
                "page_start": 6,
                "page_end": 6,
            }]
        return [{
            "clause_no": "4.1.7",
            "clause_text": "为确保运输安全此条规定为强制性条文。",
            "clause_type": "commentary",
            "source_type": "text",
            "source_ref": "document_section:s3",
            "page_start": 46,
            "page_end": 46,
        }]

    monkeypatch.setattr(norm_processor, "_process_scope_with_retries", fake_process_scope_with_retries)
    monkeypatch.setattr(norm_processor, "rebalance_scopes", lambda scopes, **kwargs: (_ for _ in ()).throw(
        AssertionError("single-standard block path should not rebalance chapter scopes")
    ))
    monkeypatch.setattr(norm_processor, "build_tree", lambda entries, current_standard_id: captured.setdefault("entries", list(entries)) or [])
    monkeypatch.setattr(norm_processor, "link_commentary", lambda clauses: clauses)
    monkeypatch.setattr(norm_processor, "validate_tree", lambda clauses: [])
    monkeypatch.setattr(norm_processor, "validate_clauses", lambda clauses, *, outline_clause_nos=None: SimpleNamespace(
        issues=[],
        warning_messages=lambda limit=10: [],
        to_dict=lambda: {"issue_count": 0},
    ))
    monkeypatch.setattr(norm_processor, "build_repair_tasks", lambda clauses, issues: [])
    monkeypatch.setattr(norm_processor._std_repo, "delete_clauses", lambda conn, current_standard_id: 0)
    monkeypatch.setattr(norm_processor._std_repo, "bulk_create_clauses", lambda conn, current_clauses: 0)
    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: None)
    monkeypatch.setattr(norm_processor, "_index_clauses", lambda standard, clauses: None)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)

    summary = norm_processor.process_standard_ai(
        object(),
        standard_id=standard_id,
        document_id="dddddddd-dddd-dddd-dddd-dddddddddddd",
    )

    assert summary["status"] == "completed"
    assert captured["outline_clause_nos"] == {"4.8"}


def test_process_standard_ai_uses_block_scopes_for_single_standard_experiment(monkeypatch) -> None:
    standard_id = UUID("ff2ddb6c-ba8e-4e42-862f-e75d5824437a")
    captured: dict[str, object] = {}

    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: [
        {"id": "s1", "section_code": "4.1.2", "title": "变压器装卸", "text": "正文", "level": 1, "page_start": 6, "page_end": 6},
    ])
    monkeypatch.setattr(norm_processor, "_normalize_sections_for_processing", lambda sections: sections)
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, document_id: [])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, document_id: None)
    monkeypatch.setattr(norm_processor, "_build_processing_scopes", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("legacy structural scope builder should not be used for the single-standard experiment")
    ))
    monkeypatch.setattr(norm_processor, "build_single_standard_blocks", lambda sections, tables: [
        BlockSegment(
            segment_type="normative_clause_block",
            chapter_label="4.1.2 变压器装卸",
            text="变压器装卸应符合规定。",
            clause_no="4.1.2",
            page_start=6,
            page_end=6,
            section_ids=["s1"],
            source_refs=["document_section:s1"],
            confidence="high",
        ),
        BlockSegment(
            segment_type="non_clause_block",
            chapter_label="本规范用词说明",
            text="1 为便于在执行本规范条文时区别对待。",
            page_start=39,
            page_end=39,
            section_ids=["s2"],
            source_refs=["document_section:s2"],
            confidence="low",
        ),
        BlockSegment(
            segment_type="commentary_block",
            chapter_label="4.1.7 条文说明",
            text="为确保运输安全此条规定为强制性条文。",
            clause_no="4.1.7",
            page_start=46,
            page_end=46,
            section_ids=["s3"],
            source_refs=["document_section:s3"],
            confidence="high",
        ),
    ])

    def fake_process_scope_with_retries(conn, scope):
        captured.setdefault("scope_types", []).append(scope.scope_type)
        if scope.scope_type == "normative":
            return [{
                "clause_no": "4.1.2",
                "clause_text": "变压器装卸应符合规定。",
                "clause_type": "normative",
                "source_type": "text",
                "source_ref": "document_section:s1",
                "page_start": 6,
                "page_end": 6,
            }]
        return [{
            "clause_no": "4.1.7",
            "clause_text": "为确保运输安全此条规定为强制性条文。",
            "clause_type": "commentary",
            "source_type": "text",
            "source_ref": "document_section:s3",
            "page_start": 46,
            "page_end": 46,
        }]

    monkeypatch.setattr(norm_processor, "_process_scope_with_retries", fake_process_scope_with_retries)
    monkeypatch.setattr(norm_processor, "rebalance_scopes", lambda scopes, **kwargs: (_ for _ in ()).throw(
        AssertionError("single-standard block path should not rebalance chapter scopes")
    ))
    monkeypatch.setattr(norm_processor, "build_tree", lambda entries, current_standard_id: captured.setdefault("entries", list(entries)) or [])
    monkeypatch.setattr(norm_processor, "link_commentary", lambda clauses: clauses)
    monkeypatch.setattr(norm_processor, "validate_tree", lambda clauses: [])
    monkeypatch.setattr(norm_processor, "validate_clauses", lambda clauses, *, outline_clause_nos=None: SimpleNamespace(
        issues=[],
        warning_messages=lambda limit=10: [],
        to_dict=lambda: {"issue_count": 0},
    ))
    monkeypatch.setattr(norm_processor, "build_repair_tasks", lambda clauses, issues: [])
    monkeypatch.setattr(norm_processor._std_repo, "delete_clauses", lambda conn, current_standard_id: 0)
    monkeypatch.setattr(norm_processor._std_repo, "bulk_create_clauses", lambda conn, current_clauses: 0)
    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: None)
    monkeypatch.setattr(norm_processor, "_index_clauses", lambda standard, clauses: None)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)

    summary = norm_processor.process_standard_ai(
        object(),
        standard_id=standard_id,
        document_id="e3003181-042a-44da-ad67-44615d7d25f2",
        force_persist_failed_quality=True,
    )

    assert summary["status"] == "completed"
    assert captured.get("scope_types", []) == []
    assert [entry["clause_no"] for entry in captured["entries"]] == ["4.1.2", "4.1.7"]


def test_process_standard_ai_uses_block_scopes_for_gb50148_even_with_new_standard_id(monkeypatch) -> None:
    standard_id = UUID("ad9e7b99-6c94-48cf-8bd3-269314090b6e")
    captured: dict[str, object] = {}

    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: [
        {"id": "s1", "section_code": "4.1.2", "title": "变压器装卸", "text": "正文", "level": 1, "page_start": 6, "page_end": 6},
    ])
    monkeypatch.setattr(norm_processor, "_normalize_sections_for_processing", lambda sections: sections)
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, document_id: [])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, document_id: None)
    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: {
        "id": standard_id,
        "standard_code": "GB 50148-2010",
        "standard_name": "电气装置安装工程 电力变压器、油浸电抗器、互感器施工及验收规范",
    })
    monkeypatch.setattr(norm_processor, "_build_processing_scopes", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("legacy structural scope builder should not be used for GB50148 reruns")
    ))
    monkeypatch.setattr(norm_processor, "build_single_standard_blocks", lambda sections, tables: [
        BlockSegment(
            segment_type="normative_clause_block",
            chapter_label="4.1.2 变压器装卸",
            text="变压器装卸应符合规定。",
            clause_no="4.1.2",
            page_start=6,
            page_end=6,
            section_ids=["s1"],
            source_refs=["document_section:s1"],
            confidence="high",
        ),
    ])
    monkeypatch.setattr(norm_processor, "_process_scope_with_retries", lambda *args, **kwargs: [])
    monkeypatch.setattr(norm_processor, "rebalance_scopes", lambda scopes, **kwargs: scopes)
    monkeypatch.setattr(norm_processor, "build_tree", lambda entries, current_standard_id: captured.setdefault("entries", list(entries)) or [])
    monkeypatch.setattr(norm_processor, "link_commentary", lambda clauses: clauses)
    monkeypatch.setattr(norm_processor, "validate_tree", lambda clauses: [])
    monkeypatch.setattr(norm_processor, "validate_clauses", lambda clauses, *, outline_clause_nos=None: SimpleNamespace(
        issues=[],
        warning_messages=lambda limit=10: [],
        to_dict=lambda: {"issue_count": 0},
    ))
    monkeypatch.setattr(norm_processor, "build_repair_tasks", lambda clauses, issues: [])
    monkeypatch.setattr(norm_processor, "_index_clauses", lambda standard, clauses: None)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)
    monkeypatch.setattr(norm_processor._std_repo, "delete_clauses", lambda conn, current_standard_id: 0)
    monkeypatch.setattr(norm_processor._std_repo, "bulk_create_clauses", lambda conn, current_clauses: 0)

    summary = norm_processor.process_standard_ai(
        object(),
        standard_id=standard_id,
        document_id="9491c69c-9ee7-4a5b-902e-16c3b2c82e9a",
    )

    assert summary["status"] == "completed"
    assert [entry["clause_no"] for entry in captured["entries"]] == ["4.1.2"]


def test_process_standard_ai_keeps_numbered_chapter_block_for_ai_in_single_standard_path(monkeypatch) -> None:
    standard_id = UUID("ad9e7b99-6c94-48cf-8bd3-269314090b6e")
    captured: dict[str, object] = {"processed_scopes": []}

    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: [
        {"id": "s1", "section_code": "1", "title": "总则", "text": "为保证施工安装质量，制定本规范。", "level": 1, "page_start": 10, "page_end": 10},
    ])
    monkeypatch.setattr(norm_processor, "_normalize_sections_for_processing", lambda sections: sections)
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, document_id: [])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, document_id: None)
    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: {
        "id": standard_id,
        "standard_code": "GB 50148-2010",
        "standard_name": "电气装置安装工程 电力变压器、油浸电抗器、互感器施工及验收规范",
    })
    monkeypatch.setattr(norm_processor, "build_single_standard_blocks", lambda sections, tables: [
        BlockSegment(
            segment_type="normative_clause_block",
            chapter_label="1 总则",
            text="为保证施工安装质量，制定本规范。",
            clause_no="1",
            page_start=10,
            page_end=10,
            section_ids=["s1"],
            source_refs=["document_section:s1"],
            confidence="medium",
        ),
    ])

    def fake_process_scope_with_retries(conn, scope):
        captured["processed_scopes"].append(scope.chapter_label)
        return [{
            "clause_no": "1.0.1",
            "clause_text": "为保证施工安装质量，制定本规范。",
            "clause_type": "normative",
            "source_type": "text",
            "source_ref": "document_section:s1",
            "page_start": 10,
            "page_end": 10,
        }]

    monkeypatch.setattr(norm_processor, "_process_scope_with_retries", fake_process_scope_with_retries)
    monkeypatch.setattr(norm_processor, "rebalance_scopes", lambda scopes, **kwargs: scopes)
    monkeypatch.setattr(norm_processor, "build_tree", lambda entries, current_standard_id: captured.setdefault("entries", list(entries)) or [])
    monkeypatch.setattr(norm_processor, "link_commentary", lambda clauses: clauses)
    monkeypatch.setattr(norm_processor, "validate_tree", lambda clauses: [])
    monkeypatch.setattr(norm_processor, "validate_clauses", lambda clauses, *, outline_clause_nos=None: SimpleNamespace(
        issues=[],
        warning_messages=lambda limit=10: [],
        to_dict=lambda: {"issue_count": 0},
    ))
    monkeypatch.setattr(norm_processor, "build_repair_tasks", lambda clauses, issues: [])
    monkeypatch.setattr(norm_processor._std_repo, "delete_clauses", lambda conn, current_standard_id: 0)
    monkeypatch.setattr(norm_processor._std_repo, "bulk_create_clauses", lambda conn, current_clauses: 0)
    monkeypatch.setattr(norm_processor, "_index_clauses", lambda standard, clauses: None)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)

    summary = norm_processor.process_standard_ai(
        object(),
        standard_id=standard_id,
        document_id="9491c69c-9ee7-4a5b-902e-16c3b2c82e9a",
    )

    assert summary["status"] == "completed"
    assert captured["processed_scopes"] == ["1 总则"]
    assert [entry["clause_no"] for entry in captured["entries"]] == ["1.0.1"]


def test_process_standard_ai_falls_back_to_deterministic_inline_clause_split_when_ai_returns_empty(monkeypatch) -> None:
    standard_id = UUID("f4a6c7c8-3a6d-4d86-8cd7-2cbfcaa0d801")
    captured: dict[str, object] = {"processed_scopes": []}

    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: [
        {"id": "s1", "section_code": "1", "title": "总则", "text": "", "level": 1, "page_start": 11, "page_end": 11},
    ])
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, document_id: [])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, document_id: None)
    monkeypatch.setattr(norm_processor, "_normalize_sections_for_processing", lambda sections: sections)
    monkeypatch.setattr(norm_processor, "_build_processing_scopes", lambda sections, tables, document=None, document_id=None: [
        ProcessingScope(
            scope_type="normative",
            chapter_label="1总则",
            text=(
                "1总则\n"
                "1.0.1为适应电气装置安装工程电气设备交接试验的需要，制定本标准。\n"
                "1.0.2本标准适用于750kV及以下交流电压等级新安装的电气设备交接试验。"
            ),
            page_start=11,
            page_end=11,
            section_ids=["s1"],
            source_refs=["document.raw_payload.pages[10]"],
        )
    ])
    monkeypatch.setattr(norm_processor, "rebalance_scopes", lambda scopes, **kwargs: scopes)

    def fake_process_scope_with_retries(conn, scope):
        captured["processed_scopes"].append(scope.chapter_label)
        return []

    monkeypatch.setattr(norm_processor, "_process_scope_with_retries", fake_process_scope_with_retries)
    monkeypatch.setattr(norm_processor, "build_tree", lambda entries, current_standard_id: captured.setdefault("entries", list(entries)) or [])
    monkeypatch.setattr(norm_processor, "link_commentary", lambda clauses: clauses)
    monkeypatch.setattr(norm_processor, "validate_tree", lambda clauses: [])
    monkeypatch.setattr(norm_processor, "validate_clauses", lambda clauses, *, outline_clause_nos=None: SimpleNamespace(
        issues=[],
        phrase_flags=[],
        warning_messages=lambda limit=10: [],
        to_dict=lambda: {"issue_count": 0, "phrase_flag_count": 0, "issues": [], "phrase_flags": []},
    ))
    monkeypatch.setattr(norm_processor, "build_repair_tasks", lambda clauses, issues: [])
    monkeypatch.setattr(norm_processor._std_repo, "delete_clauses", lambda conn, current_standard_id: 0)
    monkeypatch.setattr(norm_processor._std_repo, "bulk_create_clauses", lambda conn, current_clauses: 0)
    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: {
        "id": standard_id,
        "standard_code": "GB 1",
        "specialty": "结构",
    })
    monkeypatch.setattr(norm_processor, "_index_clauses", lambda standard, clauses: None)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)

    summary = norm_processor.process_standard_ai(
        object(),
        standard_id=standard_id,
        document_id="9491c69c-9ee7-4a5b-902e-16c3b2c82e9b",
    )

    assert summary["status"] == "completed"
    assert captured["processed_scopes"] == ["1总则"]
    assert [entry["clause_no"] for entry in captured["entries"]] == ["1", "1.0.1", "1.0.2"]


def test_parse_numbered_item_heading_rejects_decimal_clause_and_unit_prefixes() -> None:
    assert norm_processor._parse_numbered_item_heading("1测量绕组的绝缘电阻；") == ("1", "测量绕组的绝缘电阻；")
    assert norm_processor._parse_numbered_item_heading("5.0.1直流电机的试验项目，应包括下列内容：") is None
    assert norm_processor._parse_numbered_item_heading("1000V及以上的电动机应测量吸收比。") is None
    assert norm_processor._parse_numbered_item_heading("16000kW以上同步发电机应进行试验。") is None


def test_normalize_sections_for_processing_keeps_chapter_one_heading_without_space_after_number() -> None:
    sections = [
        {
            "id": "toc",
            "section_code": None,
            "title": "目 次",
            "text": "1总则 （1）\n2术语 （2）",
        },
        {
            "id": "s1",
            "section_code": None,
            "title": "1总 则",
            "text": (
                "1.0.1为适应电气装置安装工程电气设备交接试验的需要，制定本标准。\n"
                "1.0.2本标准适用于750kV及以下交流电压等级新安装的电气设备交接试验。"
            ),
            "page_start": 11,
            "page_end": 11,
        },
        {
            "id": "s2",
            "section_code": None,
            "title": "2术 语",
            "text": "2.0.1自动灭磁装置 automatic field suppression equipment",
            "page_start": 12,
            "page_end": 12,
        },
    ]

    normalized = norm_processor._normalize_sections_for_processing(sections)

    assert normalized[0]["title"] == "1总 则"
    assert normalized[1]["section_code"] == "1.0.1"
    assert normalized[2]["section_code"] == "1.0.2"
    assert normalized[3]["title"] == "2术 语"
    assert normalized[4]["section_code"] == "2.0.1"


def test_build_processing_scopes_keeps_leading_pages_when_first_section_lacks_page_anchor(monkeypatch) -> None:
    captured: dict[str, object] = {}
    fake_pages = [
        SimpleNamespace(page_number=11, normalized_text="1总则"),
        SimpleNamespace(page_number=12, normalized_text="2术语"),
    ]
    fake_asset = SimpleNamespace(
        pages=fake_pages,
        tables=[],
        full_markdown="1总则\n2术语",
    )

    monkeypatch.setattr(norm_processor, "build_document_asset", lambda **kwargs: fake_asset)
    monkeypatch.setattr(
        norm_processor,
        "build_structured_processing_scopes",
        lambda asset: captured.setdefault("pages", [page.page_number for page in asset.pages]) or [],
    )

    norm_processor._build_processing_scopes(
        [
            {"title": "1总 则", "text": "1.0.1...", "page_start": None, "page_end": None},
            {"title": "2术 语", "text": "2.0.1...", "page_start": 12, "page_end": 12},
        ],
        [],
        document={"id": "59745fdb-6819-46c2-a8c1-1f92b9eb5d41"},
        document_id="59745fdb-6819-46c2-a8c1-1f92b9eb5d41",
    )

    assert captured["pages"] == [11, 12]


def test_process_standard_ai_supplements_missing_inline_scope_entries_when_ai_response_is_incomplete(monkeypatch) -> None:
    standard_id = UUID("74f8d621-7b54-47a0-8d6d-13518132f001")
    captured: dict[str, object] = {"processed_scopes": []}

    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: [
        {"id": "s1", "section_code": "1", "title": "总则", "text": "", "level": 1, "page_start": 11, "page_end": 11},
    ])
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, document_id: [])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, document_id: None)
    monkeypatch.setattr(norm_processor, "_normalize_sections_for_processing", lambda sections: sections)
    monkeypatch.setattr(norm_processor, "_build_processing_scopes", lambda sections, tables, document=None, document_id=None: [
        ProcessingScope(
            scope_type="normative",
            chapter_label="1总则",
            text=(
                "1总则\n"
                "1.0.1为适应电气装置安装工程电气设备交接试验的需要，制定本标准。\n"
                "1.0.2本标准适用于750kV及以下交流电压等级新安装的电气设备交接试验。"
            ),
            page_start=11,
            page_end=11,
            section_ids=["s1"],
            source_refs=["document.raw_payload.pages[10]"],
        )
    ])
    monkeypatch.setattr(norm_processor, "rebalance_scopes", lambda scopes, **kwargs: scopes)

    def fake_process_scope_with_retries(conn, scope):
        captured["processed_scopes"].append(scope.chapter_label)
        return [{
            "clause_no": "1.0.2",
            "clause_text": "本标准适用于750kV及以下交流电压等级新安装的电气设备交接试验。",
            "clause_type": "normative",
            "source_type": "text",
            "source_label": "1总则",
        }]

    monkeypatch.setattr(norm_processor, "_process_scope_with_retries", fake_process_scope_with_retries)
    monkeypatch.setattr(norm_processor, "build_tree", lambda entries, current_standard_id: captured.setdefault("entries", list(entries)) or [])
    monkeypatch.setattr(norm_processor, "link_commentary", lambda clauses: clauses)
    monkeypatch.setattr(norm_processor, "validate_tree", lambda clauses: [])
    monkeypatch.setattr(norm_processor, "validate_clauses", lambda clauses, *, outline_clause_nos=None: SimpleNamespace(
        issues=[],
        phrase_flags=[],
        warning_messages=lambda limit=10: [],
        to_dict=lambda: {"issue_count": 0, "phrase_flag_count": 0, "issues": [], "phrase_flags": []},
    ))
    monkeypatch.setattr(norm_processor, "build_repair_tasks", lambda clauses, issues: [])
    monkeypatch.setattr(norm_processor._std_repo, "delete_clauses", lambda conn, current_standard_id: 0)
    monkeypatch.setattr(norm_processor._std_repo, "bulk_create_clauses", lambda conn, current_clauses: 0)
    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: {
        "id": standard_id,
        "standard_code": "GB 1",
        "specialty": "结构",
    })
    monkeypatch.setattr(norm_processor, "_index_clauses", lambda standard, clauses: None)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)

    summary = norm_processor.process_standard_ai(
        object(),
        standard_id=standard_id,
        document_id="9491c69c-9ee7-4a5b-902e-16c3b2c82e9c",
    )

    assert summary["status"] == "completed"
    assert captured["processed_scopes"] == ["1总则"]
    assert [entry["clause_no"] for entry in captured["entries"]] == ["1", "1.0.1", "1.0.2"]


def test_deterministic_inline_clause_entries_from_scope_adds_appendix_host_from_scope_label() -> None:
    scope = ProcessingScope(
        scope_type="normative",
        chapter_label="附录G电力电缆线路交叉互联系统 (1/2)",
        text=(
            "G.0.1交叉互联系统对地绝缘的直流耐压试验，应符合下列规定：\n"
            "G.0.2非线性电阻型护层过电压保护器试验，应符合下列规定："
        ),
        page_start=200,
        page_end=201,
        source_refs=["document.raw_payload.pages[199]"],
    )

    entries = norm_processor._deterministic_inline_clause_entries_from_scope(scope)

    assert [entry["clause_no"] for entry in entries] == ["G", "G.0.1", "G.0.2"]
    assert entries[0]["clause_title"] == "电力电缆线路交叉互联系统"
    assert entries[0]["source_label"] == "附录G电力电缆线路交叉互联系统"


def test_deterministic_inline_clause_entries_from_scope_filters_numeric_fragments_by_known_clause_nos() -> None:
    scope = ProcessingScope(
        scope_type="normative",
        chapter_label="17电力电缆线路",
        text=(
            "17电力电缆线路\n"
            "17.0.3绝缘电阻测量，应符合下列规定：\n"
            "1耐压试验前后,绝缘电阻测量应无明显变化；\n"
            "2橡塑电缆外护套、内衬层的绝缘电阻不应低于\n"
            "0.5MΩ/km;\n"
            "17.0.4直流耐压试验及泄漏电流测量，应符合下列规定："
        ),
        page_start=180,
        page_end=181,
        source_refs=["document.raw_payload.pages[179]"],
    )

    entries = norm_processor._deterministic_inline_clause_entries_from_scope(
        scope,
        allowed_clause_nos={"17", "17.0.3", "17.0.4"},
    )

    assert [entry["clause_no"] for entry in entries] == ["17", "17.0.3", "17.0.4"]


def test_deterministic_inline_clause_entries_from_scope_rejects_scope_mismatched_clause_numbers() -> None:
    scope = ProcessingScope(
        scope_type="normative",
        chapter_label="附录G电力电缆线路交叉互联系统 (6/16)",
        text=(
            "8.0.13外施耐压试验用来验证线端和中性点端子及它们所连接\n"
            "的绕组对地及对其他绕组的外施耐受强度。\n"
            "8.0.14长时感应电压试验(ACLD)用以模拟瞬变过电压和连续运行电压作用的可靠性。"
        ),
        page_start=210,
        page_end=211,
        source_refs=["document.raw_payload.pages[209]"],
    )

    entries = norm_processor._deterministic_inline_clause_entries_from_scope(
        scope,
        allowed_clause_nos={"8.0.13", "8.0.14"},
    )

    assert entries == []


def test_process_standard_ai_filters_scope_mismatched_ai_clause_entries(monkeypatch) -> None:
    standard_id = uuid4()
    captured: dict[str, object] = {}

    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: [
        {
            "id": "s1",
            "section_code": "10",
            "title": "10互感器",
            "text": "10.0.1互感器的试验项目，应包括下列内容：",
            "page_start": 20,
            "page_end": 20,
        },
        {
            "id": "s2",
            "section_code": "10.0.1",
            "title": "10.0.1互感器的试验项目，应包括下列内容：",
            "text": "10.0.1互感器的试验项目，应包括下列内容：",
            "page_start": 20,
            "page_end": 20,
        },
    ])
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, document_id: [])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, document_id: {"id": document_id})
    monkeypatch.setattr(norm_processor, "build_document_asset", lambda **kwargs: SimpleNamespace(pages=[], tables=[], full_markdown=""))
    monkeypatch.setattr(norm_processor, "collect_outline_clause_nos_from_pages", lambda pages: set())
    monkeypatch.setattr(norm_processor, "_collect_outline_clause_nos", lambda sections: {"10", "10.0.1"})
    monkeypatch.setattr(norm_processor, "_normalize_sections_for_processing", lambda sections: sections)
    monkeypatch.setattr(norm_processor, "_build_processing_scopes", lambda sections, tables, document=None, document_id=None: [
        ProcessingScope(
            scope_type="normative",
            chapter_label="10互感器",
            text="10.0.1互感器的试验项目，应包括下列内容：",
            page_start=20,
            page_end=20,
            source_refs=["document.raw_payload.pages[19]"],
        )
    ])
    monkeypatch.setattr(norm_processor, "rebalance_scopes", lambda scopes, **kwargs: scopes)
    monkeypatch.setattr(norm_processor, "_process_scope_with_retries", lambda conn, scope: [
        {
            "clause_no": "10.0.1",
            "clause_text": "互感器的试验项目，应包括下列内容：",
            "clause_type": "normative",
            "source_label": scope.chapter_label,
        },
        {
            "clause_no": "8.0.13",
            "clause_text": "条第4款的规定；",
            "clause_type": "normative",
            "source_label": scope.chapter_label,
        },
    ])
    monkeypatch.setattr(norm_processor, "build_tree", lambda entries, current_standard_id: captured.setdefault("entries", list(entries)) or [])
    monkeypatch.setattr(norm_processor, "_prune_empty_outline_hosts", lambda clauses, *, outline_clause_nos=None: clauses)
    monkeypatch.setattr(norm_processor, "_backfill_clause_page_anchors_from_asset", lambda clauses, document_asset: clauses)
    monkeypatch.setattr(norm_processor, "link_commentary", lambda clauses: clauses)
    monkeypatch.setattr(norm_processor, "validate_tree", lambda clauses: [])
    monkeypatch.setattr(norm_processor, "validate_clauses", lambda clauses, *, outline_clause_nos=None: SimpleNamespace(
        issues=[],
        phrase_flags=[],
        warning_messages=lambda limit=10: [],
        to_dict=lambda: {"issue_count": 0, "phrase_flag_count": 0, "issues": [], "phrase_flags": []},
    ))
    monkeypatch.setattr(norm_processor, "build_repair_tasks", lambda clauses, issues: [])
    monkeypatch.setattr(norm_processor, "run_repair_tasks", lambda conn=None, document_id=None, tasks=None: [])
    monkeypatch.setattr(norm_processor, "merge_repair_patches", lambda clauses, patches: clauses)
    monkeypatch.setattr(norm_processor._std_repo, "delete_clauses", lambda conn, current_standard_id: 0)
    monkeypatch.setattr(norm_processor._std_repo, "bulk_create_clauses", lambda conn, current_clauses: 0)
    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: {
        "id": standard_id,
        "standard_code": "GB 1",
        "specialty": "电气",
    })
    monkeypatch.setattr(norm_processor, "_index_clauses", lambda standard, clauses: None)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)

    summary = norm_processor.process_standard_ai(
        object(),
        standard_id=standard_id,
        document_id="9491c69c-9ee7-4a5b-902e-16c3b2c82e9d",
    )

    assert summary["status"] == "completed"
    assert [entry["clause_no"] for entry in captured["entries"]] == ["10.0.1"]


def test_prune_empty_outline_hosts_drops_empty_outline_clause_and_reparents_children() -> None:
    chapter_id = UUID("10000000-0000-0000-0000-000000000001")
    outline_host_id = UUID("10000000-0000-0000-0000-000000000002")
    child_id = UUID("10000000-0000-0000-0000-000000000003")

    clauses = [
        {
            "id": chapter_id,
            "clause_no": "4",
            "node_type": "clause",
            "clause_type": "normative",
            "clause_text": "电力变压器、油浸电抗器",
            "parent_id": None,
            "source_type": "text",
        },
        {
            "id": outline_host_id,
            "clause_no": "4.4",
            "node_type": "clause",
            "clause_type": "normative",
            "clause_text": "",
            "parent_id": chapter_id,
            "source_type": "text",
        },
        {
            "id": child_id,
            "clause_no": "4.4.1",
            "node_type": "clause",
            "clause_type": "normative",
            "clause_text": "采用注油排氮时，应符合下列规定：",
            "parent_id": outline_host_id,
            "source_type": "text",
        },
    ]

    result = norm_processor._prune_empty_outline_hosts(clauses, outline_clause_nos={"4", "4.4", "4.4.1"})

    assert [clause["clause_no"] for clause in result] == ["4", "4.4.1"]
    assert result[1]["parent_id"] == chapter_id


def test_prune_empty_outline_hosts_drops_heading_only_outline_clause_and_reparents_children() -> None:
    chapter_id = UUID("20000000-0000-0000-0000-000000000001")
    outline_host_id = UUID("20000000-0000-0000-0000-000000000002")
    child_id = UUID("20000000-0000-0000-0000-000000000003")

    clauses = [
        {
            "id": chapter_id,
            "clause_no": "4",
            "node_type": "clause",
            "clause_type": "normative",
            "clause_text": "电力变压器、油浸电抗器",
            "parent_id": None,
            "source_type": "text",
        },
        {
            "id": outline_host_id,
            "clause_no": "4.4",
            "node_type": "clause",
            "clause_type": "normative",
            "clause_text": "4.4 排氮",
            "parent_id": chapter_id,
            "source_type": "text",
        },
        {
            "id": child_id,
            "clause_no": "4.4.1",
            "node_type": "clause",
            "clause_type": "normative",
            "clause_text": "采用注油排氮时，应符合下列规定：",
            "parent_id": outline_host_id,
            "source_type": "text",
        },
    ]

    result = norm_processor._prune_empty_outline_hosts(clauses, outline_clause_nos={"4", "4.4", "4.4.1"})

    assert [clause["clause_no"] for clause in result] == ["4", "4.4.1"]
    assert result[1]["parent_id"] == chapter_id


def test_prune_empty_outline_hosts_drops_title_only_outline_clause_without_number_prefix() -> None:
    chapter_id = UUID("30000000-0000-0000-0000-000000000001")
    outline_host_id = UUID("30000000-0000-0000-0000-000000000002")
    child_id = UUID("30000000-0000-0000-0000-000000000003")

    clauses = [
        {
            "id": chapter_id,
            "clause_no": "5",
            "node_type": "clause",
            "clause_type": "normative",
            "clause_text": "互感器",
            "parent_id": None,
            "source_type": "text",
        },
        {
            "id": outline_host_id,
            "clause_no": "5.4",
            "node_type": "clause",
            "clause_type": "normative",
            "clause_text": "工程交接验收",
            "parent_id": chapter_id,
            "source_type": "text",
        },
        {
            "id": child_id,
            "clause_no": "5.4.1",
            "node_type": "clause",
            "clause_type": "normative",
            "clause_text": "在验收时，应进行下列检查：",
            "parent_id": outline_host_id,
            "source_type": "text",
        },
    ]

    result = norm_processor._prune_empty_outline_hosts(clauses, outline_clause_nos={"5", "5.4", "5.4.1"})

    assert [clause["clause_no"] for clause in result] == ["5", "5.4.1"]
    assert result[1]["parent_id"] == chapter_id


def test_process_standard_ai_seeds_sentence_like_section_titles_for_single_standard_experiment(monkeypatch) -> None:
    standard_id = UUID("ff2ddb6c-ba8e-4e42-862f-e75d5824437a")
    captured: dict[str, object] = {}

    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: [
        {
            "id": "s-heading",
            "section_code": "5.1",
            "title": "一般规定",
            "text": "",
            "level": 1,
            "page_start": 26,
            "page_end": 26,
        },
        {
            "id": "s1",
            "section_code": "4.1.2",
            "title": "变压器或电抗器的装卸应符合下列规定：",
            "text": "",
            "level": 1,
            "page_start": 15,
            "page_end": 15,
        },
    ])
    monkeypatch.setattr(norm_processor, "_normalize_sections_for_processing", lambda sections: sections)
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, document_id: [])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, document_id: None)
    monkeypatch.setattr(norm_processor, "_build_processing_scopes", lambda *args, **kwargs: [
        ProcessingScope(
            scope_type="normative",
            chapter_label="4.1 装卸、运输与就位",
            text="4.1.2 变压器或电抗器的装卸应符合下列规定：",
            page_start=15,
            page_end=15,
            section_ids=["s1"],
            source_refs=["document_section:s1"],
        ),
    ])
    monkeypatch.setattr(norm_processor, "rebalance_scopes", lambda scopes, **kwargs: scopes)
    monkeypatch.setattr(norm_processor, "_process_scope_with_retries", lambda conn, scope: [])
    monkeypatch.setattr(
        norm_processor,
        "build_tree",
        lambda entries, current_standard_id: captured.setdefault("entries", list(entries)) or [],
    )
    monkeypatch.setattr(norm_processor, "link_commentary", lambda clauses: clauses)
    monkeypatch.setattr(norm_processor, "validate_tree", lambda clauses: [])
    monkeypatch.setattr(norm_processor, "validate_clauses", lambda clauses, *, outline_clause_nos=None: SimpleNamespace(
        issues=[],
        warning_messages=lambda limit=10: [],
        to_dict=lambda: {"issue_count": 0},
    ))
    monkeypatch.setattr(norm_processor, "build_repair_tasks", lambda clauses, issues: [])
    monkeypatch.setattr(norm_processor._std_repo, "delete_clauses", lambda conn, current_standard_id: 0)
    monkeypatch.setattr(norm_processor._std_repo, "bulk_create_clauses", lambda conn, current_clauses: len(current_clauses))
    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: None)
    monkeypatch.setattr(norm_processor, "_index_clauses", lambda standard, clauses: None)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)

    summary = norm_processor.process_standard_ai(
        object(),
        standard_id=standard_id,
        document_id="e3003181-042a-44da-ad67-44615d7d25f2",
        force_persist_failed_quality=True,
    )

    assert summary["status"] == "completed"
    assert captured["entries"] == [
        {
            "clause_no": "4.1.2",
            "clause_title": None,
            "clause_text": "变压器或电抗器的装卸应符合下列规定：",
            "summary": None,
            "tags": [],
            "page_start": 15,
            "page_end": 15,
            "clause_type": "normative",
            "source_type": "text",
            "source_ref": "document_section:s1",
            "source_refs": ["document_section:s1"],
            "source_label": "4.1.2 变压器或电抗器的装卸应符合下列规定：",
        }
    ]


def test_process_standard_ai_uses_deterministic_entries_for_high_confidence_blocks(monkeypatch) -> None:
    standard_id = UUID("ff2ddb6c-ba8e-4e42-862f-e75d5824437a")
    captured: dict[str, object] = {}

    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: [
        {"id": "s1", "section_code": "4.1.2", "title": "变压器装卸", "text": "变压器装卸应符合规定。", "level": 1, "page_start": 6, "page_end": 6},
    ])
    monkeypatch.setattr(norm_processor, "_normalize_sections_for_processing", lambda sections: sections)
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, document_id: [
        {"id": "t1", "table_title": "表 4.2.4 变压器内油样性能", "table_html": "<table><tr><td>含水量</td><td>≤10μL/L</td></tr></table>", "page_start": 18, "page_end": 18},
    ])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, document_id: None)
    monkeypatch.setattr(norm_processor, "build_single_standard_blocks", lambda sections, tables: [
        BlockSegment(
            segment_type="normative_clause_block",
            chapter_label="4.1.2 变压器装卸",
            text="变压器装卸应符合规定。",
            clause_no="4.1.2",
            page_start=6,
            page_end=6,
            section_ids=["s1"],
            source_refs=["document_section:s1"],
            confidence="high",
        ),
        BlockSegment(
            segment_type="heading_only_block",
            chapter_label="4.2.4 变压器内油样性能",
            text="",
            clause_no="4.2.4",
            page_start=18,
            page_end=18,
            section_ids=["s2"],
            source_refs=["document_section:s2"],
            confidence="low",
        ),
        BlockSegment(
            segment_type="table_requirement_block",
            chapter_label="表格: 表 4.2.4 变压器内油样性能",
            text="表 4.2.4 变压器内油样性能\n含水量 ≤10μL/L",
            table_title="表 4.2.4 变压器内油样性能",
            page_start=18,
            page_end=18,
            source_refs=["table:t1"],
            confidence="medium",
        ),
    ])

    def fake_process_scope_with_retries(conn, scope):
        captured.setdefault("ai_scope_types", []).append(scope.scope_type)
        if scope.scope_type == "normative":
            return [{
                "clause_no": "4.1.2",
                "clause_title": None,
                "clause_text": "变压器装卸应符合规定。",
                "clause_type": "normative",
                "source_type": "text",
                "source_ref": "document_section:s1",
                "page_start": 6,
                "page_end": 6,
            }]
        return [{
            "clause_no": None,
            "clause_title": "表 4.2.4 变压器内油样性能",
            "clause_text": "含水量应≤10μL/L",
            "clause_type": "normative",
            "source_type": "table",
            "source_ref": "table:t1",
            "page_start": 18,
            "page_end": 18,
        }]

    monkeypatch.setattr(norm_processor, "_process_scope_with_retries", fake_process_scope_with_retries)
    monkeypatch.setattr(norm_processor, "rebalance_scopes", lambda scopes, **kwargs: scopes)
    monkeypatch.setattr(norm_processor, "build_tree", lambda entries, current_standard_id: captured.setdefault("entries", list(entries)) or [])
    monkeypatch.setattr(norm_processor, "link_commentary", lambda clauses: clauses)
    monkeypatch.setattr(norm_processor, "validate_tree", lambda clauses: [])
    monkeypatch.setattr(norm_processor, "validate_clauses", lambda clauses, *, outline_clause_nos=None: SimpleNamespace(
        issues=[],
        warning_messages=lambda limit=10: [],
        to_dict=lambda: {"issue_count": 0},
    ))
    monkeypatch.setattr(norm_processor, "build_repair_tasks", lambda clauses, issues: [])
    monkeypatch.setattr(norm_processor._std_repo, "delete_clauses", lambda conn, current_standard_id: 0)
    monkeypatch.setattr(norm_processor._std_repo, "bulk_create_clauses", lambda conn, current_clauses: 0)
    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: None)
    monkeypatch.setattr(norm_processor, "_index_clauses", lambda standard, clauses: None)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)

    summary = norm_processor.process_standard_ai(
        object(),
        standard_id=standard_id,
        document_id="e3003181-042a-44da-ad67-44615d7d25f2",
        force_persist_failed_quality=True,
    )

    assert summary["status"] == "completed"
    assert captured["ai_scope_types"] == ["table"]
    assert captured["entries"][0]["clause_no"] == "4.1.2"
    assert captured["entries"][0]["source_ref"] == "document_section:s1"
    assert captured["entries"][1]["source_ref"] == "table:t1"


def test_process_standard_ai_uses_deterministic_entries_for_table_intro_clause_block(monkeypatch) -> None:
    standard_id = UUID("ff2ddb6c-ba8e-4e42-862f-e75d5824437a")
    captured: dict[str, object] = {}

    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: [
        {
            "id": "s424",
            "section_code": "4.2.4",
            "title": "设备在保管期间，应经常检查。充油保管时应每隔30天对变压器内抽取油样进行试验，其变压器内油样性能应符合表4.2.4的规定：",
            "text": "",
            "level": 3,
            "page_start": 18,
            "page_end": 18,
        },
    ])
    monkeypatch.setattr(norm_processor, "_normalize_sections_for_processing", lambda sections: sections)
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, document_id: [])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, document_id: None)
    monkeypatch.setattr(norm_processor, "build_single_standard_blocks", lambda sections, tables: [
        BlockSegment(
            segment_type="normative_clause_block",
            chapter_label="4.2.4 设备在保管期间，应经常检查。充油保管时应每隔30天对变压器内抽取油样进行试验，其变压器内油样性能应符合表4.2.4的规定：",
            text="设备在保管期间，应经常检查。充油保管时应每隔30天对变压器内抽取油样进行试验，其变压器内油样性能应符合表4.2.4的规定：",
            clause_no="4.2.4",
            page_start=18,
            page_end=18,
            section_ids=["s424"],
            source_refs=["document_section:s424"],
            confidence="high",
        ),
    ])
    monkeypatch.setattr(norm_processor, "_process_scope_with_retries", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("table-intro normative clause should not call AI")
    ))
    monkeypatch.setattr(norm_processor, "build_tree", lambda entries, current_standard_id: captured.setdefault("entries", list(entries)) or [])
    monkeypatch.setattr(norm_processor, "link_commentary", lambda clauses: clauses)
    monkeypatch.setattr(norm_processor, "validate_tree", lambda clauses: [])
    monkeypatch.setattr(norm_processor, "validate_clauses", lambda clauses, *, outline_clause_nos=None: SimpleNamespace(
        issues=[],
        warning_messages=lambda limit=10: [],
        to_dict=lambda: {"issue_count": 0},
    ))
    monkeypatch.setattr(norm_processor, "build_repair_tasks", lambda clauses, issues: [])
    monkeypatch.setattr(norm_processor._std_repo, "delete_clauses", lambda conn, current_standard_id: 0)
    monkeypatch.setattr(norm_processor._std_repo, "bulk_create_clauses", lambda conn, current_clauses: 0)
    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: None)
    monkeypatch.setattr(norm_processor, "_index_clauses", lambda standard, clauses: None)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)

    summary = norm_processor.process_standard_ai(
        object(),
        standard_id=standard_id,
        document_id="e3003181-042a-44da-ad67-44615d7d25f2",
    )

    assert summary["status"] == "completed"
    assert captured["entries"] == [
        {
            "clause_no": "4.2.4",
            "clause_title": None,
            "clause_text": "设备在保管期间，应经常检查。充油保管时应每隔30天对变压器内抽取油样进行试验，其变压器内油样性能应符合表4.2.4的规定：",
            "summary": None,
            "tags": [],
            "page_start": 18,
            "page_end": 18,
            "clause_type": "normative",
            "source_type": "text",
            "source_ref": "document_section:s424",
            "source_refs": ["document_section:s424"],
            "source_label": "4.2.4 设备在保管期间，应经常检查。充油保管时应每隔30天对变压器内抽取油样进行试验，其变压器内油样性能应符合表4.2.4的规定：",
        },
        {
            "clause_no": "4.2.4",
            "clause_title": None,
            "clause_text": "设备在保管期间，应经常检查。充油保管时应每隔30天对变压器内抽取油样进行试验，其变压器内油样性能应符合表4.2.4的规定：",
            "summary": None,
            "tags": [],
            "page_start": 18,
            "page_end": 18,
            "clause_type": "normative",
            "source_type": "text",
            "source_ref": "document_section:s424",
            "source_refs": ["document_section:s424"],
            "source_label": "4.2.4 设备在保管期间，应经常检查。充油保管时应每隔30天对变压器内抽取油样进行试验，其变压器内油样性能应符合表4.2.4的规定：",
        },
    ]


def test_process_standard_ai_single_standard_block_path_uses_reconciled_asset_tables(monkeypatch) -> None:
    standard_id = UUID("ad9e7b99-6c94-48cf-8bd3-269314090b6e")
    captured: dict[str, object] = {}

    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: [
        {"id": "s1", "section_code": "4.2.4", "title": "变压器内油样性能", "text": "正文", "level": 1, "page_start": 18, "page_end": 18},
    ])
    monkeypatch.setattr(norm_processor, "_normalize_sections_for_processing", lambda sections: sections)
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, document_id: [
        {"id": "t1", "page_start": None, "page_end": None, "table_title": None, "table_html": "<table><tr><td>含水量</td><td>≤10μL/L</td></tr></table>", "raw_json": {}},
    ])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, document_id: None)
    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: {
        "id": standard_id,
        "standard_code": "GB 50148-2010",
        "standard_name": "电气装置安装工程 电力变压器、油浸电抗器、互感器施工及验收规范",
    })
    monkeypatch.setattr(norm_processor, "build_document_asset", lambda **kwargs: SimpleNamespace(
        pages=[],
        tables=[
            SimpleNamespace(
                source_ref="table:t1",
                page_start=18,
                page_end=18,
                table_title="表 4.2.4 变压器内油样性能",
                table_html="<table><tr><td>含水量</td><td>≤10μL/L</td></tr></table>",
                raw_json={"page": 18, "title": "表 4.2.4 变压器内油样性能"},
            )
        ],
    ))

    def fake_build_single_standard_blocks(sections, tables):
        captured["tables"] = tables
        return [
            BlockSegment(
                segment_type="table_requirement_block",
                chapter_label="表格: 表 4.2.4 变压器内油样性能",
                text="表 4.2.4 变压器内油样性能\n含水量 ≤10μL/L",
                table_title=tables[0]["table_title"],
                table_html=tables[0]["table_html"],
                page_start=tables[0]["page_start"],
                page_end=tables[0]["page_end"],
                source_refs=["table:t1"],
                confidence="medium",
            ),
        ]

    monkeypatch.setattr(norm_processor, "build_single_standard_blocks", fake_build_single_standard_blocks)
    monkeypatch.setattr(norm_processor, "_process_scope_with_retries", lambda *args, **kwargs: [
        {
            "clause_no": None,
            "clause_title": "表 4.2.4 变压器内油样性能",
            "clause_text": "含水量：电压等级750kV，标准值≤10μL/L。",
            "clause_type": "normative",
            "source_type": "table",
            "source_ref": "table:t1",
            "page_start": 18,
            "page_end": 18,
        }
    ])
    monkeypatch.setattr(norm_processor, "rebalance_scopes", lambda scopes, **kwargs: scopes)
    monkeypatch.setattr(norm_processor, "build_tree", lambda entries, current_standard_id: captured.setdefault("entries", list(entries)) or [])
    monkeypatch.setattr(norm_processor, "link_commentary", lambda clauses: clauses)
    monkeypatch.setattr(norm_processor, "validate_tree", lambda clauses: [])
    monkeypatch.setattr(norm_processor, "validate_clauses", lambda clauses, *, outline_clause_nos=None: SimpleNamespace(
        issues=[],
        warning_messages=lambda limit=10: [],
        to_dict=lambda: {"issue_count": 0},
    ))
    monkeypatch.setattr(norm_processor, "build_repair_tasks", lambda clauses, issues: [])
    monkeypatch.setattr(norm_processor._std_repo, "delete_clauses", lambda conn, current_standard_id: 0)
    monkeypatch.setattr(norm_processor._std_repo, "bulk_create_clauses", lambda conn, current_clauses: 0)
    monkeypatch.setattr(norm_processor, "_index_clauses", lambda standard, clauses: None)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)

    summary = norm_processor.process_standard_ai(
        object(),
        standard_id=standard_id,
        document_id="9491c69c-9ee7-4a5b-902e-16c3b2c82e9a",
    )

    assert summary["status"] == "completed"
    assert captured["tables"] == [
        {
            "id": "t1",
            "page_start": 18,
            "page_end": 18,
            "table_title": "表 4.2.4 变压器内油样性能",
            "table_html": "<table><tr><td>含水量</td><td>≤10μL/L</td></tr></table>",
            "raw_json": {"page": 18, "title": "表 4.2.4 变压器内油样性能"},
        }
    ]
    assert captured["entries"][0]["clause_title"] == "表 4.2.4 变压器内油样性能"
    assert captured["entries"][0]["page_start"] == 18
    assert captured["entries"][0]["page_end"] == 18


def test_process_standard_ai_single_standard_merges_numbered_list_items_into_clause_scope(monkeypatch) -> None:
    standard_id = UUID("ff2ddb6c-ba8e-4e42-862f-e75d5824437a")
    captured: dict[str, object] = {"scope_texts": [], "scope_refs": []}

    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: [
        {"id": "s1", "section_code": "4.1.2", "title": "变压器或电抗器的装卸应符合下列规定：", "text": "", "level": 1, "page_start": 15, "page_end": 15},
        {"id": "s2", "section_code": "1", "title": "装卸站台、码头等地点的地面应坚实。", "text": "", "level": 2, "page_start": 15, "page_end": 15},
        {"id": "s3", "section_code": "2", "title": "装卸时应设专人观测车辆、平台的升降或船只的沉浮情", "text": "况，防止超过允许范围的倾斜。", "level": 2, "page_start": 15, "page_end": 15},
    ])
    monkeypatch.setattr(norm_processor, "_normalize_sections_for_processing", lambda sections: sections)
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, document_id: [])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, document_id: None)

    def fake_process_scope_with_retries(conn, scope):
        captured["scope_texts"].append(scope.text)
        captured["scope_refs"].append(list(scope.source_refs))
        return []

    monkeypatch.setattr(norm_processor, "_process_scope_with_retries", fake_process_scope_with_retries)
    monkeypatch.setattr(norm_processor, "rebalance_scopes", lambda scopes, **kwargs: scopes)
    monkeypatch.setattr(norm_processor, "build_tree", lambda entries, current_standard_id: [])
    monkeypatch.setattr(norm_processor, "link_commentary", lambda clauses: clauses)
    monkeypatch.setattr(norm_processor, "validate_tree", lambda clauses: [])
    monkeypatch.setattr(norm_processor, "validate_clauses", lambda clauses, *, outline_clause_nos=None: SimpleNamespace(
        issues=[],
        warning_messages=lambda limit=10: [],
        to_dict=lambda: {"issue_count": 0},
    ))
    monkeypatch.setattr(norm_processor, "build_repair_tasks", lambda clauses, issues: [])
    monkeypatch.setattr(norm_processor._std_repo, "delete_clauses", lambda conn, current_standard_id: 0)
    monkeypatch.setattr(norm_processor._std_repo, "bulk_create_clauses", lambda conn, current_clauses: 0)
    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: None)
    monkeypatch.setattr(norm_processor, "_index_clauses", lambda standard, clauses: None)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)

    summary = norm_processor.process_standard_ai(
        object(),
        standard_id=standard_id,
        document_id="e3003181-042a-44da-ad67-44615d7d25f2",
    )

    assert summary["status"] == "completed"
    assert len(captured["scope_texts"]) == 1
    assert "1 装卸站台、码头等地点的地面应坚实。" in captured["scope_texts"][0]
    assert "2 装卸时应设专人观测车辆、平台的升降或船只的沉浮情况，防止超过允许范围的倾斜。" in captured["scope_texts"][0]
    assert captured["scope_refs"][0] == [
        "document_section:s1",
        "document_section:s2",
        "document_section:s3",
    ]


def test_build_single_standard_blocks_merges_numbered_items_into_clause_when_host_title_invites_items() -> None:
    blocks = build_single_standard_blocks([
        {"id": "s485", "section_code": "4.8.5", "title": "储油柜的安装应符合下列规定：", "text": "得", "page_start": 28, "page_end": 28},
        {"id": "s485#1", "section_code": "1", "title": "储油柜应按照产品技术文件要求进行检查、安装。", "text": "", "page_start": 28, "page_end": 28},
        {"id": "s485#2", "section_code": "2", "title": "油位表动作应灵活，指示应与储油柜内的真实油位对应。", "text": "", "page_start": 28, "page_end": 28},
        {"id": "s485#3", "section_code": "3", "title": "储油柜安装方向正确并进行位置复核。", "text": "", "page_start": 28, "page_end": 28},
        {"id": "s486", "section_code": "4.8.6", "title": "所有导气管应清拭干净，其连接应密封严密。", "text": "", "page_start": 28, "page_end": 28},
    ], [])

    assert [(block.segment_type, block.clause_no) for block in blocks] == [
        ("normative_clause_block", "4.8.5"),
        ("normative_clause_block", "4.8.6"),
    ]
    assert blocks[0].text == (
        "得\n"
        "1 储油柜应按照产品技术文件要求进行检查、安装。\n"
        "2 油位表动作应灵活，指示应与储油柜内的真实油位对应。\n"
        "3 储油柜安装方向正确并进行位置复核。"
    )
    assert blocks[0].source_refs == [
        "document_section:s485",
        "document_section:s485#1",
        "document_section:s485#2",
        "document_section:s485#3",
    ]


def test_build_single_standard_blocks_absorbs_numbered_items_under_non_clause_host() -> None:
    blocks = build_single_standard_blocks([
        {
            "id": "s-terms",
            "section_code": None,
            "title": "本规范用词说明",
            "text": "1 为便于在执行本规范条文时区别对待，对要求严格程度不同的用词说明如下：",
            "page_start": 39,
            "page_end": 39,
        },
        {
            "id": "s-terms-1",
            "section_code": "1",
            "title": "表示很严格，非这样做不可的：",
            "text": "正面词采用“必须”，反面词采用“严禁”。",
            "page_start": 39,
            "page_end": 39,
        },
        {
            "id": "s-terms-2",
            "section_code": "2",
            "title": "表示严格，在正常情况下均应这样做的：",
            "text": "正面词采用“应”，反面词采用“不应”或“不得”。",
            "page_start": 39,
            "page_end": 39,
        },
    ], [])

    assert [(block.segment_type, block.clause_no) for block in blocks] == [
        ("non_clause_block", None),
    ]
    assert "1 表示很严格，非这样做不可的：" in blocks[0].text
    assert "2 表示严格，在正常情况下均应这样做的：" in blocks[0].text


def test_build_single_standard_blocks_absorbs_numbered_items_under_standard_wording_note_host() -> None:
    blocks = build_single_standard_blocks([
        {
            "id": "s-terms",
            "section_code": "1",
            "title": "为便于在执行本标准条文时区别对待，对要求严格程度不同的用词说明如下：",
            "text": "",
            "page_start": 45,
            "page_end": 45,
        },
        {
            "id": "s-terms-1",
            "section_code": "1",
            "title": "表示很严格，非这样做不可的：",
            "text": "正面词采用“必须”，反面词采用“严禁”。",
            "page_start": 45,
            "page_end": 45,
        },
        {
            "id": "s-terms-2",
            "section_code": "2",
            "title": "表示严格，在正常情况下均应这样做的：",
            "text": "正面词采用“应”，反面词采用“不应”或“不得”。",
            "page_start": 45,
            "page_end": 45,
        },
    ], [])

    assert [(block.segment_type, block.clause_no) for block in blocks] == [
        ("non_clause_block", "1"),
    ]
    assert "1 表示很严格，非这样做不可的：" in blocks[0].text
    assert "2 表示严格，在正常情况下均应这样做的：" in blocks[0].text


def test_process_standard_ai_uses_deterministic_table_scope_for_single_standard_experiment(monkeypatch) -> None:
    standard_id = UUID("ff2ddb6c-ba8e-4e42-862f-e75d5824437a")
    captured: dict[str, object] = {}

    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: [
        {"id": "s1", "section_code": "4.2.4", "title": "变压器内油样性能", "text": "正文", "level": 1, "page_start": 18, "page_end": 18},
    ])
    monkeypatch.setattr(norm_processor, "_normalize_sections_for_processing", lambda sections: sections)
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, document_id: [])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, document_id: None)
    monkeypatch.setattr(norm_processor, "_build_processing_scopes", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("legacy structural scope builder should not be used for deterministic table extraction")
    ))
    monkeypatch.setattr(norm_processor, "build_single_standard_blocks", lambda sections, tables: [
        BlockSegment(
            segment_type="table_requirement_block",
            chapter_label="表格: 表 4.2.4 变压器内油样性能",
            text=(
                "<table>"
                "<tr><td>试验项目</td><td>电压等级</td><td>标准值</td><td>备注</td></tr>"
                "<tr><td rowspan=\"2\">电气强度</td><td>750kV</td><td>≥70kV</td><td rowspan=\"2\">平板电极间隙</td></tr>"
                "<tr><td>500kV</td><td>≥60kV</td></tr>"
                "<tr><td rowspan=\"2\">含水量</td><td>750kV</td><td>≤10μL/L</td><td>-</td></tr>"
                "<tr><td>500kV</td><td>≤10μL/L</td><td>-</td></tr>"
                "</table>"
            ),
            table_title="表 4.2.4 变压器内油样性能",
            table_html=(
                "<table>"
                "<tr><td>试验项目</td><td>电压等级</td><td>标准值</td><td>备注</td></tr>"
                "<tr><td rowspan=\"2\">电气强度</td><td>750kV</td><td>≥70kV</td><td rowspan=\"2\">平板电极间隙</td></tr>"
                "<tr><td>500kV</td><td>≥60kV</td></tr>"
                "<tr><td rowspan=\"2\">含水量</td><td>750kV</td><td>≤10μL/L</td><td>-</td></tr>"
                "<tr><td>500kV</td><td>≤10μL/L</td><td>-</td></tr>"
                "</table>"
            ),
            page_start=18,
            page_end=18,
            source_refs=["table:t1"],
            confidence="medium",
        ),
    ])
    monkeypatch.setattr(norm_processor, "_process_scope_with_retries", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("deterministic table scope should not call AI")
    ))
    monkeypatch.setattr(norm_processor, "build_tree", lambda entries, current_standard_id: captured.setdefault("entries", list(entries)) or [])
    monkeypatch.setattr(norm_processor, "link_commentary", lambda clauses: clauses)
    monkeypatch.setattr(norm_processor, "validate_tree", lambda clauses: [])
    monkeypatch.setattr(norm_processor, "validate_clauses", lambda clauses, *, outline_clause_nos=None: SimpleNamespace(
        issues=[],
        warning_messages=lambda limit=10: [],
        to_dict=lambda: {"issue_count": 0},
    ))
    monkeypatch.setattr(norm_processor, "build_repair_tasks", lambda clauses, issues: [])
    monkeypatch.setattr(norm_processor._std_repo, "delete_clauses", lambda conn, current_standard_id: 0)
    monkeypatch.setattr(norm_processor._std_repo, "bulk_create_clauses", lambda conn, current_clauses: 0)
    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: None)
    monkeypatch.setattr(norm_processor, "_index_clauses", lambda standard, clauses: None)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)

    summary = norm_processor.process_standard_ai(
        object(),
        standard_id=standard_id,
        document_id="e3003181-042a-44da-ad67-44615d7d25f2",
    )

    assert summary["status"] == "completed"
    assert len(captured["entries"]) == 2
    assert captured["entries"][0]["clause_title"] == "表 4.2.4 变压器内油样性能"
    assert captured["entries"][0]["source_ref"] == "table:t1"


def test_deterministic_entries_from_table_block_group_rows_by_primary_column() -> None:
    block = BlockSegment(
        segment_type="table_requirement_block",
        chapter_label="表格: 表 4.2.4 变压器内油样性能",
        text="表 4.2.4 变压器内油样性能",
        table_title="表 4.2.4 变压器内油样性能",
        table_html=(
            "<table>"
            "<tr><td>试验项目</td><td>电压等级</td><td>标准值</td><td>备注</td></tr>"
            "<tr><td rowspan=\"2\">电气强度</td><td>750kV</td><td>≥70kV</td><td rowspan=\"2\">平板电极间隙</td></tr>"
            "<tr><td>500kV</td><td>≥60kV</td></tr>"
            "<tr><td rowspan=\"2\">含水量</td><td>750kV</td><td>≤10μL/L</td><td>-</td></tr>"
            "<tr><td>500kV</td><td>≤10μL/L</td><td>-</td></tr>"
            "</table>"
        ),
        page_start=18,
        page_end=18,
        source_refs=["table:t1"],
        confidence="medium",
    )

    entries = norm_processor._deterministic_entries_from_block(block)

    assert entries == [
        {
            "clause_no": None,
            "clause_title": "表 4.2.4 变压器内油样性能",
            "clause_text": "电气强度：电压等级750kV，标准值≥70kV；电压等级500kV，标准值≥60kV；备注：平板电极间隙。",
            "summary": None,
            "tags": [],
            "page_start": 18,
            "page_end": 18,
            "clause_type": "normative",
            "source_type": "table",
            "source_ref": "table:t1",
            "source_refs": ["table:t1"],
            "source_label": "表格: 表 4.2.4 变压器内油样性能",
            "table_strategy": "parameter_limit_table",
        },
        {
            "clause_no": None,
            "clause_title": "表 4.2.4 变压器内油样性能",
            "clause_text": "含水量：电压等级750kV，标准值≤10μL/L；电压等级500kV，标准值≤10μL/L。",
            "summary": None,
            "tags": [],
            "page_start": 18,
            "page_end": 18,
            "clause_type": "normative",
            "source_type": "table",
            "source_ref": "table:t1",
            "source_refs": ["table:t1"],
            "source_label": "表格: 表 4.2.4 变压器内油样性能",
            "table_strategy": "parameter_limit_table",
        },
    ]


def test_deterministic_entries_from_normative_block_default_page_end_to_page_start() -> None:
    block = BlockSegment(
        segment_type="normative_clause_block",
        chapter_label="4.1.2 变压器装卸",
        text="变压器装卸应符合规定。",
        clause_no="4.1.2",
        page_start=18,
        page_end=None,
        source_refs=["document_section:s1"],
        confidence="high",
    )

    entries = norm_processor._deterministic_entries_from_block(block)

    assert entries == [
        {
            "clause_no": "4.1.2",
            "clause_title": None,
            "clause_text": "变压器装卸应符合规定。",
            "summary": None,
            "tags": [],
            "page_start": 18,
            "page_end": 18,
            "clause_type": "normative",
            "source_type": "text",
            "source_ref": "document_section:s1",
            "source_refs": ["document_section:s1"],
            "source_label": "4.1.2 变压器装卸",
        },
    ]


def test_is_retryable_ai_gateway_status_treats_generic_502_and_504_as_retryable() -> None:
    request = httpx.Request("POST", "http://127.0.0.1:8100/api/ai/chat")
    response_502 = httpx.Response(502, request=request, text="bad gateway")
    response_504 = httpx.Response(504, request=request, text="gateway timeout")

    exc_502 = httpx.HTTPStatusError("502", request=request, response=response_502)
    exc_504 = httpx.HTTPStatusError("504", request=request, response=response_504)

    assert norm_processor._is_retryable_ai_gateway_status(exc_502) is True
    assert norm_processor._is_retryable_ai_gateway_status(exc_504) is True


def test_process_standard_ai_repairs_symbol_numeric_anomalies_before_persist(monkeypatch) -> None:
    standard_id = UUID("78787878-7878-7878-7878-787878787878")
    inserted_clauses: list[dict] = []
    clauses = [{
        "id": uuid4(),
        "standard_id": standard_id,
        "parent_id": None,
        "clause_no": "1",
        "node_type": "clause",
        "node_key": "1",
        "node_label": None,
        "clause_title": None,
        "clause_text": "抗压强度不应小于30 MP",
        "summary": None,
        "tags": [],
        "page_start": 1,
        "page_end": 1,
        "clause_type": "normative",
        "source_type": "text",
        "source_label": "1 总则",
        "source_ref": "document_section:s1",
        "source_refs": ["document_section:s1"],
    }]

    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: [
        {"id": "s1", "title": "1 总则", "text": "正文", "level": 1, "page_start": 1, "page_end": 1},
    ])
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, document_id: [])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, document_id: None)
    monkeypatch.setattr(norm_processor, "_normalize_sections_for_processing", lambda sections: sections)
    monkeypatch.setattr(norm_processor, "_build_processing_scopes", lambda sections, tables, document=None, document_id=None: [
        ProcessingScope(
            scope_type="normative",
            chapter_label="1 总则",
            text="1 抗压强度不应小于30 MP",
            page_start=1,
            page_end=1,
            section_ids=["s1"],
        )
    ])
    monkeypatch.setattr(norm_processor, "rebalance_scopes", lambda scopes, **kwargs: scopes)
    monkeypatch.setattr(norm_processor, "_process_scope_with_retries", lambda conn, scope: [])
    monkeypatch.setattr(norm_processor, "build_tree", lambda entries, current_standard_id: deepcopy(clauses))
    monkeypatch.setattr(norm_processor, "link_commentary", lambda current_clauses: current_clauses)
    monkeypatch.setattr(norm_processor, "validate_tree", lambda current_clauses: [])
    monkeypatch.setattr(
        norm_processor,
        "run_repair_tasks",
        lambda conn, document_id, tasks: [
            SimpleNamespace(
                task_type="symbol_numeric_repair",
                source_ref="document_section:s1",
                status="patched",
                patched_text="抗压强度不应小于30 MPa",
                patched_table_html=None,
                notes="fixed",
            )
        ],
    )
    monkeypatch.setattr(norm_processor._std_repo, "delete_clauses", lambda conn, current_standard_id: 0)
    monkeypatch.setattr(
        norm_processor._std_repo,
        "bulk_create_clauses",
        lambda conn, current_clauses: inserted_clauses.extend(deepcopy(current_clauses)) or len(current_clauses),
    )
    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: {
        "id": standard_id,
        "standard_code": "GB 1",
        "specialty": "结构",
    })
    monkeypatch.setattr(norm_processor, "_index_clauses", lambda standard, current_clauses: None)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)

    summary = norm_processor.process_standard_ai(
        object(),
        standard_id=standard_id,
        document_id="98989898-9898-9898-9898-989898989898",
    )

    assert summary["status"] == "completed"
    assert summary["repair_task_count"] == 1
    assert summary["issues_before_repair"] == 1
    assert summary["issues_after_repair"] == 0
    assert inserted_clauses[0]["clause_text"] == "抗压强度不应小于30 MPa"


def test_process_standard_ai_keeps_completed_result_when_repair_tasks_timeout(monkeypatch) -> None:
    standard_id = UUID("44444444-4444-4444-4444-444444444444")
    inserted_clauses: list[dict] = []
    clauses = [{
        "id": uuid4(),
        "standard_id": standard_id,
        "parent_id": None,
        "clause_no": "1",
        "node_type": "clause",
        "node_key": "1",
        "node_label": None,
        "clause_title": None,
        "clause_text": "抗压强度不应小于30 MP",
        "summary": None,
        "tags": [],
        "page_start": 1,
        "page_end": 1,
        "clause_type": "normative",
        "source_type": "text",
        "source_label": "1 总则",
        "source_ref": "document_section:s1",
        "source_refs": ["document_section:s1"],
    }]
    validation_issue = SimpleNamespace(
        code="text.symbol_numeric",
        severity="warning",
        message="suspect unit",
        clause_id=clauses[0]["id"],
        clause_no="1",
        page_start=1,
        page_end=1,
        source_ref="document_section:s1",
        snippet="30 MP",
        details={},
    )
    validation_result = SimpleNamespace(
        issues=[validation_issue],
        warning_messages=lambda limit=10: [],
        to_dict=lambda: {"issue_count": 1},
    )

    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: [
        {"id": "s1", "title": "1 总则", "text": "正文", "level": 1, "page_start": 1, "page_end": 1},
    ])
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, document_id: [])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, document_id: None)
    monkeypatch.setattr(norm_processor, "_normalize_sections_for_processing", lambda sections: sections)
    monkeypatch.setattr(norm_processor, "_build_processing_scopes", lambda sections, tables, document=None, document_id=None: [
        ProcessingScope(
            scope_type="normative",
            chapter_label="1 总则",
            text="1 抗压强度不应小于30 MP",
            page_start=1,
            page_end=1,
            section_ids=["s1"],
        )
    ])
    monkeypatch.setattr(norm_processor, "rebalance_scopes", lambda scopes, **kwargs: scopes)
    monkeypatch.setattr(norm_processor, "_process_scope_with_retries", lambda conn, scope: [])
    monkeypatch.setattr(norm_processor, "build_tree", lambda entries, current_standard_id: deepcopy(clauses))
    monkeypatch.setattr(norm_processor, "link_commentary", lambda current_clauses: current_clauses)
    monkeypatch.setattr(norm_processor, "validate_clauses", lambda current_clauses, outline_clause_nos=None: validation_result)
    monkeypatch.setattr(
        norm_processor,
        "build_repair_tasks",
        lambda current_clauses, issues: [
            SimpleNamespace(
                task_type="symbol_numeric_repair",
                source_ref="document_section:s1",
                page_start=1,
                page_end=1,
            )
        ],
    )
    monkeypatch.setattr(
        norm_processor,
        "run_repair_tasks",
        lambda conn, document_id, tasks: (_ for _ in ()).throw(httpx.ReadTimeout("timed out")),
    )
    monkeypatch.setattr(norm_processor, "validate_tree", lambda current_clauses: [])
    monkeypatch.setattr(norm_processor._std_repo, "delete_clauses", lambda conn, current_standard_id: 0)
    monkeypatch.setattr(
        norm_processor._std_repo,
        "bulk_create_clauses",
        lambda conn, current_clauses: inserted_clauses.extend(deepcopy(current_clauses)) or len(current_clauses),
    )
    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: {
        "id": standard_id,
        "standard_code": "GB 1",
        "specialty": "结构",
    })
    monkeypatch.setattr(norm_processor, "_index_clauses", lambda standard, current_clauses: None)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)

    summary = norm_processor.process_standard_ai(
        object(),
        standard_id=standard_id,
        document_id="98989898-9898-9898-9898-989898989898",
    )

    assert summary["status"] == "completed"
    assert summary["repair_task_count"] == 1
    assert summary["issues_before_repair"] == 1
    assert summary["issues_after_repair"] == 1
    assert summary["repair_error"] == "timed out"
    assert "repair tasks failed: timed out" in summary["warnings"]
    assert inserted_clauses[0]["clause_text"] == "抗压强度不应小于30 MP"


def test_process_standard_ai_skips_repair_when_disabled(monkeypatch) -> None:
    standard_id = UUID("45454545-4545-4545-4545-454545454545")
    inserted_clauses: list[dict] = []
    clauses = [{
        "id": uuid4(),
        "standard_id": standard_id,
        "parent_id": None,
        "clause_no": "1",
        "node_type": "clause",
        "node_key": "1",
        "node_label": None,
        "clause_title": None,
        "clause_text": "抗压强度不应小于30 MP",
        "summary": None,
        "tags": [],
        "page_start": 1,
        "page_end": 1,
        "clause_type": "normative",
        "source_type": "text",
        "source_label": "1 总则",
        "source_ref": "document_section:s1",
        "source_refs": ["document_section:s1"],
    }]
    validation_issue = SimpleNamespace(
        code="text.symbol_numeric",
        severity="warning",
        message="suspect unit",
        clause_id=clauses[0]["id"],
        clause_no="1",
        page_start=1,
        page_end=1,
        source_ref="document_section:s1",
        snippet="30 MP",
        details={},
    )
    validation_result = SimpleNamespace(
        issues=[validation_issue],
        warning_messages=lambda limit=10: [],
        to_dict=lambda: {"issue_count": 1},
    )

    monkeypatch.setattr(norm_processor, "get_settings", lambda: SimpleNamespace(
        standard_ai_gateway_timeout_seconds=120.0,
        standard_ai_scope_delay_ms=0,
        standard_ai_scope_delay_jitter_ms=0,
        standard_repair_enabled=False,
    ))
    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: [
        {"id": "s1", "title": "1 总则", "text": "正文", "level": 1, "page_start": 1, "page_end": 1},
    ])
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, document_id: [])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, document_id: None)
    monkeypatch.setattr(norm_processor, "_normalize_sections_for_processing", lambda sections: sections)
    monkeypatch.setattr(norm_processor, "_build_processing_scopes", lambda sections, tables, document=None, document_id=None: [
        ProcessingScope(
            scope_type="normative",
            chapter_label="1 总则",
            text="1 抗压强度不应小于30 MP",
            page_start=1,
            page_end=1,
            section_ids=["s1"],
        )
    ])
    monkeypatch.setattr(norm_processor, "rebalance_scopes", lambda scopes, **kwargs: scopes)
    monkeypatch.setattr(norm_processor, "_process_scope_with_retries", lambda conn, scope: [])
    monkeypatch.setattr(norm_processor, "build_tree", lambda entries, current_standard_id: deepcopy(clauses))
    monkeypatch.setattr(norm_processor, "link_commentary", lambda current_clauses: current_clauses)
    monkeypatch.setattr(norm_processor, "validate_clauses", lambda current_clauses, outline_clause_nos=None: validation_result)
    monkeypatch.setattr(
        norm_processor,
        "build_repair_tasks",
        lambda current_clauses, issues: [
            SimpleNamespace(
                task_type="symbol_numeric_repair",
                source_ref="document_section:s1",
                page_start=1,
                page_end=1,
            )
        ],
    )
    monkeypatch.setattr(
        norm_processor,
        "run_repair_tasks",
        lambda conn, document_id, tasks: pytest.fail("repair should be disabled"),
    )
    monkeypatch.setattr(norm_processor, "validate_tree", lambda current_clauses: [])
    monkeypatch.setattr(norm_processor._std_repo, "delete_clauses", lambda conn, current_standard_id: 0)
    monkeypatch.setattr(
        norm_processor._std_repo,
        "bulk_create_clauses",
        lambda conn, current_clauses: inserted_clauses.extend(deepcopy(current_clauses)) or len(current_clauses),
    )
    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: {
        "id": standard_id,
        "standard_code": "GB 1",
        "specialty": "结构",
    })
    monkeypatch.setattr(norm_processor, "_index_clauses", lambda standard, current_clauses: None)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda _: None)

    summary = norm_processor.process_standard_ai(
        object(),
        standard_id=standard_id,
        document_id="97979797-9797-9797-9797-979797979797",
    )

    assert summary["status"] == "completed"
    assert summary["repair_task_count"] == 0
    assert summary["issues_before_repair"] == 1
    assert summary["issues_after_repair"] == 1
    assert summary["repair_error"] is None
    assert inserted_clauses[0]["clause_text"] == "抗压强度不应小于30 MP"


def test_process_standard_ai_uses_configured_scope_delay(monkeypatch) -> None:
    standard_id = UUID("33333333-3333-3333-3333-333333333333")
    sleep_calls: list[float] = []

    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, document_id: [
        {"id": "s1", "title": "1 总则", "text": "正文", "level": 1, "page_start": 1, "page_end": 1},
    ])
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, document_id: [])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, document_id: None)
    monkeypatch.setattr(norm_processor, "_normalize_sections_for_processing", lambda sections: sections)
    monkeypatch.setattr(norm_processor, "_build_processing_scopes", lambda sections, tables, document=None, document_id=None: [
        ProcessingScope(
            scope_type="normative",
            chapter_label="1 总则",
            text="1.0.1 正文",
            page_start=1,
            page_end=1,
            section_ids=["s1"],
        ),
        ProcessingScope(
            scope_type="normative",
            chapter_label="2 术语",
            text="2.0.1 正文",
            page_start=2,
            page_end=2,
            section_ids=["s2"],
        ),
    ])
    monkeypatch.setattr(norm_processor, "rebalance_scopes", lambda scopes, **kwargs: scopes)
    monkeypatch.setattr(norm_processor, "_process_scope_with_retries", lambda conn, scope: [])
    monkeypatch.setattr(norm_processor, "build_tree", lambda entries, current_standard_id: [])
    monkeypatch.setattr(norm_processor, "link_commentary", lambda clauses: clauses)
    monkeypatch.setattr(norm_processor, "validate_tree", lambda clauses: [])
    monkeypatch.setattr(norm_processor._std_repo, "delete_clauses", lambda conn, current_standard_id: 0)
    monkeypatch.setattr(norm_processor._std_repo, "bulk_create_clauses", lambda conn, clauses: 0)
    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: {
        "id": standard_id,
        "standard_code": "GB 1",
        "specialty": "结构",
    })
    monkeypatch.setattr(norm_processor, "_index_clauses", lambda standard, clauses: None)
    monkeypatch.setattr(
        norm_processor,
        "get_settings",
        lambda: SimpleNamespace(
            standard_ai_scope_delay_ms=200,
            standard_ai_scope_delay_jitter_ms=0,
            standard_ai_gateway_timeout_seconds=120.0,
        ),
        raising=False,
    )
    monkeypatch.setattr(norm_processor.random, "uniform", lambda start, end: 0.0, raising=False)
    monkeypatch.setattr(norm_processor.time, "sleep", lambda value: sleep_calls.append(value))

    summary = norm_processor.process_standard_ai(
        object(),
        standard_id=standard_id,
        document_id="44444444-4444-4444-4444-444444444444",
    )

    assert summary["status"] == "completed"
    assert sleep_calls == [0.2]


def test_rebalance_scopes_splits_oversized_scope_by_paragraphs() -> None:
    scopes = [
        ProcessingScope(
            scope_type="commentary",
            chapter_label="条文说明",
            text="A" * 3000 + "\n\n" + "B" * 3000 + "\n\n" + "C" * 1000,
            page_start=1,
            page_end=5,
            section_ids=["s1"],
            source_refs=["document_section:s1", "document_section:s2"],
            context={"document_id": "doc-1", "source_refs": ["document_section:s1", "document_section:s2"]},
            source_chunks=[
                {"text": "A" * 3000, "source_ref": "document_section:s1", "node_type": "page"},
                {"text": "B" * 3000 + "\n\n" + "C" * 1000, "source_ref": "document_section:s2", "node_type": "page"},
            ],
        )
    ]

    rebalanced = rebalance_scopes(scopes, max_chars=5000)

    assert len(rebalanced) == 2
    assert rebalanced[0].chapter_label == "条文说明 (1/2)"
    assert rebalanced[1].chapter_label == "条文说明 (2/2)"
    assert rebalanced[0].scope_type == "commentary"
    assert rebalanced[0].page_start == 1
    assert rebalanced[1].page_end == 5
    assert rebalanced[0].text == "A" * 3000
    assert rebalanced[1].text == "B" * 3000 + "\n\n" + "C" * 1000
    assert rebalanced[0].source_refs == ["document_section:s1"]
    assert rebalanced[1].source_refs == ["document_section:s2"]
    assert rebalanced[0].context == {
        "document_id": "doc-1",
        "source_refs": ["document_section:s1"],
        "node_types": ["page"],
    }
    assert rebalanced[1].context == {
        "document_id": "doc-1",
        "source_refs": ["document_section:s2"],
        "node_types": ["page"],
    }


def test_rebalance_scopes_uses_safer_default_limit() -> None:
    scopes = [
        ProcessingScope(
            scope_type="commentary",
            chapter_label="条文说明",
            text="A" * 2400 + "\n\n" + "B" * 2400,
            page_start=1,
            page_end=3,
            section_ids=["s1"],
        )
    ]

    rebalanced = rebalance_scopes(scopes)

    assert len(rebalanced) == 2
    assert rebalanced[0].chapter_label == "条文说明 (1/2)"
    assert rebalanced[1].chapter_label == "条文说明 (2/2)"
    assert rebalanced[0].text == "A" * 2400
    assert rebalanced[1].text == "B" * 2400


def test_rebalance_scopes_splits_clause_dense_scope_by_clause_blocks() -> None:
    scopes = [
        ProcessingScope(
            scope_type="normative",
            chapter_label="3 基本规定",
            text=(
                "3 基本规定\n\n"
                "3.0.1 第一条正文\n\n"
                "1 第一条子项\n\n"
                "3.0.2 第二条正文\n\n"
                "2 第二条子项\n\n"
                "3.0.3 第三条正文\n\n"
                "3 第三条子项"
            ),
            page_start=1,
            page_end=2,
            section_ids=["s1"],
        )
    ]

    rebalanced = rebalance_scopes(scopes, max_chars=5000, max_clause_blocks=2)

    assert len(rebalanced) == 2
    assert rebalanced[0].chapter_label == "3 基本规定 (1/2)"
    assert "3.0.1 第一条正文" in rebalanced[0].text
    assert "3.0.2 第二条正文" in rebalanced[0].text
    assert "3.0.3 第三条正文" not in rebalanced[0].text
    assert rebalanced[1].chapter_label == "3 基本规定 (2/2)"
    assert rebalanced[1].text.startswith("3.0.3 第三条正文")


def test_rebalance_scopes_uses_safer_default_clause_limit() -> None:
    scopes = [
        ProcessingScope(
            scope_type="normative",
            chapter_label="8 电力变压器",
            text=(
                "8 电力变压器\n\n"
                "8.0.1 第一条正文\n\n"
                "8.0.2 第二条正文\n\n"
                "8.0.3 第三条正文\n\n"
                "8.0.4 第四条正文\n\n"
                "8.0.5 第五条正文"
            ),
            page_start=1,
            page_end=2,
            section_ids=["s1"],
        )
    ]

    rebalanced = rebalance_scopes(scopes)

    assert len(rebalanced) == 2
    assert rebalanced[0].chapter_label == "8 电力变压器 (1/2)"
    assert "8.0.4 第四条正文" in rebalanced[0].text
    assert "8.0.5 第五条正文" not in rebalanced[0].text
    assert rebalanced[1].text == "8.0.5 第五条正文"


def test_rebalance_scopes_splits_large_single_paragraph_html_table() -> None:
    rows = "".join(
        f"<tr><td>{idx}</td><td>术语说明{idx}</td><td>这是一个较长的表格单元格内容，用于触发表格拆分。</td></tr>"
        for idx in range(1, 9)
    )
    scopes = [
        ProcessingScope(
            scope_type="commentary",
            chapter_label="2 术语 (2/12)",
            text=f"<table>{rows}</table>",
            page_start=10,
            page_end=12,
            section_ids=["s1"],
        )
    ]

    rebalanced = rebalance_scopes(scopes, max_chars=250, max_clause_blocks=2)

    assert len(rebalanced) > 1
    assert rebalanced[0].chapter_label.startswith("2 术语 (2/12) (1/")
    assert rebalanced[-1].chapter_label.endswith(f"/{len(rebalanced)})")
    assert all(part.text.startswith("<table>") for part in rebalanced)
    assert all(part.text.endswith("</table>") for part in rebalanced)


def test_rebalance_scopes_splits_long_single_line_sequences_without_blank_paragraphs() -> None:
    dense_lines = "\n".join(
        f"{idx} {'单行条目内容' * 20}"
        for idx in range(1, 9)
    )
    scopes = [
        ProcessingScope(
            scope_type="normative",
            chapter_label="4.5 器身检查",
            text=dense_lines,
            page_start=15,
            page_end=16,
            section_ids=["s1"],
        )
    ]

    rebalanced = rebalance_scopes(scopes, max_chars=200, max_clause_blocks=2)

    assert len(rebalanced) > 1
    assert rebalanced[0].chapter_label.startswith("4.5 器身检查 (1/")
