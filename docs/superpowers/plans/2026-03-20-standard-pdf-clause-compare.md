# Standard PDF Clause Compare Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将“规范规程库”从状态卡片页升级为“规范规程列表 + 规范规程查询 + PDF/条款对照查阅”工作台，支持删除整份规范、失败重试、条款查询和左 PDF / 右 AI 解析结果弹窗。

**Architecture:** 后端在现有 `standard` / `standard_clause` / `standard_processing_job` 基础上新增标准删除、标准条款查询、标准查阅聚合和 PDF 预览接口；OpenSearch 条款索引补充 `standard_name/page_start/page_end`，并在查询接口中保留数据库回填兜底。前端把规范规程主区域重构为两个固定卡片与一个统一查阅弹窗，使用 PDF.js 做页级预览与跳页联动。

**Tech Stack:** FastAPI、psycopg、pytest、OpenSearch、React 18、TypeScript、Vite、CSS、`pdfjs-dist`。

---

## File Map

- Modify: `backend/tender_backend/api/standards.py` — 新增标准删除、标准查询、查阅聚合、PDF 预览接口
- Modify: `backend/tender_backend/db/repositories/standard_repo.py` — 增加 viewer/删除/条款补数查询辅助方法
- Modify: `backend/tender_backend/services/search_service/query_service.py` — 增加面向规范规程页的查询 helper 或扩展现有条款查询
- Modify: `backend/tender_backend/services/search_service/index_manager.py` — 补充 `clause_index` 的映射字段
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py` — 写入更完整的条款索引文档
- Modify: `backend/tender_backend/workflows/standard_ingestion.py` — 统一索引字段，避免老 workflow 落后
- Modify: `backend/tender_backend/tools/reindex_standard_clauses.py` — 重建条款索引时带上新字段
- Create: `backend/tests/integration/test_standard_viewer_query_api.py` — viewer/search/delete/pdf API 集成覆盖
- Create: `backend/tests/unit/test_standard_clause_index_docs.py` — 条款索引文档构建测试
- Modify: `frontend/package.json` — 增加 PDF viewer 依赖
- Modify: `frontend/package-lock.json` — 锁定新增依赖
- Modify: `frontend/src/lib/api.ts` — 增加 viewer/search/delete/pdf 相关 DTO 与请求函数
- Modify: `frontend/src/modules/database/DatabaseModule.tsx` — 规范规程页编排与状态管理
- Create: `frontend/src/modules/database/components/StandardProgressBar.tsx` — OCR/AI 组合进度条
- Create: `frontend/src/modules/database/components/StandardClauseTree.tsx` — 条款树与选中逻辑
- Create: `frontend/src/modules/database/components/StandardPdfPane.tsx` — PDF 页级预览与跳页
- Create: `frontend/src/modules/database/components/StandardViewerModal.tsx` — 左 PDF / 右条款的统一查阅弹窗
- Create: `frontend/src/modules/database/components/StandardsTableCard.tsx` — 规范规程列表卡片
- Create: `frontend/src/modules/database/components/StandardSearchCard.tsx` — 规范规程查询卡片
- Modify: `frontend/src/styles/utilities.css` — 新增列表卡片、查询卡片、查阅弹窗和 PDF 面板样式

## Chunk 1: Add Backend Viewer/Search/Delete APIs

### Task 1: Add failing integration coverage for viewer, query, delete, and PDF preview

**Files:**
- Create: `backend/tests/integration/test_standard_viewer_query_api.py`
- Modify: `backend/tests/integration/test_standard_processing_queue_api.py`

- [ ] **Step 1: Write the failing integration tests**

Add tests covering:

- `GET /standards/{standard_id}/viewer` returns:
  - standard metadata
  - `document_id`
  - `pdf_url`
  - `clause_tree`
- `GET /standards/search?q=混凝土` returns enriched results with:
  - `standard_id`
  - `standard_name`
  - `specialty`
  - `clause_id`
  - `clause_no`
  - `tags`
  - `summary`
  - `page_start`
- `GET /standards/{standard_id}/pdf` streams the uploaded PDF as `application/pdf`
- `DELETE /standards/{standard_id}` deletes a completed standard
- `DELETE /standards/{standard_id}` returns conflict when the standard is in an active queue state

Example assertions:

```python
def test_get_standard_viewer_returns_pdf_url_and_clause_tree(client, seeded_standard):
    response = client.get(f"/api/standards/{seeded_standard['id']}/viewer")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == seeded_standard["id"]
    assert payload["pdf_url"].endswith(f"/api/standards/{seeded_standard['id']}/pdf")
    assert len(payload["clause_tree"]) >= 1
