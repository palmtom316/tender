# 招标 AI 抽取收尾合并实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 2026-05-02 升级计划与 2026-05-03 异步架构计划中所有未关闭的工作合并为一份可执行清单,跑通包 1 端到端并补齐前端进度面板,使招标 AI 抽取从「单测齐备」进入「真实可用」。

**Architecture:** 后端 run/batch 异步抽取主架构已落地(planner / repo / Celery worker / 5 个 REST API / dropped_invalid / model_policy / needs_review),本计划只做增量收尾:① AI Gateway strict tool schema 兼容性 spike;② worker 二阶段失败重试(缩批 → 升模型);③ 高价值 batch 空输出自动复核;④ 前端 AI 抽取进度面板;⑤ 端到端真实跑包 1 + 评分表 + 摘要并写入验收报告。

**Tech Stack:** Python 3.12 / FastAPI / Celery / psycopg / OpenAI SDK(对接 DeepSeek V4)/ React 18 / TanStack Query / vitest / pytest。

---

## 0. 前置背景与上游计划

本计划取代以下两份计划中尚未关闭的条目,执行完毕后两份原计划可以归档:

- `docs/plans/2026-05-02-tender-ai-extraction-upgrade-plan.md` — Phase 2 端到端 / 质量评估、Phase 4 前端 e2e 手测、Phase 5 端到端
- `docs/plans/2026-05-03-deepseek-v4-tender-extraction-architecture-plan.md` — Phase 3 strict tool schema、Phase 4 重试与复核策略、Phase 5 前端进度面板与端到端

按代码现状(2026-05-04)已完成的内容**不再**在本计划重复:

- 0033/0034/0035 三个 alembic migration 全部已落库
- `TenderAiExtractionRepository`、`ai_extraction_planner.py`、`ai_requirements_extractor.py`、`tasks_extract.py`、`tender_facts_extractor.py`、`scoring_extractor.py` 全部已实现并有单测
- 5 个 run / batch REST API 已上线(`backend/tender_backend/api/tender_documents.py`)
- AI Gateway 已支持 `response_format` / `stream` / `extra_body`(`ai_gateway/tender_ai_gateway/api/chat.py:28-29`、`fallback.py:129-180`)
- `DEFAULT_MODEL_POLICY = "v4_flash_then_pro"` 已实现 high_value 文件路由(`ai_extraction_planner.py:10,122,135`)
- `dropped_invalid` 字段已贯穿 extractor → worker → batch metadata(`ai_requirements_extractor.py:346,433` + `tasks_extract.py:115`)
- `needs_review` 状态已在 repo 中(`tender_ai_extraction_repo.py:13,134,150,260`)
- 前端摘要卡 / SourceChunkViewer / 评分表 UI 已合入(commit `52b8961`、`0d22872`)
- Frontend 单测已绿(2026-05-04 修复 `StandardSearchCard.test.tsx` / `StandardViewerModal.test.tsx` 文案漂移后)

**已知尚未完成的工作清单(本计划覆盖):**

| 编号 | 内容 | 来源 |
|---|---|---|
| T1 | DeepSeek V4 strict tool schema 兼容性 spike | A.Phase 3 |
| T2 | Worker 二阶段失败重试:首次缩批降并发 → 二次升 pro/max | A.Phase 4 |
| T3 | 高价值 batch 空输出自动复核 | A.Phase 4 |
| T4 | 后端 `GET /tender-ai-extraction-runs/{run_id}` 暴露文件级覆盖率 | A.Phase 5 |
| T5 | 前端 `lib/api` 增加 AI 抽取 run 类型与 fetcher | A.Phase 5 |
| T6 | 前端 `AiExtractionRunPanel` 组件 | A.Phase 5 |
| T7 | 前端在招标文件详情页接入进度面板 | A.Phase 5 |
| T8 | 真实端到端:对包 1 跑 requirements 抽取并产出验收报告 | A.Phase 1-2 验收 + B.Phase 2 |
| T9 | 前 20 条 AI 抽取人工质量评估 | B.Phase 2 |
| T10 | SourceChunkViewer 前端手测纪录 | B.Phase 4 |
| T11 | 评分表与摘要端到端 | B.Phase 3 / B.Phase 5 |

**Out of scope(明确不做):**

- 引入第三家模型供应商(本计划只针对 DeepSeek V4)。
- 把 1M context 整包塞一次请求的尝试(架构计划已明确仍保留 batch checkpoint)。
- 前端整体重构。
- AI 编写(章节生成)模型策略调整 — 走另一个工单。

---

## 1. 文件结构与责任分布

新增文件:

- `ai_gateway/tests/spike/test_strict_tool_schema_spike.py` — DeepSeek V4 strict tool 兼容性 spike(可被 pytest -m spike 跳过)
- `backend/tender_backend/services/extract_service/retry_policy.py` — 二阶段重试策略纯函数模块
- `backend/tests/unit/test_retry_policy.py` — 重试策略单测
- `backend/tests/unit/test_tasks_extract_retry.py` — Worker 重试集成单测(用 fake repo)
- `backend/tests/unit/test_high_value_review.py` — 高价值空输出复核单测
- `frontend/src/modules/tender/api/aiExtractionRuns.ts` — fetcher
- `frontend/src/modules/tender/api/aiExtractionRuns.test.ts`
- `frontend/src/modules/tender/components/AiExtractionRunPanel.tsx` — 顶层组件
- `frontend/src/modules/tender/components/AiExtractionRunPanel.test.tsx`
- `frontend/src/modules/tender/components/AiExtractionRunPanel.css`
- `scripts/e2e/run_package_1_ai_extraction.py` — 端到端触发脚本
- `docs/reports/2026-05-04-package-1-ai-extraction-acceptance.md` — 端到端验收报告
- `docs/reports/2026-05-04-ai-extraction-quality-sample.md` — 质量评估抽样报告
- `docs/reports/2026-05-04-source-chunk-viewer-manual-test.md` — UI 手测记录

修改文件:

- `backend/tender_backend/workers/tasks_extract.py` — 调度时调用 retry_policy + 高价值复核分支
- `backend/tender_backend/db/repositories/tender_ai_extraction_repo.py` — 新增 batch 复核入队 / 文件覆盖率聚合查询
- `backend/tender_backend/api/tender_documents.py` — `GET /tender-ai-extraction-runs/{run_id}` 输出 `file_coverage[]`
- `backend/tender_backend/api/dto.py`(若不存在则在 `tender_documents.py` 内的 Pydantic 模型上扩展)
- `frontend/src/modules/tender/pages/TenderDocumentDetailPage.tsx`(或当前等价路由组件)— 在合适位置挂接 `AiExtractionRunPanel`

---

## Task 1 — DeepSeek V4 strict tool schema 兼容性 spike

**Goal:** 用最小代价回答「strict tool calls 在 DeepSeek V4 是否可用」,产出二选一结论(改用 strict tool / 维持现状 JSON Output)。Spike 只跑一次,结论文档化即可,不强制实现到主路径。

**Files:**

- Create: `ai_gateway/tests/spike/test_strict_tool_schema_spike.py`
- Modify: `ai_gateway/pyproject.toml` 加 `markers = ["spike: smoke test that hits real DeepSeek API"]`(若已配置 pytest markers 则追加;若没有 markers 配置就新增)
- Create: `docs/reports/2026-05-04-deepseek-v4-strict-tool-spike.md`

- [ ] **Step 1: 写 spike 测试骨架**

```python
# ai_gateway/tests/spike/test_strict_tool_schema_spike.py
"""DeepSeek V4 strict tool schema compatibility spike.

Run manually:
    DEEPSEEK_API_KEY=... pytest -m spike ai_gateway/tests/spike/test_strict_tool_schema_spike.py -s

This test is excluded from CI; it is a one-shot spike documented in
docs/reports/2026-05-04-deepseek-v4-strict-tool-spike.md.
"""
from __future__ import annotations

import json
import os

import pytest
from openai import OpenAI

pytestmark = pytest.mark.spike

_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "emit_requirements",
        "description": "Emit extracted tender requirements with stable schema.",
        "strict": True,
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": ["requirements", "batch_quality"],
            "properties": {
                "requirements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["source_chunk_id", "category", "title", "requirement_text"],
                        "properties": {
                            "source_chunk_id": {"type": "string"},
                            "category": {
                                "type": "string",
                                "enum": ["qualification", "technical", "business", "scoring"],
                            },
                            "title": {"type": "string"},
                            "requirement_text": {"type": "string"},
                        },
                    },
                },
                "batch_quality": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["has_requirements"],
                    "properties": {"has_requirements": {"type": "boolean"}},
                },
            },
        },
    },
}


def test_v4_pro_accepts_strict_tool_call() -> None:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        pytest.skip("DEEPSEEK_API_KEY not configured for spike")

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    completion = client.chat.completions.create(
        model="deepseek-v4-pro",
        messages=[
            {"role": "system", "content": "Emit one fake requirement using the tool."},
            {"role": "user", "content": "chunk_id=abc, content='投标人须具有 ISO9001'"},
        ],
        tools=[_TOOL_SCHEMA],
        tool_choice={"type": "function", "function": {"name": "emit_requirements"}},
    )
    tool_calls = completion.choices[0].message.tool_calls or []
    assert tool_calls, "model returned no tool calls"
    payload = json.loads(tool_calls[0].function.arguments)
    assert payload["requirements"], "strict tool call returned empty requirements"
    assert payload["requirements"][0]["category"] in {
        "qualification",
        "technical",
        "business",
        "scoring",
    }
```

