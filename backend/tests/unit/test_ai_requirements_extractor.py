"""Unit tests for AI requirement extractor.

Boundary mocked: the AsyncClient.post call to AI Gateway. We don't exercise
psycopg here (agent_config is also mocked) so the test stays close to the
parsing/normalize logic.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from tender_backend.services.extract_service import ai_requirements_extractor as mod


def _chunk(
    *,
    text: str = "",
    source_file: str = "招标文件.docx",
    source_locator: str = "paragraph:1",
    chunk_type: str = "paragraph",
    sort_order: int = 0,
    table_rows: list[list[str]] | None = None,
) -> dict[str, Any]:
    chunk: dict[str, Any] = {
        "id": uuid4(),
        "text": text,
        "source_file": source_file,
        "source_locator": source_locator,
        "chunk_type": chunk_type,
        "sort_order": sort_order,
        "title": None,
    }
    if table_rows is not None:
        chunk["table_json"] = {"rows": table_rows}
    return chunk


def _ai_response(items: list[dict[str, Any]], **overrides: Any) -> dict[str, Any]:
    base = {
        "task_type": "extract_tender_requirements",
        "resolved_model": "deepseek-v4-pro",
        "resolved_provider": "deepseek",
        "content": __import__("json").dumps(items, ensure_ascii=False),
        "input_tokens": 100,
        "output_tokens": 200,
        "estimated_cost": 0.0,
        "latency_ms": 1234,
        "used_fallback": False,
    }
    base.update(overrides)
    return base


@pytest.fixture
def fake_conn():
    return SimpleNamespace()


def _patch_agent_config(
    monkeypatch,
    *,
    enabled: bool = True,
    primary_model: str = "deepseek-v4-pro",
    fallback_model: str = "deepseek-v4-flash",
) -> None:
    config = SimpleNamespace(
        enabled=enabled,
        base_url="https://api.deepseek.com/v1",
        api_key="sk-test",
        primary_model=primary_model,
        fallback_base_url="https://api.deepseek.com/v1",
        fallback_api_key="sk-test",
        fallback_model=fallback_model,
    )
    monkeypatch.setattr(
        mod.AgentConfigRepository,
        "get_by_key",
        lambda self, conn, key: config,
    )


def _patch_call_ai(monkeypatch, handler) -> dict[str, list]:
    """Replace `_call_ai_gateway` with `handler(prompt, primary_override, fallback_override)`.

    Returns a dict accumulating each call's payload for assertions.
    """
    captured: dict[str, list] = {"calls": []}

    async def _fake(
        client,
        *,
        prompt,
        primary_override,
        fallback_override,
        response_format=None,
        stream=False,
        max_tokens=None,
    ):
        captured["calls"].append(
            {
                "prompt": prompt,
                "primary_override": primary_override,
                "fallback_override": fallback_override,
                "response_format": response_format,
                "stream": stream,
                "max_tokens": max_tokens,
            }
        )
        return await handler(prompt, primary_override, fallback_override)

    monkeypatch.setattr(mod, "_call_ai_gateway", _fake)
    return captured


def test_extracts_normalizes_and_persists_one_requirement(monkeypatch, fake_conn) -> None:
    _patch_agent_config(monkeypatch)
    chunk = _chunk(
        text="投标人应具备建筑工程施工总承包二级及以上资质。",
        source_locator="paragraph:42",
    )
    ai_items = [
        {
            "source_chunk_id": str(chunk["id"]),
            "category": "qualification",
            "title": "施工总承包二级及以上",
            "requirement_text": "投标人应具备建筑工程施工总承包二级及以上资质。",
            "is_veto": False,
            "is_hard_constraint": True,
            "ignored_for_pricing": False,
            "confidence": 0.93,
        }
    ]

    async def _handler(prompt, primary, fallback):
        return _ai_response(ai_items)

    _patch_call_ai(monkeypatch, _handler)
    summary = asyncio.run(mod.extract_requirements_with_ai([chunk], conn=fake_conn))

    assert len(summary.requirements) == 1
    req = summary.requirements[0]
    assert req.category == "qualification"
    assert req.is_hard_constraint is True
    assert req.requires_human_confirm is True
    assert req.source_locator == "paragraph:42"
    assert req.extraction_method == "ai"
    assert summary.total_input_tokens == 100
    assert summary.total_output_tokens == 200
    assert summary.batches[0].resolved_model == "deepseek-v4-pro"


def test_drops_hallucinated_chunk_ids(monkeypatch, fake_conn) -> None:
    _patch_agent_config(monkeypatch)
    chunk = _chunk(text="评标办法详见前附表。")
    ai_items = [
        {
            "source_chunk_id": "00000000-0000-0000-0000-000000000000",
            "category": "scoring",
            "title": "评标办法",
            "requirement_text": "评标办法详见前附表。",
            "confidence": 0.9,
        },
        {
            "source_chunk_id": str(chunk["id"]),
            "category": "scoring",
            "title": "评标办法",
            "requirement_text": "评标办法详见前附表。",
            "confidence": 0.9,
        },
    ]

    async def _handler(prompt, primary, fallback):
        return _ai_response(ai_items)

    _patch_call_ai(monkeypatch, _handler)
    summary = asyncio.run(mod.extract_requirements_with_ai([chunk], conn=fake_conn))

    assert len(summary.requirements) == 1
    assert summary.batches[0].dropped_invalid == 1


def test_dedupes_same_chunk_same_category(monkeypatch, fake_conn) -> None:
    _patch_agent_config(monkeypatch)
    chunk = _chunk(text="投标保证金 5 万元。")
    ai_items = [
        {
            "source_chunk_id": str(chunk["id"]),
            "category": "business",
            "title": "投标保证金",
            "requirement_text": "投标保证金 5 万元。",
            "confidence": 0.9,
        },
        {
            "source_chunk_id": str(chunk["id"]),
            "category": "business",
            "title": "保证金金额",
            "requirement_text": "投标保证金 5 万元。",
            "confidence": 0.9,
        },
    ]

    async def _handler(prompt, primary, fallback):
        return _ai_response(ai_items)

    _patch_call_ai(monkeypatch, _handler)
    summary = asyncio.run(mod.extract_requirements_with_ai([chunk], conn=fake_conn))

    assert len(summary.requirements) == 1


def test_drops_invalid_category(monkeypatch, fake_conn) -> None:
    _patch_agent_config(monkeypatch)
    chunk = _chunk(text="项目工期 30 天。")
    ai_items = [
        {
            "source_chunk_id": str(chunk["id"]),
            "category": "made_up_category",
            "title": "工期",
            "requirement_text": "工期 30 天",
            "confidence": 0.9,
        },
    ]

    async def _handler(prompt, primary, fallback):
        return _ai_response(ai_items)

    _patch_call_ai(monkeypatch, _handler)
    summary = asyncio.run(mod.extract_requirements_with_ai([chunk], conn=fake_conn))

    assert len(summary.requirements) == 0
    assert summary.batches[0].dropped_invalid == 1


def test_runs_batches_concurrently(monkeypatch, fake_conn) -> None:
    """With concurrency=2, two slow batches finish in ~max(1, 1) seconds, not 2."""
    _patch_agent_config(monkeypatch)
    chunk_a = _chunk(text="A 条款", source_file="A.docx")
    chunk_b = _chunk(text="B 条款", source_file="B.docx")

    in_flight: list[int] = []
    max_in_flight: list[int] = [0]
    lock = asyncio.Lock()

    async def _handler(prompt, primary, fallback):
        async with lock:
            in_flight.append(1)
            max_in_flight[0] = max(max_in_flight[0], len(in_flight))
        await asyncio.sleep(0.05)
        async with lock:
            in_flight.pop()
        target_chunk = chunk_a if str(chunk_a["id"]) in prompt else chunk_b
        return _ai_response(
            [
                {
                    "source_chunk_id": str(target_chunk["id"]),
                    "category": "technical",
                    "title": "技术",
                    "requirement_text": "技术要求",
                    "confidence": 0.9,
                }
            ]
        )

    _patch_call_ai(monkeypatch, _handler)
    summary = asyncio.run(
        mod.extract_requirements_with_ai([chunk_a, chunk_b], conn=fake_conn, concurrency=2)
    )

    assert len(summary.requirements) == 2
    assert max_in_flight[0] == 2  # both batches were truly concurrent


def test_continues_when_one_batch_fails(monkeypatch, fake_conn) -> None:
    _patch_agent_config(monkeypatch)
    chunk_a = _chunk(text="A 条款", source_file="A.docx")
    chunk_b = _chunk(text="B 条款", source_file="B.docx")

    async def _handler(prompt, primary, fallback):
        if str(chunk_a["id"]) in prompt:
            raise mod.httpx.ConnectError("boom")
        return _ai_response(
            [
                {
                    "source_chunk_id": str(chunk_b["id"]),
                    "category": "technical",
                    "title": "技术",
                    "requirement_text": "B 技术要求",
                    "confidence": 0.9,
                }
            ]
        )

    _patch_call_ai(monkeypatch, _handler)
    summary = asyncio.run(
        mod.extract_requirements_with_ai([chunk_a, chunk_b], conn=fake_conn, concurrency=2)
    )

    assert len(summary.requirements) == 1
    assert summary.requirements[0].source_file == "B.docx"
    failed = [b for b in summary.batches if b.extracted == 0 and b.input_tokens == 0]
    assert len(failed) == 1
    assert failed[0].error_type == "ConnectError"
    assert failed[0].error_message == "boom"


def test_strips_markdown_fences_around_json(monkeypatch, fake_conn) -> None:
    _patch_agent_config(monkeypatch)
    chunk = _chunk(text="测试")
    items = [
        {
            "source_chunk_id": str(chunk["id"]),
            "category": "technical",
            "title": "测试",
            "requirement_text": "测试",
            "confidence": 0.9,
        }
    ]
    fenced = "```json\n" + __import__("json").dumps(items, ensure_ascii=False) + "\n```"

    async def _handler(prompt, primary, fallback):
        return _ai_response(items, content=fenced)

    _patch_call_ai(monkeypatch, _handler)
    summary = asyncio.run(mod.extract_requirements_with_ai([chunk], conn=fake_conn))

    assert len(summary.requirements) == 1


def test_parses_json_object_schema_with_batch_quality(monkeypatch, fake_conn) -> None:
    _patch_agent_config(monkeypatch)
    chunk = _chunk(text="投标人须满足技术要求。")
    content = __import__("json").dumps(
        {
            "requirements": [
                {
                    "source_chunk_id": str(chunk["id"]),
                    "category": "technical",
                    "title": "技术要求",
                    "requirement_text": "投标人须满足技术要求。",
                    "confidence": 0.9,
                }
            ],
            "batch_quality": {
                "has_requirements": True,
                "coverage_note": "已覆盖",
                "suspected_missing": False,
            },
        },
        ensure_ascii=False,
    )

    async def _handler(prompt, primary, fallback):
        return _ai_response([], content=content)

    _patch_call_ai(monkeypatch, _handler)
    summary = asyncio.run(mod.extract_requirements_with_ai([chunk], conn=fake_conn))

    assert len(summary.requirements) == 1
    assert summary.batches[0].batch_quality == {
        "has_requirements": True,
        "coverage_note": "已覆盖",
        "suspected_missing": False,
        "empty_reason": None,
        "reference_targets": [],
    }


def test_infers_reference_only_empty_reason(monkeypatch, fake_conn) -> None:
    _patch_agent_config(monkeypatch)
    chunk = _chunk(
        text="本次商务文件要求按批次制作，技术文件制作要求详见附件10，按分类递交。",
        source_file="附件10：技术投标文件制作及递交要求.xlsx",
        chunk_type="table",
    )
    content = __import__("json").dumps(
        {
            "requirements": [],
            "batch_quality": {
                "has_requirements": False,
                "coverage_note": "该附件仅列出分类说明。",
                "suspected_missing": True,
            },
        },
        ensure_ascii=False,
    )

    async def _handler(prompt, primary, fallback):
        return _ai_response([], content=content)

    _patch_call_ai(monkeypatch, _handler)
    summary = asyncio.run(mod.extract_requirements_with_ai([chunk], conn=fake_conn))

    assert summary.batches[0].extracted == 0
    assert summary.batches[0].batch_quality["empty_reason"] == "reference_only"
    assert summary.batches[0].batch_quality["suspected_missing"] is False
    assert "附件" in summary.batches[0].batch_quality["reference_targets"]


def test_infers_template_blank_empty_reason(monkeypatch, fake_conn) -> None:
    _patch_agent_config(monkeypatch)
    chunk = _chunk(
        text="本页为空白模板，相关内容待填写。",
        source_file="合同条款（空白）.docx",
    )

    async def _handler(prompt, primary, fallback):
        return _ai_response([])

    _patch_call_ai(monkeypatch, _handler)
    summary = asyncio.run(mod.extract_requirements_with_ai([chunk], conn=fake_conn))

    assert summary.batches[0].extracted == 0
    assert summary.batches[0].batch_quality["empty_reason"] == "template_blank"
    assert summary.batches[0].batch_quality["suspected_missing"] is False


def test_passes_v4_pro_with_reasoning_effort(monkeypatch, fake_conn) -> None:
    _patch_agent_config(monkeypatch)
    chunk = _chunk(text="测试")
    items = [
        {
            "source_chunk_id": str(chunk["id"]),
            "category": "technical",
            "title": "T",
            "requirement_text": "T",
            "confidence": 0.9,
        }
    ]

    async def _handler(prompt, primary, fallback):
        return _ai_response(items)

    captured = _patch_call_ai(monkeypatch, _handler)
    asyncio.run(mod.extract_requirements_with_ai([chunk], conn=fake_conn))

    assert len(captured["calls"]) == 1
    call = captured["calls"][0]
    primary = call["primary_override"]
    assert primary["model"] == "deepseek-v4-pro"
    assert primary["extra_body"] == {"thinking": {"type": "enabled"}, "reasoning_effort": "max"}


def test_preplanned_batch_uses_batch_model_without_implicit_max(monkeypatch, fake_conn) -> None:
    _patch_agent_config(monkeypatch, primary_model="deepseek-v4-pro")
    chunk = _chunk(text="普通附件说明")

    async def _handler(prompt, primary, fallback):
        return _ai_response(
            [
                {
                    "source_chunk_id": str(chunk["id"]),
                    "category": "technical",
                    "title": "普通要求",
                    "requirement_text": "普通附件说明",
                    "confidence": 0.9,
                }
            ],
            resolved_model="deepseek-v4-flash",
            finish_reason="stop",
            prompt_cache_hit_tokens=12,
            prompt_cache_miss_tokens=88,
            reasoning_tokens=7,
        )

    captured = _patch_call_ai(monkeypatch, _handler)
    summary = asyncio.run(
        mod.extract_requirements_for_batch(
            [chunk],
            conn=fake_conn,
            source_file="普通附件.docx",
            model="deepseek-v4-flash",
            reasoning_effort=None,
        )
    )

    call = captured["calls"][0]
    assert call["primary_override"]["model"] == "deepseek-v4-flash"
    assert "extra_body" not in call["primary_override"]
    assert summary.batches[0].finish_reason == "stop"
    assert summary.batches[0].prompt_cache_hit_tokens == 12
    assert summary.batches[0].prompt_cache_miss_tokens == 88
    assert summary.batches[0].reasoning_tokens == 7


def test_preplanned_batch_uses_explicit_reasoning_effort(monkeypatch, fake_conn) -> None:
    _patch_agent_config(monkeypatch)
    chunk = _chunk(text="否决条款")

    async def _handler(prompt, primary, fallback):
        return _ai_response([])

    captured = _patch_call_ai(monkeypatch, _handler)
    asyncio.run(
        mod.extract_requirements_for_batch(
            [chunk],
            conn=fake_conn,
            source_file="招标文件.docx",
            model="deepseek-v4-pro",
            reasoning_effort="max",
        )
    )

    assert captured["calls"][0]["primary_override"] == {
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "sk-test",
        "model": "deepseek-v4-pro",
        "extra_body": {"thinking": {"type": "enabled"}, "reasoning_effort": "max"},
    }


def test_build_batch_overrides_can_disable_thinking(monkeypatch, fake_conn) -> None:
    _patch_agent_config(monkeypatch)

    primary, fallback = mod.build_batch_overrides(
        fake_conn,
        model="deepseek-v4-flash",
        thinking_enabled=False,
        reasoning_effort=None,
    )

    assert primary == {
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "sk-test",
        "model": "deepseek-v4-flash",
        "extra_body": {"thinking": {"type": "disabled"}},
    }
    assert fallback is not None


def test_passes_json_response_format_to_ai_gateway(monkeypatch, fake_conn) -> None:
    _patch_agent_config(monkeypatch)
    chunk = _chunk(text="测试")

    async def _handler(prompt, primary, fallback):
        return _ai_response(
            [
                {
                    "source_chunk_id": str(chunk["id"]),
                    "category": "technical",
                    "title": "T",
                    "requirement_text": "T",
                    "confidence": 0.9,
                }
            ]
        )

    captured_payloads: list[dict] = []

    async def _fake_post(self, url, json, timeout):
        captured_payloads.append(json)

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return _ai_response(
                    [
                        {
                            "source_chunk_id": str(chunk["id"]),
                            "category": "technical",
                            "title": "T",
                            "requirement_text": "T",
                            "confidence": 0.9,
                        }
                    ]
                )

        return _Resp()

    monkeypatch.setattr(mod.httpx.AsyncClient, "post", _fake_post)
    asyncio.run(mod.extract_requirements_with_ai([chunk], conn=fake_conn))

    assert captured_payloads[0]["response_format"] == {"type": "json_object"}


def test_passes_stream_flag_to_ai_gateway(monkeypatch, fake_conn) -> None:
    _patch_agent_config(monkeypatch)
    chunk = _chunk(text="测试")

    async def _handler(prompt, primary, fallback):
        return _ai_response([])

    captured = _patch_call_ai(monkeypatch, _handler)
    asyncio.run(
        mod.extract_requirements_for_batch(
            [chunk],
            conn=fake_conn,
            source_file="招标文件.docx",
            stream=True,
        )
    )

    assert captured["calls"][0]["stream"] is True


def test_invokes_on_batch_persisted_per_batch(monkeypatch, fake_conn) -> None:
    """Incremental persistence: callback fires once per batch with requirements."""
    _patch_agent_config(monkeypatch)
    chunk_a = _chunk(text="A 条款", source_file="A.docx")
    chunk_b = _chunk(text="B 条款", source_file="B.docx")

    async def _handler(prompt, primary, fallback):
        target = chunk_a if str(chunk_a["id"]) in prompt else chunk_b
        return _ai_response(
            [
                {
                    "source_chunk_id": str(target["id"]),
                    "category": "technical",
                    "title": "T",
                    "requirement_text": "T",
                    "confidence": 0.9,
                }
            ]
        )

    _patch_call_ai(monkeypatch, _handler)
    persisted_calls: list[list[mod.AiExtractedRequirement]] = []

    async def _persist(reqs):
        persisted_calls.append(list(reqs))

    summary = asyncio.run(
        mod.extract_requirements_with_ai(
            [chunk_a, chunk_b],
            conn=fake_conn,
            concurrency=2,
            on_batch_persisted=_persist,
        )
    )

    assert len(summary.requirements) == 2
    assert len(persisted_calls) == 2
    persisted_ids = {req.source_chunk_id for batch in persisted_calls for req in batch}
    assert persisted_ids == {str(chunk_a["id"]), str(chunk_b["id"])}


def test_fast_prefilter_drops_non_candidate_chunks_before_prompt(monkeypatch, fake_conn) -> None:
    _patch_agent_config(monkeypatch)
    noisy_chunk = _chunk(text="项目背景与总体概述。", source_locator="paragraph:1")
    candidate_chunk = _chunk(text="投标人应具备有效资质并提交证明材料。", source_locator="paragraph:2")

    async def _handler(prompt, primary, fallback):
        assert str(noisy_chunk["id"]) not in prompt
        assert str(candidate_chunk["id"]) in prompt
        return _ai_response(
            [
                {
                    "source_chunk_id": str(candidate_chunk["id"]),
                    "category": "qualification",
                    "title": "资格要求",
                    "requirement_text": "投标人应具备有效资质并提交证明材料。",
                    "confidence": 0.91,
                }
            ]
        )

    _patch_call_ai(monkeypatch, _handler)
    summary = asyncio.run(
        mod.extract_requirements_for_batch(
            [noisy_chunk, candidate_chunk],
            conn=fake_conn,
            source_file="普通附件.docx",
            quality_policy="flash_extract",
        )
    )

    assert len(summary.requirements) == 1
    assert summary.batches[0].candidate_chunk_count == 1
    assert summary.batches[0].prefilter_dropped_chunks == 1


def test_fast_prefilter_keeps_top_chunks_when_no_positive_signal(monkeypatch, fake_conn) -> None:
    _patch_agent_config(monkeypatch)
    chunks = [
        _chunk(text=f"普通说明 {index}", source_locator=f"paragraph:{index}")
        for index in range(12)
    ]

    async def _handler(prompt, primary, fallback):
        count = sum(1 for chunk in chunks if str(chunk["id"]) in prompt)
        assert count == 8
        return _ai_response([])

    _patch_call_ai(monkeypatch, _handler)
    summary = asyncio.run(
        mod.extract_requirements_for_batch(
            chunks,
            conn=fake_conn,
            source_file="普通附件.docx",
            quality_policy="flash_extract",
        )
    )

    assert summary.batches[0].candidate_chunk_count == 8
    assert summary.batches[0].prefilter_dropped_chunks == 4


def test_table_or_critical_policy_uses_table_prompt_variant(monkeypatch, fake_conn) -> None:
    _patch_agent_config(monkeypatch)
    table_chunk = _chunk(
        text="",
        table_rows=[["评分项", "分值"], ["业绩", "10分"]],
        source_locator="table:1",
    )

    async def _handler(prompt, primary, fallback):
        assert "抽取模式：table" in prompt
        assert "资格表、评分表、报价参考表" in prompt
        return _ai_response([])

    _patch_call_ai(monkeypatch, _handler)
    summary = asyncio.run(
        mod.extract_requirements_for_batch(
            [table_chunk],
            conn=fake_conn,
            source_file="评分表.xlsx",
            quality_policy="table_or_critical_extract",
        )
    )

    assert len(summary.batches) == 1


def test_table_or_critical_policy_uses_critical_prompt_variant_without_table(monkeypatch, fake_conn) -> None:
    _patch_agent_config(monkeypatch)
    chunk = _chunk(text="投标人不得存在废标情形。", source_locator="paragraph:3")

    async def _handler(prompt, primary, fallback):
        assert "抽取模式：critical" in prompt
        assert "重点覆盖资格、评分、否决、废标、递交、技术规范" in prompt
        return _ai_response([])

    _patch_call_ai(monkeypatch, _handler)
    summary = asyncio.run(
        mod.extract_requirements_for_batch(
            [chunk],
            conn=fake_conn,
            source_file="关键条款.docx",
            quality_policy="table_or_critical_extract",
        )
    )

    assert len(summary.batches) == 1
