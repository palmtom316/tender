# Project Template Instance Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the project-scoped template adjustment workflow: create project, auto-select a base template, clone it into a project template instance, reconcile tender-required directories, generate bid documents from that instance, and feed review failures back into the template instance without corrupting global templates.

**Architecture:** Keep three layers separate: global template package, project template instance, and generated bid content. The template adjustment workbench edits structured chapter blocks in the project template instance; the bid authoring workspace consumes the confirmed instance to generate and review project-specific content. Successful project-specific improvements can later be promoted back to the global template package through an explicit versioned merge.

**Tech Stack:** FastAPI, psycopg, Alembic, PostgreSQL JSONB, React 18, TypeScript, TanStack Query, Vitest, pytest, existing `template_packages`, `projects`, `bid_outline`, `bid_generation`, and `authoring` modules.

---

## Product Decision Record

- 投标人员自己维护模板。
- 模板维护界面必须表单化，不做自由源码式模板编辑器。
- 模板调整区只调整“项目模板实例”，默认不修改全局基础模板。
- 招标文件解析出的目录要求与原模板目录不一致时，在模板调整区做差异融合和人工确认。
- 标书编写区按确认后的项目模板实例生成投标文件。
- 标书生成质量或审查不过时，先判断问题来源：
  - 模板结构、提示词、占位符、素材位、分页、页眉页脚问题：回到模板调整区修项目模板实例。
  - 项目资料缺失、AI正文事实错误、素材错配问题：在标书编写区修生成内容或项目资料。
- 项目结束后，项目模板实例中的有效改动可以“提议合并”回全局模板，形成新版模板。

## Existing Context

Existing code already contains these foundations:

- Project category and selected template:
  - `backend/tender_backend/api/projects.py`
  - `backend/tender_backend/db/repositories/project_repository.py`
  - `backend/tender_backend/services/template_selection_service.py`
  - `frontend/src/modules/projects/ProjectsModule.tsx`
- Global template packages and items:
  - `backend/tender_backend/api/template_packages.py`
  - `backend/tender_backend/db/repositories/bid_template_package_repo.py`
  - `backend/tender_backend/services/template_service/package_importer.py`
  - `backend/tender_backend/services/template_service/business_template_preview.py`
  - `backend/tender_backend/services/template_service/docx_renderer.py`
  - `frontend/src/lib/api.ts`
- Tender parsing, requirements, outline, and authoring:
  - `backend/tender_backend/api/bid_outline.py`
  - `backend/tender_backend/api/bid_generation.py`
  - `backend/tender_backend/services/outline_reconciliation_service.py`
  - `backend/tender_backend/services/bid_outline_planner.py`
  - `backend/tender_backend/services/bid_chapter_generation.py`
  - `frontend/src/modules/authoring/AuthoringModule.tsx`
  - `frontend/src/modules/authoring/ParseContent.tsx`
  - `frontend/src/modules/authoring/RequirementsContent.tsx`
  - `frontend/src/modules/authoring/EditorContent.tsx`
  - `frontend/src/modules/authoring/chapterDelivery.ts`
  - `frontend/src/modules/authoring/businessMaterialWorkbench.ts`

## Target Flow

- [ ] Project is created with `category_code`.
- [ ] System recommends and confirms a global template package for the project category.
- [ ] System creates a project template instance from the selected global package.
- [ ] Tender files are parsed into requirements, directory requirements, format rules, material requirements, and review constraints.
- [ ] Template adjustment workbench compares parsed tender directory requirements against the project template instance.
- [ ] Tender engineer adjusts chapter order, chapter inclusion, AI prompts, fixed text, variables, material placeholders, page breaks, header/footer references, and conditional rules through forms.
- [ ] User confirms the project template instance.
- [ ] Bid authoring workspace generates bid content from the confirmed project template instance.
- [ ] Review/compliance issues are classified by source and routed either to template adjustment or bid authoring.
- [ ] Project template instance can be promoted back to global template as a versioned proposal after project completion.

## Frontend Workflow Redesign

The current Authoring module has four tabs:

- `upload`: 文件上传
- `parse`: 解析结果
- `requirements`: 需求确认
- `editor`: 章节编辑

The new workflow must make the project template instance explicit. The Authoring module should become a guided production flow:

- `upload`: 上传招标文件
- `parse`: 解析招标要求
- `requirements`: 确认关键要求
- `template`: 调整项目模板
- `editor`: 生成/编写标书

### Navigation Rules