- [ ] **Step 2: 配置 pytest spike marker 跳过 CI**

确认 `ai_gateway/pyproject.toml`(若不存在则到 `setup.cfg` / `pytest.ini`)中追加:

```toml
[tool.pytest.ini_options]
markers = [
    "spike: optional spike tests against real DeepSeek API; not run in CI",
]
addopts = "-m 'not spike'"
```

如果文件已有 `[tool.pytest.ini_options]`,只追加 markers 与 addopts,不要覆盖。

- [ ] **Step 3: 验证默认 pytest 仍跳过 spike**

Run: `cd ai_gateway && ../.venv/bin/pytest -q`
Expected: `14 passed`(或更多,但 spike 文件应被跳过,terminal 不应出现 strict_tool_schema_spike)。

- [ ] **Step 4: 真实跑一次 spike 并记录结论**

Run(本机有 DEEPSEEK_API_KEY 时):

```bash
DEEPSEEK_API_KEY=... cd ai_gateway && ../.venv/bin/pytest -m spike tests/spike/test_strict_tool_schema_spike.py -s
```

按以下结构填写 `docs/reports/2026-05-04-deepseek-v4-strict-tool-spike.md`:

```markdown
# DeepSeek V4 strict tool schema 兼容性 spike 结论

> **执行日期:** 2026-05-04
> **执行命令:** 见 `ai_gateway/tests/spike/test_strict_tool_schema_spike.py`

## 1. 模型 / 参数

- model: `deepseek-v4-pro`
- tool_choice: forced function call `emit_requirements`
- strict: true
- additionalProperties: false / required 全字段

## 2. 真实响应摘要

- HTTP 状态:
- 是否返回 tool_calls:
- arguments JSON 是否合法:
- arguments 是否符合 strict 约束(无多余字段、无类型漂移、enum 合法):

## 3. 结论

二选一:

- ✅ 兼容 → 下一阶段把 `extract_tender_requirements_strict` profile 接入 strict tool path,fallback 仍保留 JSON Output。
- ❌ 不兼容 → 继续维持 JSON Output,本计划 T1 关闭并把结论记入此报告;不再投入。

## 4. 后续计划

(若兼容)新增工单:把 strict tool 接入 fallback.py 的实现路径与默认 task_type 路由 — 不在本计划内。
```

- [ ] **Step 5: 提交**

```bash
git add ai_gateway/tests/spike/test_strict_tool_schema_spike.py \
        ai_gateway/pyproject.toml \
        docs/reports/2026-05-04-deepseek-v4-strict-tool-spike.md
git commit -m "spike: deepseek v4 strict tool schema compatibility check"
```

---

## Task 2 — Worker 二阶段失败重试策略

**Goal:** 实现 batch 失败时的两段升级:第一次失败 → 把 chunk_ids 二分拆批 + 标记 `retry_count=1` 重新入队;第二次失败 → 升级到 `deepseek-v4-pro` + `reasoning_effort=max` 重试;第三次失败 → 进入 `needs_review`。当前 `tasks_extract.py:99-126` 只在内部计数,没有真正的拆批/升模型。

**Files:**

- Create: `backend/tender_backend/services/extract_service/retry_policy.py`
- Create: `backend/tests/unit/test_retry_policy.py`
- Modify: `backend/tender_backend/workers/tasks_extract.py`
- Modify: `backend/tender_backend/db/repositories/tender_ai_extraction_repo.py`(增加拆批方法)
- Create: `backend/tests/unit/test_tasks_extract_retry.py`

- [ ] **Step 1: 写 retry_policy 单测**

```python
# backend/tests/unit/test_retry_policy.py
import pytest

from tender_backend.services.extract_service.retry_policy import (
    RetryAction,
    decide_retry_action,
)


def test_first_failure_splits_batch_when_more_than_one_chunk() -> None:
    action = decide_retry_action(
        retry_count=0, chunk_count=8, model="deepseek-v4-flash", high_value=False,
    )
    assert action == RetryAction(kind="split", new_model=None, reasoning_effort=None)


def test_first_failure_on_single_chunk_escalates_to_pro() -> None:
    action = decide_retry_action(
        retry_count=0, chunk_count=1, model="deepseek-v4-flash", high_value=False,
    )
    assert action == RetryAction(
        kind="escalate", new_model="deepseek-v4-pro", reasoning_effort="max",
    )


def test_second_failure_escalates_to_pro_max() -> None:
    action = decide_retry_action(
        retry_count=1, chunk_count=4, model="deepseek-v4-flash", high_value=False,
    )
    assert action == RetryAction(
        kind="escalate", new_model="deepseek-v4-pro", reasoning_effort="max",
    )


def test_third_failure_returns_needs_review() -> None:
    action = decide_retry_action(
        retry_count=2, chunk_count=4, model="deepseek-v4-pro", high_value=True,
    )
    assert action == RetryAction(kind="needs_review", new_model=None, reasoning_effort=None)


def test_high_value_first_failure_skips_split() -> None:
    """高价值文件不拆批,直接升模型,以保证语义完整。"""
    action = decide_retry_action(
        retry_count=0, chunk_count=8, model="deepseek-v4-flash", high_value=True,
    )
    assert action == RetryAction(
        kind="escalate", new_model="deepseek-v4-pro", reasoning_effort="max",
    )
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd backend && ../.venv/bin/pytest tests/unit/test_retry_policy.py -q`
Expected: 全部 fail, ImportError on `retry_policy`。

- [ ] **Step 3: 实现 retry_policy 模块**

```python
# backend/tender_backend/services/extract_service/retry_policy.py
"""Decide what to do when an AI extraction batch fails.

Two-stage escalation:
- 1st failure: split a multi-chunk batch in half (普通文件) or escalate to
  v4-pro/max immediately (高价值文件 / 单 chunk batch).
- 2nd failure: escalate to v4-pro + reasoning_effort=max.
- 3rd+ failure: stop retrying, mark needs_review for human triage.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ActionKind = Literal["split", "escalate", "needs_review"]


@dataclass(frozen=True)
class RetryAction:
    kind: ActionKind
    new_model: str | None
    reasoning_effort: str | None


_ESCALATE_PRO_MAX = RetryAction(
    kind="escalate", new_model="deepseek-v4-pro", reasoning_effort="max",
)
_NEEDS_REVIEW = RetryAction(kind="needs_review", new_model=None, reasoning_effort=None)


def decide_retry_action(
    *, retry_count: int, chunk_count: int, model: str, high_value: bool,
) -> RetryAction:
    if retry_count >= 2:
        return _NEEDS_REVIEW
    if retry_count == 1:
        return _ESCALATE_PRO_MAX
    # First failure
    if high_value or chunk_count <= 1:
        return _ESCALATE_PRO_MAX
    return RetryAction(kind="split", new_model=None, reasoning_effort=None)
```

- [ ] **Step 4: 跑测试看通过**

Run: `cd backend && ../.venv/bin/pytest tests/unit/test_retry_policy.py -q`
Expected: `5 passed`。

- [ ] **Step 5: 在 repo 中加拆批方法**

在 `backend/tender_backend/db/repositories/tender_ai_extraction_repo.py` 增加:

```python
def split_batch_in_half(
    self,
    conn,
    *,
    batch_id: UUID,
) -> list[UUID]:
    """Split a batch's chunk_ids into two new pending batches and mark the
    original as ``skipped`` with reason ``split_for_retry``. Returns the
    new batch ids in order. Caller commits."""
    batch = self.get_batch(conn, batch_id=batch_id)
    if batch is None:
        raise ValueError(f"batch not found: {batch_id}")
    chunk_ids = list(batch.get("chunk_ids_json") or [])
    if len(chunk_ids) < 2:
        raise ValueError("cannot split a batch with fewer than 2 chunks")
    midpoint = len(chunk_ids) // 2
    halves = [chunk_ids[:midpoint], chunk_ids[midpoint:]]
    new_ids: list[UUID] = []
    next_index = self._next_batch_index(conn, run_id=batch["run_id"], source_file=batch["source_file"])
    for offset, half in enumerate(halves):
        new_id = self.create_batch(
            conn,
            run_id=batch["run_id"],
            tender_document_id=batch["tender_document_id"],
            tender_document_file_id=batch.get("tender_document_file_id"),
            source_file=batch["source_file"],
            batch_index=next_index + offset,
            chunk_ids=half,
            chunk_count=len(half),
            input_char_count=int((batch.get("input_char_count") or 0) * len(half) / max(len(chunk_ids), 1)),
            estimated_input_tokens=int((batch.get("estimated_input_tokens") or 0) * len(half) / max(len(chunk_ids), 1)),
            model=batch["model"],
            reasoning_effort=batch.get("reasoning_effort"),
            response_format=batch.get("response_format") or "json_object",
            metadata_json={**(batch.get("metadata_json") or {}), "split_from": str(batch_id)},
        )
        new_ids.append(new_id)
    self.mark_batch_skipped(
        conn,
        batch_id=batch_id,
        skip_reason="split_for_retry",
    )
    return new_ids
```

如果 `_next_batch_index` 不存在,在同一文件加一个内部 helper 查询 `MAX(batch_index)` + 1。`mark_batch_skipped` / `create_batch` 是已有方法,如果命名不同请按现有 API 调用。

- [ ] **Step 6: 改 worker 接入 retry_policy**

修改 `backend/tender_backend/workers/tasks_extract.py:99-126` 区段,把现有的 `mark_batch_failed(retryable=...)` 替换为:

```python
from tender_backend.services.extract_service.retry_policy import decide_retry_action

# 在 except / failed 分支内:
action = decide_retry_action(
    retry_count=int(batch.get("retry_count") or 0),
    chunk_count=int(batch.get("chunk_count") or 0),
    model=batch.get("model") or "deepseek-v4-flash",
    high_value=bool((batch.get("metadata_json") or {}).get("high_value")),
)
if action.kind == "needs_review":
    _ai_repo.mark_batch_failed(
        conn,
        batch_id=batch_uuid,
        error_type=usage.error_type if usage else "AiExtractionError",
        error_message=usage.error_type if usage else "AI extraction batch failed",
        retryable=False,  # 触发 needs_review 分支
    )
elif action.kind == "split":
    new_ids = _ai_repo.split_batch_in_half(conn, batch_id=batch_uuid)
    for nid in new_ids:
        run_tender_ai_extraction_batch.delay(batch_id=str(nid))
elif action.kind == "escalate":
    _ai_repo.mark_batch_for_retry(
        conn,
        batch_id=batch_uuid,
        new_model=action.new_model,
        new_reasoning_effort=action.reasoning_effort,
    )
    run_tender_ai_extraction_batch.delay(batch_id=str(batch_uuid))
```

`mark_batch_for_retry` 若不存在,在 repo 中新增:它把 `status='pending'`、`retry_count += 1`、`model = new_model`、`reasoning_effort = new_reasoning_effort` 写回。

- [ ] **Step 7: 写 worker 集成单测**

```python
# backend/tests/unit/test_tasks_extract_retry.py
"""End-to-end-ish test using a fake repo + monkeypatched extract_requirements_for_batch."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# 与既有 worker 测试一致,使用项目里已有的 fake fixtures
# 若项目有 backend/tests/conftest.py 的 fake_repo / fake_pool fixture 直接复用


def test_split_action_creates_two_batches(monkeypatch, fake_pool, fake_ai_repo):
    """First failure on a multi-chunk普通 batch should split into 2 new batches."""
    fake_ai_repo.add_batch(
        id="b1", chunk_count=8, retry_count=0, model="deepseek-v4-flash",
        high_value=False, status="running",
    )
    monkeypatch.setattr(
        "tender_backend.workers.tasks_extract._run_async",
        MagicMock(side_effect=RuntimeError("simulated upstream failure")),
    )

    from tender_backend.workers.tasks_extract import run_tender_ai_extraction_batch
    run_tender_ai_extraction_batch(batch_id="b1")

    assert fake_ai_repo.split_calls == [{"batch_id": "b1"}]
    assert len(fake_ai_repo.enqueued_batches) == 2


def test_second_failure_escalates_to_pro(monkeypatch, fake_pool, fake_ai_repo):
    fake_ai_repo.add_batch(
        id="b2", chunk_count=4, retry_count=1, model="deepseek-v4-flash",
        high_value=False, status="running",
    )
    monkeypatch.setattr(
        "tender_backend.workers.tasks_extract._run_async",
        MagicMock(side_effect=RuntimeError("simulated upstream failure")),
    )
    from tender_backend.workers.tasks_extract import run_tender_ai_extraction_batch
    run_tender_ai_extraction_batch(batch_id="b2")

    assert fake_ai_repo.last_retry_update["new_model"] == "deepseek-v4-pro"
    assert fake_ai_repo.last_retry_update["new_reasoning_effort"] == "max"
    assert fake_ai_repo.enqueued_batches == ["b2"]


def test_third_failure_marks_needs_review(monkeypatch, fake_pool, fake_ai_repo):
    fake_ai_repo.add_batch(
        id="b3", chunk_count=4, retry_count=2, model="deepseek-v4-pro",
        high_value=True, status="running",
    )
    monkeypatch.setattr(
        "tender_backend.workers.tasks_extract._run_async",
        MagicMock(side_effect=RuntimeError("simulated upstream failure")),
    )
    from tender_backend.workers.tasks_extract import run_tender_ai_extraction_batch
    run_tender_ai_extraction_batch(batch_id="b3")

    assert fake_ai_repo.last_failed["retryable"] is False
    assert fake_ai_repo.enqueued_batches == []
```

注:`fake_pool` / `fake_ai_repo` fixture 在 `backend/tests/conftest.py` 内对齐既有 worker 测试风格。如果当前没有这两个 fixture,实现一个最小 in-memory `FakeAiRepo` 暴露:`get_run/get_batch/mark_batch_running/mark_batch_succeeded/mark_batch_failed/refresh_run_progress/split_batch_in_half/mark_batch_for_retry` 并把 `_ai_repo` 替换为它。

- [ ] **Step 8: 跑全部 retry 测试**

Run: `cd backend && ../.venv/bin/pytest tests/unit/test_retry_policy.py tests/unit/test_tasks_extract_retry.py -q`
Expected: `8 passed`。

- [ ] **Step 9: 跑 backend 全量回归**

Run: `cd backend && ../.venv/bin/pytest -q`
Expected: 之前的 `475 passed, 49 skipped` + 本次新增 8 用例 → `483 passed, 49 skipped`(±数字以实际为准,关键是不能减少现有通过数)。

- [ ] **Step 10: 提交**

```bash
git add backend/tender_backend/services/extract_service/retry_policy.py \
        backend/tender_backend/workers/tasks_extract.py \
        backend/tender_backend/db/repositories/tender_ai_extraction_repo.py \
        backend/tests/unit/test_retry_policy.py \
        backend/tests/unit/test_tasks_extract_retry.py
git commit -m "feat: two-stage retry for tender ai extraction batches"
```

---

## Task 3 — 高价值 batch 空输出自动复核

**Goal:** 当 batch 状态成功落库但 `extracted_requirements=0` 且 `metadata_json.high_value=true` 时,自动用 `deepseek-v4-pro` + `reasoning_effort=max` 复核一次。复核仍 0 → 标记 `needs_review`,而不是默默 success。

**Files:**

- Modify: `backend/tender_backend/workers/tasks_extract.py`
- Create: `backend/tests/unit/test_high_value_review.py`

- [ ] **Step 1: 写测试先**

