# Technical Bid Async Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert long-running technical chapter generation into an async, pollable job so chapter 8 can run real 100-page AI generation without blocking the only backend request thread.

**Architecture:** Reuse the existing workflow_run persistence as the authoritative async job record. Add a non-blocking submit endpoint that creates a workflow/job row and executes generation in a background thread, plus a status endpoint that returns run state, error, and generated draft linkage. Keep the current synchronous endpoint for short/debug use; route the frontend/test flow to async for long chapters.

**Tech Stack:** FastAPI, existing workflow repository tables, Python background task/threadpool, psycopg, pytest.

---

### Task 1: Add failing API tests for async submit + poll

**Files:**
- Modify: `backend/tests/unit/test_bid_generation_api.py`
- Test: `backend/tests/unit/test_bid_generation_api.py`

- [ ] **Step 1: Write the failing tests**

```python
from uuid import uuid4
from fastapi.testclient import TestClient

from tender_backend.main import app


def test_async_generate_technical_chapter_returns_202_with_run_id(monkeypatch):
    project_id = uuid4()
    chapter_id = uuid4()

    monkeypatch.setattr("tender_backend.api.bid_generation.require_resource_project_access", lambda *a, **k: project_id)
    monkeypatch.setattr("tender_backend.api.bid_generation.require_project_access", lambda *a, **k: None)
    monkeypatch.setattr("tender_backend.api.bid_generation._project_repo.get", lambda *a, **k: None)
    monkeypatch.setattr("tender_backend.api.bid_generation._template_instances.build_generation_inputs", lambda *a, **k: {"metadata": {}})
    monkeypatch.setattr(
        "tender_backend.api.bid_generation.enqueue_technical_generation",
        lambda **kwargs: {"run_id": "run-123", "state": "pending", "chapter_id": str(chapter_id)},
        raising=False,
    )

    client = TestClient(app)
    res = client.post(
        f"/api/projects/{project_id}/technical-bid/chapters/{chapter_id}/generate-async",
        headers={"Authorization": "Bearer dev-token"},
        json={"target_pages": 100},
    )

    assert res.status_code == 202
    assert res.json()["run_id"] == "run-123"
    assert res.json()["state"] == "pending"


def test_get_technical_generation_run_status_returns_draft_link(monkeypatch):
    project_id = uuid4()
    chapter_id = uuid4()

    monkeypatch.setattr("tender_backend.api.bid_generation.require_project_access", lambda *a, **k: None)
    monkeypatch.setattr(
        "tender_backend.api.bid_generation.get_technical_generation_run_status",
        lambda **kwargs: {
            "run_id": "run-123",
            "state": "completed",
            "chapter_id": str(chapter_id),
            "draft_id": "draft-456",
            "error": None,
        },
        raising=False,
    )

    client = TestClient(app)
    res = client.get(
        f"/api/projects/{project_id}/technical-bid/generation-runs/run-123",
        headers={"Authorization": "Bearer dev-token"},
    )

    assert res.status_code == 200
    assert res.json()["state"] == "completed"
    assert res.json()["draft_id"] == "draft-456"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && PYTHONPATH=. ../.venv/bin/pytest tests/unit/test_bid_generation_api.py -k 'generate_async or generation_run_status' -q`
Expected: FAIL because endpoint/functions do not exist yet.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/unit/test_bid_generation_api.py
git commit -m "test: cover async technical generation api"
```

### Task 2: Add failing service tests for enqueue + status mapping

**Files:**
- Create: `backend/tests/unit/test_technical_generation_async.py`
- Test: `backend/tests/unit/test_technical_generation_async.py`

- [ ] **Step 1: Write the failing tests**

```python
from uuid import uuid4

from tender_backend.services.technical_generation_async import (
    enqueue_technical_generation,
    get_technical_generation_run_status,
)


