# Ad Hoc Chapter Task Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make tender able to safely handle a tender-required chapter that has no similar baseline template by turning it into a guided task card, collecting confirmed business inputs, generating a confirmed outline, generating a constrained draft, and blocking export until coverage passes.

**Architecture:** Keep this as a narrow MVP inside the existing bid chapter and authoring workflow. Store the ad hoc chapter task card under `bid_chapter.metadata_json.ad_hoc_task_card`, but only create it for chapters explicitly marked as ad hoc by reconciliation or user action. Generation is status-machine driven: no title-only drafting, no prompt UI for bid engineers, and no export until `draft_ready` plus `chapter_draft.coverage_report_json.coverage_passed=true`.

**Tech Stack:** FastAPI, psycopg, PostgreSQL JSONB, React 18, TypeScript, TanStack Query, pytest, Vitest, existing `bid_chapter`, `chapter_draft`, `project_requirement`, `bid_chapter_requirement`, `EditorContent`, `chapterDelivery`, and export gate modules.

---

## Product Scope

This plan handles one problem only: an招标文件明确要求新增一个独立章节，但配网工程技术/商务基准模板中没有相似章节。

The MVP supports three ad hoc chapter types:

- `technical_special_plan`: 技术专项方案，如施工现场总平面布置、临电临水、停电组织、应急处置、绿色施工专项。
- `material_attachment`: 资料附件章节，如新增证明材料、证书、承诺函附件、专项说明附件。
- `table_checklist`: 表格清单章节，如人员驻场表、设备投入表、风险清单、响应表。

This plan does not implement a generic prompt platform, global template evolution, model profile management, or safe limited generation mode.

## Final Product Decisions

### Decision 1: Strict trigger with manual fallback

A chapter may enter the ad hoc task-card flow only through one of these entry points:

1. `bid_chapter.metadata_json.ad_hoc_required = true`.
2. `bid_chapter.metadata_json.template_match_status = "missing"`.
3. `template_directory_reconciliation_service` emits an `add_chapter` suggestion with:

```json
{
  "ad_hoc_required": true,
  "suggested_initial_status": "task_card_pending"
}
```

Manual fallback is allowed through a user action `创建新增章节任务卡`, but the backend must reject it unless the chapter belongs to the project, the user has access, the chapter is not a normal baseline chapter, and the chapter has at least one mapped tender source requirement. If the user explicitly chooses “无来源，仅人工补录”, status must become `blocked_insufficient_evidence`.

The backend must not create a task card just because a GET endpoint was called, just because a chapter has no template block, or for existing mature baseline chapters such as technical 8/9/10.

### Decision 2: Single status source

The card has one status field only:

```json
{"status": "outline_confirmed"}
```

Do not store `outline_confirmed: true` or parallel status booleans.

Valid statuses:

- `task_card_pending`
- `needs_input`
- `outline_ready`
- `outline_confirmed`
- `draft_ready`
- `blocked_insufficient_evidence`

Allowed state flow:

```text
task_card_pending -> needs_input -> outline_ready -> outline_confirmed -> draft_ready
any state -> blocked_insufficient_evidence
blocked_insufficient_evidence -> needs_input
```

### Decision 3: Coverage report storage

Ad hoc generation must write coverage to:

```text
chapter_draft.coverage_report_json
```

Never write coverage to `chapter_draft.page_estimate_json`. Do not write coverage into formal bid正文 by default.

Coverage report shape:

```json
{
  "coverage_passed": true,
  "covered_requirement_ids": ["uuid-1"],
  "missing_requirement_ids": [],
  "covered_points": [
    {
      "requirement_id": "uuid-1",
      "source_locator": "P32 技术评分标准第4项",
      "must_respond": "施工现场布置原则",
      "covered_by_heading": "施工现场总平面布置"
    }
  ],
  "missing_points": [],
  "manual_review_required": false
}
```

### Decision 4: No safe limited generation mode in MVP

