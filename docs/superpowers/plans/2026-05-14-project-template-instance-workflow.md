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
- 答疑、补遗、澄清到达后，不新建一套流程；复用现有 `tender_clarification` / `ClarificationMergeService`，触发项目模板实例的增量差异融合，受影响项必须重新确认。
- 盖章、签字、骑缝章不是普通文本提示，必须是可预览、可审查、可提交前勾选的结构化模板块。
- 条款响应/偏离不是目录对齐的副产品，必须逐条绑定 `project_requirement` 与模板章节/块，未响应条款阻断生成/导出。
- 格式规则本期先固化为 `project_template_instance.metadata_json.format_profile` 和 `seal_units`，渲染深度可分阶段实现，但数据边界现在确定。
- 标书编写区按确认后的项目模板实例生成投标文件。
- 标书生成质量或审查不过时，先判断问题来源：
  - 模板结构、提示词、占位符、素材位、分页、页眉页脚问题：回到模板调整区修项目模板实例。
  - 项目资料缺失、AI正文事实错误、素材错配问题：在标书编写区修生成内容或项目资料。
- 项目结束后，项目模板实例中的有效改动可以“提议合并”回全局模板，形成新版模板。

## Review Verification Notes

对 `2026-05-14-project-template-instance-workflow-bidding-engineer-review.md` 的核实结果：

- P0-1 答疑/补遗：代码库已有 `tender_clarification`、`ClarificationMergeService`、`RequirementsContent` 的澄清/补遗入口，并会把受影响 requirement/outline/chapter/draft 标记 stale。原计划缺口不是“没有答疑模块”，而是“答疑影响未进入项目模板实例 reconciliation”。本计划补增量 reconciliation，不重复新增 `tender_document.document_type`。
- P0-2 盖章签字：代码库已有签章类 requirement 识别和提交清单雏形，但模板块只覆盖 `fixed_text/page_break/header_footer`，无法在模板预览和提交前形成硬确认。本计划新增 `seal_mark` 块和盖章确认清单。
- P0-3 格式规则：原计划只把 `formatting_rule` 当 review source，没有明确格式配置落点。本计划在 `metadata_json` 固化 `format_profile` 与 `seal_units`；复杂 DOCX 样式渲染不扩成独立大模块。
- P0-4 条款级响应：代码库已有 `bid_chapter_requirement`、`compliance_matrix` 和偏差表 UI，但没有“每条 requirement 至少一个响应块”的硬约束。本计划新增 `project_requirement_response`，作为模板实例到生成内容之间的响应覆盖账本。
- P1-1 资质/业绩/人员：已有 master-data 与人员/设备选择基础，本计划只增强 `asset_placeholder.render_options_json.asset_filter` 与过期告警边界，不在本计划重做资料库。
- P1-2 报价/BOQ：已有 `external_bid_attachment` 和 pricing volume 边界。本计划不做结构化报价引擎，只声明 `pricing_block/excel_attachment` 为外部报价挂载边界。
- P1-3 多人协作锁：当前项目模板章节尚不存在，必须在新表中预留乐观锁/短锁字段，避免上线后多人编辑互相覆盖。
- P1-4 截止时间：`project.submission_deadline` 已存在。本计划把它和 `locked_for_generation`、导出 gate 联动，不新增重复 `bid_deadline` 字段。

## Scope Decisions From Review

### Must enter this plan

- 答疑/补遗触发的项目模板实例增量 reconciliation。
- `seal_mark` 模板块、预览标记、提交前盖章/签字硬确认。
- `format_profile`、`seal_units` 数据边界。
- `project_requirement_response` 条款级响应覆盖账本。
- 三级目录/跨层移动 reconciliation 测试、200+ 章节生成性能基线、三类新增 issue source。
- 章节短锁和 `lock_version`，因为项目模板实例表是本计划新建，预留成本最低。
- 截止时间联动最终锁定，因为字段已存在，属于流程闭环。

### Explicitly defer

- 独立资质/业绩/人员证书库重构：沿用现有 master-data，本计划只做模板占位符筛选和过期提示接口。
- 结构化报价/BOQ 公式引擎：本计划只支持报价附件挂载边界，后续单独计划。
- 多方案变体、历史标书反向沉淀、多级会签流：不进入当前 MVP，避免把模板实例工作流扩成全量投标平台重构。

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
- [ ] Tender engineer adjusts chapter order by mouse drag-and-drop in the project template chapter tree, e.g. moving original Chapter 5 after Chapter 7, and adjusts chapter inclusion, AI prompts, fixed text, variables, material placeholders, page breaks, header/footer references, and conditional rules through forms.
- [ ] User confirms the project template instance.
- [ ] Bid authoring workspace generates bid content from the confirmed project template instance.
- [ ] Review/compliance issues are classified by source and routed either to template adjustment or bid authoring.
- [ ] Project template instance can be promoted back to global template as a versioned proposal after project completion.

## Template Edit Propagation Rules

Template editing must follow these rules:

- [ ] Saving a template block changes the current project template instance.
- [ ] Saving a template block refreshes the template preview immediately.
- [ ] Saving a template block affects future generation and future DOCX rendering.
- [ ] Saving a template block does not silently rewrite existing generated bid text, chart assets, or exported DOCX files.
- [ ] Generated artifacts store which template instance version/revision created them.
- [ ] When a newer relevant template revision exists, generated artifacts are marked stale.
- [ ] Stale generated artifacts require explicit user action: regenerate chapter, regenerate chart, rerender table, or rerender DOCX.
- [ ] Final export is blocked when stale generated artifacts remain.

### Editable Template Block Types

The template editor must support these business-facing block groups:

- `fixed_text`
  - Directly editable fixed chapter text.
  - Save affects preview immediately and future DOCX rendering.

- `table_definition`
  - Editable table title, header rows, fixed rows, field bindings, repeating-header option, and table note text.
  - Save affects preview immediately and future DOCX/table rendering.