def test_enqueue_technical_generation_creates_pending_run(monkeypatch):
    captured = {}

    class _Repo:
        async def create_run(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("tender_backend.services.technical_generation_async.WorkflowRepository", lambda: _Repo())
    monkeypatch.setattr("tender_backend.services.technical_generation_async.start_background_generation", lambda **kwargs: None)

    result = enqueue_technical_generation(
        project_id=str(uuid4()),
        chapter_id=str(uuid4()),
        created_by="Developer",
        rewrite_note=None,
        target_pages=100,
    )

    assert result["state"] == "pending"
    assert captured["workflow_name"] == "generate_section_async"


def test_get_technical_generation_run_status_maps_completed_context(monkeypatch):
    run_id = "run-123"
    chapter_id = str(uuid4())

    class _Repo:
        async def get_run(self, _run_id):
            return {
                "id": run_id,
                "project_id": str(uuid4()),
                "state": "completed",
                "current_step": "save_draft",
                "error": None,
                "context_json": {"chapter_id": chapter_id, "draft_id": "draft-456"},
            }

    monkeypatch.setattr("tender_backend.services.technical_generation_async.WorkflowRepository", lambda: _Repo())

    result = get_technical_generation_run_status(project_id=str(uuid4()), run_id=run_id)

    assert result["state"] == "completed"
    assert result["draft_id"] == "draft-456"
    assert result["chapter_id"] == chapter_id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && PYTHONPATH=. ../.venv/bin/pytest tests/unit/test_technical_generation_async.py -q`
Expected: FAIL because module/service does not exist.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/unit/test_technical_generation_async.py
git commit -m "test: cover technical generation async service"
```

### Task 3: Implement async generation service with workflow_run persistence

**Files:**
- Create: `backend/tender_backend/services/technical_generation_async.py`
- Modify: `backend/tender_backend/db/repositories/workflow_repo.py`
- Test: `backend/tests/unit/test_technical_generation_async.py`

- [ ] **Step 1: Write minimal implementation**

```python
# backend/tender_backend/services/technical_generation_async.py
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from tender_backend.core.threadpool_compat import run_in_threadpool
from tender_backend.db.repositories.workflow_repo import WorkflowRepository
from tender_backend.db.psycopg_pool import get_pool
from tender_backend.core.config import get_settings
from tender_backend.services.technical_bid_writer import TechnicalBidWriter
from tender_backend.workflows.states import WorkflowState


def enqueue_technical_generation(*, project_id: str, chapter_id: str, created_by: str | None, rewrite_note: str | None, target_pages: int | None) -> dict[str, Any]:
    run_id = uuid.uuid4().hex
    payload = {
        "chapter_id": chapter_id,
        "created_by": created_by,
        "rewrite_note": rewrite_note,
        "target_pages": target_pages,
        "draft_id": None,
    }
    asyncio.run(_create_pending_run(run_id=run_id, project_id=project_id, context=payload))
    start_background_generation(run_id=run_id, project_id=project_id)
    return {"run_id": run_id, "state": "pending", "chapter_id": chapter_id}


async def _create_pending_run(*, run_id: str, project_id: str, context: dict[str, Any]) -> None:
    repo = WorkflowRepository()
    await repo.create_run(run_id=run_id, workflow_name="generate_section_async", project_id=project_id, trace_id=run_id[:16])
    await repo.save_context(run_id, context)


def start_background_generation(*, run_id: str, project_id: str) -> None:
    async def _runner() -> None:
        repo = WorkflowRepository()
        await repo.update_run_state(run_id, WorkflowState.RUNNING)
        pool = get_pool(database_url=get_settings().database_url)
        with pool.connection() as conn:
            run = await repo.get_run(run_id)
            context = dict(run.get("context_json") or {})
            result = await run_in_threadpool(
                TechnicalBidWriter().generate_chapter,
                conn,
                project_id=project_id,
                chapter_id=context["chapter_id"],
                created_by=context.get("created_by"),
                rewrite_note=context.get("rewrite_note"),
                target_pages=context.get("target_pages"),
            )
            draft = result.get("draft") or {}
            context["draft_id"] = str(draft.get("id")) if draft.get("id") else None
            await repo.save_context(run_id, context)
            await repo.update_run_state(run_id, WorkflowState.COMPLETED)

    asyncio.get_event_loop().create_task(_runner())


def get_technical_generation_run_status(*, project_id: str, run_id: str) -> dict[str, Any]:
    run = asyncio.run(WorkflowRepository().get_run(run_id))
    context = dict(run.get("context_json") or {})
    if str(run.get("project_id")) != str(project_id):
        raise ValueError("run not found")
    return {
        "run_id": str(run["id"]),
        "state": str(run["state"]),
        "chapter_id": context.get("chapter_id"),
        "draft_id": context.get("draft_id"),
        "error": run.get("error"),
        "current_step": run.get("current_step"),
    }
```

- [ ] **Step 2: Add repository helper if needed**

```python
# backend/tender_backend/db/repositories/workflow_repo.py
async def get_run(self, run_id: str) -> dict:
    ...
```

If `get_run` already exists, do not duplicate it; only reuse it.

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. ../.venv/bin/pytest tests/unit/test_technical_generation_async.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/tender_backend/services/technical_generation_async.py backend/tender_backend/db/repositories/workflow_repo.py backend/tests/unit/test_technical_generation_async.py
git commit -m "feat: add async technical generation service"
```

### Task 4: Expose async submit + poll endpoints

**Files:**
- Modify: `backend/tender_backend/api/bid_generation.py`
- Test: `backend/tests/unit/test_bid_generation_api.py`

- [ ] **Step 1: Wire endpoints**

```python
from fastapi import status
from tender_backend.services.technical_generation_async import (
    enqueue_technical_generation,
    get_technical_generation_run_status,
)

@router.post("/projects/{project_id}/technical-bid/chapters/{chapter_id}/generate-async", status_code=status.HTTP_202_ACCEPTED)
async def generate_technical_chapter_async(...):
    ...
    return enqueue_technical_generation(
        project_id=str(project_id),
        chapter_id=str(chapter_id),
        created_by=user.display_name,
        rewrite_note=payload.rewrite_note if payload else None,
        target_pages=payload.target_pages if payload else None,
    )

@router.get("/projects/{project_id}/technical-bid/generation-runs/{run_id}")
async def get_technical_generation_status(...):
    ...
    return get_technical_generation_run_status(project_id=str(project_id), run_id=run_id)
```

- [ ] **Step 2: Run API tests to verify they pass**

Run: `cd backend && PYTHONPATH=. ../.venv/bin/pytest tests/unit/test_bid_generation_api.py -k 'generate_async or generation_run_status' -q`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tender_backend/api/bid_generation.py backend/tests/unit/test_bid_generation_api.py
git commit -m "feat: expose async technical generation api"
```

### Task 5: Persist draft_id/current step during async execution failures and success

**Files:**
- Modify: `backend/tender_backend/services/technical_generation_async.py`
- Modify: `backend/tests/unit/test_technical_generation_async.py`
- Test: `backend/tests/unit/test_technical_generation_async.py`

- [ ] **Step 1: Add failing test for failure status**

```python
def test_async_runner_marks_failed_on_generation_error(monkeypatch):
    ...
    assert result["state"] == "failed"
    assert "timeout" in result["error"]
```

- [ ] **Step 2: Implement failure capture**

```python
try:
    ...
except Exception as exc:
    await repo.update_run_state(run_id, WorkflowState.FAILED, error=str(exc))
```

- [ ] **Step 3: Run service tests**

Run: `cd backend && PYTHONPATH=. ../.venv/bin/pytest tests/unit/test_technical_generation_async.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/tender_backend/services/technical_generation_async.py backend/tests/unit/test_technical_generation_async.py
git commit -m "fix: persist async technical generation failures"
```

### Task 6: Verify end-to-end on local project with real AI

**Files:**
- Modify: none
- Test: live local API verification

- [ ] **Step 1: Submit async 100-page chapter 8 generation**

Run:
```bash
curl -sS -H 'Authorization: Bearer dev-token' -H 'Content-Type: application/json' \
  -X POST http://127.0.0.1:18000/api/projects/c42f62a8-7e48-4514-ad01-d509088bee9c/technical-bid/chapters/5d024fdb-170d-47d5-aba2-6119d4a16319/generate-async \
  -d '{"target_pages":100}' | python3 -m json.tool
```
Expected: HTTP 202 with `run_id` and `state=pending|running`.

- [ ] **Step 2: Poll until completed**

Run:
```bash
curl -sS -H 'Authorization: Bearer dev-token' \
  http://127.0.0.1:18000/api/projects/c42f62a8-7e48-4514-ad01-d509088bee9c/technical-bid/generation-runs/<run_id> | python3 -m json.tool
```
Expected: eventually `state=completed` and non-empty `draft_id`.

- [ ] **Step 3: Verify draft/chart/export evidence**

Run:
```bash
curl -sS -H 'Authorization: Bearer dev-token' http://127.0.0.1:18000/api/projects/c42f62a8-7e48-4514-ad01-d509088bee9c/drafts | python3 -m json.tool
curl -sS -H 'Authorization: Bearer dev-token' http://127.0.0.1:18000/api/projects/c42f62a8-7e48-4514-ad01-d509088bee9c/chart-assets | python3 -m json.tool
curl -sS -H 'Authorization: Bearer dev-token' http://127.0.0.1:18000/api/projects/c42f62a8-7e48-4514-ad01-d509088bee9c/export-gates | python3 -m json.tool
```
Expected: chapter 8 draft present, charts generated, export gates reflect actual closure state.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test: verify async chapter 8 generation flow"
```
