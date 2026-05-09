# AI Chart Generation And DOCX Injection Implementation Plan

**Date:** 2026-05-09

**Status:** Approved architecture plan, review feedback incorporated, pending implementation.

**Goal:** Add traceable AI-assisted chart generation for tender bid documents. AI produces structured chart specs only; the tender system validates, renders SVG/PNG through Mermaid or native renderers, stores chart assets, and injects approved charts into DOCX templates at explicit placeholders.

---

## Tracking Legend

- `[ ]` Not started
- `[~]` In progress
- `[x]` Completed
- `[!]` Blocked or needs product decision

---

## Scope Decisions Already Confirmed

- [x] AI must not generate executable drawing code for backend execution.
- [x] AI output is a structured JSON chart spec.
- [x] Mermaid is the primary renderer for flow, organization, system, emergency, and Gantt-style charts.
- [x] Matrix-style charts use native system rendering because Mermaid layout control is weak for tender tables/matrices.
- [x] DOCX injection should use PNG fallback first for Word compatibility, while preserving SVG as the canonical rendered asset.
- [x] Chart assets must be traceable, reviewable, and reusable through `chart_asset`.

---

## Target Architecture

```text
chapter/template requires chart
        ↓
build chart generation context
        ↓
AI Gateway returns strict chart spec JSON
        ↓
ChartGenerationService validates and normalizes spec
        ↓
choose renderer by chart_type
        ↓
MermaidRenderer or NativeSvgRenderer
        ↓
persist spec_json, mermaid_source, rendered_svg, rendered_png_path, status
        ↓
ChartAssetInjector replaces {{chart:*}} placeholders during DOCX export
```

Existing code to extend:

- `backend/tender_backend/services/chart_generation_service.py`
- `backend/tender_backend/api/charts.py`
- `backend/tender_backend/services/export_service/docx_exporter.py`
- `backend/tender_backend/services/export_service/equipment_table_injector.py`
- `backend/tender_backend/services/template_service/docx_renderer.py`
- `frontend/src/modules/authoring/EditorContent.tsx`
- `frontend/src/lib/api.ts`

Migration note:

- Do not modify existing migration `0038_bid_workflow_generation_review_assets.py`; applied migrations are immutable. Add a new migration, expected next file `backend/tender_backend/db/alembic/versions/0042_chart_asset_columns.py`.

---

## Supported Chart Types

MVP support:

- [ ] `construction_flow`: Mermaid flowchart.
- [ ] `org_chart`: Mermaid flowchart.
- [ ] `quality_system`: Mermaid flowchart.
- [ ] `safety_system`: Mermaid flowchart.
- [ ] `emergency_org`: Mermaid flowchart.
- [ ] `schedule_gantt`: Mermaid gantt.
- [ ] `risk_matrix`: native SVG renderer.
- [ ] `responsibility_matrix`: DOCX table or native SVG renderer.

Future candidates:

- [ ] scoring response matrix.
- [ ] milestone timeline.
- [ ] resource allocation chart.
- [ ] material/equipment mobilization flow.

---

## Data Contract

### Flow-Like Chart Spec

AI returns JSON similar to:

```json
{
  "chart_type": "construction_flow",
  "title": "施工流程图",
  "placeholder_key": "construction_flow_main",
  "direction": "TB",
  "nodes": [
    {"id": "prepare", "label": "施工准备"},
    {"id": "survey", "label": "现场勘察"},
    {"id": "install", "label": "设备安装"}
  ],
  "edges": [
    {"from": "prepare", "to": "survey"},
    {"from": "survey", "to": "install"}
  ]
}
```

Used by:

- `construction_flow`
- `org_chart`
- `quality_system`
- `safety_system`
- `emergency_org`

### Gantt Chart Spec

Used by `schedule_gantt`:

```json
{
  "chart_type": "schedule_gantt",
  "title": "施工进度计划图",
  "placeholder_key": "schedule_gantt_main",
  "date_format": "YYYY-MM-DD",
  "tasks": [
    {"id": "prepare", "label": "施工准备", "start": "2026-06-01", "end": "2026-06-05", "group": "准备阶段"},
    {"id": "install", "label": "设备安装", "start": "2026-06-06", "end": "2026-06-20", "group": "施工阶段"}
  ],
  "dependencies": [
    {"from": "prepare", "to": "install"}
  ]
}
```

### Risk Matrix Spec

Used by `risk_matrix`:

```json
{
  "chart_type": "risk_matrix",
  "title": "项目风险矩阵",
  "placeholder_key": "risk_matrix_main",
  "rows": ["低影响", "中影响", "高影响"],
  "columns": ["低概率", "中概率", "高概率"],
  "cells": [
    {"row": "高影响", "column": "中概率", "items": ["工期延误"], "level": "high"},
    {"row": "中影响", "column": "低概率", "items": ["材料供应波动"], "level": "medium"}
  ]
}
```

### Responsibility Matrix Spec

Used by `responsibility_matrix`:

```json
{
  "chart_type": "responsibility_matrix",
  "title": "职责分工矩阵",
  "placeholder_key": "responsibility_matrix_main",
  "roles": ["项目经理", "技术负责人", "安全负责人"],
  "activities": ["施工准备", "技术交底", "安全检查"],
  "assignments": [
    {"role": "项目经理", "activity": "施工准备", "level": "负责"},
    {"role": "技术负责人", "activity": "技术交底", "level": "负责"},
    {"role": "安全负责人", "activity": "安全检查", "level": "负责"}
  ]
}
```

### Validation Rules

- [ ] `chart_type` must be in the supported whitelist.
- [ ] `placeholder_key` must be unique per project when present.
- [ ] Node ids must use safe ASCII identifiers.
- [ ] Labels must be plain text; no HTML/script/style.
- [ ] Node count, edge count, task count, row count, column count, assignment count, and text lengths must have hard limits.
- [ ] Edges must reference existing nodes.
- [ ] Gantt tasks must have parseable dates and `end >= start`.
- [ ] Matrix values must be selected from allowed labels or normalized by the system.
- [ ] Invalid specs must not be approved or injected into formal DOCX exports.

### Persistence Strategy

Add a light migration instead of hiding query-critical fields in JSONB:

```sql
ALTER TABLE chart_asset
  ADD COLUMN IF NOT EXISTS placeholder_key TEXT,
  ADD COLUMN IF NOT EXISTS mermaid_source TEXT,
  ADD COLUMN IF NOT EXISTS rendered_png_path TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_chart_asset_project_placeholder
  ON chart_asset(project_id, placeholder_key)
  WHERE placeholder_key IS NOT NULL;
```

Core data:

```text
chart_asset.spec_json
chart_asset.rendered_svg
chart_asset.rendered_path
chart_asset.rendered_png_path
chart_asset.placeholder_key
chart_asset.mermaid_source
chart_asset.status
chart_asset.metadata_json.source_kind
chart_asset.metadata_json.render_engine
chart_asset.metadata_json.validation
chart_asset.metadata_json.approved_by
chart_asset.metadata_json.approved_at
chart_asset.metadata_json.stale_reason
chart_asset.metadata_json.source_context
```

`placeholder_key`, `mermaid_source`, and `rendered_png_path` are first-class data because they are used for lookup, rerendering, and DOCX injection. Validation, approval audit, renderer metadata, and stale diagnostics can remain in `metadata_json`.

---

## Caption And Numbering Contract

Formal tender documents require chart captions such as `图8-1 项目管理组织机构图`.