- `asset_placeholder`
  - Editable company qualification/proof asset slot: label, placeholder key, asset type, required flag, matching rule, and help text.
  - Save affects future material binding and future DOCX rendering.

- `ai_prompt`
  - Editable AI writing prompt for chapter content.
  - Save affects future AI text generation and marks existing generated draft stale.

- `chart_prompt`
  - Editable AI chart generation prompt, chart type, Mermaid/source-code guidance, and placeholder key.
  - Save affects future chart generation and marks existing chart assets stale.

- `page_format`
  - Editable page break, title level, section break, header/footer reference, margins, orientation, and page numbering rule.
  - Save affects preview immediately and future DOCX rendering.

Existing block compatibility:

- Existing `page_break` and `header_footer` blocks should be normalized into the `page_format` panel in the frontend.
- Existing chart metadata can initially be stored in `render_options_json` on `chart_prompt` blocks.
- Existing `fixed_text`, `ai_prompt`, and `asset_placeholder` blocks remain valid.

### Stale Impact Rules

- `fixed_text`
  - Stales: DOCX render/export artifacts for the same chapter.
  - Does not stale: AI text draft unless fixed text is included in the AI prompt inputs for that chapter.

- `table_definition`
  - Stales: table render output, DOCX render/export artifacts for the same chapter.
  - Does not stale: AI text draft by default.

- `asset_placeholder`
  - Stales: material binding status and DOCX render/export artifacts for the same chapter.
  - Does not stale: AI text draft by default.

- `ai_prompt`
  - Stales: generated chapter text draft for the same chapter.
  - Stales: DOCX render/export artifacts that include that draft.

- `chart_prompt`
  - Stales: chart assets for the same chapter and placeholder key.
  - Stales: DOCX render/export artifacts that include that chart.

- `page_format`
  - Stales: DOCX render/export artifacts for the same chapter and following section boundary when a section break changes.
  - Does not stale: generated text or chart content.

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
  - Supports mouse drag-and-drop reorder within the same parent, e.g. moving original Chapter 5 to the Chapter 7 position.
  - Supports drag-and-drop move across hierarchy levels only when the target parent is valid for the volume/chapter type.
  - After drop, renumbers visible chapter codes from persisted tree order and marks tender-directory order diff as manually overridden.

- Center: selected chapter template form.
  - Fixed text section.
  - AI prompt section, collapsed by default.
  - Variables section.
  - Material/asset placeholders section.
  - Page break section.
  - Header/footer section.
  - Seal/signature mark section.
  - Requirement response coverage section.
  - Format profile section.
  - Conditional display section.
  - Chapter actions: save, disable, duplicate, mark resolved.

- Right: read-only template preview.
  - Uses sample project data.
  - Shows fixed text and placeholders.
  - Makes page break, header, footer, seal/signature, requirement-response, and unresolved placeholder markers visible.
  - Shows preview limitations explicitly through status labels, not long instructional copy.

### Bid Authoring Page Adjustment

The current `EditorContent` should stop behaving as if it owns template structure. It should consume the confirmed project template instance:

- Show template instance name, version, confirmation time, unresolved issue count, unanswered requirement count, and pending seal checklist count.
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
  - Produce add/remove/rename/reorder/split/merge/move suggestions, including source metadata (`tender_document`, `tender_addendum`, or `manual`).

- `backend/tender_backend/services/template_edit_propagation_service.py`
  - Computes which generated artifacts are affected by a template block edit.
  - Marks drafts, charts, and export artifacts stale after relevant template edits.
  - Clears stale markers after explicit regeneration/rerender.

- `backend/tender_backend/api/project_template_instances.py`
  - API endpoints for reading, editing, confirming, previewing, reconciling, and proposing global template promotion.

- `backend/tests/unit/test_project_template_instance_service.py`
- `backend/tests/unit/test_template_directory_reconciliation_service.py`
- `backend/tests/unit/test_template_edit_propagation_service.py`
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
  - Regeneration endpoints must clear stale-template markers for regenerated artifacts.

- `backend/tender_backend/services/bid_chapter_generation.py`
  - Consume chapter block model: fixed text, AI prompt block, variables, material placeholders, page controls, and conditional rules.
  - Save template instance and revision metadata on generated chapter drafts.

- `backend/tender_backend/db/repositories/chapter_draft_repo.py`
  - Store and clear stale-template metadata for generated text drafts.

- `backend/tender_backend/db/repositories/chart_asset_repo.py`
  - Store and clear stale-template metadata for generated chart assets.

- `backend/tender_backend/services/chart_service/*`
  - Save template instance and revision metadata on generated chart assets.

- `backend/tender_backend/services/template_service/docx_renderer.py`
  - Render project template instance blocks into DOCX-compatible structure and preview output.

- `backend/tender_backend/workflows/export_bid.py`
  - Use confirmed project template instance for final package gates.
  - Fail export gates when stale template-generated artifacts remain.

### Frontend Create

- `frontend/src/modules/authoring/AuthoringWorkflowStatus.tsx`
  - Shared operational status strip for upload, parse, requirements, template adjustment, and editor pages.

- `frontend/src/modules/authoring/authoringWorkflow.ts`
  - Pure workflow-state helpers for current step, next action, blocked reasons, and tab routing.

- `frontend/src/modules/templates/templateEditPropagation.ts`
  - Pure helpers for impact labels, stale messages, and whether confirmation/export should be blocked.

- `frontend/src/modules/templates/TemplateBlockPanels.tsx`
  - Form panels for fixed text, table definition, asset placeholders, AI prompt, chart prompt, and page format.

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
- `frontend/src/modules/templates/templateEditPropagation.test.ts`
- `frontend/src/modules/templates/ProjectTemplateWorkbench.test.tsx`
- `frontend/src/modules/templates/templateInstanceModel.test.ts`

### Frontend Modify

- `frontend/src/lib/navigation.ts`
  - Add the `authoring/template` tab between `requirements` and `editor`.

- `frontend/src/lib/api.ts`
  - Add project template instance types and API functions.
  - Add template revision and stale metadata to project template, draft, chart, preview, and export gate types.

