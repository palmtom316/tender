# Ad Hoc Chapter Task Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make tender able to generate a new tender-required chapter that has no similar baseline template by turning it into a guided chapter task card, then generating an outline and draft from confirmed business inputs.

**Architecture:** Keep this as a narrow MVP inside the existing bid chapter and authoring workflow. Store the ad hoc chapter task card in `bid_chapter.metadata_json.ad_hoc_task_card`, expose a small API to classify/update/confirm it, and extend chapter generation to require a confirmed task card before generating a template-less chapter. The bid engineer answers business questions and confirms an outline; they never write prompts.

**Tech Stack:** FastAPI, psycopg, PostgreSQL JSONB, React 18, TypeScript, TanStack Query, pytest, Vitest, existing `bid_chapter`, `chapter_draft`, `project_requirement`, `bid_chapter_requirement`, `EditorContent`, and `chapterDelivery` modules.

---

## Product Scope

This plan handles only one hard problem: an招标文件明确要求新增一个独立章节，但配网工程技术/商务基准模板中没有相似章节。

The MVP supports three ad hoc chapter types:

- `technical_special_plan`: 技术专项方案，如施工现场总平面布置、临电临水、停电组织、应急处置、绿色施工专项。
- `material_attachment`: 资料附件章节，如新增证明材料、证书、承诺函附件、专项说明附件。
- `table_checklist`: 表格清单章节，如人员驻场表、设备投入表、风险清单、响应表。

This plan does not implement model profiles, a generic prompt platform, or global template evolution.

## Product Rules

- The system never generates a full new chapter from title alone.
- New template-less chapters start in status `task_card_pending`.
- The task card must show source anchors, required response points, missing inputs, and generation type.
- The bid engineer answers 2 to 5 business questions, not prompts.
- Technical special plan chapters generate an outline first; draft generation is blocked until the outline is confirmed.
- Material attachment chapters create material slots and do not generate long AI prose.
- Table checklist chapters create a table structure first; prose generation is optional and short.
- Every generated draft includes a coverage report showing which source requirements were covered.
- If evidence is insufficient, the UI says what is missing and offers a safe limited generation mode.

## Existing Context

Important existing files:

- `backend/tender_backend/services/bid_chapter_generation.py`
  - Generates deterministic chapter drafts from `bid_chapter`, mapped requirements, and optional project template blocks.
- `backend/tender_backend/api/bid_outline.py`
  - Exposes `POST /projects/{project_id}/bid-chapters/{chapter_id}/generate`.
- `backend/tender_backend/api/bid_generation.py`
  - Exposes technical chapter context and generation endpoints.
- `frontend/src/modules/authoring/EditorContent.tsx`
  - Main authoring UI for chapter editing, material composition, technical generation, and charts.
- `frontend/src/modules/authoring/chapterDelivery.ts`
  - Existing frontend helpers for chapter delivery kind, material slots, and chart task cards.
- `frontend/src/lib/api.ts`
  - Existing API client for bid outline, generation, drafts, charts, and template instance calls.

## Data Model

No new table is required for the MVP. Store the task card in `bid_chapter.metadata_json.ad_hoc_task_card`.

Shape:

```json
{
  "status": "task_card_pending",
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
      "key": "site_plan",
      "label": "是否有现场平面图",
      "input_type": "choice",
      "options": ["uploaded", "not_available_text_only"],
      "required": true,
      "answer": null
    },
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
  "outline_confirmed": false,
  "coverage_report": {
    "covered_requirement_ids": [],
    "missing_requirement_ids": []
  }
}
```

Valid statuses:

- `task_card_pending`
- `needs_input`
- `outline_ready`
- `outline_confirmed`
- `draft_ready`
- `blocked_insufficient_evidence`

## User Flow

