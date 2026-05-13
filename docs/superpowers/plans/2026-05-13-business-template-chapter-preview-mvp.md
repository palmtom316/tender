# Business Template Chapter Preview MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `国网配网工程商务标` visible and usable in the chapter editor as a left-side chapter directory, a center page-by-page template preview, and a right-side material checklist/binding panel for business chapters.

**Architecture:** Keep the feature inside the existing `Authoring -> EditorContent` flow instead of creating a new route. Add one backend preview endpoint that parses the selected single-DOCX business template directly from `word/document.xml`, detects chapter boundaries and page breaks, and returns chapter/page preview data. Reuse the existing business material slot workbench on the frontend, but change the left side from “abstract slot list” to “template chapter directory + page preview + slot checklist”.

**Tech Stack:** FastAPI, psycopg, Python stdlib `zipfile` + XML parsing, React 19 + TypeScript, TanStack Query, Vitest + Testing Library, pytest.

---

## File Structure

- Create: `backend/tender_backend/services/template_service/business_template_preview.py`
  - Parse single-DOCX template packages into preview chapters/pages without adding new dependencies.
- Modify: `backend/tender_backend/api/template_packages.py`
  - Add a project-scoped preview endpoint that resolves the project’s selected template package and returns preview data.
- Create: `backend/tests/unit/test_business_template_preview.py`
  - Lock parser behavior for chapter detection and page splitting.
- Modify: `backend/tests/integration/test_template_package_api.py`
  - Cover the new project-scoped preview endpoint using an uploaded template package.
- Modify: `frontend/src/lib/api.ts`
  - Add preview response types and fetch function.
- Create: `frontend/src/modules/authoring/businessTemplatePreview.ts`
  - Bridge backend preview chapters to current business material slot rules and selection state.
- Modify: `frontend/src/modules/authoring/EditorContent.tsx`
  - Add business template chapter directory, center preview pages, right-side material checklist, and bind actions.
- Modify: `frontend/src/modules/authoring/EditorContent.test.tsx`
  - Add UI regression tests for chapter preview visibility, chapter selection, and bound-material state.

---

### Task 1: Add backend DOCX chapter preview parser

**Files:**
- Create: `backend/tender_backend/services/template_service/business_template_preview.py`
- Test: `backend/tests/unit/test_business_template_preview.py`

- [ ] **Step 1: Write the failing parser test**

Create `backend/tests/unit/test_business_template_preview.py` with a test that verifies a DOCX with explicit page breaks becomes two business chapters with correct page ranges.

```python
from pathlib import Path
from zipfile import ZipFile

from tender_backend.services.template_service.business_template_preview import parse_business_template_preview


def _write_minimal_docx(path: Path, document_xml: str) -> None:
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
      <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
      <Default Extension="xml" ContentType="application/xml"/>
      <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
    </Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
    </Relationships>"""
    with ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document_xml)


def test_parse_business_template_preview_splits_chapters_and_pages(tmp_path: Path) -> None:
    docx_path = tmp_path / "preview.docx"
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:r><w:t>一、商务偏差表</w:t></w:r></w:p>
        <w:p><w:r><w:t>商务偏差表正文第一页</w:t></w:r><w:r><w:br w:type="page"/></w:r></w:p>
        <w:p><w:r><w:t>二、承诺函</w:t></w:r></w:p>
        <w:p><w:r><w:t>承诺函正文第一页</w:t></w:r><w:r><w:br w:type="page"/></w:r></w:p>
      </w:body>
    </w:document>"""
    _write_minimal_docx(docx_path, document_xml)

    preview = parse_business_template_preview(docx_path)

    assert [chapter.chapter_title for chapter in preview.chapters] == ["商务偏差表", "承诺函"]
    assert [(chapter.page_start, chapter.page_end) for chapter in preview.chapters] == [(1, 1), (2, 2)]
    assert preview.chapters[0].pages[0].blocks[0] == "商务偏差表正文第一页"
    assert preview.chapters[1].pages[0].blocks[0] == "承诺函正文第一页"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd /home/palmtom/projects/tender/backend
../.venv/bin/pytest tests/unit/test_business_template_preview.py -q
```