- `frontend/src/modules/authoring/AuthoringModule.tsx`
  - Add route/tab entry for template adjustment before bid authoring.
  - Render `ProjectTemplateWorkbench` when `tab === "template"`.

- `frontend/src/modules/authoring/EditorContent.tsx`
  - Read confirmed project template instance status.
  - Block or warn generation if template instance has unresolved critical directory/template issues.
  - Show stale-template badges for generated chapters/charts caused by template edits.
  - Add explicit actions: `按新模板重新生成正文`, `按新模板重新生成图表`, `重新渲染本章`.

- `frontend/src/modules/export/ExportGateContent.tsx`
  - Show stale-template gate with direct link back to authoring/template or editor.

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
  - `format_profile`: font family/size, paragraph spacing, line spacing, margins, heading levels, page numbering rules.
  - `seal_units`: sealed/printed volumes, binding method, separate-envelope rules, copy-count rules.
  - `standard_variables`: project-level variable dictionary extracted from tender summary, e.g. `project.name`, `project.tender_no`, `project.tenderer`, `project.bidder`, `project.legal_representative`, `project.manager`, `project.duration`, `project.price`.
  - `clarification_reconciliation`: latest applied clarification id/round and unresolved impact counts.
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
- `lock_owner TEXT NULL`
- `locked_until TIMESTAMPTZ NULL`
- `lock_version INT NOT NULL DEFAULT 1`
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
  - for `seal_mark`: `seal_subtype`, `required_position`, `applies_to_pages`, `confirmation_required`.
  - for `asset_placeholder`: `asset_filter`, `valid_until_field`, `expiry_warning_days`.
  - for `pricing_block` / `excel_attachment`: `volume_type`, `attachment_type`, `required_sheet_names`.
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Block type values:

- `fixed_text`
- `table_definition`
- `ai_prompt`
- `chart_prompt`
- `variable`
- `asset_placeholder`
- `page_format`
- `page_break`
- `header_footer`
- `condition`
- `seal_mark`
- `pricing_block`
- `excel_attachment`

### `project_requirement_response`