```python
# backend/tests/unit/test_high_value_review.py
from unittest.mock import MagicMock


def test_high_value_zero_extraction_triggers_review(monkeypatch, fake_pool, fake_ai_repo):
    fake_ai_repo.add_batch(
        id="b-hv-1", chunk_count=10, retry_count=0,
        model="deepseek-v4-flash", high_value=True, status="running",
        metadata_review_state="initial",
    )
    monkeypatch.setattr(
        "tender_backend.workers.tasks_extract._run_async",
        MagicMock(return_value=_summary(extracted=0)),
    )
    from tender_backend.workers.tasks_extract import run_tender_ai_extraction_batch
    run_tender_ai_extraction_batch(batch_id="b-hv-1")

    assert fake_ai_repo.last_retry_update["new_model"] == "deepseek-v4-pro"
    assert fake_ai_repo.last_retry_update["new_reasoning_effort"] == "max"
    assert fake_ai_repo.last_metadata_update["review_state"] == "review_pending"


def test_high_value_review_zero_again_marks_needs_review(monkeypatch, fake_pool, fake_ai_repo):
    fake_ai_repo.add_batch(
        id="b-hv-2", chunk_count=10, retry_count=1,
        model="deepseek-v4-pro", high_value=True, status="running",
        metadata_review_state="review_pending",
    )
    monkeypatch.setattr(
        "tender_backend.workers.tasks_extract._run_async",
        MagicMock(return_value=_summary(extracted=0)),
    )
    from tender_backend.workers.tasks_extract import run_tender_ai_extraction_batch
    run_tender_ai_extraction_batch(batch_id="b-hv-2")

    assert fake_ai_repo.last_marked_status == "needs_review"


def _summary(*, extracted: int):
    """Build a minimal BatchSummary stub matching ai_requirements_extractor."""
    summary = MagicMock()
    summary.batches = [MagicMock(failed=False, dropped_invalid=0, latency_ms=1234,
                                 resolved_model="deepseek-v4-flash")]
    summary.total_input_tokens = 1000
    summary.total_output_tokens = 0
    return summary


def test_normal_value_zero_extraction_does_not_review(monkeypatch, fake_pool, fake_ai_repo):
    """普通文件 0 抽取条数仍视为成功 (batch_quality.has_requirements=false 由 extractor 决定)。"""
    fake_ai_repo.add_batch(
        id="b-nv-1", chunk_count=10, retry_count=0,
        model="deepseek-v4-flash", high_value=False, status="running",
    )
    monkeypatch.setattr(
        "tender_backend.workers.tasks_extract._run_async",
        MagicMock(return_value=_summary(extracted=0)),
    )
    from tender_backend.workers.tasks_extract import run_tender_ai_extraction_batch
    run_tender_ai_extraction_batch(batch_id="b-nv-1")

    assert fake_ai_repo.last_marked_status == "succeeded"
    assert fake_ai_repo.last_retry_update is None
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd backend && ../.venv/bin/pytest tests/unit/test_high_value_review.py -q`
Expected: 全部 fail(因为复核分支还没实现)。

- [ ] **Step 3: 在 worker `mark_batch_succeeded` 之前加复核分支**

定位 `tasks_extract.py:108-117`(`else: _ai_repo.mark_batch_succeeded(...)` 分支),在 `mark_batch_succeeded` 之前加入:

```python
review_state = (batch.get("metadata_json") or {}).get("review_state", "initial")
high_value = bool((batch.get("metadata_json") or {}).get("high_value"))
extracted_count = len(persisted)
needs_high_value_review = (
    high_value and extracted_count == 0 and review_state == "initial"
)

if needs_high_value_review:
    _ai_repo.mark_batch_for_retry(
        conn,
        batch_id=batch_uuid,
        new_model="deepseek-v4-pro",
        new_reasoning_effort="max",
        metadata_patch={"review_state": "review_pending"},
    )
    run_tender_ai_extraction_batch.delay(batch_id=str(batch_uuid))
elif high_value and extracted_count == 0 and review_state == "review_pending":
    _ai_repo.mark_batch_failed(
        conn,
        batch_id=batch_uuid,
        error_type="EmptyHighValueReview",
        error_message="高价值 batch 复核后仍 0 条 requirement",
        retryable=False,
    )
else:
    _ai_repo.mark_batch_succeeded(...)  # 维持现状
```

`mark_batch_for_retry` 需要支持 `metadata_patch` 参数(浅合并到 `metadata_json`),如果还没有则在 repo 中加 4 行。

- [ ] **Step 4: 跑全量 retry + review 测试**

Run: `cd backend && ../.venv/bin/pytest tests/unit/test_high_value_review.py tests/unit/test_tasks_extract_retry.py -q`
Expected: `6 passed`(3 + 3)。

- [ ] **Step 5: 跑 backend 全量回归**

Run: `cd backend && ../.venv/bin/pytest -q`
Expected: 通过数比上轮新增 3。

- [ ] **Step 6: 提交**

```bash
git add backend/tender_backend/workers/tasks_extract.py \
        backend/tender_backend/db/repositories/tender_ai_extraction_repo.py \
        backend/tests/unit/test_high_value_review.py
git commit -m "feat: auto-review zero-output high-value tender ai batches"
```

---

## Task 4 — `GET /tender-ai-extraction-runs/{run_id}` 暴露文件级覆盖率

**Goal:** 前端面板需要显示「文件名 / chunks / batches / requirements / 失败批次 / skip reason」。当前 `GET /tender-ai-extraction-runs/{run_id}` 只返回 run 级聚合。

**Files:**

- Modify: `backend/tender_backend/db/repositories/tender_ai_extraction_repo.py`
- Modify: `backend/tender_backend/api/tender_documents.py`
- Modify: `backend/tests/unit/test_tender_ai_extraction_repo.py`(若文件名不同请用 `grep -r "TenderAiExtractionRepository" backend/tests` 找)
- Modify: `backend/tests/integration/test_tender_documents_api.py` 或 `backend/tests/api/test_tender_documents.py`(任选已存在的招标文件 API 测试套件)

- [ ] **Step 1: 写 repo 单测**

```python
def test_aggregate_file_coverage_groups_by_source_file(repo, conn):
    # 假设已有 fixture 创建 1 个 run + 5 个 batch 跨 2 个文件
    coverage = repo.aggregate_file_coverage(conn, run_id=run_id)
    files = {row["source_file"]: row for row in coverage}
    assert files["招标文件.docx"]["batches"] == 3
    assert files["招标文件.docx"]["succeeded"] == 2
    assert files["招标文件.docx"]["failed"] == 1
    assert files["招标文件.docx"]["extracted_requirements"] == 17
    assert files["签到表.docx"]["skipped"] == 1
    assert files["签到表.docx"]["skip_reason"] == "blank_signature_form"
```

- [ ] **Step 2: 实现 `aggregate_file_coverage`**

在 repo 中加一段 SQL 聚合:

```python
def aggregate_file_coverage(self, conn, *, run_id: UUID) -> list[dict]:
    sql = """
        SELECT
            source_file,
            COUNT(*) AS batches,
            COUNT(*) FILTER (WHERE status = 'succeeded') AS succeeded,
            COUNT(*) FILTER (WHERE status = 'failed') AS failed,
            COUNT(*) FILTER (WHERE status = 'needs_review') AS needs_review,
            COUNT(*) FILTER (WHERE status = 'skipped') AS skipped,
            SUM(chunk_count) AS chunks,
            SUM(extracted_requirements) AS extracted_requirements,
            MAX(skip_reason) FILTER (WHERE status = 'skipped') AS skip_reason
        FROM tender_ai_extraction_batch
        WHERE run_id = %s
        GROUP BY source_file
        ORDER BY source_file
    """
    with conn.cursor() as cur:
        cur.execute(sql, (run_id,))
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
```

- [ ] **Step 3: 把 file_coverage 接入 API 输出**

在 `tender_documents.py` 的 `get_tender_ai_extraction_run` 内,把 `aggregate_file_coverage` 结果挂到 response 的 `file_coverage` 字段。同步在该路由的 Pydantic 响应模型(应为 `TenderAiExtractionRunOut` 或类似名)增加:

```python
class TenderAiExtractionFileCoverage(BaseModel):
    source_file: str
    batches: int
    succeeded: int
    failed: int
    needs_review: int
    skipped: int
    chunks: int
    extracted_requirements: int
    skip_reason: str | None


class TenderAiExtractionRunOut(BaseModel):
    # 既有字段保留
    file_coverage: list[TenderAiExtractionFileCoverage] = []
```

- [ ] **Step 4: 写 API 单测**

```python
def test_get_run_returns_file_coverage(api_client, seeded_run):
    response = api_client.get(f"/api/tender-ai-extraction-runs/{seeded_run.id}")
    assert response.status_code == 200
    body = response.json()
    files = {f["source_file"]: f for f in body["file_coverage"]}
    assert files["招标文件.docx"]["succeeded"] >= 1
    assert "skip_reason" in files["签到表.docx"]
```