- Project cards should continue opening `authoring/upload` for new projects.
- After parsing starts or finishes, the upload page should direct the user to `parse`.
- After key requirements are confirmed, the requirements page should direct the user to `template`.
- `editor` should show a blocking banner when the project template instance is missing, unconfirmed, or has unresolved critical reconciliation issues.
- Review issue links should navigate to:
  - `authoring/template` when the issue source is template structure, prompt, placeholder, page break, header/footer, or condition logic.
  - `authoring/editor` when the issue source is generated content, project material, AI factual quality, or material binding.

### Authoring Top-Level Progress UI

Add a compact workflow status strip to Authoring pages. It should show:

- 项目建立
- 文件解析
- 要求确认
- 模板调整
- 标书编写
- 审查/导出

Each step should have one of these states:

- `done`
- `active`
- `blocked`
- `pending`

The status strip is not a marketing timeline. It should be dense, operational, and clickable when the destination is available.

### Template Adjustment Page Layout

The `template` tab is a three-column form-based workbench:

- Left: project template chapter tree.
  - Shows volume/chapter hierarchy.
  - Shows tender-directory diff badges.
  - Shows unresolved issue count per chapter.
  - Supports selecting a chapter.

- Center: selected chapter template form.
  - Fixed text section.
  - AI prompt section, collapsed by default.
  - Variables section.
  - Material/asset placeholders section.
  - Page break section.
  - Header/footer section.
  - Conditional display section.
  - Chapter actions: save, disable, duplicate, mark resolved.

- Right: read-only template preview.
  - Uses sample project data.
  - Shows fixed text and placeholders.
  - Makes page break, header, footer, and unresolved placeholder markers visible.
  - Shows preview limitations explicitly through status labels, not long instructional copy.

### Bid Authoring Page Adjustment

The current `EditorContent` should stop behaving as if it owns template structure. It should consume the confirmed project template instance:

- Show template instance name, version, confirmation time, and unresolved issue count.
- Generate chapters from the confirmed template instance.
- For business/qualification chapters, keep material binding and composition in the authoring context.
- For technical chapters, keep AI writing and chart tasks in the authoring context.
- Keep advanced prompt details discoverable, but avoid making prompt editing the main action in bid authoring.

### Project List Adjustment

Project cards should expose workflow state, not only project metadata:

- Template status: 未生成 / 待调整 / 已确认 / 有阻断问题
- Next action:
  - 上传招标文件
  - 确认要求
  - 调整模板
  - 编写标书
  - 审查导出

Clicking the project card should navigate to the next incomplete workflow step when possible.

## File Structure

### Backend Create

- `backend/tender_backend/db/alembic/versions/0051_project_template_instances.py`
  - Tables for project template instances, chapters, blocks, assets/placeholders, revisions, and promotion proposals.

- `backend/tender_backend/db/repositories/project_template_instance_repo.py`
  - CRUD and revision-safe persistence for project template instances.

- `backend/tender_backend/services/project_template_instance_service.py`
  - Clone global template package into project template instance.
  - Maintain chapter/block structure.
  - Confirm instance and record workflow events.

- `backend/tender_backend/services/template_directory_reconciliation_service.py`
  - Compare tender-required directory against current project template instance.
  - Produce add/remove/rename/reorder/split/merge suggestions.

- `backend/tender_backend/api/project_template_instances.py`
  - API endpoints for reading, editing, confirming, previewing, reconciling, and proposing global template promotion.

- `backend/tests/unit/test_project_template_instance_service.py`
- `backend/tests/unit/test_template_directory_reconciliation_service.py`
- `backend/tests/integration/test_project_template_instances_api.py`

### Backend Modify

- `backend/tender_backend/main.py`
  - Register `project_template_instances` router.

- `backend/tender_backend/api/projects.py`
  - After template selection, ensure project template instance exists.

- `backend/tender_backend/api/template_packages.py`
  - Keep global package APIs read-oriented for project workflows; do not let project workbench mutate global package by default.

- `backend/tender_backend/api/bid_generation.py`
  - Generate bid content from confirmed project template instance instead of raw global template package when available.

- `backend/tender_backend/services/bid_chapter_generation.py`
  - Consume chapter block model: fixed text, AI prompt block, variables, material placeholders, page controls, and conditional rules.

- `backend/tender_backend/services/template_service/docx_renderer.py`
  - Render project template instance blocks into DOCX-compatible structure and preview output.

- `backend/tender_backend/workflows/export_bid.py`
  - Use confirmed project template instance for final package gates.

### Frontend Create

- `frontend/src/modules/authoring/AuthoringWorkflowStatus.tsx`
  - Shared operational status strip for upload, parse, requirements, template adjustment, and editor pages.

