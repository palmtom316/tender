# Standard Batch Upload Queue Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为规范规程处理增加批量上传、自动入队和两段单并发流水线，满足 “一次可上传多个 PDF，OCR 全局单并发，AI 解析全局单并发，且两个阶段可流水并行” 的业务要求。

**Architecture:** 新增 `standard_processing_job` 队列表作为 OCR/AI 两段流水线的事实来源，后端通过应用内调度器分别驱动 OCR 和 AI 单并发处理。前端把现有单文件表单升级为逐条录入的批量上传编辑器，并展示 `queued_ocr / parsing / queued_ai / processing / completed / failed` 等汇总状态以及阶段状态。

**Tech Stack:** FastAPI、psycopg、Alembic、pytest、React 18、TypeScript、Vite、CSS。

---

## File Map

- Modify: `backend/tender_backend/api/standards.py` — 批量上传、列表/详情状态扩展、失败重试入队
- Modify: `backend/tender_backend/main.py` — 应用启动时注册并唤醒调度器
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py` — 拆分 OCR 阶段与 AI 阶段执行入口，保留现有解析逻辑
- Modify: `backend/tender_backend/db/repositories/standard_repo.py` — 扩展标准列表/详情查询，承载汇总状态字段更新
- Modify: `backend/tests/integration/test_standard_mineru_batch_flow.py` — 复用现有规范处理测试，补充分段执行回归
- Modify: `frontend/src/lib/api.ts` — 批量上传 DTO、标准状态字段、重试接口类型
- Modify: `frontend/src/modules/database/DatabaseModule.tsx` — 批量上传编辑器、状态展示、失败重试按钮、轮询条件
- Modify: `frontend/src/styles/utilities.css` — 批量上传表格/行内编辑样式
- Create: `backend/tender_backend/db/alembic/versions/0007_standard_processing_queue.py` — 新增队列表结构
- Create: `backend/tender_backend/db/repositories/standard_processing_job_repository.py` — 队列表仓储
- Create: `backend/tender_backend/services/norm_service/standard_processing_scheduler.py` — OCR/AI 双循环调度器
- Create: `backend/tests/integration/test_standard_processing_job_repository.py` — 队列表仓储与认领逻辑测试
- Create: `backend/tests/integration/test_standard_processing_queue_api.py` — 批量上传、列表状态、失败重试 API 测试
- Create: `backend/tests/integration/test_standard_processing_scheduler.py` — 调度器单并发与流水线行为测试

## Chunk 1: Establish Queue Persistence

### Task 1: Add failing repository tests for queue lifecycle

**Files:**
- Create: `backend/tests/integration/test_standard_processing_job_repository.py`
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Write the failing repository tests**

Add tests covering:

- create job with `ocr_status="queued"` and `ai_status="blocked"`
- claim earliest queued OCR job
- claim earliest queued AI job
- reset failed OCR job back to OCR queue
- reset failed AI job back to AI queue without touching OCR status

Example test shape:

```python
def test_claim_next_ocr_job_returns_oldest_queued_job(conn):
    repo = StandardProcessingJobRepository()
    first = repo.create(conn, standard_id=uuid4(), document_id=uuid4())
    repo.create(conn, standard_id=uuid4(), document_id=uuid4())

    claimed = repo.claim_next_ocr_job(conn)

    assert claimed is not None
    assert claimed.id == first.id
    assert claimed.ocr_status == "running"