- [ ] System finds a tender-required chapter that is not in the baseline template.
- [ ] System creates a normal `bid_chapter` row with metadata `ad_hoc_task_card.status=task_card_pending`.
- [ ] Authoring editor shows a task card instead of a blank editor.
- [ ] User answers required business questions.
- [ ] User clicks `生成章节大纲`.
- [ ] System generates a conservative outline from source anchors, must-respond points, and user answers.
- [ ] User confirms or edits the outline.
- [ ] User clicks `生成正文`.
- [ ] System generates the draft and coverage report.
- [ ] Export is blocked if the task card remains pending, missing required inputs, or has unconfirmed outline.

## File Structure

Backend create:

- `backend/tender_backend/services/ad_hoc_chapter_task_card.py`
  - Builds, validates, updates, outlines, and checks coverage for ad hoc chapter task cards.

- `backend/tests/unit/test_ad_hoc_chapter_task_card.py`
  - Unit tests for classification, required questions, outline generation, and coverage checks.

Backend modify:

- `backend/tender_backend/services/bid_chapter_generation.py`
  - Blocks generation for template-less ad hoc chapters until task card prerequisites are met.
  - Uses confirmed task card outline as the main structure.

- `backend/tender_backend/api/bid_outline.py`
  - Adds small endpoints for reading/updating task cards and generating/confirming outlines.

- `backend/tender_backend/services/template_directory_reconciliation_service.py`
  - Marks add-chapter suggestions without a source template match as `ad_hoc_required=true`.

- `backend/tests/unit/test_bid_chapter_generation.py`
  - Adds tests for blocked generation and task-card-driven generation.

- `backend/tests/integration/test_bid_generation_api.py`
  - Adds API tests for task card update, outline confirmation, and draft generation.

Frontend create:

- `frontend/src/modules/authoring/AdHocChapterTaskCard.tsx`
  - Renders source anchors, required response points, business questions, outline, and actions.

- `frontend/src/modules/authoring/adHocChapterTaskCard.ts`
  - Pure helpers for status labels, missing-input validation, and outline edit state.

- `frontend/src/modules/authoring/adHocChapterTaskCard.test.ts`
  - Tests helper behavior.

Frontend modify:

- `frontend/src/lib/api.ts`
  - Adds task card API types and fetch/update/generate-outline/confirm-outline functions.

- `frontend/src/modules/authoring/EditorContent.tsx`
  - Displays `AdHocChapterTaskCard` when selected chapter has `metadata_json.ad_hoc_task_card`.

- `frontend/src/modules/authoring/chapterDelivery.ts`
  - Adds delivery kind `ad_hoc_task_card` so the UI can route cleanly.

- `frontend/src/modules/authoring/EditorContent.test.tsx`
  - Verifies task card UI replaces prompt/editor controls for ad hoc chapters.

## Task 1: Define Task Card Service

**Files:**

- Create: `backend/tender_backend/services/ad_hoc_chapter_task_card.py`
- Create: `backend/tests/unit/test_ad_hoc_chapter_task_card.py`

- [ ] **Step 1: Write tests for chapter type classification**

Test cases:

```python
def test_classifies_site_layout_as_technical_special_plan() -> None:
    card = build_initial_task_card(
        chapter_title="施工现场总平面布置及临电临水方案",
        source_requirements=[{"id": "r1", "title": "现场总平面布置", "requirement_text": "应提供施工现场总平面布置及临电临水方案"}],
    )
    assert card["chapter_type"] == "technical_special_plan"
    assert card["status"] in {"task_card_pending", "needs_input"}


def test_classifies_certificate_appendix_as_material_attachment() -> None:
    card = build_initial_task_card(
        chapter_title="专项承诺函及相关证明材料",
        source_requirements=[{"id": "r1", "title": "证明材料", "requirement_text": "须提供专项承诺函及证明材料"}],
    )
    assert card["chapter_type"] == "material_attachment"
```

- [ ] **Step 2: Implement `build_initial_task_card`**

Rules:

- Titles containing `方案`, `措施`, `布置`, `临电`, `临水`, `应急`, `停电`, `绿色施工` classify as `technical_special_plan`.
- Titles containing `证明`, `证书`, `附件`, `承诺函`, `说明` classify as `material_attachment`.
- Titles containing `表`, `清单`, `矩阵`, `台账` classify as `table_checklist`.
- Default classification is `technical_special_plan`, but status is `blocked_insufficient_evidence` if there are no source requirements.

- [ ] **Step 3: Add required questions by type**

For `technical_special_plan`, include these generic questions:

- `site_type`: 项目现场类型.
- `has_site_drawing`: 是否有现场图或布置图.
- `special_constraint`: 是否有特殊施工限制.

For `material_attachment`, include:

- `material_source`: 资料来源.
- `attachment_required`: 是否必须上传附件.

For `table_checklist`, include:

- `table_basis`: 表格数据来源.
- `manual_review_required`: 是否需要人工逐项确认.

- [ ] **Step 4: Run unit tests**

Run:

```bash
cd backend && python -m pytest tests/unit/test_ad_hoc_chapter_task_card.py -v
```

Expected: tests pass.

## Task 2: Generate Safe Outline From Task Card

**Files:**

- Modify: `backend/tender_backend/services/ad_hoc_chapter_task_card.py`
- Test: `backend/tests/unit/test_ad_hoc_chapter_task_card.py`

- [ ] **Step 1: Add outline generation tests**

Test that `technical_special_plan` outline includes:

- 编制依据
- 工程条件与限制
- 专项方案
- 安全文明施工
- 检查与验收
- 招标要求响应表

Test that `material_attachment` outline includes:

- 材料说明
- 资料清单
- 有效性检查

Test that `table_checklist` outline includes:

- 表格说明
- 字段定义
- 数据来源
- 人工确认

- [ ] **Step 2: Implement `generate_task_card_outline`**

Signature:

```python
def generate_task_card_outline(card: dict[str, Any]) -> list[dict[str, Any]]:
```

Return rows:

```json
[
  {
    "heading": "编制依据",
    "purpose": "说明本章来自招标文件要求和项目资料",
    "must_cover": ["来源页码", "评分点", "强制要求"]
  }
]
```

- [ ] **Step 3: Implement validation**

`validate_task_card_ready_for_outline(card)` returns:

```python
{"ready": False, "missing_input_keys": ["site_type"]}
```

Generation is blocked until all `required=true` inputs have non-empty answers.

- [ ] **Step 4: Run unit tests**

Run:

```bash
cd backend && python -m pytest tests/unit/test_ad_hoc_chapter_task_card.py -v
```

Expected: tests pass.

## Task 3: Add Task Card API

**Files:**

- Modify: `backend/tender_backend/api/bid_outline.py`
- Test: `backend/tests/integration/test_bid_generation_api.py`

- [ ] **Step 1: Add request/response models**

Models:

```python
class AdHocTaskCardUpdateBody(BaseModel):
    answers: dict[str, Any] = {}
    chapter_type: str | None = None

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
- Loads `bid_chapter`.
- If metadata has no task card, builds one from mapped requirements and stores it.
- Returns the card.

- [ ] **Step 3: Add PATCH endpoint**

Route:

```text
PATCH /projects/{project_id}/bid-chapters/{chapter_id}/ad-hoc-task-card
```

Behavior:

- Updates answers and optional chapter type.
- Revalidates status.
- Stores back into `metadata_json.ad_hoc_task_card`.

- [ ] **Step 4: Add outline endpoint**

Route:

```text
POST /projects/{project_id}/bid-chapters/{chapter_id}/ad-hoc-task-card/outline
```

Behavior:

- Validates required answers.
- Generates outline.
- Stores `outline` and status `outline_ready`.

- [ ] **Step 5: Add confirm outline endpoint**

Route:

```text
POST /projects/{project_id}/bid-chapters/{chapter_id}/ad-hoc-task-card/confirm-outline
```

Body:

```json
{"outline": [{"heading": "编制依据", "purpose": "说明来源", "must_cover": ["招标要求"]}]}
```

Behavior:

- Stores edited outline.
- Sets `outline_confirmed=true`.
- Sets status `outline_confirmed`.

- [ ] **Step 6: Run API tests**

Run:

```bash
cd backend && python -m pytest tests/integration/test_bid_generation_api.py -v
```

Expected: task card endpoints pass.

## Task 4: Block Unsafe Generation And Use Confirmed Outline

**Files:**

- Modify: `backend/tender_backend/services/bid_chapter_generation.py`
- Test: `backend/tests/unit/test_bid_chapter_generation.py`

- [ ] **Step 1: Add blocked generation tests**

Cases:

- No source requirements and ad hoc card status `blocked_insufficient_evidence` raises `ValueError`.
- Missing required answers raises `ValueError`.
- Outline not confirmed raises `ValueError`.

- [ ] **Step 2: Add task-card-driven generation test**

Given a chapter with:

```json
{
  "ad_hoc_task_card": {
    "status": "outline_confirmed",
    "chapter_type": "technical_special_plan",
    "must_respond": ["临时用电方案"],
    "outline_confirmed": true,
    "outline": [
      {"heading": "编制依据", "purpose": "说明来源", "must_cover": ["招标文件P32"]},
      {"heading": "临时用电方案", "purpose": "响应临电要求", "must_cover": ["接入点", "安全措施"]}
    ]
  }
}
```

Assert generated `content_md` includes:

- `## 编制依据`
- `## 临时用电方案`
- `## 招标要求响应表`

- [ ] **Step 3: Implement generation branch**

In `generate_bid_chapter_draft`, before normal strategy selection:

- Read `chapter.metadata_json.ad_hoc_task_card`.
- If present, validate prerequisites.
- Build markdown from confirmed outline, mapped requirements, answers, and source anchors.
- Write `coverage_report` into `chapter_draft.page_estimate_json` or `chapter_draft.metadata_json` if available; if no metadata column exists, write the report into the end of `content_md` under `## 覆盖检查`.

- [ ] **Step 4: Run tests**

Run:

```bash
cd backend && python -m pytest tests/unit/test_bid_chapter_generation.py -v
```

Expected: blocked and confirmed task card paths pass.

## Task 5: Mark Add-Chapter Suggestions As Ad Hoc When No Template Match Exists

**Files:**

- Modify: `backend/tender_backend/services/template_directory_reconciliation_service.py`
- Test: `backend/tests/unit/test_template_directory_reconciliation_service.py`

- [ ] **Step 1: Add test**

When a directory requirement has no exact, source, or title match, the `add_chapter` suggestion payload includes:

```json
{
  "ad_hoc_required": true,
  "suggested_initial_status": "task_card_pending"
}
```

- [ ] **Step 2: Implement payload flags**

Only add the flags to missing-template `add_chapter` suggestions. Do not add them to move/reorder suggestions where a source template item exists.

- [ ] **Step 3: Run tests**

Run:

```bash
cd backend && python -m pytest tests/unit/test_template_directory_reconciliation_service.py -v
```

Expected: tests pass.

## Task 6: Frontend Task Card Model

**Files:**