Expected: FAIL with `ModuleNotFoundError` or missing `parse_business_template_preview`.

- [ ] **Step 3: Write the minimal parser implementation**

Create `backend/tender_backend/services/template_service/business_template_preview.py` and implement a parser that:
- opens `word/document.xml` with `zipfile.ZipFile`,
- walks paragraph nodes in order,
- accumulates text blocks per page,
- detects chapter headings via `^(?P<index>[一二三四五六七八九十]+|\\d+(?:\\.\\d+)*)[、．.](?P<title>.+)$`,
- starts a new chapter when a heading appears,
- increments page number when a paragraph contains `<w:br w:type="page">`,
- strips “（本页不编辑正文）” marker blocks from preview output.

Core shapes:

```python
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET


@dataclass(frozen=True)
class BusinessTemplatePreviewPage:
    page_number: int
    blocks: list[str]


@dataclass(frozen=True)
class BusinessTemplatePreviewChapter:
    chapter_code: str
    chapter_title: str
    page_start: int
    page_end: int
    pages: list[BusinessTemplatePreviewPage]


@dataclass(frozen=True)
class BusinessTemplatePreview:
    package_title: str
    chapters: list[BusinessTemplatePreviewChapter]


def parse_business_template_preview(docx_path: Path) -> BusinessTemplatePreview:
    ...
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
cd /home/palmtom/projects/tender/backend
../.venv/bin/pytest tests/unit/test_business_template_preview.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/services/template_service/business_template_preview.py backend/tests/unit/test_business_template_preview.py
git commit -m "feat: add business template preview parser"
```

---

### Task 2: Expose a project-scoped business template preview API

**Files:**
- Modify: `backend/tender_backend/api/template_packages.py`
- Modify: `backend/tests/integration/test_template_package_api.py`

- [ ] **Step 1: Write the failing API test**

Add this test to `backend/tests/integration/test_template_package_api.py`:

```python
def test_project_business_template_preview_returns_chapters(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_url = _db_url()
    if not db_url:
        pytest.skip("DATABASE_URL not set; skipping integration test")

    import_root = tmp_path / "imports"
    import_root.mkdir()
    monkeypatch.setenv("TEMPLATE_IMPORT_ROOTS", str(import_root))
    get_settings.cache_clear()

    template_path = tmp_path / "国网配网工程商务标.docx"
    template = Document()
    template.add_paragraph("一、商务偏差表")
    template.add_paragraph("商务偏差表正文")
    template.add_page_break()
    template.add_paragraph("二、承诺函")
    template.add_paragraph("承诺函正文")
    template.save(template_path)

    with psycopg.connect(db_url) as conn:
        _apply_template_schema(conn)
        _reset_template_tables(conn)
        conn.execute(load_initial_schema_sql())
        conn.commit()

    client = SyncASGIClient(app)
    client.headers.update(_AUTH_HEADERS)
    try:
        with template_path.open("rb") as handle:
            uploaded = client.post(
                "/api/template-packages/upload",
                data={
                    "project_type": "国网配网工程",
                    "template_kind": "business",
                    "display_name": "国网配网工程商务标",
                    "category_code": "sgcc_distribution",
                },
                files={"file": (template_path.name, handle, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            )
        assert uploaded.status_code == 201
        package_id = uploaded.json()["id"]

        project = client.post("/api/projects", json={"name": "预览项目", "industry": "power", "business_line": "sgcc_distribution"})
        assert project.status_code == 200
        project_id = project.json()["id"]

        confirmed = client.post(
            f"/api/projects/{project_id}/template-selection",
            json={"package_id": package_id},
        )
        assert confirmed.status_code == 200

        preview = client.get(f"/api/projects/{project_id}/business-template-preview")
        assert preview.status_code == 200
        assert [chapter["chapter_title"] for chapter in preview.json()["chapters"]] == ["商务偏差表", "承诺函"]
    finally:
        client.close()
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd /home/palmtom/projects/tender/backend
../.venv/bin/pytest tests/integration/test_template_package_api.py -q
```