- `frontend/src/modules/authoring/authoringWorkflow.ts`
  - Pure workflow-state helpers for current step, next action, blocked reasons, and tab routing.

- `frontend/src/modules/templates/ProjectTemplateWorkbench.tsx`
  - Three-column workbench: chapter tree, form-based chapter template editor, read-only preview.

- `frontend/src/modules/templates/ChapterTree.tsx`
  - Template directory tree with tender-diff badges and chapter status.

- `frontend/src/modules/templates/ChapterTemplateForm.tsx`
  - Form sections for fixed text, AI prompt, variables, assets, page breaks, header/footer, conditions, and review routing.

- `frontend/src/modules/templates/TemplatePreviewPane.tsx`
  - Project template preview with sample project data and explicit page/header/footer markers.

- `frontend/src/modules/templates/templateInstanceModel.ts`
  - Frontend types, pure mapping helpers, and validation helpers.

- `frontend/src/modules/authoring/authoringWorkflow.test.ts`
- `frontend/src/modules/templates/ProjectTemplateWorkbench.test.tsx`
- `frontend/src/modules/templates/templateInstanceModel.test.ts`

### Frontend Modify

- `frontend/src/lib/navigation.ts`
  - Add the `authoring/template` tab between `requirements` and `editor`.

- `frontend/src/lib/api.ts`
  - Add project template instance types and API functions.

- `frontend/src/modules/authoring/AuthoringModule.tsx`
  - Add route/tab entry for template adjustment before bid authoring.
  - Render `ProjectTemplateWorkbench` when `tab === "template"`.

- `frontend/src/modules/authoring/EditorContent.tsx`
  - Read confirmed project template instance status.
  - Block or warn generation if template instance has unresolved critical directory/template issues.

- `frontend/src/modules/projects/ProjectsModule.tsx`
  - Surface project template instance status after project creation/template confirmation.
  - Navigate users to the next incomplete workflow step instead of always opening upload.

- `frontend/src/components/layout/WorkspaceTabs.tsx`
  - No structural rewrite expected, but tests must verify the new Authoring tab appears in the correct order.

## Data Model

### `project_template_instance`

- `id UUID PRIMARY KEY`
- `project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE`
- `base_template_package_id UUID NULL REFERENCES bid_template_package(id) ON DELETE SET NULL`
- `category_code VARCHAR(64) NOT NULL`
- `display_name TEXT NOT NULL`
- `status TEXT NOT NULL DEFAULT 'draft'`
- `version INT NOT NULL DEFAULT 1`
- `confirmed_at TIMESTAMPTZ NULL`
- `confirmed_by TEXT NULL`
- `metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Status values:

- `draft`
- `needs_reconciliation`
- `ready_for_authoring`
- `locked_for_generation`
- `superseded`

### `project_template_chapter`

- `id UUID PRIMARY KEY`
- `template_instance_id UUID NOT NULL REFERENCES project_template_instance(id) ON DELETE CASCADE`
- `project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE`
- `parent_id UUID NULL REFERENCES project_template_chapter(id) ON DELETE CASCADE`
- `source_template_item_id UUID NULL REFERENCES bid_template_item(id) ON DELETE SET NULL`
- `chapter_code TEXT NOT NULL`
- `chapter_title TEXT NOT NULL`
- `volume_type TEXT NOT NULL`
- `sort_order INT NOT NULL DEFAULT 0`
- `enabled BOOLEAN NOT NULL DEFAULT TRUE`
- `chapter_status TEXT NOT NULL DEFAULT 'draft'`
- `tender_requirement_status TEXT NOT NULL DEFAULT 'not_checked'`
- `metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### `project_template_block`

- `id UUID PRIMARY KEY`
- `template_chapter_id UUID NOT NULL REFERENCES project_template_chapter(id) ON DELETE CASCADE`
- `project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE`
- `block_type TEXT NOT NULL`
- `sort_order INT NOT NULL DEFAULT 0`
- `label TEXT NOT NULL`
- `content_text TEXT NOT NULL DEFAULT ''`
- `prompt_text TEXT NOT NULL DEFAULT ''`
- `placeholder_key TEXT NULL`
- `asset_type TEXT NULL`
- `required BOOLEAN NOT NULL DEFAULT FALSE`
- `render_options_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `condition_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Block type values:

- `fixed_text`
- `ai_prompt`
- `variable`
- `asset_placeholder`
- `page_break`
- `header_footer`
- `condition`

### `project_template_revision`