- [ ] Add caption data to chart specs or derived metadata: `caption_title`, `caption_prefix`, `chapter_code`, and optional `figure_no`.
- [ ] Default caption title to `chart_asset.title`.
- [ ] Generate figure numbers as `图<chapter-number>-<sequence>` when the chart is tied to a bid chapter.
- [ ] Use a project-level/chapter-level sequence computed during DOCX injection, unless `figure_no` is explicitly fixed by a template or user approval.
- [ ] Insert a centered caption paragraph adjacent to the image, preferably below the figure unless template rules specify otherwise.
- [ ] Apply a consistent caption style: centered, Chinese font compatible with the document, smaller than body text.
- [ ] Keep caption generation idempotent so rerendering or reinjecting does not duplicate captions.
- [ ] Add tests for captions, numbering order, chapter-scoped numbering, explicit figure number override, and no duplicate caption on repeated injection.

---

## File Map

Likely backend files to create:

- `backend/tender_backend/db/alembic/versions/0042_chart_asset_columns.py`: first-class placeholder and render-output columns.
- `backend/tender_backend/services/chart_service/specs.py`: pydantic chart spec models and validation helpers.
- `backend/tender_backend/services/chart_service/renderers/base.py`: renderer protocol and render result type.
- `backend/tender_backend/services/chart_service/renderers/mermaid.py`: JSON spec to Mermaid source and SVG/PNG rendering.
- `backend/tender_backend/services/chart_service/renderers/native_svg.py`: risk matrix and responsibility matrix SVG rendering.
- `backend/tender_backend/services/chart_service/svg_sanitizer.py`: SVG safety cleanup.
- `backend/tender_backend/services/chart_service/png_converter.py`: SVG to PNG conversion for DOCX.
- `backend/tender_backend/services/chart_service/captions.py`: figure numbering and caption paragraph helpers.
- `backend/tender_backend/services/export_service/chart_asset_injector.py`: DOCX placeholder replacement.
- `backend/tender_backend/db/repositories/chart_asset_repo.py`: chart asset queries, update, approval, lookup by placeholder.
- `backend/tests/unit/test_chart_spec_validation.py`
- `backend/tests/unit/test_mermaid_chart_renderer.py`
- `backend/tests/unit/test_native_svg_chart_renderer.py`
- `backend/tests/unit/test_chart_caption_numbering.py`
- `backend/tests/unit/test_chart_asset_injector.py`

Likely backend files to modify:

- `backend/tender_backend/services/chart_generation_service.py`: orchestrate validation, rendering, persistence, approval state.
- `backend/tender_backend/api/charts.py`: add generate, rerender, approve, lookup, and preview endpoints.
- `backend/tender_backend/services/export_service/docx_exporter.py`: invoke `ChartAssetInjector`.
- `backend/tender_backend/services/template_service/docx_renderer.py`: support chart injection for template-item DOCX renders if needed.
- `backend/tender_backend/services/technical_bid_writer.py`: request chart generation for chart-worthy chapters.
- `backend/tender_backend/services/bid_chapter_generation.py`: include chart placeholder guidance in generated chapter drafts only where relevant.
- `backend/tender_backend/workflows/export_bid.py`: add formal export gate for unapproved chart assets if placeholders exist.
- `backend/pyproject.toml`: add renderer/converter dependencies if needed.
- `backend/Dockerfile`: add only image conversion dependencies needed by the backend if Mermaid uses sidecar.
- `infra/docker-compose.yml`: add Mermaid render sidecar service.
- `infra/.env.example`: add Mermaid render service URL and timeout settings.

Likely frontend files to modify:

- `frontend/src/lib/api.ts`: chart generation, approval, rerender, and supported-type APIs.
- `frontend/src/modules/authoring/EditorContent.tsx`: improve chart list and preview entry point.
- `frontend/src/modules/authoring/ChartAssetPanel.tsx`: chart list, SVG preview, status, placeholder key, approve/rerender actions.
- `frontend/src/modules/export/ExportGateContent.tsx`: show missing/unapproved chart blocking status.

---

## Phase 1: Chart Spec Contract And Validation

**Objective:** Make AI chart output deterministic, bounded, and auditable before adding Mermaid execution.