If evidence is insufficient, status is `blocked_insufficient_evidence`. The UI only shows missing evidence, missing inputs, missing attachments, and suggested补充方式. It must not generate draft, limited draft, gap正文, or exportable content.

### Decision 5: Type-specific generation

`technical_special_plan`:

- Requires confirmed outline before draft.
- May use existing AI/LLM generation only when constrained by `source_anchors`, `must_respond`, answers, mapped requirements, and confirmed outline.
- Must not invent site conditions, personnel, equipment, dates, standards, or commitments.

`material_attachment`:

- Does not generate long prose.
- Generates material说明, 资料清单, 附件占位符, and 有效性检查表 only.

`table_checklist`:

- Generates table structure first and only short说明.
- Missing data remains `待确认`, `{{ placeholder }}`, or `资料库选择`.

### Decision 6: Classification priority

`build_initial_task_card` classifies in this order:

1. `table_checklist` when title/source indicates 表, 清单, 矩阵, 台账, 响应表, 核查表, 明细表, 汇总表, 统计表 and the deliverable is structured data.
2. `material_attachment` when title/source indicates 证明, 证书, 附件, 承诺函, 截图, 报告, 说明材料, 证明材料.
3. `technical_special_plan` when title/source indicates 方案, 措施, 布置, 临电, 临水, 应急, 停电, 绿色施工, 专项, 组织, 保障.
4. Default to `technical_special_plan` if source requirements exist; otherwise `blocked_insufficient_evidence`.

Conflict examples:

- `专项方案响应表` -> `table_checklist`
- `临电临水措施清单` -> `table_checklist`
- `承诺函及证明材料清单` -> `table_checklist`
- `证明材料附件` -> `material_attachment`
- `绿色施工专项说明` -> `material_attachment`
- `绿色施工专项方案` -> `technical_special_plan`

### Decision 7: Strict PATCH semantics

PATCH may update answers and `chapter_type`, but:

- Unknown answer keys return 422.
- `choice` answers must be in `options`.
- Empty required answers keep status `needs_input`.
- Changing `chapter_type` rebuilds `missing_inputs`, clears `outline`, clears coverage, and returns status to `needs_input`.
- Changing required answers after outline generation clears the old outline and returns status to `needs_input`.
- Changing answers after `draft_ready` marks the existing draft stale or sets `draft_stale=true`, returns status to `needs_input`, and blocks export.

### Decision 8: Safe metadata update

Only update `metadata_json.ad_hoc_task_card`. Preserve all other metadata keys such as `template_key`, `parent_code`, `render_mode`, and `ad_hoc_required`.

Preferred SQL:

```sql
UPDATE bid_chapter
SET metadata_json = jsonb_set(
  COALESCE(metadata_json, '{}'::jsonb),
  '{ad_hoc_task_card}',
  %s::jsonb,
  true
)
WHERE id = %s
  AND project_id = %s
RETURNING *;
```

### Decision 9: Frontend entry condition

`chapterDeliveryKind` returns `ad_hoc_task_card` when either field exists:

```ts
Boolean(chapter?.metadata_json?.ad_hoc_task_card) ||
Boolean(chapter?.metadata_json?.ad_hoc_required)
```

If only `ad_hoc_required` exists, `AdHocChapterTaskCard` calls GET to let the backend create or return the card.

### Decision 10: Export gate location

Before editing export code, locate the active path used by `frontend/src/modules/export/ExportGateContent.tsx`. Add ad hoc blocking only at that backend gate aggregation point. Tests must prove the frontend receives the blocking issue from that active path.

Blocking statuses:

- `task_card_pending`
- `needs_input`
- `outline_ready`
- `outline_confirmed`
- `blocked_insufficient_evidence`

Non-blocking status is only `draft_ready`, and only when a draft exists and `coverage_report_json.coverage_passed=true`.

User-facing issue:

```text
新增章节任务卡未完成
```

Hint:

```text
请先补充信息、确认大纲并生成正文。
```