- `id UUID PRIMARY KEY`
- `template_instance_id UUID NOT NULL REFERENCES project_template_instance(id) ON DELETE CASCADE`
- `project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE`
- `revision_no INT NOT NULL`
- `change_type TEXT NOT NULL`
- `change_summary TEXT NOT NULL`
- `snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_by TEXT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### `template_promotion_proposal`

- `id UUID PRIMARY KEY`
- `template_instance_id UUID NOT NULL REFERENCES project_template_instance(id) ON DELETE CASCADE`
- `base_template_package_id UUID NULL REFERENCES bid_template_package(id) ON DELETE SET NULL`
- `project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE`
- `proposal_status TEXT NOT NULL DEFAULT 'draft'`
- `diff_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_by TEXT NULL`
- `reviewed_by TEXT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `reviewed_at TIMESTAMPTZ NULL`

## API Contract

- `GET /api/projects/{project_id}/template-instance`
  - Returns the current project template instance, chapters, blocks, reconciliation summary, and status.

- `POST /api/projects/{project_id}/template-instance`
  - Creates the instance from selected global template package if missing.

- `PATCH /api/project-template-instances/{instance_id}`
  - Updates instance display name or metadata.

- `PATCH /api/project-template-chapters/{chapter_id}`
  - Updates chapter title, code, order, enabled state, and status.

- `POST /api/project-template-chapters/{chapter_id}/blocks`
  - Adds a structured block to a chapter.

- `PATCH /api/project-template-blocks/{block_id}`
  - Updates a block's form fields.

- `DELETE /api/project-template-blocks/{block_id}`
  - Deletes a user-added block or disables a cloned block.

- `POST /api/projects/{project_id}/template-instance/reconcile-directory`
  - Compares tender parsed directory requirements with the current project template instance.

- `POST /api/projects/{project_id}/template-instance/apply-reconciliation`
  - Applies selected reconciliation suggestions.

- `POST /api/project-template-instances/{instance_id}/confirm`
  - Marks template instance ready for bid authoring if no critical unresolved issues remain.

- `GET /api/project-template-instances/{instance_id}/preview`
  - Returns render preview with sample project data and visible page/header/footer markers.

- `POST /api/project-template-instances/{instance_id}/promotion-proposals`
  - Creates a proposal to merge project template changes back to global template.

## Implementation Tasks

### Task 1: Persist Project Template Instances

**Files:**
- Create: `backend/tender_backend/db/alembic/versions/0051_project_template_instances.py`
- Create: `backend/tender_backend/db/repositories/project_template_instance_repo.py`
- Create: `backend/tests/unit/test_project_template_instance_service.py`

- [ ] Write repository tests for creating a project template instance with chapters and blocks cloned from a package.
- [ ] Run: `cd backend && ../.venv/bin/pytest tests/unit/test_project_template_instance_service.py -q`
- [ ] Expected initial result: FAIL because repository/service files do not exist.
- [ ] Add Alembic migration with the four tables listed in **Data Model**.
- [ ] Implement dataclasses for instance, chapter, block, revision, and promotion proposal.
- [ ] Implement repository methods:
  - `create_instance(conn, project_id, base_template_package_id, category_code, display_name)`
  - `get_current_for_project(conn, project_id)`
  - `list_chapters(conn, instance_id)`
  - `list_blocks(conn, chapter_id)`
  - `replace_chapter_order(conn, instance_id, ordered_chapter_ids)`
  - `update_chapter(conn, chapter_id, fields)`
  - `create_block(conn, chapter_id, fields)`
  - `update_block(conn, block_id, fields)`
  - `delete_block(conn, block_id)`
  - `record_revision(conn, instance_id, change_type, change_summary, snapshot_json, created_by)`
- [ ] Rerun repository tests and confirm PASS.
- [ ] Commit: `git add backend/tender_backend/db/alembic/versions/0051_project_template_instances.py backend/tender_backend/db/repositories/project_template_instance_repo.py backend/tests/unit/test_project_template_instance_service.py && git commit -m "Add project template instance persistence"`

### Task 2: Clone Global Template Package Into Project Instance

**Files:**
- Create: `backend/tender_backend/services/project_template_instance_service.py`
- Modify: `backend/tender_backend/api/projects.py`
- Modify: `backend/tender_backend/api/template_packages.py`
- Test: `backend/tests/unit/test_project_template_instance_service.py`