```

```python
def test_delete_standard_blocks_active_processing(client, seeded_running_standard):
    response = client.delete(f"/api/standards/{seeded_running_standard['id']}")

    assert response.status_code == 409
    assert "running" in response.json()["detail"].lower()
```

- [ ] **Step 2: Run the focused integration tests to verify RED**

Run:

```bash
cd backend && .venv314/bin/pytest tests/integration/test_standard_viewer_query_api.py -q
```

Expected: FAIL because the viewer/search/delete/pdf routes do not exist yet.

- [ ] **Step 3: Commit the failing test baseline**

```bash
git add backend/tests/integration/test_standard_viewer_query_api.py backend/tests/integration/test_standard_processing_queue_api.py
git commit -m "test: cover standard viewer query api"
```

### Task 2: Implement backend viewer/search/delete/pdf behavior

**Files:**
- Modify: `backend/tender_backend/api/standards.py`
- Modify: `backend/tender_backend/db/repositories/standard_repo.py`
- Modify: `backend/tender_backend/db/repositories/standard_processing_job_repository.py`
- Test: `backend/tests/integration/test_standard_viewer_query_api.py`

- [ ] **Step 1: Add repository helpers for viewer and deletion**

Extend `StandardRepository` with helpers such as:

```python
def get_standard_file(self, conn: Connection, standard_id: UUID) -> dict | None: ...
def get_clause(self, conn: Connection, clause_id: UUID) -> dict | None: ...
def list_neighbor_clauses(self, conn: Connection, *, standard_id: UUID, sort_order: int, radius: int = 2) -> list[dict]: ...
def delete_standard(self, conn: Connection, *, standard_id: UUID) -> int: ...
```

`get_standard_file()` should join `standard -> document -> project_file` and return:

- `document_id`
- `project_file_id`
- `filename`
- `content_type`
- `storage_key`

`delete_standard()` should remove the whole standard aggregate, not a single clause.

- [ ] **Step 2: Add the new API routes**

Implement in `backend/tender_backend/api/standards.py`:

- `GET /standards/{standard_id}/viewer`
- `GET /standards/{standard_id}/pdf`
- `GET /standards/search`
- `DELETE /standards/{standard_id}`

Recommended response shape for viewer:

```python
{
    **_serialize_standard(std, clause_count=clause_count),
    "document_id": str(file_meta["document_id"]),
    "pdf_url": f"/api/standards/{standard_id}/pdf",
    "clause_tree": tree,
}
```

Recommended response shape for search:

```python
{
    "standard_id": "...",
    "standard_name": "混凝土结构设计规范",
    "specialty": "结构",
    "clause_id": "...",
    "clause_no": "3.2.1",
    "tags": ["结构", "混凝土", "强制性条文"],
    "summary": "规定了混凝土最低强度等级要求",
    "page_start": 15,
    "page_end": 15,
}
```

- [ ] **Step 3: Enforce delete safety**

For `DELETE /standards/{standard_id}`:

- forbid deletion when `processing_status` is one of:
  - `queued_ocr`
  - `parsing`
  - `queued_ai`
  - `processing`
- allow deletion when status is:
  - `completed`
  - `failed`
  - `pending`

Return:

```python
raise HTTPException(status_code=409, detail="Cannot delete a standard while processing is active")
```

- [ ] **Step 4: Add DB fallback enrichment for search hits**

If OpenSearch search results do not include `standard_name/page_start/page_end`, hydrate them using `clause_id` from PostgreSQL before returning the API response.

This avoids blocking the feature on full reindex completion.

- [ ] **Step 5: Re-run the focused backend tests to verify GREEN**

Run:

```bash
cd backend && .venv314/bin/pytest tests/integration/test_standard_viewer_query_api.py -q
```

Expected: PASS with viewer/search/delete/pdf preview behaviors covered.

- [ ] **Step 6: Commit the backend API implementation**

```bash
git add backend/tender_backend/api/standards.py backend/tender_backend/db/repositories/standard_repo.py backend/tender_backend/db/repositories/standard_processing_job_repository.py backend/tests/integration/test_standard_viewer_query_api.py
git commit -m "feat: add standard viewer search delete api"
```

## Chunk 2: Enrich Clause Search Index Data

### Task 3: Add failing tests for clause index document enrichment

**Files:**
- Create: `backend/tests/unit/test_standard_clause_index_docs.py`
- Modify: `backend/tender_backend/tools/reindex_standard_clauses.py`

- [ ] **Step 1: Write the failing unit tests**

Add tests for `build_clause_index_docs()` that assert each indexed document contains:

- `standard_name`
- `page_start`
- `page_end`

Example:

```python
def test_build_clause_index_docs_includes_viewer_fields():
    docs = build_clause_index_docs(
        {"id": uuid4(), "standard_code": "GB 50010", "standard_name": "混凝土结构设计规范", "specialty": "结构"},
        [{"id": uuid4(), "clause_no": "3.2.1", "summary": "摘要", "tags": ["结构"], "page_start": 15, "page_end": 16}],
    )

    _, body = docs[0]
    assert body["standard_name"] == "混凝土结构设计规范"
    assert body["page_start"] == 15
    assert body["page_end"] == 16