```

- [ ] **Step 2: Run the repository tests to verify RED**

Run: `cd backend && pytest tests/integration/test_standard_processing_job_repository.py -q`

Expected: FAIL with import errors or missing repository methods because the queue repository does not exist yet.

- [ ] **Step 3: Commit the failing test baseline**

```bash
git add backend/tests/integration/test_standard_processing_job_repository.py backend/pyproject.toml
git commit -m "test: add standard processing queue repository coverage"
```

### Task 2: Implement queue storage and migration

**Files:**
- Create: `backend/tender_backend/db/alembic/versions/0007_standard_processing_queue.py`
- Create: `backend/tender_backend/db/repositories/standard_processing_job_repository.py`
- Modify: `backend/tender_backend/db/repositories/standard_repo.py`
- Test: `backend/tests/integration/test_standard_processing_job_repository.py`

- [ ] **Step 1: Add the migration**

Create `standard_processing_job` with:

- `id`
- `standard_id` unique not null FK
- `document_id` not null
- `ocr_status`, `ocr_error`, `ocr_started_at`, `ocr_finished_at`, `ocr_attempts`
- `ai_status`, `ai_error`, `ai_started_at`, `ai_finished_at`, `ai_attempts`
- timestamps

Keep defaults aligned with the design:

```sql
ocr_status VARCHAR(16) NOT NULL DEFAULT 'queued'
ai_status VARCHAR(16) NOT NULL DEFAULT 'blocked'
```

- [ ] **Step 2: Implement the repository with atomic claim methods**

Add a typed dataclass and methods such as:

```python
def claim_next_ocr_job(self, conn: Connection) -> StandardProcessingJob | None: ...
def claim_next_ai_job(self, conn: Connection) -> StandardProcessingJob | None: ...
def mark_ocr_completed(self, conn: Connection, *, job_id: UUID) -> None: ...
def mark_ai_failed(self, conn: Connection, *, job_id: UUID, error: str) -> None: ...
def retry(self, conn: Connection, *, standard_id: UUID) -> StandardProcessingJob: ...
```

Use a single `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED ...) RETURNING *` pattern for claim operations so concurrency rules remain in the database.

- [ ] **Step 3: Extend standard projections with queue fields**

Update `StandardRepository` read helpers so list/detail queries can return:

- `processing_status`
- `error_message`
- `ocr_status`
- `ai_status`

Either join queue state in repository helpers or add a dedicated query helper for API composition. Keep the public API shape stable for existing consumers except for added fields.

- [ ] **Step 4: Re-run repository tests to verify GREEN**

Run: `cd backend && pytest tests/integration/test_standard_processing_job_repository.py -q`

Expected: PASS with all queue lifecycle tests green.

- [ ] **Step 5: Commit persistence layer**

```bash
git add backend/tender_backend/db/alembic/versions/0007_standard_processing_queue.py backend/tender_backend/db/repositories/standard_processing_job_repository.py backend/tender_backend/db/repositories/standard_repo.py backend/tests/integration/test_standard_processing_job_repository.py
git commit -m "feat: add standard processing queue persistence"
```

## Chunk 2: Build Backend Queue Execution

### Task 3: Add failing scheduler tests for single-concurrency pipeline behavior

**Files:**
- Create: `backend/tests/integration/test_standard_processing_scheduler.py`
- Modify: `backend/tests/integration/test_standard_mineru_batch_flow.py`

- [ ] **Step 1: Write the failing scheduler tests**

Cover:

- only one OCR job is claimed per scheduler tick
- only one AI job is claimed per scheduler tick
- OCR completion promotes the same job to `ai_status="queued"`
- AI worker can run while another standard is in OCR
- failed OCR does not block the next queued OCR job
- failed AI retry reuses OCR output

Example expectation:

```python
def test_run_one_scheduler_tick_processes_one_ocr_and_one_ai(monkeypatch, conn):
    scheduler = StandardProcessingScheduler(...)
    scheduler.run_once()
    assert captured["ocr_calls"] == [first_document_id]
    assert captured["ai_calls"] == [ready_standard_id]
```

- [ ] **Step 2: Run the scheduler tests to verify RED**

Run: `cd backend && pytest tests/integration/test_standard_processing_scheduler.py -q`

Expected: FAIL because the scheduler module and split execution entrypoints do not exist yet.

- [ ] **Step 3: Commit the scheduler red tests**

```bash
git add backend/tests/integration/test_standard_processing_scheduler.py backend/tests/integration/test_standard_mineru_batch_flow.py
git commit -m "test: cover standard queue scheduler behavior"
```

### Task 4: Split OCR and AI execution and implement the scheduler

**Files:**
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py`
- Create: `backend/tender_backend/services/norm_service/standard_processing_scheduler.py`
- Modify: `backend/tender_backend/main.py`
- Test: `backend/tests/integration/test_standard_processing_scheduler.py`
- Test: `backend/tests/integration/test_standard_mineru_batch_flow.py`

- [ ] **Step 1: Extract explicit OCR and AI-stage functions**

Refactor `norm_processor.py` so the scheduler can call stages independently:

```python
def ensure_standard_ocr(conn: Connection, *, document_id: str) -> int: ...
def process_standard_ai(conn: Connection, *, standard_id: UUID, document_id: str) -> dict: ...
```