- [ ] Add tests for idempotent instance creation after project template confirmation.
- [ ] Add tests that project instance defaults do not mutate `bid_template_package` or `bid_template_item`.
- [ ] Run: `cd backend && ../.venv/bin/pytest tests/unit/test_project_template_instance_service.py -q`
- [ ] Expected initial result: FAIL because service does not yet clone package items.
- [ ] Implement `ProjectTemplateInstanceService.ensure_for_project(conn, project_id, actor=None)`.
- [ ] Clone each selected `bid_template_item` into `project_template_chapter`.
- [ ] Generate default blocks per chapter:
  - `fixed_text` for cloned static content reference.
  - `asset_placeholder` for known material slots.
  - `ai_prompt` only when source item or category indicates AI-written content.
  - `page_break` at chapter boundaries.
  - `header_footer` reference inherited from package metadata.
- [ ] Update project template selection confirmation path so it creates the project template instance after `selected_template_package_id` is set.
- [ ] Rerun tests and confirm PASS.
- [ ] Commit: `git add backend/tender_backend/services/project_template_instance_service.py backend/tender_backend/api/projects.py backend/tender_backend/api/template_packages.py backend/tests/unit/test_project_template_instance_service.py && git commit -m "Clone selected templates into project instances"`

### Task 3: Add Project Template Instance API

**Files:**
- Create: `backend/tender_backend/api/project_template_instances.py`
- Modify: `backend/tender_backend/main.py`
- Create: `backend/tests/integration/test_project_template_instances_api.py`

- [ ] Write integration tests covering:
  - `GET /api/projects/{project_id}/template-instance`
  - `POST /api/projects/{project_id}/template-instance`
  - `PATCH /api/project-template-chapters/{chapter_id}`
  - `POST /api/project-template-chapters/{chapter_id}/blocks`
  - `PATCH /api/project-template-blocks/{block_id}`
  - `POST /api/project-template-instances/{instance_id}/confirm`
- [ ] Run: `cd backend && ../.venv/bin/pytest tests/integration/test_project_template_instances_api.py -q`
- [ ] Expected initial result: FAIL with missing routes.
- [ ] Implement Pydantic models:
  - `ProjectTemplateInstanceOut`
  - `ProjectTemplateChapterOut`
  - `ProjectTemplateBlockOut`
  - `ProjectTemplateChapterUpdate`
  - `ProjectTemplateBlockCreate`
  - `ProjectTemplateBlockUpdate`
  - `ProjectTemplateConfirmOut`
- [ ] Enforce project access for all project-scoped operations.
- [ ] Reject confirmation when critical reconciliation issues remain.
- [ ] Register router in `backend/tender_backend/main.py`.
- [ ] Rerun integration tests and confirm PASS.
- [ ] Commit: `git add backend/tender_backend/api/project_template_instances.py backend/tender_backend/main.py backend/tests/integration/test_project_template_instances_api.py && git commit -m "Add project template instance API"`

### Task 4: Reconcile Tender Directory With Project Template

**Files:**
- Create: `backend/tender_backend/services/template_directory_reconciliation_service.py`
- Modify: `backend/tender_backend/api/project_template_instances.py`
- Create: `backend/tests/unit/test_template_directory_reconciliation_service.py`
- Modify: `backend/tests/integration/test_project_template_instances_api.py`

- [ ] Write unit tests for directory diff suggestions:
  - required chapter missing from template -> `add_chapter`
  - template chapter not required by tender -> `disable_chapter`
  - same meaning but different title -> `rename_chapter`
  - order mismatch -> `reorder_chapter`
  - tender chapter is more detailed -> `split_chapter`
  - template chapters can map to one tender chapter -> `merge_chapter`
- [ ] Run: `cd backend && ../.venv/bin/pytest tests/unit/test_template_directory_reconciliation_service.py -q`
- [ ] Expected initial result: FAIL because service does not exist.
- [ ] Implement `TemplateDirectoryReconciliationService.build_suggestions(project_requirements, template_chapters)`.
- [ ] Store reconciliation summary in `project_template_instance.metadata_json.reconciliation`.
- [ ] Implement apply endpoint that accepts selected suggestion IDs and records a template revision.
- [ ] Add integration tests for reconcile/apply endpoints.
- [ ] Rerun unit and integration tests.
- [ ] Commit: `git add backend/tender_backend/services/template_directory_reconciliation_service.py backend/tender_backend/api/project_template_instances.py backend/tests/unit/test_template_directory_reconciliation_service.py backend/tests/integration/test_project_template_instances_api.py && git commit -m "Reconcile tender directory with project templates"`

### Task 5: Add Frontend Workflow Navigation And Status