Do not expose internal status names in the frontend.

## Data Model

No new table is required for the MVP. Store the task card in `bid_chapter.metadata_json.ad_hoc_task_card`.

Shape:

```json
{
  "status": "needs_input",
  "chapter_type": "technical_special_plan",
  "source_anchors": [
    {
      "requirement_id": "uuid",
      "source_file": "招标文件.pdf",
      "source_locator": "P32 技术评分标准第4项",
      "text": "应提供施工现场总平面布置及临电临水方案"
    }
  ],
  "must_respond": [
    "施工现场布置原则",
    "临时用电方案",
    "临时用水方案",
    "材料堆放与机械布置",
    "安全文明施工"
  ],
  "missing_inputs": [
    {
      "key": "site_type",
      "label": "项目现场类型",
      "input_type": "choice",
      "options": ["城区道路", "小区配网", "乡镇线路", "开关站周边"],
      "required": true,
      "answer": null
    }
  ],
  "outline": [],
  "draft_stale": false
}
```

## User Flow

- [ ] System identifies an add-chapter requirement with no source template match and marks it `ad_hoc_required=true`.
- [ ] Authoring editor routes the chapter to `AdHocChapterTaskCard` because `ad_hoc_required` or `ad_hoc_task_card` exists.
- [ ] Component calls GET to create or load the task card.
- [ ] User answers required business questions.
- [ ] User clicks `生成章节大纲`.
- [ ] Backend validates required answers and generates a conservative outline.
- [ ] User confirms or edits the outline.
- [ ] User clicks `生成正文`.
- [ ] Backend generates type-specific draft and writes `chapter_draft.coverage_report_json`.
- [ ] Export is blocked until status is `draft_ready`, a draft exists, and coverage passes.

## File Structure

Backend create:

- `backend/tender_backend/services/ad_hoc_chapter_task_card.py`
  - Owns classification, task-card construction, validation, safe metadata merge helpers, outline generation, draft markdown construction, and coverage checks.

- `backend/tests/unit/test_ad_hoc_chapter_task_card.py`
  - Unit tests for classification priority, required questions, PATCH validation, outline generation, metadata preservation, draft construction, and coverage checks.

Backend modify:

- `backend/tender_backend/services/bid_chapter_generation.py`
  - Blocks unsafe ad hoc generation and uses confirmed task card outline/type-specific generation.

- `backend/tender_backend/api/bid_outline.py`
  - Adds MVP task-card endpoints, or imports a focused router if the codebase already has a better route module pattern.

- `backend/tender_backend/services/template_directory_reconciliation_service.py`
  - Marks add-chapter suggestions without template match as ad hoc required.

- Active export gate backend service found through `ExportGateContent.tsx`
  - Adds ad hoc blocking issue.

Frontend create:

- `frontend/src/modules/authoring/adHocChapterTaskCard.ts`
  - Pure helpers for status labels, missing-input validation, and action availability.

- `frontend/src/modules/authoring/AdHocChapterTaskCard.tsx`
  - UI for source anchors, must-respond points, business questions, outline preview/edit, and task actions.

Frontend modify:

- `frontend/src/lib/api.ts`
  - Adds task-card types and API client functions.

- `frontend/src/modules/authoring/EditorContent.tsx`
  - Routes ad hoc chapters to task-card UI and hides prompt controls.

- `frontend/src/modules/authoring/chapterDelivery.ts`
  - Adds delivery kind `ad_hoc_task_card` using Decision 9.

- `frontend/src/modules/export/ExportGateContent.tsx`
  - Only if its current API response shape requires frontend display adjustments.

## Standard Test Commands

Use project-root commands, not `cd backend && python -m pytest`:

```bash
PYTHONPATH=.:backend .venv/bin/pytest -q backend/tests/unit/test_ad_hoc_chapter_task_card.py
PYTHONPATH=.:backend .venv/bin/pytest -q backend/tests/unit/test_bid_chapter_generation.py
PYTHONPATH=.:backend .venv/bin/pytest -q backend/tests/unit/test_template_directory_reconciliation_service.py
PYTHONPATH=.:backend .venv/bin/pytest -q backend/tests/integration/test_bid_generation_api.py
```