`process_standard()` can remain as a compatibility wrapper that simply calls the two stage functions in order, but the scheduler must use the split entrypoints.

- [ ] **Step 2: Implement the scheduler service**

Create a scheduler with:

- idempotent `ensure_started()`
- one OCR loop
- one AI loop
- `run_ocr_once()` and `run_ai_once()` helpers for deterministic tests
- crash recovery for stale `running` jobs before each loop iteration

Keep the implementation application-local and thread-based; do not reintroduce “one request spawns one pipeline thread per standard.”

- [ ] **Step 3: Wire scheduler startup into the app**

Update `backend/tender_backend/main.py` so application startup initializes and starts the scheduler once, using the configured DB pool. Avoid duplicate starts in hot reload by guarding with module-level state inside the scheduler service.

- [ ] **Step 4: Run focused backend verification**

Run: `cd backend && pytest tests/integration/test_standard_processing_scheduler.py tests/integration/test_standard_mineru_batch_flow.py -q`

Expected: PASS; scheduler tests prove `OCR=1` and `AI=1` while existing MinerU flow tests remain green.

- [ ] **Step 5: Commit the scheduler**

```bash
git add backend/tender_backend/services/norm_service/norm_processor.py backend/tender_backend/services/norm_service/standard_processing_scheduler.py backend/tender_backend/main.py backend/tests/integration/test_standard_processing_scheduler.py backend/tests/integration/test_standard_mineru_batch_flow.py
git commit -m "feat: add standard processing scheduler"
```

### Task 5: Convert the standards API to batch upload and retry semantics

**Files:**
- Modify: `backend/tender_backend/api/standards.py`
- Modify: `backend/tender_backend/db/repositories/standard_repo.py`
- Modify: `backend/tender_backend/db/repositories/standard_processing_job_repository.py`
- Create: `backend/tests/integration/test_standard_processing_queue_api.py`

- [ ] **Step 1: Write the failing API tests**

Cover:

- batch upload accepts multiple files and matching metadata rows
- upload rejects mismatched file/metadata counts
- upload rejects rows missing `standard_code` or `standard_name`
- successful upload creates queue jobs and returns `queued_ocr`
- retry endpoint requeues OCR failures from OCR and AI failures from AI only
- list/detail endpoints include `ocr_status` and `ai_status`

Example request pattern:

```python
response = client.post(
    "/api/standards/upload",
    files=[("files", ("a.pdf", b"%PDF", "application/pdf")), ("files", ("b.pdf", b"%PDF", "application/pdf"))],
    data={"items_json": json.dumps([
        {"filename": "a.pdf", "standard_code": "GB 1", "standard_name": "规范A"},
        {"filename": "b.pdf", "standard_code": "GB 2", "standard_name": "规范B"},
    ])},
)
```

- [ ] **Step 2: Run the API tests to verify RED**

Run: `cd backend && pytest tests/integration/test_standard_processing_queue_api.py -q`

Expected: FAIL because the upload endpoint only accepts one file and the response shape lacks queue fields.

- [ ] **Step 3: Implement the batch API**

Update `backend/tender_backend/api/standards.py` to:

- accept `files: list[UploadFile]`
- accept one JSON form field for per-file metadata rows
- validate every row before any queue job creation
- create `standard_processing_job` rows during upload
- call `scheduler.ensure_started()` / `scheduler.wake()` after commit

Keep file-to-metadata matching deterministic by filename plus array order; reject ambiguous duplicates rather than guessing.

- [ ] **Step 4: Rework `/standards/{id}/process` into retry-only semantics**

Allow retries only from failed states:

- `ocr_status="failed"` -> reset OCR to `queued`, AI to `blocked`
- `ai_status="failed"` and `ocr_status="completed"` -> reset AI to `queued`

Return `409` for queued/running/completed items.

- [ ] **Step 5: Run the API verification**

Run: `cd backend && pytest tests/integration/test_standard_processing_queue_api.py tests/integration/test_standard_processing_job_repository.py tests/integration/test_standard_processing_scheduler.py -q`

Expected: PASS for upload, retry, and queue-state coverage.

- [ ] **Step 6: Commit the backend API layer**

```bash
git add backend/tender_backend/api/standards.py backend/tender_backend/db/repositories/standard_repo.py backend/tender_backend/db/repositories/standard_processing_job_repository.py backend/tests/integration/test_standard_processing_queue_api.py
git commit -m "feat: add batch upload and retry queue api"
```