- [ ] **Step 5: 跑相关测试**

Run: `cd backend && ../.venv/bin/pytest tests/unit/test_tender_ai_extraction_repo.py -q`
Run: `cd backend && ../.venv/bin/pytest -k "tender_documents" -q`
Expected: 全绿。

- [ ] **Step 6: 提交**

```bash
git add backend/tender_backend/api/tender_documents.py \
        backend/tender_backend/db/repositories/tender_ai_extraction_repo.py \
        backend/tests/unit/test_tender_ai_extraction_repo.py \
        backend/tests/**/test_tender_documents*.py
git commit -m "feat: expose per-file coverage on tender ai extraction runs"
```

---

## Task 5 — 前端 AI 抽取 run API 类型与 fetcher

**Goal:** 把 5 个 run/batch 端点封装成可被组件调用的 fetcher,并暴露 TypeScript 类型。

**Files:**

- Create: `frontend/src/modules/tender/api/aiExtractionRuns.ts`
- Create: `frontend/src/modules/tender/api/aiExtractionRuns.test.ts`

- [ ] **Step 1: 写 fetcher 单测(用 MSW 或现有 fetch mock 风格)**

参照 `frontend/src/lib/api.ts`(找当前项目是用 fetch wrapper 还是 axios)的既有风格。最小测:

```typescript
// frontend/src/modules/tender/api/aiExtractionRuns.test.ts
import { describe, expect, it, vi } from "vitest";

import { fetchAiExtractionRun, retryFailedBatches } from "./aiExtractionRuns";

describe("aiExtractionRuns", () => {
  it("GET run returns parsed payload", async () => {
    const mockFetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "run-1", status: "running",
          total_batches: 10, succeeded_batches: 4, failed_batches: 1,
          skipped_batches: 0, file_coverage: [
            { source_file: "招标文件.docx", batches: 5, succeeded: 4, failed: 1,
              needs_review: 0, skipped: 0, chunks: 200,
              extracted_requirements: 30, skip_reason: null },
          ],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    const run = await fetchAiExtractionRun("run-1");
    expect(run.status).toBe("running");
    expect(run.file_coverage).toHaveLength(1);
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/tender-ai-extraction-runs/run-1"),
      expect.any(Object),
    );
  });

  it("POST retry-failed posts to the right path", async () => {
    const mockFetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ run_id: "run-1", reset_batches: 2 }),
        { status: 200, headers: { "content-type": "application/json" } }),
    );
    const result = await retryFailedBatches("run-1");
    expect(result.reset_batches).toBe(2);
    const [path, init] = mockFetch.mock.calls[0];
    expect(path).toContain("/api/tender-ai-extraction-runs/run-1/retry-failed");
    expect(init?.method).toBe("POST");
  });
});
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd frontend && ./node_modules/.bin/vitest run src/modules/tender/api/aiExtractionRuns.test.ts`
Expected: 模块不存在错误。

- [ ] **Step 3: 实现 fetcher**

```typescript
// frontend/src/modules/tender/api/aiExtractionRuns.ts
export type AiExtractionRunStatus =
  | "pending" | "running" | "completed" | "partial" | "failed" | "cancelled";

export type AiExtractionFileCoverage = {
  source_file: string;
  batches: number;
  succeeded: number;
  failed: number;
  needs_review: number;
  skipped: number;
  chunks: number;
  extracted_requirements: number;
  skip_reason: string | null;
};

export type AiExtractionRun = {
  id: string;
  status: AiExtractionRunStatus;
  total_batches: number;
  succeeded_batches: number;
  failed_batches: number;
  skipped_batches: number;
  total_chunks?: number;
  covered_chunks?: number;
  extracted_requirements?: number;
  total_input_tokens?: number;
  total_output_tokens?: number;
  file_coverage: AiExtractionFileCoverage[];
};

export type AiExtractionBatchStatus =
  | "pending" | "running" | "succeeded" | "failed" | "skipped" | "needs_review";

export type AiExtractionBatch = {
  id: string;
  source_file: string;
  batch_index: number;
  status: AiExtractionBatchStatus;
  chunk_count: number;
  model: string;
  reasoning_effort: string | null;
  retry_count: number;
  max_retries: number;
  extracted_requirements: number;
  dropped_invalid: number;
  error_type: string | null;
  error_message: string | null;
  skip_reason: string | null;
};

const BASE = "/api";

async function jsonOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export async function fetchAiExtractionRun(runId: string): Promise<AiExtractionRun> {
  return jsonOrThrow(await fetch(`${BASE}/tender-ai-extraction-runs/${runId}`, {
    headers: { accept: "application/json" },
  }));
}

export async function fetchAiExtractionBatches(
  runId: string,
  status?: AiExtractionBatchStatus,
): Promise<AiExtractionBatch[]> {
  const search = status ? `?status=${encodeURIComponent(status)}` : "";
  return jsonOrThrow(await fetch(
    `${BASE}/tender-ai-extraction-runs/${runId}/batches${search}`,
    { headers: { accept: "application/json" } },
  ));
}

export async function retryFailedBatches(
  runId: string,
): Promise<{ run_id: string; reset_batches: number }> {
  return jsonOrThrow(await fetch(
    `${BASE}/tender-ai-extraction-runs/${runId}/retry-failed`,
    { method: "POST", headers: { accept: "application/json" } },
  ));
}

export async function cancelExtractionRun(
  runId: string,
): Promise<{ run_id: string; cancelled: number }> {
  return jsonOrThrow(await fetch(
    `${BASE}/tender-ai-extraction-runs/${runId}/cancel`,
    { method: "POST", headers: { accept: "application/json" } },
  ));
}

export async function startAiExtractionRun(
  tenderDocumentId: string,
  body: { mode?: string; model_policy?: string; only_failed?: boolean } = {},
): Promise<{ run_id: string; status: AiExtractionRunStatus; total_batches: number }> {
  return jsonOrThrow(await fetch(
    `${BASE}/tender-documents/${tenderDocumentId}/ai-extraction-runs`,
    {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify(body),
    },
  ));
}
```

- [ ] **Step 4: 测试通过**

Run: `cd frontend && ./node_modules/.bin/vitest run src/modules/tender/api/aiExtractionRuns.test.ts`
Expected: `2 passed`。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/modules/tender/api/aiExtractionRuns.ts \
        frontend/src/modules/tender/api/aiExtractionRuns.test.ts
git commit -m "feat: tender ai extraction run api client"
```

---

## Task 6 — `AiExtractionRunPanel` 组件

**Goal:** 一个自给自足组件,接收 `runId` prop,显示 run 总览 + 文件覆盖表 + 失败批次列表 + 重试 / 取消按钮,5 秒轮询直到 run terminal。

**Files:**

- Create: `frontend/src/modules/tender/components/AiExtractionRunPanel.tsx`
- Create: `frontend/src/modules/tender/components/AiExtractionRunPanel.test.tsx`
- Create: `frontend/src/modules/tender/components/AiExtractionRunPanel.css`

- [ ] **Step 1: 写 React 组件单测**

```tsx
// frontend/src/modules/tender/components/AiExtractionRunPanel.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AiExtractionRunPanel } from "./AiExtractionRunPanel";

const { fetchRun, fetchBatches, retryFailed } = vi.hoisted(() => ({
  fetchRun: vi.fn(),
  fetchBatches: vi.fn(),
  retryFailed: vi.fn(),
}));

vi.mock("../api/aiExtractionRuns", () => ({
  fetchAiExtractionRun: fetchRun,
  fetchAiExtractionBatches: fetchBatches,
  retryFailedBatches: retryFailed,
}));

function withClient(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>;
}