Frontend commands:

```bash
cd frontend && npm test -- adHocChapterTaskCard.test.ts EditorContent.test.tsx ExportGateContent.test.tsx
```

---

## Task 1: Define Task Card Service And Status Machine

**Files:**

- Create: `backend/tender_backend/services/ad_hoc_chapter_task_card.py`
- Create: `backend/tests/unit/test_ad_hoc_chapter_task_card.py`

- [ ] **Step 1: Write classification tests**

Add tests for the exact conflict examples in Decision 6:

```python
def test_classification_priority_table_over_attachment_and_plan() -> None:
    card = build_initial_task_card(
        chapter_title="承诺函及证明材料清单",
        source_requirements=[{"id": "r1", "title": "证明材料清单", "requirement_text": "须提供承诺函及证明材料清单"}],
    )
    assert card["chapter_type"] == "table_checklist"


def test_classification_green_special_statement_is_attachment() -> None:
    card = build_initial_task_card(
        chapter_title="绿色施工专项说明",
        source_requirements=[{"id": "r1", "title": "专项说明", "requirement_text": "须提供绿色施工专项说明材料"}],
    )
    assert card["chapter_type"] == "material_attachment"


def test_no_source_requirements_blocks_evidence() -> None:
    card = build_initial_task_card(chapter_title="新增专项方案", source_requirements=[])
    assert card["status"] == "blocked_insufficient_evidence"
```

- [ ] **Step 2: Implement card construction**

Implement:

```python
def build_initial_task_card(*, chapter_title: str, source_requirements: list[dict[str, Any]], manual_no_source: bool = False) -> dict[str, Any]:
    ...
```

Rules:

- Use Decision 6 classification priority.
- Build `source_anchors` from requirement id, source file, source locator, and text.
- Derive `must_respond` from requirement titles/text, de-duplicated and non-empty.
- If no source requirements or `manual_no_source=True`, return `blocked_insufficient_evidence`.
- Otherwise status is `needs_input` when required questions exist.

- [ ] **Step 3: Implement required questions by type**

Use these `missing_inputs`:

`technical_special_plan`:

- `site_type`: choice, required, options `城区道路`, `小区配网`, `乡镇线路`, `开关站周边`, `其他`.
- `has_site_drawing`: choice, required, options `uploaded`, `not_available_text_only`.
- `special_constraint`: text, optional.

`material_attachment`:

- `material_source`: choice, required, options `company_asset_library`, `user_upload`, `tender_required_only`.
- `attachment_required`: choice, required, options `yes`, `no`.

`table_checklist`:

- `table_basis`: choice, required, options `company_database`, `user_input`, `tender_requirement_only`.
- `manual_review_required`: choice, required, options `yes`, `no`.

- [ ] **Step 4: Implement status validation helpers**

Implement:

```python
VALID_STATUSES = {...}
BLOCKING_STATUSES = {...}

def validate_task_card_status(card: dict[str, Any]) -> None: ...
def missing_required_inputs(card: dict[str, Any]) -> list[str]: ...
def validate_task_card_ready_for_outline(card: dict[str, Any]) -> dict[str, Any]: ...
def validate_task_card_ready_for_draft(card: dict[str, Any]) -> None: ...
```

- [ ] **Step 5: Run tests**

```bash
PYTHONPATH=.:backend .venv/bin/pytest -q backend/tests/unit/test_ad_hoc_chapter_task_card.py
```

Expected: tests pass.

## Task 2: Strict PATCH Semantics And Metadata Preservation

**Files:**

- Modify: `backend/tender_backend/services/ad_hoc_chapter_task_card.py`
- Test: `backend/tests/unit/test_ad_hoc_chapter_task_card.py`

- [ ] **Step 1: Add PATCH validation tests**

