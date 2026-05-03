from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

from tender_backend.services.extract_service import tender_facts_extractor as mod


def _chunk(text: str):
    return {
        "id": uuid4(),
        "source_file": "采购文件.docx",
        "source_locator": "paragraph:1",
        "text": text,
    }


def test_rule_fallback_extracts_summary_without_ai_config(monkeypatch) -> None:
    monkeypatch.setattr(
        mod.AgentConfigRepository,
        "get_by_key",
        lambda self, conn, key: None,
    )
    chunks = [_chunk("项目名称：居民供电设施改造项目 招标人：REDACTED 投标截止时间：2026年6月1日")]

    result = asyncio.run(mod.extract_tender_summary_with_ai(chunks, conn=SimpleNamespace()))

    assert result.model == "rule"
    assert "居民供电设施" in (result.summary["project_name"] or "")
    assert "国网重庆" in (result.summary["tenderer"] or "")
    assert result.source_chunk_ids == [str(chunks[0]["id"])]


def test_ai_json_output_merges_with_rule_fallback(monkeypatch) -> None:
    config = SimpleNamespace(
        enabled=True,
        base_url="https://api.deepseek.com/v1",
        api_key="sk-test",
        primary_model="deepseek-v4-pro",
        fallback_base_url="",
        fallback_api_key="",
        fallback_model="",
    )
    monkeypatch.setattr(mod.AgentConfigRepository, "get_by_key", lambda self, conn, key: config)
    chunks = [_chunk("项目名称：居民供电设施改造项目 招标人：REDACTED")]
    captured: list[dict] = []

    async def _fake_post(self, url, json, timeout):
        captured.append(json)

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "resolved_model": "deepseek-v4-pro",
                    "content": __import__("json").dumps({"project_name": "AI项目", "tenderer": None}),
                }

        return _Resp()

    monkeypatch.setattr(mod.httpx.AsyncClient, "post", _fake_post)

    result = asyncio.run(mod.extract_tender_summary_with_ai(chunks, conn=SimpleNamespace()))

    assert result.model == "deepseek-v4-pro"
    assert result.summary["project_name"] == "AI项目"
    assert "国网重庆" in (result.summary["tenderer"] or "")
    assert captured[0]["response_format"] == {"type": "json_object"}