- Create: `frontend/src/modules/authoring/adHocChapterTaskCard.ts`
- Create: `frontend/src/modules/authoring/adHocChapterTaskCard.test.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add API types and client functions**

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
- `canGenerateOutline(card)` is false until required answers exist.
- `canGenerateDraft(card)` is true only when outline is confirmed.

- [ ] **Step 3: Implement helpers**

Keep helpers pure and independent of React.

- [ ] **Step 4: Run frontend helper tests**

Run:

```bash
cd frontend && npm test -- adHocChapterTaskCard.test.ts
```

Expected: helper tests pass.

## Task 7: Frontend Task Card UI

**Files:**

- Create: `frontend/src/modules/authoring/AdHocChapterTaskCard.tsx`
- Modify: `frontend/src/modules/authoring/EditorContent.tsx`
- Modify: `frontend/src/modules/authoring/chapterDelivery.ts`
- Test: `frontend/src/modules/authoring/EditorContent.test.tsx`

- [ ] **Step 1: Add delivery kind**

`chapterDeliveryKind` returns `ad_hoc_task_card` when:

```ts
Boolean(chapter?.metadata_json?.ad_hoc_task_card)
```

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

- Hide the normal raw draft editor until draft exists.
- Show task card first.
- After draft generation, show existing draft preview/edit workflow below the card.

- [ ] **Step 4: Add UI test**

Assert:

- Ad hoc chapter shows `还缺` when required answers are missing.
- `生成正文` is disabled until outline is confirmed.
- Prompt-related text is not rendered.

- [ ] **Step 5: Run UI tests**

Run:

```bash
cd frontend && npm test -- EditorContent.test.tsx adHocChapterTaskCard.test.ts
```

Expected: tests pass.

## Task 8: Export Gate For Pending Task Cards

**Files:**

- Modify: `backend/tender_backend/services/delivery_package.py` or the existing export gate service used by `frontend/src/modules/export/ExportGateContent.tsx`.
- Test: `backend/tests/unit/test_export_gates.py`
- Test: `frontend/src/modules/export/ExportGateContent.test.tsx`

- [ ] **Step 1: Add backend gate test**

If any enabled `bid_chapter.metadata_json.ad_hoc_task_card.status` is one of:

- `task_card_pending`
- `needs_input`
- `outline_ready`
- `blocked_insufficient_evidence`

Then export gate returns a blocking issue:

```text
新增章节任务卡未完成
```

- [ ] **Step 2: Implement gate check**

The gate should include chapter code/title and a user-facing action hint:

```text
请先补充信息、确认大纲并生成正文。
```

- [ ] **Step 3: Add frontend test**

Export gate displays the blocking issue without exposing internal status names.

- [ ] **Step 4: Run gate tests**

Run:

```bash
cd backend && python -m pytest tests/unit/test_export_gates.py -v
cd frontend && npm test -- ExportGateContent.test.tsx
```

Expected: export is blocked until ad hoc task cards are complete.

## Task 9: Focused Verification

**Files:**

- No new files.

- [ ] **Step 1: Run backend focused suite**

Run:

```bash
cd backend && python -m pytest \
  tests/unit/test_ad_hoc_chapter_task_card.py \
  tests/unit/test_bid_chapter_generation.py \
  tests/unit/test_template_directory_reconciliation_service.py \
  tests/integration/test_bid_generation_api.py \
  -v
```

Expected: all selected tests pass.

- [ ] **Step 2: Run frontend focused suite**

Run:

```bash
cd frontend && npm test -- adHocChapterTaskCard.test.ts EditorContent.test.tsx ExportGateContent.test.tsx
```

Expected: all selected tests pass.

- [ ] **Step 3: Manual smoke scenario**

Use a local project:

1. Add or simulate a tender requirement for `施工现场总平面布置及临电临水方案`.
2. Confirm it creates an ad hoc chapter task card.
3. Answer required questions.
4. Generate outline.
5. Confirm outline.
6. Generate draft.
7. Confirm export gate no longer blocks this chapter.

Expected: the bid engineer never writes a prompt.

## Rollout

- [ ] Enable read-only task cards first.
- [ ] Enable answer saving and outline generation.
- [ ] Enable draft generation only after blocked-generation tests pass.
- [ ] Enable export gate after at least one manual smoke scenario passes.

## Self-Review

- Spec coverage: template-less new chapter, task card, guided questions, safe outline-first generation, coverage report, export gate, and no-prompt UX are covered.
- Placeholder scan: the plan contains concrete file paths, statuses, API routes, test cases, and verification commands.
- Type consistency: `ad_hoc_task_card`, `technical_special_plan`, `material_attachment`, `table_checklist`, `outline_confirmed`, and task card API names are used consistently.