- [ ] Create chart spec models for flow-like charts, Gantt charts, risk matrix, and responsibility matrix.
- [ ] Add explicit examples and schema tests for flow-like charts, Gantt charts, risk matrix, and responsibility matrix.
- [ ] Implement normalization for ids, directions, labels, matrix axes, and placeholder keys.
- [ ] Enforce limits for nodes, edges, tasks, rows, columns, assignments, label length, and total rendered text.
- [ ] Reject unsafe characters and markup in user/AI-provided text.
- [ ] Preserve validation result in `metadata_json.validation`.
- [ ] Prototype prompt output against target models early, with mocked or manual DeepSeek/Qwen responses, to confirm schema shape is realistic before renderer work hardens around it.
- [ ] Add unit tests for valid specs, unsupported chart types, unsafe labels, dangling edges, excessive nodes, and invalid matrices.
- [ ] Acceptance: invalid AI output cannot produce an approved chart asset; valid specs produce stable normalized JSON.

---

## Phase 2: Mermaid Rendering

**Objective:** Render flow, organization, system, emergency, and Gantt charts through Mermaid while keeping source generated by the system.

- [ ] Implement `MermaidSourceBuilder` from normalized spec to Mermaid DSL.
- [ ] Use a Mermaid sidecar container as the default deployment model to avoid adding Puppeteer/Chromium weight to the backend image.
- [ ] Add sidecar API contract: render Mermaid source to SVG/PNG with timeout, size limit, and no external network dependency.
- [ ] Add render timeout, input-size limit, and no-network execution policy.
- [ ] Ensure sidecar image installs Chinese fonts such as Noto Sans CJK so headless Chromium renders Chinese labels correctly.
- [ ] Sanitize rendered SVG before persistence.
- [ ] Generate PNG fallback for DOCX insertion.
- [ ] Store Mermaid source in `chart_asset.mermaid_source`.
- [ ] Store renderer identity/version in `metadata_json.render_engine`.
- [ ] Add tests for construction flow, org chart, quality system, safety system, emergency org, and Gantt source generation.
- [ ] Acceptance: each Mermaid-backed chart type produces sanitized SVG and PNG fallback from the same spec.

---

## Phase 3: Native SVG Matrix Rendering

**Objective:** Render tender matrix charts with stable, document-friendly layout.

- [ ] Implement `RiskMatrixSvgRenderer`.
- [ ] Implement `ResponsibilityMatrixRenderer`.
- [ ] Use fixed tender document styling: readable Chinese font stack, restrained colors, consistent line widths, and predictable margins.
- [ ] Add text wrapping and max-cell overflow handling.
- [ ] Add deterministic canvas sizing based on row/column counts.
- [ ] Convert native SVG output to PNG fallback.
- [ ] Add tests for 3x3 risk matrix, sparse matrix, long labels, empty cells, and responsibility values.
- [ ] Acceptance: matrix charts remain legible and stable under realistic tender labels and can be inserted into DOCX.

---

## Phase 4: Chart Asset Persistence And APIs

**Objective:** Make generated charts reviewable and reusable from backend and frontend.

- [ ] Add migration `0042_chart_asset_columns.py` with `placeholder_key`, `mermaid_source`, `rendered_png_path`, and unique project placeholder index.
- [ ] Add repository methods to create, update, list, lookup by placeholder, approve, and rerender chart assets.
- [ ] Extend `/api/projects/{project_id}/chart-assets` with generation metadata.
- [ ] Add endpoint to generate chart spec from AI context.
- [ ] Add endpoint to rerender an existing spec.
- [ ] Add endpoint to approve or mark chart as needing review.
- [ ] Add endpoint to fetch rendered SVG or PNG safely.
- [ ] Link charts to chapters through `outline_node_id` where possible and preserve source context in metadata.
- [ ] Mark associated charts stale when source chapter content, mapped requirements, or source context changes.
- [ ] Define regeneration behavior: create a new chart version by default; allow explicit replacement only for unapproved drafts.
- [ ] Require project access on every chart endpoint.
- [ ] Add tests for access control, create/update, approval, placeholder lookup, and missing chart handling.
- [ ] Acceptance: a project can hold multiple chart assets with statuses, placeholder keys, specs, and rendered outputs.