Test unknown key, invalid choice, chapter type change, answer change after outline, and answer change after draft:

```python
def test_patch_rejects_unknown_answer_key() -> None:
    card = build_initial_task_card(chapter_title="临电临水方案", source_requirements=[{"id": "r1", "title": "方案", "requirement_text": "临电临水方案"}])
    with pytest.raises(ValueError, match="unknown answer key"):
        update_task_card_answers(card, answers={"unknown_key": "x"})


def test_patch_invalidates_outline_when_required_answer_changes() -> None:
    card = build_initial_task_card(chapter_title="临电临水方案", source_requirements=[{"id": "r1", "title": "方案", "requirement_text": "临电临水方案"}])
    card["status"] = "outline_confirmed"
    card["outline"] = [{"heading": "编制依据", "purpose": "说明来源", "must_cover": ["招标要求"]}]
    updated = update_task_card_answers(card, answers={"site_type": "城区道路"})
    assert updated["status"] == "needs_input"
    assert updated["outline"] == []
```

- [ ] **Step 2: Implement update helpers**

Implement:

```python
def update_task_card_answers(card: dict[str, Any], *, answers: dict[str, Any]) -> dict[str, Any]: ...
def change_task_card_type(card: dict[str, Any], *, chapter_type: str) -> dict[str, Any]: ...
def merge_task_card_metadata(metadata: dict[str, Any] | None, card: dict[str, Any]) -> dict[str, Any]: ...
```

`merge_task_card_metadata` must preserve existing metadata keys.

- [ ] **Step 3: Add metadata preservation test**

```python
def test_merge_task_card_metadata_preserves_existing_keys() -> None:
    metadata = {
        "template_key": "sgcc_distribution_technical_v1",
        "parent_code": "8",
        "render_mode": "single_docx_section",
        "ad_hoc_required": True,
    }
    merged = merge_task_card_metadata(metadata, {"status": "needs_input", "chapter_type": "technical_special_plan"})
    assert merged["template_key"] == "sgcc_distribution_technical_v1"
    assert merged["parent_code"] == "8"
    assert merged["render_mode"] == "single_docx_section"
    assert merged["ad_hoc_required"] is True
    assert merged["ad_hoc_task_card"]["status"] == "needs_input"
```

- [ ] **Step 4: Run tests**

```bash
PYTHONPATH=.:backend .venv/bin/pytest -q backend/tests/unit/test_ad_hoc_chapter_task_card.py
```

Expected: tests pass.

## Task 3: Generate Safe Outline And Draft Content

**Files:**

- Modify: `backend/tender_backend/services/ad_hoc_chapter_task_card.py`
- Test: `backend/tests/unit/test_ad_hoc_chapter_task_card.py`

- [ ] **Step 1: Add outline tests by type**

Expected outline headings:

`technical_special_plan`: 编制依据, 工程条件与限制, 专项方案, 安全文明施工, 检查与验收, 招标要求响应表.

`material_attachment`: 材料说明, 资料清单, 附件占位符, 有效性检查.

`table_checklist`: 表格说明, 字段定义, 数据来源, 人工确认.

- [ ] **Step 2: Implement outline generation**

Signature:

```python
def generate_task_card_outline(card: dict[str, Any]) -> list[dict[str, Any]]:
    ...
```

Each row shape:

```json
{"heading": "编制依据", "purpose": "说明本章来自招标文件要求和项目资料", "must_cover": ["来源页码", "评分点", "强制要求"]}
```

- [ ] **Step 3: Add draft construction tests**

For `technical_special_plan`, assert generated markdown includes confirmed outline headings and `## 招标要求响应表`.

For `material_attachment`, assert no long prose and includes `{{ asset:ad_hoc_material_attachment:n }}`.

For `table_checklist`, assert markdown includes a table and `待确认` placeholders.

- [ ] **Step 4: Implement draft construction and coverage**

Implement:

```python
def build_task_card_draft_markdown(card: dict[str, Any], requirements: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    ...
```

Return content markdown and coverage report. Coverage passes only when every `must_respond` item appears in at least one outline heading or `must_cover` entry.

- [ ] **Step 5: Run tests**

```bash
PYTHONPATH=.:backend .venv/bin/pytest -q backend/tests/unit/test_ad_hoc_chapter_task_card.py
```

Expected: tests pass.

## Task 4: Add Task Card API

**Files:**

- Modify: `backend/tender_backend/api/bid_outline.py`
- Test: `backend/tests/integration/test_bid_generation_api.py`

- [ ] **Step 1: Add request/response models**

Add models:

```python
class AdHocTaskCardUpdateBody(BaseModel):
    answers: dict[str, Any] = {}
    chapter_type: str | None = None

class AdHocTaskCardConfirmOutlineBody(BaseModel):
    outline: list[dict[str, Any]]

class AdHocTaskCardOut(BaseModel):
    chapter_id: UUID
    card: dict[str, Any]
```

- [ ] **Step 2: Add GET endpoint**

Route:

```text
GET /projects/{project_id}/bid-chapters/{chapter_id}/ad-hoc-task-card
```

Behavior:

- Requires project access.
- Loads chapter by both `project_id` and `chapter_id`.
- If card exists, returns it.
- If no card exists, creates one only when Decision 1 trigger conditions pass.
- Preserves existing metadata when writing.
- Rejects normal baseline chapters with 409.

- [ ] **Step 3: Add PATCH endpoint**

Route:

```text
PATCH /projects/{project_id}/bid-chapters/{chapter_id}/ad-hoc-task-card
```

Behavior:

- Applies Decision 7 strict validation.
- Preserves metadata.
- Returns updated card.

- [ ] **Step 4: Add outline endpoints**

Routes:

```text
POST /projects/{project_id}/bid-chapters/{chapter_id}/ad-hoc-task-card/outline
POST /projects/{project_id}/bid-chapters/{chapter_id}/ad-hoc-task-card/confirm-outline
```

Outline generation sets status `outline_ready`. Confirm outline stores edited outline and sets status `outline_confirmed`.

- [ ] **Step 5: Add API tests**

Cover:

- GET creates card only for `ad_hoc_required`.
- GET rejects normal baseline chapter.
- PATCH rejects unknown answer key.
- Confirm outline changes status to `outline_confirmed`.
- `chapter_id` belonging to another project returns 404 or 403.

- [ ] **Step 6: Run API tests**

```bash
PYTHONPATH=.:backend .venv/bin/pytest -q backend/tests/integration/test_bid_generation_api.py
```

Expected: task-card API tests pass.

## Task 5: Block Unsafe Generation And Use Confirmed Outline

**Files:**

- Modify: `backend/tender_backend/services/bid_chapter_generation.py`
- Test: `backend/tests/unit/test_bid_chapter_generation.py`

- [ ] **Step 1: Add blocked generation tests**

Cases:

- `blocked_insufficient_evidence` raises `ValueError`.
- Missing required answers raises `ValueError`.
- `outline_ready` raises `ValueError` because outline is not confirmed.
- No draft generated from title alone.

- [ ] **Step 2: Add task-card-driven generation test**

Given card status `outline_confirmed`, assert `content_md` includes:

- `## 编制依据`
- `## 临时用电方案`
- `## 招标要求响应表`

Assert saved draft has:

```python
row["coverage_report_json"]["coverage_passed"] is True
```

- [ ] **Step 3: Implement generation branch**

In `generate_bid_chapter_draft`, before normal strategy selection:

- Read `chapter.metadata_json.ad_hoc_task_card`.
- If present, validate status.
- Use `build_task_card_draft_markdown`.
- Insert/update `chapter_draft.coverage_report_json`.
- Set card status `draft_ready` only after draft save and coverage pass.

- [ ] **Step 4: Run tests**