**Files:**
- Create: `frontend/src/modules/authoring/authoringWorkflow.ts`
- Create: `frontend/src/modules/authoring/authoringWorkflow.test.ts`
- Create: `frontend/src/modules/authoring/AuthoringWorkflowStatus.tsx`
- Modify: `frontend/src/lib/navigation.ts`
- Modify: `frontend/src/modules/authoring/AuthoringModule.tsx`
- Modify: `frontend/src/modules/projects/ProjectsModule.tsx`
- Modify: `frontend/src/modules/projects/ProjectsModule.test.tsx`

- [ ] Write helper tests for workflow routing:
  - new project with no document -> next tab is `upload`
  - parsed document with unconfirmed requirements -> next tab is `requirements`
  - confirmed requirements with draft template -> next tab is `template`
  - confirmed template -> next tab is `editor`
  - template blocker -> `editor` is blocked with a reason
- [ ] Run: `cd frontend && npx vitest run src/modules/authoring/authoringWorkflow.test.ts`
- [ ] Expected initial result: FAIL because helper file does not exist.
- [ ] Add `template` tab to `frontend/src/lib/navigation.ts` between `requirements` and `editor`:

```ts
{ id: "template", label: "模板调整" },
```

- [ ] Implement `authoringWorkflow.ts` helpers:
  - `authoringSteps(status)`
  - `nextAuthoringTab(status)`
  - `editorBlockReason(status)`
  - `projectNextAction(status)`
- [ ] Implement `AuthoringWorkflowStatus.tsx` as a dense clickable status strip.
- [ ] Add `AuthoringWorkflowStatus` to every Authoring page through `AuthoringModule.tsx`, not by duplicating it in each page.
- [ ] Update `ProjectsModule.tsx` so project cards route to the next incomplete workflow step when status data exists; fallback remains `authoring/upload`.
- [ ] Add tests that:
  - Workspace tabs include `模板调整`.
  - Project card can navigate to `authoring/template`.
  - Status strip marks `模板调整` active on the template tab.
- [ ] Run:

```bash
cd frontend && npx vitest run \
  src/modules/authoring/authoringWorkflow.test.ts \
  src/modules/projects/ProjectsModule.test.tsx
```

- [ ] Commit: `git add frontend/src/lib/navigation.ts frontend/src/modules/authoring/authoringWorkflow.ts frontend/src/modules/authoring/authoringWorkflow.test.ts frontend/src/modules/authoring/AuthoringWorkflowStatus.tsx frontend/src/modules/authoring/AuthoringModule.tsx frontend/src/modules/projects/ProjectsModule.tsx frontend/src/modules/projects/ProjectsModule.test.tsx && git commit -m "Add authoring template workflow navigation"`

### Task 6: Build Form-Based Template Adjustment Workbench

**Files:**
- Create: `frontend/src/modules/templates/templateInstanceModel.ts`
- Create: `frontend/src/modules/templates/templateInstanceModel.test.ts`
- Create: `frontend/src/modules/templates/ChapterTree.tsx`
- Create: `frontend/src/modules/templates/ChapterTemplateForm.tsx`
- Create: `frontend/src/modules/templates/TemplatePreviewPane.tsx`
- Create: `frontend/src/modules/templates/ProjectTemplateWorkbench.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/modules/authoring/AuthoringModule.tsx`
- Create: `frontend/src/modules/templates/ProjectTemplateWorkbench.test.tsx`

- [ ] Write pure helper tests for mapping API blocks to form sections and detecting unresolved critical template issues.
- [ ] Run: `cd frontend && npx vitest run src/modules/templates/templateInstanceModel.test.ts`
- [ ] Expected initial result: FAIL because helper file does not exist.
- [ ] Add API types/functions to `frontend/src/lib/api.ts` for all project template instance endpoints.
- [ ] Implement `templateInstanceModel.ts` helpers:
  - `groupBlocksByFormSection(blocks)`
  - `chapterStatusLabel(chapter)`
  - `templateInstanceCanConfirm(instance)`
  - `reconciliationSeverityCounts(summary)`
- [ ] Implement `ChapterTree` with badges:
  - missing from tender
  - newly added
  - disabled
  - changed order
  - unresolved critical issue
- [ ] Implement `ChapterTemplateForm` as form sections:
  - fixed text
  - AI prompt
  - variables
  - asset placeholders
  - page breaks
  - header/footer
  - conditions
- [ ] Implement `TemplatePreviewPane` as read-only preview with visible page/header/footer markers.
- [ ] Implement `ProjectTemplateWorkbench` three-column layout and mutations.
- [ ] Render `ProjectTemplateWorkbench` from `AuthoringModule.tsx` when `tab === "template"`.
- [ ] Write React tests for:
  - chapter tree loads
  - fixed text edits save
  - AI prompt section is collapsed by default and can be expanded
  - unresolved critical directory issue disables confirmation
  - successful confirmation enables bid authoring path
