from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4
from zipfile import ZipFile

import httpx
import pytest

from tender_backend.services.norm_service import norm_processor
from tender_backend.services.norm_service.layout_compressor import PageWindow, compress_sections
from tender_backend.services.norm_service.prompt_builder import build_prompt
from tender_backend.services.norm_service.scope_splitter import ProcessingScope, rebalance_scopes, split_into_scopes
from tender_backend.services.norm_service.tree_builder import validate_tree
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


def _zip_bytes(full_md: str, extra_files: dict[str, str] | None = None) -> bytes:
    buf = BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("full.md", full_md)
        for name, content in (extra_files or {}).items():
            zf.writestr(name, content)
    return buf.getvalue()


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
            return _FakeResponse(content=_zip_bytes(
                "1 总则\n正文内容\n\n2 术语\n术语正文",
                {
                    "middle.json": (
                        '{"pages": ['
                        '{"page_number": 7, "markdown": "1 总则\\n正文内容"},'
                        '{"page_number": 8, "markdown": "2 术语\\n术语正文"}'
                        "]}"),
                },
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
            "files": [{"name": "spec.pdf", "data_id": "11111111-1111-1111-1111-111111111111"}],
            "model_version": "vlm",
            "is_ocr": True,
            "enable_table": True,
            "language": "ch",
        },
        {"Authorization": "Bearer token"},
    )
    assert ("PUT", "https://upload.example.com/file-1", pdf_bytes, None) in calls
    assert ("GET", "https://mineru.net/api/v4/extract-results/batch/batch-123", None, {"Authorization": "Bearer token"}) in calls
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
            return _FakeResponse(content=_zip_bytes(
                "1 总则\n正文内容",
                {
                    "middle.json": (
                        '{"pages": ['
                        '{"page_number": 7, "markdown": "1 总则\\n正文内容"}'
                        '], "tables": ['
                        '{"page": 8, "title": "主要参数", "html": "<table><tr><td>额定电压</td><td>10kV</td></tr></table>"}'
                        "]}"
                    ),
                },
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
                "page": 8,
                "title": "主要参数",
                "html": "<table><tr><td>额定电压</td><td>10kV</td></tr></table>",
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
        primary_model="deepseek-chat",
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
                "resolved_model": "deepseek-reasoner",
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
        primary_model="deepseek-reasoner",
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
    assert calls[0] == "8 电力变压器"
    assert calls[1:] == ["8 电力变压器 (1/2)", "8 电力变压器 (2/2)"]
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
    assert calls[0] == "4 电力变压器"
    assert calls[1:] == ["4 电力变压器 (1/2)", "4 电力变压器 (2/2)"]


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
            "source_type": "table",
            "source_label": "表格: 主要参数",
        }
    ]


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
    assert "<table><tr><td>额定电压</td><td>10kV</td></tr></table>" in prompt
    assert "来源引用: table:t1" in prompt
    assert '"node_type": "table"' in prompt


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
        lambda clauses: SimpleNamespace(
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