```bash
PYTHONPATH=.:backend .venv/bin/pytest -q backend/tests/unit/test_bid_chapter_generation.py
```

Expected: blocked and confirmed task-card paths pass.

## Task 6: Mark Missing Template Add-Chapter Suggestions As Ad Hoc

**Files:**

- Modify: `backend/tender_backend/services/template_directory_reconciliation_service.py`
- Test: `backend/tests/unit/test_template_directory_reconciliation_service.py`

- [ ] **Step 1: Add reconciliation test**

When a directory requirement has no exact, source, or title match, `add_chapter` suggestion payload includes:

```json
{
  "ad_hoc_required": true,
  "suggested_initial_status": "task_card_pending",
  "template_match_status": "missing"
}
```

- [ ] **Step 2: Implement payload flags**

Only add flags to missing-template `add_chapter` suggestions. Do not add them to move/reorder suggestions where a source template item exists.

- [ ] **Step 3: Run tests**

```bash
PYTHONPATH=.:backend .venv/bin/pytest -q backend/tests/unit/test_template_directory_reconciliation_service.py
```

Expected: tests pass.

## Task 7: Frontend Task Card Model And API Client

**Files:**

- Create: `frontend/src/modules/authoring/adHocChapterTaskCard.ts`
- Create: `frontend/src/modules/authoring/adHocChapterTaskCard.test.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add API types and functions**

Add:

- `AdHocTaskCard`
- `fetchAdHocTaskCard(projectId, chapterId)`
- `updateAdHocTaskCard(projectId, chapterId, payload)`
- `generateAdHocTaskCardOutline(projectId, chapterId)`
- `confirmAdHocTaskCardOutline(projectId, chapterId, outline)`

- [ ] **Step 2: Add helper tests**

Test:

- `taskCardStatusLabel("needs_input")` returns `待补充信息`.
- `missingRequiredInputs(card)` returns only required unanswered inputs.
- `canGenerateOutline(card)` is false until required answers exist and status allows it.
- `canGenerateDraft(card)` is true only when status is `outline_confirmed`.
- `isExportBlockingAdHocStatus("draft_ready")` is false and all other statuses above are true.

- [ ] **Step 3: Implement pure helpers**

Keep helpers independent of React.

- [ ] **Step 4: Run frontend helper tests**

```bash
cd frontend && npm test -- adHocChapterTaskCard.test.ts
```

Expected: helper tests pass.

## Task 8: Frontend Task Card UI

**Files:**

- Create: `frontend/src/modules/authoring/AdHocChapterTaskCard.tsx`
- Modify: `frontend/src/modules/authoring/EditorContent.tsx`
- Modify: `frontend/src/modules/authoring/chapterDelivery.ts`
- Test: `frontend/src/modules/authoring/EditorContent.test.tsx`

- [ ] **Step 1: Add delivery kind**

`chapterDeliveryKind` returns `ad_hoc_task_card` using Decision 9.

- [ ] **Step 2: Build task card component**

The component shows:

- Chapter title.
- Source anchors.
- Must respond points.
- Required business questions.
- Outline preview/edit area.
- Buttons: `保存信息`, `生成章节大纲`, `确认大纲`, `生成正文`.

Do not show raw prompt, model selector, JSON, or block metadata.

- [ ] **Step 3: Integrate into editor**

When selected chapter is ad hoc:

- Hide normal raw draft editor until draft exists.
- Show task card first.
- If only `ad_hoc_required` exists, show loading text while calling GET.
- After draft generation, show existing draft preview/edit workflow below the card.

- [ ] **Step 4: Add UI tests**

Assert:

- Ad hoc chapter shows `还缺` when required answers are missing.
- `生成正文` is disabled until status is `outline_confirmed`.
- Prompt-related text is not rendered.
- Chapter with only `ad_hoc_required` enters task-card UI.

- [ ] **Step 5: Run UI tests**

```bash
cd frontend && npm test -- EditorContent.test.tsx adHocChapterTaskCard.test.ts
```

Expected: tests pass.

## Task 9: Export Gate For Pending Task Cards

**Files:**

- Locate first: `frontend/src/modules/export/ExportGateContent.tsx`
- Modify: active backend route/service used by that component
- Test: `backend/tests/unit/test_export_gates.py`
- Test: `frontend/src/modules/export/ExportGateContent.test.tsx`

- [ ] **Step 0: Locate active export gate path**

Inspect:

```text
frontend/src/modules/export/ExportGateContent.tsx
frontend/src/lib/api.ts
```

Then identify the backend route and service actually used. Add the ad hoc blocking check only at that backend gate aggregation point.

- [ ] **Step 1: Add backend gate test**

If any enabled `bid_chapter.metadata_json.ad_hoc_task_card.status` is blocking, gate returns issue:

```text
新增章节任务卡未完成
```

with hint:

```text
请先补充信息、确认大纲并生成正文。
```

Only `draft_ready` plus existing draft plus `coverage_report_json.coverage_passed=true` is non-blocking.

- [ ] **Step 2: Implement gate check**

Include chapter code/title in issue details. Do not expose internal status names in user-facing message.

- [ ] **Step 3: Add frontend test**

Export gate displays the blocking issue and does not display `task_card_pending`, `needs_input`, `outline_ready`, `outline_confirmed`, or `blocked_insufficient_evidence`.

- [ ] **Step 4: Run gate tests**

```bash
PYTHONPATH=.:backend .venv/bin/pytest -q backend/tests/unit/test_export_gates.py
cd frontend && npm test -- ExportGateContent.test.tsx
```

Expected: export is blocked until ad hoc task cards are complete.

## Task 10: Focused Verification And Manual Smoke

**Files:** No new files.

- [ ] **Step 1: Run backend focused suite**

```bash
PYTHONPATH=.:backend .venv/bin/pytest -q \
  backend/tests/unit/test_ad_hoc_chapter_task_card.py \
  backend/tests/unit/test_bid_chapter_generation.py \
  backend/tests/unit/test_template_directory_reconciliation_service.py \
  backend/tests/integration/test_bid_generation_api.py \
  backend/tests/unit/test_export_gates.py