- [ ] Run: `cd frontend && npx vitest run src/modules/templates/templateInstanceModel.test.ts src/modules/templates/ProjectTemplateWorkbench.test.tsx`
- [ ] Commit: `git add frontend/src/lib/api.ts frontend/src/modules/templates frontend/src/modules/authoring/AuthoringModule.tsx && git commit -m "Add project template adjustment workbench"`

### Task 7: Generate Bid Content From Confirmed Project Template Instance

**Files:**
- Modify: `backend/tender_backend/api/bid_generation.py`
- Modify: `backend/tender_backend/services/bid_chapter_generation.py`
- Modify: `backend/tender_backend/services/template_service/docx_renderer.py`
- Modify: `backend/tender_backend/workflows/export_bid.py`
- Modify: `frontend/src/modules/authoring/EditorContent.tsx`
- Test: `backend/tests/unit/test_project_template_instance_service.py`
- Test: `backend/tests/integration/test_project_template_instances_api.py`
- Test: `frontend/src/modules/authoring/EditorContent.test.tsx`

- [ ] Write backend tests that generation is blocked when no confirmed project template instance exists.
- [ ] Write backend tests that fixed text, AI prompt blocks, asset placeholders, and page breaks are included in generation inputs.
- [ ] Run backend tests and verify initial FAIL.
- [ ] Update generation services to resolve template source in this order:
  - confirmed project template instance
  - selected global package fallback only for legacy projects
- [ ] Add generation run metadata:
  - `template_instance_id`
  - `template_instance_version`
  - `template_revision_no`
- [ ] Update frontend authoring to show template instance status before generation.
- [ ] Add frontend tests that bid generation requires a confirmed template instance for new projects.
- [ ] Run:
  - `cd backend && ../.venv/bin/pytest tests/unit/test_project_template_instance_service.py tests/integration/test_project_template_instances_api.py -q`
  - `cd frontend && npx vitest run src/modules/authoring/EditorContent.test.tsx`
- [ ] Commit: `git add backend/tender_backend/api/bid_generation.py backend/tender_backend/services/bid_chapter_generation.py backend/tender_backend/services/template_service/docx_renderer.py backend/tender_backend/workflows/export_bid.py frontend/src/modules/authoring/EditorContent.tsx backend/tests frontend/src/modules/authoring/EditorContent.test.tsx && git commit -m "Generate bids from confirmed project templates"`

### Task 8: Route Review Failures Back To Template Or Content

**Files:**
- Modify: `backend/tender_backend/api/post_bid.py`
- Modify: `backend/tender_backend/db/repositories/post_bid_review_repo.py`
- Modify: `frontend/src/modules/authoring/EditorContent.tsx`
- Modify: `frontend/src/modules/templates/ProjectTemplateWorkbench.tsx`
- Test: `backend/tests/unit/test_project_template_instance_service.py`
- Test: `frontend/src/modules/templates/ProjectTemplateWorkbench.test.tsx`

- [ ] Add tests for review issue source classification:
  - `template_structure`
  - `template_prompt`
  - `template_placeholder`
  - `formatting_rule`
  - `project_material`
  - `generated_content`
- [ ] Run tests and verify initial FAIL.
- [ ] Add review issue metadata fields via migration if existing `metadata_json` is not enough:
  - `issue_source`
  - `template_chapter_id`
  - `template_block_id`
  - `suggested_workspace`
- [ ] Update review issue creation so template-caused problems deep-link to the template adjustment workbench.
- [ ] Update frontend review issue cards with actions that navigate through `useNavigation().navigate`:
  - `去模板调整`
  - `去标书编写`
- [ ] Rerun tests.
- [ ] Commit: `git add backend/tender_backend/api/post_bid.py backend/tender_backend/db/repositories/post_bid_review_repo.py frontend/src/modules/authoring/EditorContent.tsx frontend/src/modules/templates/ProjectTemplateWorkbench.tsx backend/tests frontend/src/modules/templates/ProjectTemplateWorkbench.test.tsx && git commit -m "Route review issues to template or content workspaces"`

### Task 9: Promote Project Template Changes Back To Global Template

**Files:**
- Modify: `backend/tender_backend/api/project_template_instances.py`
- Modify: `backend/tender_backend/services/project_template_instance_service.py`
- Modify: `backend/tender_backend/db/repositories/project_template_instance_repo.py`
- Modify: `frontend/src/modules/templates/ProjectTemplateWorkbench.tsx`
- Test: `backend/tests/integration/test_project_template_instances_api.py`
- Test: `frontend/src/modules/templates/ProjectTemplateWorkbench.test.tsx`