```

- [ ] **Step 2: Run the unit test to verify RED**

Run:

```bash
cd backend && .venv314/bin/pytest tests/unit/test_standard_clause_index_docs.py -q
```

Expected: FAIL because the index docs do not yet carry the viewer fields.

- [ ] **Step 3: Commit the failing index-doc test**

```bash
git add backend/tests/unit/test_standard_clause_index_docs.py backend/tender_backend/tools/reindex_standard_clauses.py
git commit -m "test: cover standard clause index doc fields"
```

### Task 4: Update indexing paths and reindex tooling

**Files:**
- Modify: `backend/tender_backend/services/search_service/index_manager.py`
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py`
- Modify: `backend/tender_backend/workflows/standard_ingestion.py`
- Modify: `backend/tender_backend/tools/reindex_standard_clauses.py`
- Test: `backend/tests/unit/test_standard_clause_index_docs.py`

- [ ] **Step 1: Extend the OpenSearch mapping**

Update `CLAUSE_INDEX_MAPPINGS` to include:

```python
"standard_name": {"type": "text", "analyzer": "cn_default"},
"page_start": {"type": "integer"},
"page_end": {"type": "integer"},
```

Do not remove existing fields.

- [ ] **Step 2: Update all clause indexing producers**

Align clause index payloads in:

- `norm_processor._index_clauses()`
- `workflows/standard_ingestion.py`
- `tools/reindex_standard_clauses.py`

Required payload keys:

```python
{
    "standard_id": str(standard["id"]),
    "standard_code": standard.get("standard_code"),
    "standard_name": standard.get("standard_name"),
    "clause_id": doc_id,
    "clause_no": clause.get("clause_no"),
    "clause_title": clause.get("clause_title"),
    "clause_text": clause.get("clause_text"),
    "summary": clause.get("summary"),
    "tags": clause.get("tags", []),
    "specialty": standard.get("specialty"),
    "page_start": clause.get("page_start"),
    "page_end": clause.get("page_end"),
}
```

- [ ] **Step 3: Preserve compatibility for existing indices**

Do not assume all deployed environments will recreate `clause_index` immediately.

Document in code comments and implementation notes that:

- new documents will be indexed with richer fields
- search API still performs DB fallback when a field is missing

- [ ] **Step 4: Re-run the unit test to verify GREEN**

Run:

```bash
cd backend && .venv314/bin/pytest tests/unit/test_standard_clause_index_docs.py -q
```

Expected: PASS with enriched clause index docs.

- [ ] **Step 5: Commit the indexing changes**

```bash
git add backend/tender_backend/services/search_service/index_manager.py backend/tender_backend/services/norm_service/norm_processor.py backend/tender_backend/workflows/standard_ingestion.py backend/tender_backend/tools/reindex_standard_clauses.py backend/tests/unit/test_standard_clause_index_docs.py
git commit -m "feat: enrich standard clause search index"
```

## Chunk 3: Build the Frontend Workbench and Viewer Modal

### Task 5: Add frontend API contracts and PDF viewer dependency

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add the PDF viewer dependency**