```

Expected: all selected tests pass.

- [ ] **Step 2: Run frontend focused suite**

```bash
cd frontend && npm test -- adHocChapterTaskCard.test.ts EditorContent.test.tsx ExportGateContent.test.tsx
```

Expected: all selected tests pass.

- [ ] **Step 3: Manual smoke scenario**

Use a local project:

1. Add or simulate requirement `施工现场总平面布置及临电临水方案` with source locator.
2. Confirm reconciliation marks a missing-template `add_chapter` suggestion as `ad_hoc_required=true`.
3. Open authoring editor and confirm task card UI appears.
4. Answer required questions.
5. Generate outline.
6. Confirm outline.
7. Generate draft.
8. Confirm `chapter_draft.coverage_report_json.coverage_passed=true`.
9. Confirm export gate no longer blocks this chapter.

Expected: the bid engineer never writes a prompt.

## Rollout

- [ ] Enable backend service and API behind existing auth first.
- [ ] Enable frontend read-only task card display.
- [ ] Enable answer saving and outline generation.
- [ ] Enable draft generation only after blocked-generation tests pass.
- [ ] Enable export gate after at least one manual smoke scenario passes.

## Self-Review

- Spec coverage: strict ad hoc trigger, single status, coverage storage, no safe limited generation, type-specific generation, classification priority, strict PATCH, metadata preservation, frontend entry, and export gate location are all covered by tasks.
- Placeholder scan: this plan contains concrete file paths, status names, API routes, test cases, and verification commands; no `TBD` or unbounded implementation placeholders remain.
- Type consistency: `ad_hoc_task_card`, `ad_hoc_required`, `template_match_status`, `technical_special_plan`, `material_attachment`, `table_checklist`, `coverage_report_json`, and `draft_ready` are used consistently.