describe("AiExtractionRunPanel", () => {
  it("renders summary, file coverage and failed batches", async () => {
    fetchRun.mockResolvedValueOnce({
      id: "run-1", status: "partial",
      total_batches: 5, succeeded_batches: 3, failed_batches: 1, skipped_batches: 1,
      file_coverage: [
        { source_file: "招标文件.docx", batches: 3, succeeded: 2, failed: 1,
          needs_review: 0, skipped: 0, chunks: 200,
          extracted_requirements: 30, skip_reason: null },
        { source_file: "签到表.docx", batches: 1, succeeded: 0, failed: 0,
          needs_review: 0, skipped: 1, chunks: 0,
          extracted_requirements: 0, skip_reason: "blank_signature_form" },
      ],
    });
    fetchBatches.mockResolvedValueOnce([
      { id: "b1", source_file: "招标文件.docx", batch_index: 2,
        status: "failed", chunk_count: 40, model: "deepseek-v4-pro",
        reasoning_effort: "max", retry_count: 2, max_retries: 3,
        extracted_requirements: 0, dropped_invalid: 0,
        error_type: "ReadError", error_message: "upstream timeout",
        skip_reason: null },
    ]);

    render(withClient(<AiExtractionRunPanel runId="run-1" />));

    expect(await screen.findByText("AI 抽取任务进度")).toBeInTheDocument();
    expect(screen.getByText(/部分完成/)).toBeInTheDocument();
    expect(screen.getByText("招标文件.docx")).toBeInTheDocument();
    expect(screen.getByText("blank_signature_form")).toBeInTheDocument();
    expect(screen.getByText("ReadError")).toBeInTheDocument();
  });

  it("clicks retry button to call retryFailedBatches", async () => {
    fetchRun.mockResolvedValue({
      id: "run-1", status: "partial",
      total_batches: 1, succeeded_batches: 0, failed_batches: 1, skipped_batches: 0,
      file_coverage: [],
    });
    fetchBatches.mockResolvedValue([]);
    retryFailed.mockResolvedValueOnce({ run_id: "run-1", reset_batches: 1 });

    render(withClient(<AiExtractionRunPanel runId="run-1" />));
    const button = await screen.findByRole("button", { name: "重试失败批次" });
    await userEvent.click(button);

    await waitFor(() => expect(retryFailed).toHaveBeenCalledWith("run-1"));
  });
});
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd frontend && ./node_modules/.bin/vitest run src/modules/tender/components/AiExtractionRunPanel.test.tsx`
Expected: 模块不存在。

- [ ] **Step 3: 实现组件**

```tsx
// frontend/src/modules/tender/components/AiExtractionRunPanel.tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  AiExtractionBatch, AiExtractionRunStatus,
  fetchAiExtractionBatches, fetchAiExtractionRun, retryFailedBatches,
} from "../api/aiExtractionRuns";
import "./AiExtractionRunPanel.css";

const STATUS_LABEL: Record<AiExtractionRunStatus, string> = {
  pending: "等待开始",
  running: "执行中",
  completed: "已完成",
  partial: "部分完成",
  failed: "失败",
  cancelled: "已取消",
};

function isTerminal(status: AiExtractionRunStatus): boolean {
  return status === "completed" || status === "failed" || status === "cancelled";
}

type AiExtractionRunPanelProps = {
  runId: string;
};