Add `pdfjs-dist` to `frontend/package.json`.

Expected dependency addition:

```json
"dependencies": {
  "pdfjs-dist": "^4.x",
  ...
}
```

- [ ] **Step 2: Install the dependency**

Run:

```bash
cd frontend && npm install
```

Expected: `package-lock.json` updates with `pdfjs-dist`.

- [ ] **Step 3: Add the new API types and functions**

Extend `frontend/src/lib/api.ts` with:

- `StandardViewerData`
- `StandardSearchHit`
- `fetchStandardViewer()`
- `searchStandardClauses()`
- `deleteStandard()`

Recommended shapes:

```ts
export interface StandardViewerData extends StandardDetail {
  document_id: string;
  pdf_url: string;
}

export interface StandardSearchHit {
  standard_id: string;
  standard_name: string;
  specialty: string | null;
  clause_id: string;
  clause_no: string | null;
  tags: string[];
  summary: string | null;
  page_start: number | null;
  page_end: number | null;
}
```

- [ ] **Step 4: Run frontend build to verify the API layer stays GREEN**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS. No UI has been wired yet, but the type layer compiles.

- [ ] **Step 5: Commit the API contract and dependency changes**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/lib/api.ts
git commit -m "feat: add standard viewer api contracts"
```

### Task 6: Implement the table cards, query card, and viewer modal

**Files:**
- Modify: `frontend/src/modules/database/DatabaseModule.tsx`
- Create: `frontend/src/modules/database/components/StandardProgressBar.tsx`
- Create: `frontend/src/modules/database/components/StandardClauseTree.tsx`
- Create: `frontend/src/modules/database/components/StandardPdfPane.tsx`
- Create: `frontend/src/modules/database/components/StandardViewerModal.tsx`
- Create: `frontend/src/modules/database/components/StandardsTableCard.tsx`
- Create: `frontend/src/modules/database/components/StandardSearchCard.tsx`
- Modify: `frontend/src/styles/utilities.css`

- [ ] **Step 1: Extract reusable clause tree and progress bar components**

Move the current in-file clause tree rendering logic out of `DatabaseModule.tsx` into:

- `StandardClauseTree.tsx`
- `StandardProgressBar.tsx`

`StandardProgressBar` should accept:

```ts
type StandardProgressBarProps = {
  processingStatus: string;
  ocrStatus: string | null;
  aiStatus: string | null;
};
```

and render:

- percentage fill
- status label
- failure styling by failed stage

- [ ] **Step 2: Build the PDF pane**

Create `StandardPdfPane.tsx` using `pdfjs-dist` to:

- load a PDF by URL
- render the current page
- expose next/prev page controls
- accept a controlled target page

Suggested props:

```ts
type StandardPdfPaneProps = {
  pdfUrl: string;
  targetPage: number | null;
};
```

Keep the first version page-level only; no text-layer highlighting.

- [ ] **Step 3: Build the unified viewer modal**

Create `StandardViewerModal.tsx` with:

- left: `StandardPdfPane`
- right: `StandardClauseTree` + selected clause detail
- modes:
  - `browse`
  - `search-hit`

Suggested props:

```ts
type StandardViewerModalProps = {
  open: boolean;
  mode: "browse" | "search-hit";
  viewerData: StandardViewerData | null;
  initialClauseId?: string | null;
  onClose: () => void;
};
```

- [ ] **Step 4: Replace the card grid with the standards table card**

Implement `StandardsTableCard.tsx` to render:

- `规范编号`
- `规范名称`
- `专业`
- `状态`
- `编辑`
- `查阅`

Actions:

- delete
- retry on failed rows
- open viewer

Use the existing `.data-table` pattern where possible instead of inventing a new table system.

- [ ] **Step 5: Add the search card**

Implement `StandardSearchCard.tsx` with:

- search input
- query button or debounced input
- results table/list showing:
  - `规范名称`
  - `专业`
  - `条款号`
  - `条款标签`
  - `总结`
- click result -> open viewer modal in `search-hit` mode

- [ ] **Step 6: Recompose `DatabaseModule.tsx`**

Update the standards tab to render:

1. upload form
2. `StandardsTableCard`
3. `StandardSearchCard`
4. one shared `StandardViewerModal`

Keep polling only for the standards list; do not poll search results unless the user re-queries.

- [ ] **Step 7: Add CSS for the workbench and modal**

Extend `frontend/src/styles/utilities.css` for:

- standards table card
- search card
- progress bar
- viewer modal shell
- PDF pane
- split layout
- clause detail sidebar

Use the existing visual language of the repo rather than introducing a new design system.

- [ ] **Step 8: Run frontend build to verify GREEN**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS with the new cards and modal compiled.

- [ ] **Step 9: Commit the frontend workbench**

```bash
git add frontend/src/modules/database/DatabaseModule.tsx frontend/src/modules/database/components/StandardProgressBar.tsx frontend/src/modules/database/components/StandardClauseTree.tsx frontend/src/modules/database/components/StandardPdfPane.tsx frontend/src/modules/database/components/StandardViewerModal.tsx frontend/src/modules/database/components/StandardsTableCard.tsx frontend/src/modules/database/components/StandardSearchCard.tsx frontend/src/styles/utilities.css
git commit -m "feat: add standard pdf compare workbench ui"
```

## Chunk 4: Verify End-to-End Behavior and Finish

### Task 7: Run full verification on backend and frontend

**Files:**
- Test: `backend/tests/integration/test_standard_processing_job_repository.py`
- Test: `backend/tests/integration/test_standard_processing_scheduler.py`
- Test: `backend/tests/integration/test_standard_processing_queue_api.py`
- Test: `backend/tests/integration/test_standard_mineru_batch_flow.py`
- Test: `backend/tests/integration/test_standard_viewer_query_api.py`
- Test: `backend/tests/unit/test_standard_clause_index_docs.py`
- Test: `frontend` build output

- [ ] **Step 1: Run the backend focused suites**

Run:

```bash
DATABASE_URL=postgresql://tender:change-me@localhost:5432/tender \
PYTHONPATH=backend \
.venv314/bin/pytest \
backend/tests/integration/test_standard_processing_job_repository.py \
backend/tests/integration/test_standard_processing_scheduler.py \
backend/tests/integration/test_standard_processing_queue_api.py \
backend/tests/integration/test_standard_mineru_batch_flow.py \
backend/tests/integration/test_standard_viewer_query_api.py \
backend/tests/unit/test_standard_clause_index_docs.py -q
```

Expected: PASS with the new viewer/query/delete behavior and existing queue behavior both green.

- [ ] **Step 2: Run the frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 3: Re-read the requirements checklist against the built behavior**

Manually verify from the code and tested API surface:

- no standalone clause delete action exists
- standards page shows two fixed cards below upload
- list card uses table, not card wall
- query card returns clause hits
- viewer modal is left PDF / right AI result
- list mode opens full tree
- query mode opens hit + context

- [ ] **Step 4: Commit the verification checkpoint**

```bash
git add backend/tests/integration/test_standard_viewer_query_api.py backend/tests/unit/test_standard_clause_index_docs.py frontend/src/lib/api.ts frontend/src/modules/database/DatabaseModule.tsx frontend/src/modules/database/components frontend/src/styles/utilities.css backend/tender_backend/api/standards.py backend/tender_backend/db/repositories/standard_repo.py backend/tender_backend/services/search_service/index_manager.py backend/tender_backend/services/search_service/query_service.py backend/tender_backend/services/norm_service/norm_processor.py backend/tender_backend/workflows/standard_ingestion.py backend/tender_backend/tools/reindex_standard_clauses.py
git commit -m "test: verify standard pdf compare workflow"
```

### Task 8: Optional manual acceptance pass

**Files:**
- Runtime behavior only

- [ ] **Step 1: Start the local stack if not already running**

Run:

```bash
cd infra && docker-compose up -d postgres
```

Expected: local DB available for API verification.

- [ ] **Step 2: Launch the app and perform one manual browse/query pass**

Verify:

- upload still works
- completed standard appears in table
- delete removes a completed standard
- failed standard shows retry
- search returns hits
- clicking a hit opens the compare modal
- clicking a clause changes the PDF page

- [ ] **Step 3: Record any manual-only issues before merge**

If manual acceptance is skipped, explicitly note:

```text
No browser-based manual acceptance was performed; only backend tests and frontend build were run.
```

---

Plan complete and saved to `docs/superpowers/plans/2026-03-20-standard-pdf-clause-compare.md`. Ready to execute?