- [ ] Write tests for creating a promotion proposal from a project template instance.
- [ ] Write tests that promotion does not mutate global templates until explicitly approved.
- [ ] Run tests and verify initial FAIL.
- [ ] Implement diff generation between base package snapshot and project template instance.
- [ ] Implement `POST /api/project-template-instances/{instance_id}/promotion-proposals`.
- [ ] Add frontend action `提议沉淀为新版模板`.
- [ ] Add proposal status display:
  - `draft`
  - `submitted`
  - `approved`
  - `rejected`
- [ ] Rerun tests.
- [ ] Commit: `git add backend/tender_backend/api/project_template_instances.py backend/tender_backend/services/project_template_instance_service.py backend/tender_backend/db/repositories/project_template_instance_repo.py frontend/src/modules/templates/ProjectTemplateWorkbench.tsx backend/tests/integration/test_project_template_instances_api.py frontend/src/modules/templates/ProjectTemplateWorkbench.test.tsx && git commit -m "Add project template promotion proposals"`

### Task 10: End-To-End Verification

**Files:**
- Modify as needed:
  - `backend/tests/integration/test_project_template_instances_api.py`
  - `frontend/src/modules/templates/ProjectTemplateWorkbench.test.tsx`
  - `frontend/src/modules/projects/ProjectsModule.test.tsx`
  - `frontend/src/modules/authoring/EditorContent.test.tsx`

- [ ] Run backend targeted suite:

```bash
cd backend && ../.venv/bin/pytest \
  tests/unit/test_project_template_instance_service.py \
  tests/unit/test_template_directory_reconciliation_service.py \
  tests/integration/test_project_template_instances_api.py \
  tests/integration/test_template_package_api.py \
  tests/integration/test_authz_routes.py \
  -q
```

- [ ] Expected: all selected tests PASS.
- [ ] Run frontend targeted suite:

```bash
cd frontend && npx vitest run \
  src/modules/authoring/authoringWorkflow.test.ts \
  src/modules/templates/templateInstanceModel.test.ts \
  src/modules/templates/ProjectTemplateWorkbench.test.tsx \
  src/modules/projects/ProjectsModule.test.tsx \
  src/modules/authoring/EditorContent.test.tsx
```

- [ ] Expected: all selected tests PASS.
- [ ] Run frontend build:

```bash
cd frontend && npm run build
```

- [ ] Expected: TypeScript and Vite build PASS.
- [ ] Inspect final diff:

```bash
git status --short
git diff --stat
```

- [ ] Commit final verification/doc updates:

```bash
git add docs/superpowers/plans/2026-05-14-project-template-instance-workflow.md
git commit -m "Document project template instance workflow plan"
```

## Acceptance Criteria

- [ ] New projects have a selected base template and a project template instance.
- [ ] Authoring includes a visible `模板调整` step between requirements confirmation and bid editing.
- [ ] Project cards and Authoring tabs can route users to the next incomplete workflow step.
- [ ] Template adjustment edits project template instances only.
- [ ] Tender directory differences are visible, actionable, and tracked.
- [ ] The template adjustment UI is form-based for tender engineers.
- [ ] Header, footer, page break, fixed text, AI prompt, variables, and material placeholders are explicit template blocks.
- [ ] Bid generation uses the confirmed project template instance.
- [ ] Review failures can route users to the right workspace.
- [ ] Project-specific template improvements can be proposed back to global templates without automatic global mutation.
- [ ] All backend and frontend targeted tests pass.

## Risk Controls

- [ ] Prevent global template pollution by making project template instances the default edit target.
- [ ] Prevent workflow drift by keeping `upload -> parse -> requirements -> template -> editor` as the only primary forward path for new projects.
- [ ] Prevent low-quality generation by blocking generation when critical template reconciliation issues are unresolved.
- [ ] Prevent template/content confusion by adding review issue source classification.
- [ ] Prevent form complexity from overwhelming tender engineers by collapsing AI prompt advanced controls by default.
- [ ] Preserve auditability with revision snapshots for every template confirmation and reconciliation apply action.

## Tracking Notes

- Use this plan as the checklist source of truth.
- Each task should land in a separate commit.
- Do not merge project template instance changes back to global templates without an explicit promotion proposal and approval step.
- Keep the existing global template package APIs stable for imported template management.
- Keep the existing authoring workspace usable for legacy projects that do not yet have project template instances.