---

## Phase 5: AI Spec Generation

**Objective:** Let AI propose chart specs from tender context without controlling rendering code.

- [ ] Add chart-generation prompt templates with strict JSON-only output.
- [ ] Build chart context from project facts, confirmed requirements, bid chapter outline, selected equipment/personnel, and chapter draft where available.
- [ ] Add JSON parsing and schema validation with repair/retry only for schema-level failures.
- [ ] Mark low-confidence or partially repaired specs as `needs_review`.
- [ ] Add generation run metadata: model, prompt version, source context ids, and validation result.
- [ ] Add tests using mocked AI Gateway responses for valid JSON, malformed JSON, unsafe content, and incomplete specs.
- [ ] Acceptance: AI can propose chart specs, but backend validation decides whether they become draft assets or review-needed assets.

---

## Phase 6: DOCX Placeholder Injection

**Objective:** Replace template placeholders with approved chart images during DOCX rendering/export.

- [ ] Define placeholder syntax: `{{chart:<placeholder_key_or_chart_type>}}`.
- [ ] Implement `ChartAssetInjector` modeled after `EquipmentTableInjector`, with the minimal repository lookup needed for end-to-end DOCX insertion.
- [ ] Replace matching paragraph with chart image.
- [ ] Add caption paragraph after the inserted image using `图<chapter-number>-<sequence> <title>` unless an explicit figure number is already set.
- [ ] Apply centered caption formatting and a stable document style.
- [ ] Compute chapter-scoped chart numbering deterministically during injection.
- [ ] Avoid duplicate captions if an existing template caption is intentionally present.
- [ ] Prefer approved chart by placeholder key; fallback to latest approved chart by `chart_type` only when unambiguous.
- [ ] Support preview mode with draft charts; formal mode requires approved charts.
- [ ] Add useful error messages for missing, ambiguous, unrendered, or unapproved charts.
- [ ] Invoke injector from `render_docx` after template rendering and before final save.
- [ ] Invoke injector from plain DOCX flow if generated drafts include chart placeholders.
- [ ] Add integration tests that create a DOCX with chart placeholders and verify images are embedded.
- [ ] Acceptance: DOCX templates containing chart placeholders export with chart images in the correct positions.

---

## Phase 7: Export Gate And Review Flow

**Objective:** Prevent formal exports from silently omitting or inserting unreviewed charts.

- [ ] Detect chart placeholders in rendered DOCX templates or in generation context before export.
- [ ] Block formal export when a required chart is missing, unrendered, or not approved.
- [ ] Allow preview export to include draft charts with metadata-visible status in export result.
- [ ] Add review issue or export preflight warning for missing chart assets.
- [ ] Add tests for formal export blocked by missing chart, formal export blocked by draft chart, and preview export allowed.
- [ ] Acceptance: formal bid export includes only approved charts or fails with actionable diagnostics.

---

## Phase 8: Frontend Chart Review MVP

**Objective:** Give users enough UI to inspect, regenerate, approve, and place charts.

- [ ] Add chart asset panel to authoring workspace.
- [ ] Show chart type, title, status, placeholder key, and created/updated time.
- [ ] Render SVG preview safely.
- [ ] Add approve and rerender actions.
- [ ] Show validation issues from `metadata_json.validation`.
- [ ] Show copyable placeholder text, for example `{{chart:construction_flow_main}}`.
- [ ] Add export gate display for missing/unapproved charts.
- [ ] Acceptance: users can review chart assets and understand exactly which template placeholder each chart will fill.

---

## Phase 9: Documentation And Operational Readiness

**Objective:** Make renderer dependencies, fallback behavior, and failure modes explicit.