Expected: FAIL with 404 because `/api/projects/{project_id}/business-template-preview` does not exist.

- [ ] **Step 3: Add the minimal endpoint**

In `backend/tender_backend/api/template_packages.py`:
- add `BusinessTemplatePreviewPageOut`, `BusinessTemplatePreviewChapterOut`, `BusinessTemplatePreviewOut`,
- add `GET /projects/{project_id}/business-template-preview`,
- resolve project via `ProjectRepository().get(...)`,
- require `selected_template_package_id`,
- load package with `_repo.get_by_id(...)`,
- resolve `docx_path = Path(package.source_root) / item.relative_path`,
- call `parse_business_template_preview(docx_path)`,
- return JSON-safe output.

Minimal endpoint contract:

```python
@router.get("/projects/{project_id}/business-template-preview", response_model=BusinessTemplatePreviewOut)
async def get_project_business_template_preview(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> BusinessTemplatePreviewOut:
    require_project_access(conn, project_id=project_id, user=user)
    ...
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
cd /home/palmtom/projects/tender/backend
../.venv/bin/pytest tests/unit/test_business_template_preview.py tests/integration/test_template_package_api.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/api/template_packages.py backend/tests/integration/test_template_package_api.py
git commit -m "feat: expose project business template preview api"
```

---