export function AiExtractionRunPanel({ runId }: AiExtractionRunPanelProps) {
  const queryClient = useQueryClient();

  const runQuery = useQuery({
    queryKey: ["ai-extraction-run", runId],
    queryFn: () => fetchAiExtractionRun(runId),
    refetchInterval: (data) => (data && isTerminal(data.status) ? false : 5000),
  });

  const failedBatchesQuery = useQuery({
    queryKey: ["ai-extraction-batches", runId, "failed"],
    queryFn: () => fetchAiExtractionBatches(runId, "failed"),
    refetchInterval: (data) => 5000,
  });

  const retry = useMutation({
    mutationFn: () => retryFailedBatches(runId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ai-extraction-run", runId] });
      queryClient.invalidateQueries({ queryKey: ["ai-extraction-batches", runId] });
    },
  });

  if (runQuery.isLoading) {
    return <div className="ai-run-panel" aria-busy>正在加载抽取任务...</div>;
  }
  if (runQuery.isError || !runQuery.data) {
    return <div className="ai-run-panel ai-run-panel--error">加载失败</div>;
  }
  const run = runQuery.data;
  const failed = failedBatchesQuery.data ?? [];

  return (
    <section className="ai-run-panel" aria-label="AI 抽取任务进度">
      <header className="ai-run-panel__header">
        <h3>AI 抽取任务进度</h3>
        <span className={`ai-run-panel__status ai-run-panel__status--${run.status}`}>
          {STATUS_LABEL[run.status]}
        </span>
      </header>

      <dl className="ai-run-panel__metrics">
        <div><dt>批次</dt><dd>{run.total_batches}</dd></div>
        <div><dt>成功</dt><dd>{run.succeeded_batches}</dd></div>
        <div><dt>失败</dt><dd>{run.failed_batches}</dd></div>
        <div><dt>跳过</dt><dd>{run.skipped_batches}</dd></div>
      </dl>

      <table className="ai-run-panel__file-table">
        <caption>文件覆盖</caption>
        <thead>
          <tr>
            <th>文件</th><th>chunks</th><th>批次</th>
            <th>成功</th><th>失败</th><th>需复核</th>
            <th>跳过</th><th>抽取条数</th><th>跳过原因</th>
          </tr>
        </thead>
        <tbody>
          {run.file_coverage.map((row) => (
            <tr key={row.source_file}>
              <td>{row.source_file}</td>
              <td>{row.chunks}</td>
              <td>{row.batches}</td>
              <td>{row.succeeded}</td>
              <td>{row.failed}</td>
              <td>{row.needs_review}</td>
              <td>{row.skipped}</td>
              <td>{row.extracted_requirements}</td>
              <td>{row.skip_reason ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {failed.length > 0 && (
        <div className="ai-run-panel__failed">
          <div className="ai-run-panel__failed-header">
            <h4>失败批次 ({failed.length})</h4>
            <button
              type="button"
              onClick={() => retry.mutate()}
              disabled={retry.isPending}
            >
              重试失败批次
            </button>
          </div>
          <ul>
            {failed.map((batch) => (
              <li key={batch.id}>
                <strong>{batch.source_file}#{batch.batch_index}</strong>{" "}
                <span>{batch.error_type}</span>
                <span> · 重试 {batch.retry_count}/{batch.max_retries}</span>
                {batch.error_message && (
                  <p className="ai-run-panel__error-message">{batch.error_message}</p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 4: 写最小 CSS**

```css
/* frontend/src/modules/tender/components/AiExtractionRunPanel.css */
.ai-run-panel { border: 1px solid var(--border, #ddd); padding: 16px; border-radius: 12px; }
.ai-run-panel--error { color: #d32f2f; }
.ai-run-panel__header { display: flex; justify-content: space-between; align-items: center; }
.ai-run-panel__metrics { display: flex; gap: 16px; margin: 12px 0; }
.ai-run-panel__metrics div { display: flex; flex-direction: column; }
.ai-run-panel__metrics dt { font-size: 12px; color: #666; }
.ai-run-panel__metrics dd { margin: 0; font-size: 18px; font-weight: 600; }
.ai-run-panel__status { padding: 2px 8px; border-radius: 999px; font-size: 12px; }
.ai-run-panel__status--running { background: #e3f2fd; color: #1565c0; }
.ai-run-panel__status--partial { background: #fff8e1; color: #ef6c00; }
.ai-run-panel__status--completed { background: #e8f5e9; color: #2e7d32; }
.ai-run-panel__status--failed { background: #ffebee; color: #c62828; }
.ai-run-panel__file-table { width: 100%; border-collapse: collapse; margin-top: 12px; }
.ai-run-panel__file-table th, .ai-run-panel__file-table td { border-bottom: 1px solid #eee; padding: 6px 8px; text-align: left; }
.ai-run-panel__failed { margin-top: 16px; }
.ai-run-panel__failed-header { display: flex; justify-content: space-between; align-items: center; }
.ai-run-panel__failed ul { padding-left: 16px; }
.ai-run-panel__error-message { color: #c62828; margin: 4px 0 8px; }
```

- [ ] **Step 5: 测试通过**

Run: `cd frontend && ./node_modules/.bin/vitest run src/modules/tender/components/AiExtractionRunPanel.test.tsx`
Expected: `2 passed`。

- [ ] **Step 6: 跑前端全量回归**

Run: `cd frontend && ./node_modules/.bin/vitest run`
Expected: 上一轮 9 passed + 本任务新增 2 + Task 5 新增 2 = `13 passed`(±)。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/modules/tender/components/AiExtractionRunPanel.tsx \
        frontend/src/modules/tender/components/AiExtractionRunPanel.test.tsx \
        frontend/src/modules/tender/components/AiExtractionRunPanel.css
git commit -m "feat: tender ai extraction run progress panel"
```

---

## Task 7 — 招标文件详情页接入进度面板

**Goal:** 在招标文件详情/要求确认页(已存在的页面,通过 grep 定位)中,如果存在最近的 ai-extraction run,渲染 `AiExtractionRunPanel`。

**Files:**

- Modify: 通过 `grep -r "ai-extract-requirements\|ExtractRequirements\|RequirementsContent" frontend/src --include='*.tsx'` 定位的页面组件,通常位于 `frontend/src/modules/tender/pages/` 或 `frontend/src/routes/`
- Modify: `frontend/src/lib/api.ts`(或等价位置)— 增加 `fetchLatestAiExtractionRun(tenderDocumentId)` 若后端无对应端点,改为本地从 detail payload 中读取

- [ ] **Step 1: 定位招标文件详情页路由组件**

Run: `grep -rn "ai-extract-requirements\|ai-extraction-runs" frontend/src --include='*.tsx' --include='*.ts'`
预期产出 1-3 个候选位置;选择名字含 "Detail" / "Requirements" / "Page" 的最高层组件。

- [ ] **Step 2: 在该页面组件 import 并渲染 panel**

把以下片段加入合适位置(应在「关键条款列表」上方或侧栏):

```tsx
import { AiExtractionRunPanel } from "../components/AiExtractionRunPanel";

// 渲染:
{latestRunId && <AiExtractionRunPanel runId={latestRunId} />}
```

`latestRunId` 来源:若详情接口已经返回该字段,直接用;否则在 `useQuery` 中再调用一次 `fetch(${BASE}/tender-documents/${id}/ai-extraction-runs/latest)`,如果该端点不存在,本计划范围内**不要**新增端点(超 scope),改为:点击「开始 AI 抽取」按钮后把返回的 `run_id` 存到组件 state 并渲染。

- [ ] **Step 3: 手测页面**

启动后端 + 前端 dev server(参见 README),打开任一招标文件详情页,点击 「AI 抽取」,确认 panel 出现并轮询。截图存到 `docs/reports/2026-05-04-source-chunk-viewer-manual-test.md`(与 Task 10 共用同一报告)。

- [ ] **Step 4: 跑前端全量**

Run: `cd frontend && ./node_modules/.bin/vitest run`
Expected: 不出现回归。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/...   # 实际改动文件
git commit -m "feat: render ai extraction run panel on tender detail page"
```

---

## Task 8 — 端到端验证:对包 1 跑完整 AI 抽取

**Goal:** 用真实 DeepSeek API 跑完一次包 1 的 requirements 抽取,产出验收数据(wall-clock、token、failed_batches、覆盖率、AI vs keyword 对比)并写入报告。

**Files:**

- Create: `scripts/e2e/run_package_1_ai_extraction.py`
- Create: `docs/reports/2026-05-04-package-1-ai-extraction-acceptance.md`

- [ ] **Step 1: 写触发脚本**

```python
# scripts/e2e/run_package_1_ai_extraction.py
"""End-to-end driver: trigger AI extraction for the canonical package 1 tender
document and poll until terminal. Prints metrics suitable for the acceptance
report (token usage, latency, file coverage, failed batches).

Usage:
    python scripts/e2e/run_package_1_ai_extraction.py \
        --tender-document-id <uuid> \
        --base-url http://localhost:8000

Pre-requisites:
- backend + ai-gateway + Celery worker (queue=ai_tasks) running
- DEEPSEEK_API_KEY exported on the worker
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tender-document-id", required=True)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--timeout-seconds", type=int, default=60 * 30)
    args = parser.parse_args()

    started = time.monotonic()
    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        create = client.post(
            f"/api/tender-documents/{args.tender_document_id}/ai-extraction-runs",
            json={"mode": "requirements", "model_policy": "v4_flash_then_pro"},
        )
        create.raise_for_status()
        run_id = create.json()["run_id"]
        print(f"run_id={run_id}")

        while True:
            elapsed = time.monotonic() - started
            if elapsed > args.timeout_seconds:
                print(f"timeout after {elapsed:.0f}s", file=sys.stderr)
                return 2
            run = client.get(f"/api/tender-ai-extraction-runs/{run_id}").json()
            status = run["status"]
            print(
                f"[{elapsed:5.0f}s] status={status} "
                f"succeeded={run['succeeded_batches']}/{run['total_batches']} "
                f"failed={run['failed_batches']} "
                f"skipped={run['skipped_batches']}"
            )
            if status in {"completed", "failed", "cancelled"}:
                break
            time.sleep(15)

        elapsed = time.monotonic() - started
        print("=" * 80)
        print(f"wall_clock_seconds={elapsed:.0f}")
        print(f"final_status={run['status']}")
        print(f"total_input_tokens={run.get('total_input_tokens')}")
        print(f"total_output_tokens={run.get('total_output_tokens')}")
        print("file_coverage:")
        print(json.dumps(run.get("file_coverage", []), indent=2, ensure_ascii=False))
        return 0 if run["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 执行验证**

```bash
# 在 host 上启动 docker compose 栈(包含 worker-ai)
cd infra && docker compose up -d backend ai-gateway worker-io worker-ai postgres redis minio

# 找到包 1 的 tender_document_id;若不知道,先查询:
curl http://localhost:8000/api/projects | jq
# (或从已有数据 fixtures 中拿到)

python scripts/e2e/run_package_1_ai_extraction.py \
  --tender-document-id <uuid> \
  --base-url http://localhost:8000 \
  | tee /tmp/run-2026-05-04.log
```

如果 `worker-ai` service 在 `infra/docker-compose.yml` 中尚未定义,先增加(沿用 worker-io 的 image/env,只是 `command` 替换为 `celery -A tender_backend.workers.celery_app worker -Q ai_tasks --loglevel=info`)。这个修改本身不在本 Task 的代码 diff 中,而属于运维步骤,可在本步骤同时提交。

- [ ] **Step 3: 把指标写入验收报告**

填写 `docs/reports/2026-05-04-package-1-ai-extraction-acceptance.md`:

```markdown
# 包 1 AI 抽取端到端验收报告

> **执行日期:** 2026-05-04
> **触发命令:** `python scripts/e2e/run_package_1_ai_extraction.py ...`
> **run_id:** ...

## 1. 总体指标

| 指标 | 实测 | 目标(Plan A §10 / Plan B 验收) |
|---|---:|---|
| wall-clock | XXXs | 初版 ≤ 1200s,优化版 ≤ 600s |
| total_batches | | |
| succeeded | | |
| failed | | 目标 0 |
| skipped | | 必须有 skip reason |
| input_tokens | | ≤ 400k |
| output_tokens | | ≤ 60k |
| 抽出 requirement 总条数 | | 800-1500 期望区间 |
| `extraction_method='merged'` 占比 | | ≥ 30% |

## 2. 文件覆盖明细

(粘贴 `file_coverage` JSON,逐文件标注是否符合预期)

## 3. 失败批次(若有)

(列出 `error_type` / `error_message` / `retry_count` / 是否进入 needs_review)

## 4. AI vs Keyword 对比

- keyword 抽取条数:2082(基线)
- AI 抽取条数:
- 重叠条数(merged):
- AI 唯一条数:
- keyword 唯一条数:

## 5. 结论

- [ ] 满足 Plan A 验收 §10 (failed_batches=0, JSON 失败率 <1%)
- [ ] 满足 Plan B 验收(merged ≥ 30%, 摘要 5 项必填全部命中, 评分表 dimension 完整)
- [ ] 不满足项与跟进:
```

- [ ] **Step 4: 提交**

```bash
git add scripts/e2e/run_package_1_ai_extraction.py \
        docs/reports/2026-05-04-package-1-ai-extraction-acceptance.md \
        infra/docker-compose.yml   # 若加了 worker-ai
git commit -m "test: end-to-end ai extraction acceptance for package 1"
```

---

## Task 9 — 前 20 条 AI 抽取人工质量评估

**Goal:** 拿 Task 8 的 run 抽 20 条,人工评估 title/category/requirement_text,目标 ≥16/20「准确精炼」,产出问题样本与改进建议。

**Files:**

- Create: `scripts/sample/dump_top_requirements.py`
- Create: `docs/reports/2026-05-04-ai-extraction-quality-sample.md`

- [ ] **Step 1: 写抽样脚本**

```python
# scripts/sample/dump_top_requirements.py
"""Dump first N AI-extracted requirements (with source chunk content) for
manual quality review."""
from __future__ import annotations

import argparse
import json

import psycopg


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--dsn", default="postgresql://tender:tender@localhost:5432/tender")
    args = parser.parse_args()

    sql = """
        SELECT r.id, r.category, r.title, r.requirement_text, r.source_chunk_id,
               r.is_veto, r.is_hard_constraint, r.confidence, c.text AS chunk_text,
               c.source_file, c.sort_order
        FROM project_requirement r
        LEFT JOIN tender_source_chunk c ON c.id = r.source_chunk_id
        WHERE r.project_id = %s
          AND r.extraction_method IN ('ai', 'merged')
        ORDER BY r.created_at ASC
        LIMIT %s
    """
    with psycopg.connect(args.dsn) as conn, conn.cursor() as cur:
        cur.execute(sql, (args.project_id, args.limit))
        cols = [c.name for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 执行抽样并人工评估**

```bash
python scripts/sample/dump_top_requirements.py \
  --project-id <package-1-project-uuid> \
  > /tmp/top20-2026-05-04.json
```

按以下结构填 `docs/reports/2026-05-04-ai-extraction-quality-sample.md`:

```markdown
# AI 抽取质量抽样报告(前 20 条)

> **来源:** Task 8 run_id=...
> **抽样:** 按 created_at 升序 20 条 extraction_method ∈ ('ai', 'merged')

## 评估表

| 序号 | category | title | 是否准确 | 是否精炼 | 是否引用正确 source_chunk | 备注 |
|---:|---|---|---|---|---|---|
| 1 | | | | | | |
| ... | | | | | | |
| 20 | | | | | | |

合计「准确精炼」: __ / 20(目标 ≥ 16)

## 问题样本

(列举不准确 / 冗长 / 引用错误的条目,给出原文与 AI 输出的对比)

## 改进建议

(若 < 16,列出 prompt / chunk 边界 / category 枚举上的具体修改建议,放下一个工单)
```

- [ ] **Step 3: 提交**

```bash
git add scripts/sample/dump_top_requirements.py \
        docs/reports/2026-05-04-ai-extraction-quality-sample.md
git commit -m "test: ai extraction quality sample for package 1"
```

---

## Task 10 — SourceChunkViewer 前端 e2e 手测

**Goal:** Plan B Phase 4 已合入代码,但被多次推迟手测。本 task 要求在浏览器中走完点击 requirement → 抽屉打开 → 内容(段落 / 表格)正确渲染 → 关闭抽屉 → PDF 锚点跳转(若适用)的全流程,记录截图。

**Files:**

- Create / Append: `docs/reports/2026-05-04-source-chunk-viewer-manual-test.md`

- [ ] **Step 1: 启动栈**

```bash
cd infra && docker compose up -d
cd ../frontend && npm run dev
```

- [ ] **Step 2: 走 5 个流程并截图**

| 步骤 | 期望 |
|---|---|
| 打开包 1 项目要求确认页 | RequirementsContent 列表正常加载 |
| 点击带 source_chunk_id 的 requirement | 右侧 Drawer 打开 |
| Drawer 标题展示 source_file + locator | ✓ |
| Drawer 内容:`text` chunk 渲染段落 | ✓ |
| Drawer 内容:`table` chunk 渲染 `<table>` | ✓ |
| 关闭抽屉 | 列表恢复焦点 |

每步截图存 `docs/reports/screenshots/2026-05-04/source-chunk-viewer/01..06.png`。

- [ ] **Step 3: 写报告**

报告框架:

```markdown
# SourceChunkViewer 手测报告

> **执行日期:** 2026-05-04
> **代码版本:** git HEAD = ...

| 步骤 | 截图 | 结果 | 备注 |
|---|---|---|---|
| 1 列表加载 | screenshots/.../01.png | ✅ / ❌ | |
| ... | | | |

## 发现的问题

(若有,列出可复现步骤、严重性、建议优先级)
```

- [ ] **Step 4: 提交**

```bash
git add docs/reports/2026-05-04-source-chunk-viewer-manual-test.md \
        docs/reports/screenshots/2026-05-04/source-chunk-viewer/*.png
git commit -m "test: source chunk viewer manual test report"
```

---

## Task 11 — 评分表 / 摘要端到端验证

**Goal:** Plan B Phase 3 / Phase 5 的端到端被多次推迟。Task 8 跑完 requirements 后,顺手跑摘要与评分表抽取,验收摘要必填字段命中、评分表 dimension 完整、max_score 总分一致。

**Files:**

- Modify: `scripts/e2e/run_package_1_ai_extraction.py`(在末尾追加摘要 + 评分调用)
- Append: `docs/reports/2026-05-04-package-1-ai-extraction-acceptance.md` 第 6 / 7 节

- [ ] **Step 1: 在脚本末尾追加摘要调用**

```python
# scripts/e2e/run_package_1_ai_extraction.py 末尾追加:

facts = client.post(
    f"/api/tender-documents/{args.tender_document_id}/extract-facts"
).json()
print("facts=", json.dumps(facts, ensure_ascii=False, indent=2))

scoring = client.post(
    f"/api/tender-documents/{args.tender_document_id}/extract-scoring-criteria"
).json()
print("scoring=", json.dumps(scoring, ensure_ascii=False, indent=2))
```

(端点名以 `backend/tender_backend/api/tender_documents.py` 实际定义为准,Plan B 已记录这两个端点存在;先 grep 确认。)

- [ ] **Step 2: 执行**

```bash
python scripts/e2e/run_package_1_ai_extraction.py --tender-document-id <uuid>
```

- [ ] **Step 3: 在验收报告补摘要 / 评分章节**

```markdown
## 6. 摘要抽取验收

| 字段 | 是否命中 | 实际值 |
|---|---|---|
| 项目名称 | | |
| 招标人 | | |
| 控制价 | | |
| 保证金 | | |
| 开标时间 | | |

## 7. 评分表结构化验收

- 技术评分 dimension 数量:实际 / 原表
- 商务评分 dimension 数量:实际 / 原表
- max_score 合计:实际 / 原表
- 不一致项:
```

- [ ] **Step 4: 提交**

```bash
git add scripts/e2e/run_package_1_ai_extraction.py \
        docs/reports/2026-05-04-package-1-ai-extraction-acceptance.md
git commit -m "test: facts and scoring end-to-end on package 1"
```

---

## 2. 验收指标(总览)

合并自两份原计划,实测指标在 Task 8 / 9 / 11 报告里逐一打勾:

| 指标 | 目标 |
|---|---:|
| 创建 AI 抽取任务 API 响应时间 | ≤ 1 秒 |
| 包 1 wall-clock(初版) | ≤ 20 分钟 |
| run 完成时 failed batch | 0 |
| 无解释 zero requirement 高价值文件 | 0 |
| 每个有内容 chunk 的 batch 归属率 | 100% |
| 每个 failed batch 可重试率 | 100% |
| JSON/schema 解析失败率 | < 1% |
| 人工脚本补跑需求 | 0 |
| AI 抽取 requirement 总量 | 800-1500 |
| `extraction_method='merged'` 占比 | ≥ 30% |
| 前 20 条 AI 抽取「准确精炼」 | ≥ 16 |
| 摘要必填 5 字段命中 | 全部 |
| 评分表 dimension 完整度 | 100% |
| max_score 合计与原表一致 | 是 |

---

## 3. 风险与决策点

- DeepSeek strict tool calls 兼容性以 Task 1 spike 结论为准。若兼容,后续工单接入主路径;若不兼容,本计划不再投入。
- worker 拆批假设每个 chunk 可独立喂模型;若文件在边界处有跨 chunk 的语义(罕见),拆批可能丢失上下文 → 高价值文件已通过 `high_value=true` 跳过拆批,只升模型。
- 端到端依赖真实 DeepSeek 配额与 docker compose 栈完整启动。出现 502/ReadError 时不算 plan 失败,而是触发 Task 2 的二阶段重试 — 报告里如实记录。
- `worker-ai` 队列必须独立部署,否则会和 `worker-io` 互相阻塞 — Task 8 步骤 2 已包含。

---

## 4. 计划归档

执行完毕(全部 Task checkbox 打勾)后:

- [ ] 在 `docs/plans/2026-05-02-tender-ai-extraction-upgrade-plan.md` 顶部加 `> **状态:** 已被 docs/plans/2026-05-04-tender-ai-extraction-completion-plan.md 取代,2026-05-04 归档。`
- [ ] 在 `docs/plans/2026-05-03-deepseek-v4-tender-extraction-architecture-plan.md` 顶部加同样的归档标记
- [ ] 把 `Out of scope` 中的 strict tool 主路径接入工单(若 spike 通过)写成新 plan