- `id UUID PRIMARY KEY`
- `project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE`
- `template_instance_id UUID NOT NULL REFERENCES project_template_instance(id) ON DELETE CASCADE`
- `requirement_id UUID NOT NULL REFERENCES project_requirement(id) ON DELETE CASCADE`
- `template_chapter_id UUID NULL REFERENCES project_template_chapter(id) ON DELETE SET NULL`
- `template_block_id UUID NULL REFERENCES project_template_block(id) ON DELETE SET NULL`
- `response_status TEXT NOT NULL DEFAULT 'unanswered'`
- `response_text TEXT NOT NULL DEFAULT ''`
- `deviation_note TEXT NOT NULL DEFAULT ''`
- `source_type TEXT NOT NULL DEFAULT 'tender_requirement'`
- `source_clarification_id UUID NULL REFERENCES tender_clarification(id) ON DELETE SET NULL`
- `metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `UNIQUE (template_instance_id, requirement_id)`

Response status values:

- `unanswered`
- `full_response`
- `partial_response`
- `deviation`
- `not_applicable`

### `project_template_seal_confirmation`

- `id UUID PRIMARY KEY`
- `project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE`
- `template_instance_id UUID NOT NULL REFERENCES project_template_instance(id) ON DELETE CASCADE`
- `seal_block_id UUID NOT NULL REFERENCES project_template_block(id) ON DELETE CASCADE`
- `confirmation_status TEXT NOT NULL DEFAULT 'pending'`
- `confirmed_by TEXT NULL`
- `confirmed_at TIMESTAMPTZ NULL`
- `note TEXT NOT NULL DEFAULT ''`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `UNIQUE (template_instance_id, seal_block_id)`

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

Every block edit must record a revision. `change_type` values for template edit propagation:

- `fixed_text_edit`
- `table_definition_edit`
- `asset_placeholder_edit`
- `ai_prompt_edit`
- `chart_prompt_edit`
- `page_format_edit`

The `snapshot_json` for these revisions must include:

- `template_block_id`
- `block_type`
- `before`
- `after`
- `affected_artifact_types`

### Generated artifact template revision metadata

Add these columns to `chapter_draft`:

- `template_instance_id UUID NULL REFERENCES project_template_instance(id) ON DELETE SET NULL`
- `template_revision_no INT NULL`
- `is_stale_by_template BOOLEAN NOT NULL DEFAULT FALSE`
- `template_stale_reason TEXT NULL`
- `stale_by_template_block_id UUID NULL REFERENCES project_template_block(id) ON DELETE SET NULL`

Add these columns to `chart_asset`:

- `template_instance_id UUID NULL REFERENCES project_template_instance(id) ON DELETE SET NULL`
- `template_revision_no INT NULL`
- `is_stale_by_template BOOLEAN NOT NULL DEFAULT FALSE`
- `template_stale_reason TEXT NULL`
- `stale_by_template_block_id UUID NULL REFERENCES project_template_block(id) ON DELETE SET NULL`

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

- `POST /api/project-template-instances/{instance_id}/chapters/reorder`
  - Persists drag-and-drop chapter tree order.
  - Request body: `ordered_tree` with `{chapter_id, parent_id, sort_order}` rows for the complete affected sibling set or subtree.
  - Records a `manual_reorder` revision with before/after chapter paths.
  - Rejects moves that put a chapter under itself/descendant, cross incompatible volume boundaries, or conflict with another user's active chapter lock.

- `POST /api/project-template-chapters/{chapter_id}/blocks`
  - Adds a structured block to a chapter.

- `PATCH /api/project-template-blocks/{block_id}`
  - Updates a block's form fields.

- `DELETE /api/project-template-blocks/{block_id}`
  - Deletes a user-added block or disables a cloned block.

- `POST /api/projects/{project_id}/template-instance/reconcile-directory`
  - Compares tender parsed directory requirements with the current project template instance.
  - Accepts optional `base_revision_no` and `clarification_id`; when present, performs incremental comparison against the last confirmed snapshot and marks clarification/addendum impacts as non-skippable until handled.

- `POST /api/projects/{project_id}/template-instance/apply-reconciliation`
  - Applies selected reconciliation suggestions.
  - Rejects skipping suggestions with `source_type === "tender_addendum"` and `severity === "critical"` unless an explicit `not_applicable` reason is supplied.

- `GET /api/project-template-instances/{instance_id}/requirement-responses`
  - Returns per-requirement response coverage, mapped chapter/block, response status, and unresolved count.

- `PATCH /api/project-requirement-responses/{response_id}`
  - Updates response status, response text, deviation note, and mapped template block.

- `GET /api/project-template-instances/{instance_id}/seal-checklist`
  - Returns all required `seal_mark` blocks as a submission checklist.

- `POST /api/project-template-instances/{instance_id}/seal-checklist/{seal_block_id}/confirm`
  - Confirms one required seal/signature item before final generation/export.

- `POST /api/project-template-chapters/{chapter_id}/lock`
  - Acquires or refreshes a short edit lock for a chapter.

- `DELETE /api/project-template-chapters/{chapter_id}/lock`
  - Releases the chapter lock held by the current actor.

- `POST /api/project-template-instances/{instance_id}/confirm`
  - Marks template instance ready for bid authoring if no critical unresolved issues remain.

- `GET /api/project-template-instances/{instance_id}/preview`
  - Returns render preview with sample project data and visible page/header/footer markers.

- `POST /api/project-template-instances/{instance_id}/promotion-proposals`
  - Creates a proposal to merge project template changes back to global template.

- `PATCH /api/project-template-blocks/{block_id}`
  - Updates the block.
  - Records a `project_template_revision`.
  - Runs stale-impact propagation.
  - Returns updated block plus impact summary:

```json
{
  "block": { "id": "block-id", "block_type": "ai_prompt" },
  "revision_no": 12,
  "impact": {
    "stale_draft_count": 1,
    "stale_chart_count": 0,
    "stale_export_artifact_count": 1,
    "message": "AI 提示词已更新，相关章节正文需重新生成。"
  }
}
```

- `GET /api/project-template-instances/{instance_id}/preview`
  - Returns preview generated from latest saved template blocks.
  - Includes `template_revision_no`.

- `POST /api/bid-chapters/{chapter_id}/regenerate-from-template`
  - Regenerates chapter text using the latest `ai_prompt`.
  - Clears stale template markers for that chapter draft.

- `POST /api/chart-assets/{asset_id}/regenerate-from-template`
  - Regenerates chart using the latest `chart_prompt`.
  - Clears stale template markers for that chart asset.

- `POST /api/projects/{project_id}/render-from-template`
  - Rerenders current DOCX preview/export staging artifacts using latest template blocks.
  - Clears stale render/export markers when render succeeds.

## Implementation Tasks

### Task 1: Persist Project Template Instances

**Files:**
- Create: `backend/tender_backend/db/alembic/versions/0051_project_template_instances.py`
- Create: `backend/tender_backend/db/repositories/project_template_instance_repo.py`
- Create: `backend/tests/unit/test_project_template_instance_service.py`

- [ ] Write repository tests for creating a project template instance with chapters and blocks cloned from a package.
- [ ] Run: `cd backend && ../.venv/bin/pytest tests/unit/test_project_template_instance_service.py -q`
- [ ] Expected initial result: FAIL because repository/service files do not exist.
- [ ] Add Alembic migration with all tables listed in **Data Model**: project template instance, chapter, block, requirement response, seal confirmation, revision, and promotion proposal.
- [ ] Implement dataclasses for instance, chapter, block, requirement response, seal confirmation, revision, and promotion proposal.
- [ ] Implement repository methods:
  - `create_instance(conn, project_id, base_template_package_id, category_code, display_name)`
  - `get_current_for_project(conn, project_id)`
  - `list_chapters(conn, instance_id)`
  - `list_blocks(conn, chapter_id)`
  - `replace_chapter_order(conn, instance_id, ordered_chapter_ids)`
  - `move_chapter(conn, chapter_id, new_parent_id, new_sort_order, actor)`
  - `update_chapter(conn, chapter_id, fields)`
  - `create_block(conn, chapter_id, fields)`
  - `update_block(conn, block_id, fields)`
  - `delete_block(conn, block_id)`
  - `list_requirement_responses(conn, instance_id)`
  - `upsert_requirement_response(conn, instance_id, requirement_id, template_chapter_id, template_block_id, fields)`
  - `list_seal_checklist(conn, instance_id)`
  - `confirm_seal_item(conn, instance_id, seal_block_id, actor, note)`
  - `try_lock_chapter(conn, chapter_id, actor, ttl_seconds)`
  - `release_chapter_lock(conn, chapter_id, actor)`
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
  - `seal_mark` blocks when source requirements or template text contain `签章` / `盖章` / `签字` / `骑缝章` / `法定代表人`.
  - `excel_attachment` placeholder for pricing volumes so the template workflow has an explicit boundary to the external pricing module.
- [ ] Initialize `project_requirement_response` rows for confirmed non-stale `project_requirement` rows; default status is `unanswered` until a chapter/block mapping exists.
- [ ] Initialize `metadata_json.format_profile`, `metadata_json.seal_units`, and `metadata_json.standard_variables` from tender summary/project fields when available.
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
  - `POST /api/project-template-instances/{instance_id}/chapters/reorder`
  - `POST /api/project-template-chapters/{chapter_id}/blocks`
  - `PATCH /api/project-template-blocks/{block_id}`
  - `POST /api/project-template-instances/{instance_id}/confirm`
  - `GET /api/project-template-instances/{instance_id}/requirement-responses`
  - `PATCH /api/project-requirement-responses/{response_id}`
  - `GET /api/project-template-instances/{instance_id}/seal-checklist`
  - `POST /api/project-template-chapters/{chapter_id}/lock`
- [ ] Run: `cd backend && ../.venv/bin/pytest tests/integration/test_project_template_instances_api.py -q`
- [ ] Expected initial result: FAIL with missing routes.
- [ ] Implement Pydantic models:
  - `ProjectTemplateInstanceOut`
  - `ProjectTemplateChapterOut`
  - `ProjectTemplateBlockOut`
  - `ProjectTemplateChapterUpdate`
  - `ProjectTemplateChapterReorderBody`
  - `ProjectTemplateChapterReorderOut`
  - `ProjectTemplateBlockCreate`
  - `ProjectTemplateBlockUpdate`
  - `ProjectTemplateConfirmOut`
  - `RequirementResponseOut`
  - `RequirementResponseUpdate`
  - `SealChecklistItemOut`
  - `ChapterLockOut`
- [ ] Enforce project access for all project-scoped operations.
- [ ] Implement chapter reorder endpoint so drag-and-drop can move Chapter 5 after Chapter 7 by updating `parent_id`, `sort_order`, and revision snapshot atomically.
- [ ] Reject confirmation when critical reconciliation issues remain, any non-stale required requirement has `unanswered` response status, or required `seal_mark` blocks are missing checklist entries.
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
  - three-level nested tender directory `1.2.3` maps without flattening into the wrong parent
  - cross-level movement from `2.1` to `1.3.1` produces `move_chapter` instead of delete+add when identity is stable
  - clarification/addendum changed a previously confirmed chapter title -> suggestion source is `tender_addendum` and severity is `critical`
  - clarification/addendum adds a new mandatory format/signature requirement -> suggestion cannot be skipped without explicit `not_applicable` reason
- [ ] Run: `cd backend && ../.venv/bin/pytest tests/unit/test_template_directory_reconciliation_service.py -q`
- [ ] Expected initial result: FAIL because service does not exist.
- [ ] Implement `TemplateDirectoryReconciliationService.build_suggestions(project_requirements, template_chapters)`.
- [ ] Store reconciliation summary in `project_template_instance.metadata_json.reconciliation` and clarification impact summary in `metadata_json.clarification_reconciliation`.
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
- [ ] Implement mouse drag-and-drop in `ChapterTree`:
  - dragging original Chapter 5 below Chapter 7 updates the in-memory tree immediately
  - dropping calls `POST /api/project-template-instances/{instance_id}/chapters/reorder`
  - failed save rolls the tree back and shows a concise error
  - locked chapters cannot be dragged or used as drop targets by another actor
  - same-parent reorder is supported in MVP; cross-parent drag is allowed only when backend validation accepts the target parent
- [ ] Implement `ChapterTemplateForm` as form sections:
  - fixed text
  - AI prompt
  - variables
  - asset placeholders, including `asset_filter` and expiry warning fields
  - page breaks
  - header/footer
  - seal marks: company seal, legal representative seal/signature, project manager signature, paging seal
  - pricing/excel attachment boundary blocks
  - requirement responses: full response, partial response, deviation, not applicable
  - format profile: font, spacing, margins, binding/seal unit notes
  - conditions
- [ ] Implement `TemplatePreviewPane` as read-only preview with visible page/header/footer/seal/signature/requirement-response markers.
- [ ] Implement `ProjectTemplateWorkbench` three-column layout and mutations.
- [ ] Render `ProjectTemplateWorkbench` from `AuthoringModule.tsx` when `tab === "template"`.
- [ ] Write React tests for:
  - chapter tree loads
  - dragging Chapter 5 after Chapter 7 calls reorder API with updated sibling order and rerenders Chapter 7 before Chapter 5
  - reorder API failure rolls back the visible chapter order
  - fixed text edits save
  - AI prompt section is collapsed by default and can be expanded
  - unresolved critical directory issue disables confirmation
  - unanswered required requirement disables confirmation
  - required seal mark appears in preview and seal checklist
  - chapter locked by another actor disables editing and shows lock owner
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
- [ ] Write backend tests that fixed text, AI prompt blocks, asset placeholders, seal marks, requirement responses, format profile, and page breaks are included in generation inputs.
- [ ] Write backend performance test that building generation inputs for a 200+ chapter project template instance stays under 2 seconds on the test database and does not issue per-block N+1 queries.
- [ ] Write backend tests that generation is blocked when `project.submission_deadline` has passed unless the instance status is already `locked_for_generation`.
- [ ] Run backend tests and verify initial FAIL.
- [ ] Update generation services to resolve template source in this order:
  - confirmed project template instance
  - selected global package fallback only for legacy projects
- [ ] Add generation run metadata:
  - `template_instance_id`
  - `template_instance_version`
  - `template_revision_no`
  - `requirement_response_coverage`
  - `format_profile_hash`
  - `seal_checklist_status`
- [ ] Update frontend authoring to show template instance status, unanswered requirement count, pending seal checklist count, and deadline/lock status before generation.
- [ ] Add frontend tests that bid generation requires a confirmed template instance for new projects.
- [ ] Run:
  - `cd backend && ../.venv/bin/pytest tests/unit/test_project_template_instance_service.py tests/integration/test_project_template_instances_api.py -q`
  - `cd frontend && npx vitest run src/modules/authoring/EditorContent.test.tsx`
- [ ] Commit: `git add backend/tender_backend/api/bid_generation.py backend/tender_backend/services/bid_chapter_generation.py backend/tender_backend/services/template_service/docx_renderer.py backend/tender_backend/workflows/export_bid.py frontend/src/modules/authoring/EditorContent.tsx backend/tests frontend/src/modules/authoring/EditorContent.test.tsx && git commit -m "Generate bids from confirmed project templates"`

### Task 8: Route Review Failures Back To Template Or Content

**Files:**
- Create: `backend/tender_backend/db/alembic/versions/0052_review_issue_template_routing.py`
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
  - `tender_addendum`
  - `seal_missing`
  - `requirement_not_responded`
  - `project_material`
  - `generated_content`
- [ ] Run tests and verify initial FAIL.
- [ ] Add `review_issue` routing columns in `0052_review_issue_template_routing.py`:
  - `issue_source`
  - `template_chapter_id`
  - `template_block_id`
  - `suggested_workspace`
  - `requirement_response_id`
  - `seal_block_id`
  - `source_clarification_id`
- [ ] Update review issue creation so template-caused problems deep-link to the template adjustment workbench.
- [ ] Update frontend review issue cards with actions that navigate through `useNavigation().navigate`:
  - `去模板调整`
  - `去标书编写`
- [ ] Rerun tests.
- [ ] Commit: `git add backend/tender_backend/db/alembic/versions/0052_review_issue_template_routing.py backend/tender_backend/api/post_bid.py backend/tender_backend/db/repositories/post_bid_review_repo.py frontend/src/modules/authoring/EditorContent.tsx frontend/src/modules/templates/ProjectTemplateWorkbench.tsx backend/tests frontend/src/modules/templates/ProjectTemplateWorkbench.test.tsx && git commit -m "Route review issues to template or content workspaces"`

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

### Task 10: Add Template Revision Metadata To Generated Artifacts

**Files:**
- Create: `backend/tender_backend/db/alembic/versions/0053_template_edit_propagation.py`
- Modify: `backend/tender_backend/db/repositories/chapter_draft_repo.py`
- Modify: `backend/tender_backend/db/repositories/chart_asset_repo.py`
- Test: `backend/tests/unit/test_template_edit_propagation_service.py`

- [ ] Write failing tests that a generated chapter draft can store `template_instance_id`, `template_revision_no`, and stale-template fields.
- [ ] Write failing tests that a chart asset can store `template_instance_id`, `template_revision_no`, and stale-template fields.
- [ ] Run:

```bash
cd backend && ../.venv/bin/pytest tests/unit/test_template_edit_propagation_service.py -q
```

- [ ] Expected initial result: FAIL because migration/repository fields do not exist.
- [ ] Add migration columns listed in **Generated artifact template revision metadata**.
- [ ] Update repository row dataclasses and mappers for chapter drafts and chart assets.
- [ ] Add repository methods:
  - `mark_stale_by_template(conn, *, project_id, chapter_id=None, template_block_id, reason)`
  - `clear_template_stale(conn, *, artifact_id)`
- [ ] Rerun the unit test and confirm PASS.
- [ ] Commit: `git add backend/tender_backend/db/alembic/versions/0053_template_edit_propagation.py backend/tender_backend/db/repositories/chapter_draft_repo.py backend/tender_backend/db/repositories/chart_asset_repo.py backend/tests/unit/test_template_edit_propagation_service.py && git commit -m "Track template revision on generated artifacts"`

### Task 11: Record Template Revisions And Propagate Stale Impact

**Files:**
- Create: `backend/tender_backend/services/template_edit_propagation_service.py`
- Modify: `backend/tender_backend/api/project_template_instances.py`
- Modify: `backend/tender_backend/db/repositories/project_template_instance_repo.py`
- Test: `backend/tests/unit/test_template_edit_propagation_service.py`
- Test: `backend/tests/integration/test_project_template_instances_api.py`

- [ ] Write failing tests for stale impact rules:
  - `ai_prompt` edit stales chapter draft.
  - `chart_prompt` edit stales matching chart asset.
  - `page_format` edit stales DOCX/export metadata but not AI text.
  - `fixed_text` edit stales render/export metadata.
- [ ] Run: `cd backend && ../.venv/bin/pytest tests/unit/test_template_edit_propagation_service.py tests/integration/test_project_template_instances_api.py -q`
- [ ] Expected initial result: FAIL because propagation service and API impact response do not exist.
- [ ] Update `ProjectTemplateInstanceRepository.record_revision` to return the inserted revision row or revision number.
- [ ] Implement `TemplateEditPropagationService.classify_block_edit(block_type, before, after)`.
- [ ] Implement `TemplateEditPropagationService.apply_stale_impact(conn, *, block, revision_no, actor)`.
- [ ] Update `PATCH /api/project-template-blocks/{block_id}` to load old block, update block, record revision, propagate stale impact, and return impact summary.
- [ ] Rerun tests and confirm PASS.
- [ ] Commit: `git add backend/tender_backend/services/template_edit_propagation_service.py backend/tender_backend/api/project_template_instances.py backend/tender_backend/db/repositories/project_template_instance_repo.py backend/tests/unit/test_template_edit_propagation_service.py backend/tests/integration/test_project_template_instances_api.py && git commit -m "Propagate stale impact after template edits"`

### Task 12: Save Generation Outputs With Template Revision

**Files:**
- Modify: `backend/tender_backend/services/bid_chapter_generation.py`
- Modify: `backend/tender_backend/api/bid_generation.py`
- Modify: `backend/tender_backend/services/chart_service/*`
- Test: `backend/tests/unit/test_template_edit_propagation_service.py`
- Test: `backend/tests/integration/test_project_template_instances_api.py`

- [ ] Write failing tests that generated chapter text stores the current project template instance id and revision number.
- [ ] Write failing tests that generated chart assets store the current project template instance id and revision number.
- [ ] Run: `cd backend && ../.venv/bin/pytest tests/unit/test_template_edit_propagation_service.py tests/integration/test_project_template_instances_api.py -q`
- [ ] Expected initial result: FAIL because generation does not persist template revision metadata.
- [ ] Resolve current project template instance and latest revision before generating chapter text.
- [ ] Save `template_instance_id` and `template_revision_no` on the generated draft.
- [ ] Resolve current project template instance and latest revision before generating chart assets.
- [ ] Save `template_instance_id` and `template_revision_no` on the generated chart asset.
- [ ] Clear `is_stale_by_template` and stale reason after successful regeneration.
- [ ] Rerun tests and confirm PASS.
- [ ] Commit: `git add backend/tender_backend/services/bid_chapter_generation.py backend/tender_backend/api/bid_generation.py backend/tender_backend/services/chart_service backend/tests/unit/test_template_edit_propagation_service.py backend/tests/integration/test_project_template_instances_api.py && git commit -m "Stamp generated outputs with template revision"`

### Task 13: Block Export When Template-Stale Artifacts Remain

**Files:**
- Modify: `backend/tender_backend/workflows/export_bid.py`
- Modify: `frontend/src/modules/export/ExportGateContent.tsx`
- Modify: `frontend/src/lib/api.ts`
- Test: `frontend/src/modules/export/ExportGateContent.test.tsx`
- Test: backend export gate tests if present

- [ ] Write failing frontend test that export gate shows `模板修改后未重新生成` when stale-template artifacts remain.
- [ ] Write failing backend test that export gate reports `stale_template_artifact_count > 0` when drafts/charts are stale by template.
- [ ] Run:

```bash
cd frontend && npx vitest run src/modules/export/ExportGateContent.test.tsx
cd backend && ../.venv/bin/pytest tests/integration -q -k export
```

- [ ] Expected initial result: frontend FAIL for missing gate; backend may fail or report no matching tests. If backend has no export-specific test file, add coverage to the nearest export gate integration test.
- [ ] Update export gate response type in `frontend/src/lib/api.ts`.
- [ ] Update `export_bid.py` to compute stale-template artifacts.
- [ ] Render gate label and blocked state in `ExportGateContent.tsx`.
- [ ] Add direct action label `返回模板调整` or `重新生成标书内容`.
- [ ] Rerun tests and confirm PASS.
- [ ] Commit: `git add backend/tender_backend/workflows/export_bid.py frontend/src/lib/api.ts frontend/src/modules/export/ExportGateContent.tsx frontend/src/modules/export/ExportGateContent.test.tsx backend/tests && git commit -m "Block export on template-stale artifacts"`

### Task 14: Build Editable Template Block Panels

**Files:**
- Create: `frontend/src/modules/templates/templateEditPropagation.ts`
- Create: `frontend/src/modules/templates/templateEditPropagation.test.ts`
- Create: `frontend/src/modules/templates/TemplateBlockPanels.tsx`
- Modify: `frontend/src/modules/templates/ChapterTemplateForm.tsx`
- Modify: `frontend/src/modules/templates/ProjectTemplateWorkbench.tsx`
- Modify: `frontend/src/lib/api.ts`
- Test: `frontend/src/modules/templates/ProjectTemplateWorkbench.test.tsx`

- [ ] Write helper tests for impact message mapping:
  - `ai_prompt` -> "相关章节正文需重新生成"
  - `chart_prompt` -> "相关图表需重新生成"
  - `table_definition` -> "相关表格和 DOCX 需重新渲染"
  - `asset_placeholder` -> "相关资料位和 DOCX 需重新渲染"
  - `page_format` -> "相关页面需重新渲染"
- [ ] Write React tests that each panel appears for its block type:
  - fixed text textarea
  - table title/header form
  - asset placeholder form
  - AI prompt textarea
  - chart prompt/code textarea
  - page format fields
- [ ] Run: `cd frontend && npx vitest run src/modules/templates/templateEditPropagation.test.ts src/modules/templates/ProjectTemplateWorkbench.test.tsx`
- [ ] Expected initial result: FAIL because helper and panels do not exist.
- [ ] Implement `templateEditPropagation.ts`.
- [ ] Implement `TemplateBlockPanels.tsx`.
- [ ] Replace minimal fixed-text-only UI in `ChapterTemplateForm.tsx` with the six block panels.
- [ ] Update `ProjectTemplateWorkbench.tsx` so successful block save invalidates `["project-template-instance", projectId]`, `["project-template-preview", instanceId]`, and relevant authoring queries for drafts/charts.
- [ ] Show save impact banner from API response.
- [ ] Rerun tests and confirm PASS.
- [ ] Commit: `git add frontend/src/modules/templates/templateEditPropagation.ts frontend/src/modules/templates/templateEditPropagation.test.ts frontend/src/modules/templates/TemplateBlockPanels.tsx frontend/src/modules/templates/ChapterTemplateForm.tsx frontend/src/modules/templates/ProjectTemplateWorkbench.tsx frontend/src/lib/api.ts frontend/src/modules/templates/ProjectTemplateWorkbench.test.tsx && git commit -m "Add editable template block panels"`

### Task 15: Refresh Template Preview From Latest Saved Blocks

**Files:**
- Modify: `backend/tender_backend/api/project_template_instances.py`
- Modify: `backend/tender_backend/services/template_service/docx_renderer.py`
- Modify: `frontend/src/modules/templates/TemplatePreviewPane.tsx`
- Modify: `frontend/src/modules/templates/ProjectTemplateWorkbench.tsx`
- Test: `frontend/src/modules/templates/ProjectTemplateWorkbench.test.tsx`
- Test: `backend/tests/integration/test_project_template_instances_api.py`

- [ ] Write failing backend test that preview reflects saved fixed text, table definition, asset placeholder, chart prompt marker, and page format.
- [ ] Write failing frontend test that right preview updates after saving fixed text.
- [ ] Run:

```bash
cd backend && ../.venv/bin/pytest tests/integration/test_project_template_instances_api.py -q
cd frontend && npx vitest run src/modules/templates/ProjectTemplateWorkbench.test.tsx
```

- [ ] Expected initial result: FAIL because preview is currently structural and not tied to all block types.
- [ ] Update preview endpoint to include `template_revision_no`, `pages`, and block render markers.
- [ ] Update `TemplatePreviewPane.tsx` to render fixed text, table preview, asset placeholder chips, AI prompt marker, chart prompt/code marker, and page/header/footer markers.
- [ ] Refresh preview after save without requiring full page reload.
- [ ] Rerun tests and confirm PASS.
- [ ] Commit: `git add backend/tender_backend/api/project_template_instances.py backend/tender_backend/services/template_service/docx_renderer.py frontend/src/modules/templates/TemplatePreviewPane.tsx frontend/src/modules/templates/ProjectTemplateWorkbench.tsx backend/tests/integration/test_project_template_instances_api.py frontend/src/modules/templates/ProjectTemplateWorkbench.test.tsx && git commit -m "Refresh template preview from saved blocks"`

### Task 16: Surface Stale Template Warnings In Bid Authoring

**Files:**
- Modify: `frontend/src/modules/authoring/EditorContent.tsx`
- Modify: `frontend/src/modules/authoring/EditorContent.test.tsx`
- Modify: `frontend/src/lib/api.ts`

- [ ] Write failing tests that stale drafts show `模板已更新，需重新生成正文`.
- [ ] Write failing tests that stale chart assets show `模板已更新，需重新生成图表`.
- [ ] Write failing tests that regenerate buttons call the correct API.
- [ ] Run: `cd frontend && npx vitest run src/modules/authoring/EditorContent.test.tsx`
- [ ] Expected initial result: FAIL because template-stale fields/actions are not surfaced.
- [ ] Add stale-template fields to draft and chart asset frontend types.
- [ ] Add stale banners next to affected chapter drafts and chart task cards.
- [ ] Add explicit regeneration actions: `按新模板重新生成正文`, `按新模板重新生成图表`, `重新渲染本章`.
- [ ] Invalidate authoring queries after regeneration succeeds.
- [ ] Rerun tests and confirm PASS.
- [ ] Commit: `git add frontend/src/lib/api.ts frontend/src/modules/authoring/EditorContent.tsx frontend/src/modules/authoring/EditorContent.test.tsx && git commit -m "Show template-stale warnings in authoring"`

### Task 17: End-To-End Verification

**Files:**
- Modify as needed:
  - `backend/tests/integration/test_project_template_instances_api.py`
  - `frontend/src/modules/templates/ProjectTemplateWorkbench.test.tsx`
  - `frontend/src/modules/projects/ProjectsModule.test.tsx`
  - `frontend/src/modules/authoring/EditorContent.test.tsx`
  - `frontend/src/modules/export/ExportGateContent.test.tsx`

- [ ] Run backend targeted suite:

```bash
cd backend && ../.venv/bin/pytest \
  tests/unit/test_project_template_instance_service.py \
  tests/unit/test_template_directory_reconciliation_service.py \
  tests/unit/test_template_edit_propagation_service.py \
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
  src/modules/templates/templateEditPropagation.test.ts \
  src/modules/templates/ProjectTemplateWorkbench.test.tsx \
  src/modules/projects/ProjectsModule.test.tsx \
  src/modules/authoring/EditorContent.test.tsx \
  src/modules/export/ExportGateContent.test.tsx
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
- [ ] Operators can freely reorder project template chapters by mouse drag-and-drop in the template adjustment page, including moving original Chapter 5 to the Chapter 7 position, with persisted order, renumbered display, and revision audit trail.
- [ ] The template adjustment UI is form-based for tender engineers.
- [ ] Header, footer, page break, page format, fixed text, table definition, AI prompt, chart prompt/code, variables, material placeholders, seal/signature marks, and pricing attachment boundaries are explicit template blocks.
- [ ] Editing fixed text saves to the project template instance and refreshes preview.
- [ ] Editing table definition saves to the project template instance and refreshes preview.
- [ ] Editing asset placeholders saves to the project template instance and refreshes preview.
- [ ] Editing AI prompts marks existing generated text stale.
- [ ] Editing chart prompts/code marks existing chart assets stale.
- [ ] Editing page format marks DOCX render/export artifacts stale.
- [ ] Existing generated bid content is never silently overwritten by template saves.
- [ ] Authoring shows stale-template warnings and explicit regeneration actions.
- [ ] Export is blocked while stale-template artifacts remain.
- [ ] Regeneration/rerender clears stale markers only for artifacts actually regenerated or rerendered.
- [ ] 答疑/补遗/澄清 can trigger incremental reconciliation against the confirmed project template instance, and critical impacts cannot be silently skipped.
- [ ] Every non-stale required tender requirement has a `project_requirement_response` row and a resolved status before generation/export.
- [ ] Required seal/signature marks are visible in preview and appear in a pre-submission checklist.
- [ ] Format profile and seal unit data are persisted on the project template instance even if advanced DOCX styling is implemented later.
- [ ] Chapter edit locking prevents two users from overwriting the same project template chapter.
- [ ] `project.submission_deadline` participates in final lock/export gating without adding a duplicate deadline field.
- [ ] Bid generation uses the confirmed project template instance.
- [ ] Review failures can route users to the right workspace.
- [ ] Project-specific template improvements can be proposed back to global templates without automatic global mutation.
- [ ] All backend and frontend targeted tests pass.

## Risk Controls

- [ ] Prevent global template pollution by making project template instances the default edit target.
- [ ] Prevent workflow drift by keeping `upload -> parse -> requirements -> template -> editor` as the only primary forward path for new projects.
- [ ] Prevent low-quality generation by blocking generation when critical template reconciliation issues, unanswered requirements, or pending required seal confirmations are unresolved.
- [ ] Prevent template/content confusion by adding review issue source classification.
- [ ] Prevent silent data loss by never overwriting generated content after template saves; force explicit regeneration/rerender.
- [ ] If an edit affects only preview/rendering, do not force AI regeneration.
- [ ] If an edit affects AI or chart prompts, do not silently rerun AI; require explicit user action.
- [ ] Prevent form complexity from overwhelming tender engineers by collapsing AI prompt advanced controls by default.
- [ ] Preserve auditability with revision snapshots for every template confirmation, manual drag-and-drop chapter reorder, clarification reconciliation, seal checklist confirmation, and reconciliation apply action.
- [ ] Keep pricing/BOQ out of this plan except for explicit external attachment boundaries; do not half-build a formula engine inside template blocks.

## Tracking Notes

- Use this plan as the checklist source of truth.
- Each task should land in a separate commit.
- Do not merge project template instance changes back to global templates without an explicit promotion proposal and approval step.
- Keep the existing global template package APIs stable for imported template management.
- Keep the existing authoring workspace usable for legacy projects that do not yet have project template instances.