- [ ] Document Mermaid renderer installation and runtime requirements.
- [ ] Document the Mermaid sidecar container contract and explain why it is preferred over embedding Puppeteer/Chromium in the backend image.
- [ ] Document Chinese font requirements for Mermaid/Chromium rendering.
- [ ] Document SVG to PNG conversion dependency.
- [ ] Document placeholder syntax and supported chart types.
- [ ] Document chart caption and figure-numbering rules.
- [ ] Document formal-vs-preview export behavior.
- [ ] Add troubleshooting notes for Mermaid render failures, missing PNG converter, malformed specs, and unsupported chart types.
- [ ] Add sample chart specs under docs or tests.
- [ ] Acceptance: a developer can set up local rendering and verify DOCX chart injection using documented commands and fixtures.

---

## MVP Acceptance Criteria

- [ ] System can generate or accept structured specs for at least `construction_flow`, `org_chart`, and `risk_matrix`.
- [ ] Same spec can be re-rendered into stable SVG.
- [ ] SVG and PNG fallback are persisted or discoverable for each rendered chart.
- [ ] `chart_asset` records include spec, rendered output, status, validation metadata, and placeholder identity.
- [ ] DOCX templates with `{{chart:*}}` placeholders are exported with inserted chart images.
- [ ] Inserted chart images include formal captions and deterministic figure numbers.
- [ ] Formal export blocks missing/unapproved required chart assets.
- [ ] Frontend can preview and approve chart assets.
- [ ] Unit tests cover spec validation, Mermaid source generation, native SVG rendering, caption numbering, and DOCX injection.

---

## Risks And Mitigations

- [ ] Mermaid CLI/runtime dependency may complicate deployment.
  Mitigation: use a Mermaid sidecar container by default. Avoid embedding Puppeteer/Chromium in the backend image. External APIs such as mermaid.ink are not suitable for internal/offline deployments.
- [ ] Headless Mermaid rendering may miss Chinese fonts.
  Mitigation: install Noto Sans CJK or equivalent fonts in the Mermaid sidecar and include a smoke test with Chinese labels.
- [ ] Word SVG compatibility is inconsistent.
  Mitigation: insert PNG fallback into DOCX while preserving SVG as the canonical asset.
- [ ] AI may produce invalid or verbose chart specs.
  Mitigation: strict schema validation, bounded limits, and `needs_review` status.
- [ ] Matrix labels may overflow fixed cells.
  Mitigation: native renderer must implement wrapping, row-height expansion, and max-size warnings.
- [ ] Ambiguous placeholders can inject the wrong chart.
  Mitigation: prefer unique `placeholder_key`; allow chart-type fallback only when one approved asset exists.
- [ ] Formal exports could skip placeholders silently.
  Mitigation: add export preflight/gate checks and integration tests.
- [ ] Figure numbers could drift when templates are edited.
  Mitigation: compute numbering during final injection and keep explicit overrides visible in chart metadata.

---

## Suggested Implementation Order

1. [ ] Spec models and validation.
2. [ ] Mermaid source builder and renderer integration.
3. [ ] SVG to PNG conversion.
4. [ ] DOCX `ChartAssetInjector` with captions and numbering.
5. [ ] Chart asset repository/API updates.
6. [ ] Native SVG matrix renderers.
7. [ ] AI spec generation.
8. [ ] Export gate checks.
9. [ ] Frontend review panel.
10. [ ] Documentation and deployment notes.

---

## Review Feedback Incorporated

- [x] Added formal chart caption and `图<chapter>-<sequence>` numbering requirements.
- [x] Added separate flow, Gantt, risk matrix, and responsibility matrix spec examples.
- [x] Replaced JSONB-only persistence with a new `0042` migration for `placeholder_key`, `mermaid_source`, and `rendered_png_path`.
- [x] Removed any implication that existing migration `0038` should be modified.
- [x] Adjusted implementation order to prove Mermaid to PNG to DOCX earlier.
- [x] Chose Mermaid sidecar as the default deployment model and documented Chinese font requirements.
- [x] Added chart stale/version lifecycle requirements.
- [x] Added early AI prompt/schema prototype validation in Phase 1.