## Chunk 3: Ship Frontend Batch Upload UX

### Task 6: Add failing type/build expectations for the new API contract

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/modules/database/DatabaseModule.tsx`

- [ ] **Step 1: Update the API types first**

Add TypeScript interfaces for:

- `StandardQueueState`
- `BatchStandardUploadItem`
- `BatchStandardUploadResponse`

and expand `Standard` / `StandardDetail` with:

- `ocr_status`
- `ai_status`
- optional `queue_position`

Temporarily update imports/usages so the old UI no longer type-checks cleanly.

- [ ] **Step 2: Run the frontend build to verify RED**

Run: `cd frontend && npm run build`

Expected: FAIL because `DatabaseModule.tsx` still assumes the single-file upload API and older status shapes.

- [ ] **Step 3: Commit the type-level red state**

```bash
git add frontend/src/lib/api.ts frontend/src/modules/database/DatabaseModule.tsx
git commit -m "test: encode standard batch queue api contract in frontend types"
```

### Task 7: Implement batch upload editor and queue-aware list UI

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/modules/database/DatabaseModule.tsx`
- Modify: `frontend/src/styles/utilities.css`

- [ ] **Step 1: Implement the batch upload client**

Replace `uploadStandard(file, data)` with a batch helper:

```ts
export function uploadStandards(
  items: Array<{ file: File; standard_code: string; standard_name: string; version_year?: string; specialty?: string }>
): Promise<BatchStandardUploadResponse>
```

Serialize files as repeated `files` form parts and metadata as one JSON field such as `items_json`.

- [ ] **Step 2: Replace the single-file form with a batch editor**

In `DatabaseModule.tsx`:

- generate one editable row per selected file
- require `standard_code` and `standard_name` before submit
- allow removing rows before upload
- clear the batch editor on success

Keep the component in the same module file unless it becomes too large; if it does, split out focused helpers rather than growing one monolith.

- [ ] **Step 3: Make list and detail views queue-aware**

Update UI behavior to:

- remove the “开始AI处理” button
- show stage-specific helper text for `queued_ocr`, `parsing`, `queued_ai`, `processing`
- show “重新入队” only for failed items
- poll while any standard is queued or running
- refresh after retry requests

- [ ] **Step 4: Add the supporting styles**

Extend `utilities.css` with classes for:

- batch upload grid / table
- row actions
- compact per-row inputs
- stage status hint text

Preserve the current visual language; do not introduce a new design system just for this flow.

- [ ] **Step 5: Run the frontend build to verify GREEN**

Run: `cd frontend && npm run build`

Expected: PASS with the new batch editor and queue-aware UI compiling cleanly.

- [ ] **Step 6: Commit the frontend UX**

```bash
git add frontend/src/lib/api.ts frontend/src/modules/database/DatabaseModule.tsx frontend/src/styles/utilities.css
git commit -m "feat: add standards batch upload queue ui"
```

### Task 8: Run end-to-end verification and record manual checks

**Files:**
- Modify: `docs/superpowers/plans/2026-03-19-standard-batch-upload-queue.md`

- [ ] **Step 1: Run the complete backend test suite for this feature area**

Run: `cd backend && pytest tests/integration/test_standard_processing_job_repository.py tests/integration/test_standard_processing_scheduler.py tests/integration/test_standard_processing_queue_api.py tests/integration/test_standard_mineru_batch_flow.py -q`

Expected: PASS with no failures.

- [ ] **Step 2: Run the frontend production build**

Run: `cd frontend && npm run build`

Expected: PASS.

- [ ] **Step 3: Perform manual acceptance checks**

Verify in the running app:

1. Upload 2+ PDF files in one batch.
2. Each row requires `规范编号` and `规范名称`.
3. Upload success immediately shows `OCR排队中`.
4. While file A is `AI处理中`, file B can be `解析中`.
5. An OCR failure can be retried from OCR.
6. An AI failure can be retried without repeating OCR.

Record any deviations directly under this task before calling the work complete.

- [ ] **Step 4: Commit final verification notes if needed**

```bash
git add docs/superpowers/plans/2026-03-19-standard-batch-upload-queue.md
git commit -m "docs: record standard batch queue verification notes"
```
