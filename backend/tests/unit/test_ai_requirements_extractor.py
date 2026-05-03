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


def _patch_agent_config(monkeypatch, *, enabled: bool = True) -> None:
    config = SimpleNamespace(
        enabled=enabled,
        base_url="https://api.deepseek.com/v1",
        api_key="sk-test",
        primary_model="deepseek-v4-pro",
        fallback_base_url="https://api.deepseek.com/v1",
        fallback_api_key="sk-test",
        fallback_model="deepseek-v4-flash",
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

    async def _fake(client, *, prompt, primary_override, fallback_override):
        captured["calls"].append(
            {
                "prompt": prompt,
                "primary_override": primary_override,
                "fallback_override": fallback_override,
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
    assert primary["extra_body"] == {"reasoning_effort": "max"}


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