### Task 3: Add frontend preview types and chapter-preview view model

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/modules/authoring/businessTemplatePreview.ts`
- Modify: `frontend/src/modules/authoring/EditorContent.test.tsx`

- [ ] **Step 1: Write the failing frontend view-model test**

Add a test to `frontend/src/modules/authoring/EditorContent.test.tsx` that expects a business chapter preview card to appear when the selected project has a template preview response.

```tsx
it("shows business template chapter preview pages for business chapters", async () => {
  fetchBidOutlineMock.mockResolvedValueOnce({
    id: "outline-1",
    project_id: "proj-1",
    outline_name: "默认目录",
    status: "confirmed",
    chapters: [
      {
        id: "chapter-business-1",
        project_id: "proj-1",
        outline_id: "outline-1",
        chapter_code: "1",
        chapter_title: "商务偏差表",
        volume_type: "business",
        sort_order: 1,
        metadata_json: {},
      },
    ],
  });
  fetchDraftsMock.mockResolvedValueOnce([]);
  assembleBusinessBidMock.mockResolvedValueOnce({
    project_id: "proj-1",
    run: {},
    chapters: [],
    response_matrix: [],
    missing_materials: [],
    boundary: "完成",
  });
  fetchBusinessTemplatePreviewMock.mockResolvedValueOnce({
    package_title: "国网配网工程商务标",
    chapters: [
      {
        chapter_code: "1",
        chapter_title: "商务偏差表",
        page_start: 1,
        page_end: 1,
        pages: [{ page_number: 1, blocks: ["商务偏差表", "序号 采购文件条目号"] }],
      },
    ],
  });

  render(withClient(<EditorContent />));
  fireEvent.click(await screen.findByRole("button", { name: "资格商务装配" }));
  await waitFor(() => expect(fetchBusinessTemplatePreviewMock).toHaveBeenCalled());

  expect(await screen.findByText("模板页面预览")).toBeInTheDocument();
  expect(screen.getByText("P1")).toBeInTheDocument();
  expect(screen.getByText("序号 采购文件条目号")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd /home/palmtom/projects/tender/frontend
npm test -- --run src/modules/authoring/EditorContent.test.tsx
```

Expected: FAIL because the preview fetch function and UI do not exist.

- [ ] **Step 3: Add API types and preview bridge helpers**

In `frontend/src/lib/api.ts`, add:

```ts
export interface BusinessTemplatePreviewPage {
  page_number: number;
  blocks: string[];
}

export interface BusinessTemplatePreviewChapter {
  chapter_code: string;
  chapter_title: string;
  page_start: number;
  page_end: number;
  pages: BusinessTemplatePreviewPage[];
}

export interface BusinessTemplatePreview {
  package_title: string;
  chapters: BusinessTemplatePreviewChapter[];
}

export function fetchBusinessTemplatePreview(projectId: string, options?: { signal?: AbortSignal }): Promise<BusinessTemplatePreview> {
  return request<BusinessTemplatePreview>(`/projects/${projectId}/business-template-preview`, { signal: options?.signal });
}
```

Create `frontend/src/modules/authoring/businessTemplatePreview.ts` to:
- find the preview chapter that best matches the current outline chapter,
- normalize page blocks for rendering,
- surface a `previewAvailable` boolean.

Core helper:

```ts
export function matchPreviewChapter(
  preview: BusinessTemplatePreview | undefined,
  chapter: Pick<BidChapter, "chapter_code" | "chapter_title" | "volume_type"> | null | undefined,
) {
  if (!preview || !chapter || chapter.volume_type === "technical") return null;
  return preview.chapters.find((row) => row.chapter_code === chapter.chapter_code)
    ?? preview.chapters.find((row) => row.chapter_title.includes(chapter.chapter_title) || chapter.chapter_title.includes(row.chapter_title))
    ?? null;
}
```

- [ ] **Step 4: Run the test to verify it still fails on UI only**

Run:

```bash
cd /home/palmtom/projects/tender/frontend
npm test -- --run src/modules/authoring/EditorContent.test.tsx
```

Expected: FAIL, but now because the rendering is missing rather than the API symbols.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/modules/authoring/businessTemplatePreview.ts frontend/src/modules/authoring/EditorContent.test.tsx
git commit -m "feat: add business template preview api client"
```

---

### Task 4: Render chapter directory + page preview + material checklist in EditorContent

**Files:**
- Modify: `frontend/src/modules/authoring/EditorContent.tsx`
- Modify: `frontend/src/modules/authoring/EditorContent.test.tsx`

- [ ] **Step 1: Write the failing interaction test for chapter switching**

Extend `frontend/src/modules/authoring/EditorContent.test.tsx`:

```tsx
it("switches preview pages and material checklist when selecting another business chapter", async () => {
  fetchBidOutlineMock.mockResolvedValueOnce({
    id: "outline-1",
    project_id: "proj-1",
    outline_name: "默认目录",
    status: "confirmed",
    chapters: [
      { id: "chapter-business-1", project_id: "proj-1", outline_id: "outline-1", chapter_code: "1", chapter_title: "商务偏差表", volume_type: "business", sort_order: 1, metadata_json: {} },
      { id: "chapter-business-2", project_id: "proj-1", outline_id: "outline-1", chapter_code: "2", chapter_title: "承诺函", volume_type: "business", sort_order: 2, metadata_json: {} },
    ],
  });
  fetchDraftsMock.mockResolvedValueOnce([]);
  assembleBusinessBidMock.mockResolvedValueOnce({
    project_id: "proj-1",
    run: {},
    chapters: [],
    response_matrix: [],
    missing_materials: [{ chapter_code: "2", material_name: "信用中国查询报告", material_type: "evidence_asset", reason: "缺资料" }],
    boundary: "完成",
  });
  fetchBusinessTemplatePreviewMock.mockResolvedValueOnce({
    package_title: "国网配网工程商务标",
    chapters: [
      { chapter_code: "1", chapter_title: "商务偏差表", page_start: 1, page_end: 1, pages: [{ page_number: 1, blocks: ["商务偏差表正文"] }] },
      { chapter_code: "2", chapter_title: "承诺函", page_start: 2, page_end: 3, pages: [{ page_number: 2, blocks: ["承诺函正文"] }] },
    ],
  });

  render(withClient(<EditorContent />));
  fireEvent.click(await screen.findByRole("button", { name: "资格商务装配" }));
  await waitFor(() => expect(fetchBusinessTemplatePreviewMock).toHaveBeenCalled());
  fireEvent.click(await screen.findByRole("button", { name: "查看章节 2 承诺函" }));

  expect(await screen.findByText("承诺函正文")).toBeInTheDocument();
  expect(screen.getByText("信用中国查询报告")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd /home/palmtom/projects/tender/frontend
npm test -- --run src/modules/authoring/EditorContent.test.tsx
```

Expected: FAIL because the business chapter directory and preview switcher do not exist.

- [ ] **Step 3: Implement the business chapter preview UI**

In `frontend/src/modules/authoring/EditorContent.tsx`:
- add a query for `fetchBusinessTemplatePreview(projectId)` enabled only after business assembly begins and when a business chapter is selected,
- render a left-side business chapter directory with button label `查看章节 ${chapter.chapter_code} ${chapter.chapter_title}`,
- render a center card titled `模板页面预览`,
- render each page as a card headed with `P${page.page_number}`,
- keep the right-side `资料位清单` and `资料候选区`,
- preserve the existing technical chapter cards unchanged.

Minimal UI contract:

```tsx
<section className="chapter-delivery-card" aria-label="模板页面预览">
  <div className="chapter-delivery-card__header">
    <div>
      <strong>模板页面预览</strong>
      <p>按模板分页展示固定正文，当前版本只读，不直接编辑版式。</p>
    </div>
    <Badge variant="info">{matchedPreviewChapter?.pages.length ?? 0} 页</Badge>
  </div>
</section>
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
cd /home/palmtom/projects/tender/frontend
npm test -- --run src/modules/authoring/EditorContent.test.tsx src/modules/projects/ProjectsModule.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/modules/authoring/EditorContent.tsx frontend/src/modules/authoring/EditorContent.test.tsx
git commit -m "feat: add business template chapter preview ui"
```

---

### Task 5: Verify end-to-end business preview path and keep technical flow stable

**Files:**
- Modify: `frontend/src/modules/authoring/EditorContent.test.tsx`
- Modify: `backend/tests/integration/test_template_package_api.py`

- [ ] **Step 1: Add the final regression assertions**

Add/keep tests that prove:
- business chapters show `模板页面预览`,
- technical chapters still show `图表任务`,
- binding a business material candidate still flips slot state to `已匹配`.

Use these exact assertions:

```tsx
expect(await screen.findByLabelText("图表任务")).toBeInTheDocument();
expect(screen.queryByText("模板页面预览")).not.toBeInTheDocument();
expect(await screen.findByText("已匹配")).toBeInTheDocument();
```

- [ ] **Step 2: Run backend and frontend focused suites**

Run:

```bash
cd /home/palmtom/projects/tender/backend
../.venv/bin/pytest tests/unit/test_business_template_preview.py tests/integration/test_template_package_api.py -q

cd /home/palmtom/projects/tender/frontend
npm test -- --run src/modules/authoring/EditorContent.test.tsx src/modules/projects/ProjectsModule.test.tsx
```

Expected: all PASS.

- [ ] **Step 3: Run one local API sanity check**

Run:

```bash
cd /home/palmtom/projects/tender
curl -sS "http://127.0.0.1:18000/api/projects/<PROJECT_ID>/business-template-preview" -H "Authorization: Bearer dev-token"
```

Expected: JSON containing `package_title` and `chapters`.

- [ ] **Step 4: Do a manual browser verification**

Manual check in local frontend:
- open a project with `selected_template_package_id`,
- go to `智能编制 -> 章节编辑`,
- click `资格商务装配`,
- confirm a business chapter shows:
  - left chapter directory,
  - center `模板页面预览`,
  - right `资料位清单` and `资料候选区`,
- click a technical chapter and confirm `图表任务` still appears.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/integration/test_template_package_api.py frontend/src/modules/authoring/EditorContent.test.tsx
git commit -m "test: verify business template preview flow"
```

---

## Self-Review

- **Spec coverage:** The plan covers the agreed MVP: visible business template chapter directory, readable paged content preview, right-side material checklist/binding, and no regression for technical chapters.
- **Placeholder scan:** No `TODO`/`TBD` placeholders remain; each task names exact files, commands, and expected failures.
- **Type consistency:** The plan uses a single preview model end-to-end: `BusinessTemplatePreview -> BusinessTemplatePreviewChapter -> BusinessTemplatePreviewPage`.

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-13-business-template-chapter-preview-mvp.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
