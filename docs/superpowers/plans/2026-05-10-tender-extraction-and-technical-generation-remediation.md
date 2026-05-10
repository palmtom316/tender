# Tender Extraction Focus And Technical Bid Generation Remediation Plan

**Date:** 2026-05-10

**Status:** Root-cause remediation plan, implementation in progress.

**Goal:** Fix the current tender analysis and technical bid generation workflow so the system extracts only bid-writing-relevant constraints, removes pricing noise, preserves confirmed priorities, follows the user-provided business/technical bid directory templates unless the tender documents explicitly conflict with them, generates substantial SGCC technical-bid chapters, and uses chart assets as first-class chapter content instead of optional manual decorations.

**Root-Cause Basis:** This plan is based on the code review of:

- `backend/tender_backend/services/extract_service/ai_requirements_extractor.py`
- `backend/tender_backend/services/extract_service/requirements_extractor.py`
- `backend/tender_backend/services/requirement_grouping_service.py`
- `backend/tender_backend/services/tender_constraint_service.py`
- `backend/tender_backend/services/bid_outline_planner.py`
- `backend/tender_backend/services/bid_chapter_generation.py`
- `backend/tender_backend/services/technical_bid_writer.py`
- `backend/tender_backend/services/chart_generation_service.py`
- `backend/tender_backend/services/export_service/chart_asset_injector.py`
- `backend/tender_backend/services/business_bid_assembler.py`
- `backend/tender_backend/services/compliance_check_service.py`
- `backend/tender_backend/services/delivery_package.py`
- `backend/tender_backend/services/review_service/compliance_matrix.py`
- `backend/tender_backend/workflows/generate_section.py`
- `backend/tender_backend/api/exports.py`
- `frontend/src/modules/authoring/EditorContent.tsx`
- `frontend/src/modules/authoring/RequirementsContent.tsx`
- `frontend/src/modules/export/ExportGateContent.tsx`
- `frontend/src/lib/api.ts`

---

## Tracking Legend

- `[ ]` Not started
- `[~]` In progress
- `[x]` Completed
- `[!]` Blocked or needs product decision
- `P0` Critical path for the first releasable remediation slice
- `P1` First-version enhancement after P0 is stable
- `P2` Follow-up hardening or broader workflow polish

---

## Review Verification Addendum

The review report at `/Users/palmtom/Projects/tender/docs/superpowers/reports/2026-05-10-tender-extraction-and-technical-generation-remediation-review.md` was verified against the current branch. The reported gaps are valid and are incorporated into this plan:

- Phase 1 acceptance is a one-way invariant: rule fallback must not produce a broader active set than the scoped AI/policy path. AI and deterministic rules do not need byte-for-byte identical decisions.
- Constraint subtype storage is `tender_constraint_item.constraint_subtype`; `project_requirement.category` remains backward-compatible, and metadata keeps trace/details only.
- Template conflicts can only be triggered by deterministic, rule-based signals: missing mandatory attachment/section, explicit separate-volume/separate-seal/submission-order anchors, or uncovered veto/rejection clauses. AI may draft the explanation, but it cannot trigger the override.
- Phase 7 deterministic fallback is the Phase 6 strategy renderer with no AI call. There must not be a second independent fallback skeleton.
- Legacy exception is explicit project metadata: `project.metadata_json.legacy_pre_constraint_set = true`, set by backfill only and surfaced in UI as a legacy status.
- Rollback policy uses `EXTRACTION_SCOPE_POLICY=strict|legacy`; persisted markers are `scoped_v1` and `legacy_v0`.
- Bid bond amount is submission-readiness/checklist metadata only. It is not an active writing constraint unless the text also contains signature, seal, format, deadline, validity, or submission obligations.
- Chart behavior defaults to strategy-generated placeholders and draft chart assets; formal export requires approval only for referenced charts.
- `CATEGORY_CHAPTER` must be removed from non-legacy outline mapping. Legacy projects may use a separate, explicit compatibility path only.
- Technical chapter strategies live under `backend/tender_backend/services/technical_chapter_strategies/*.py` so strategy rendering is versioned and unit-testable.

---

## Problem Statement

Current behavior is structurally biased toward noisy extraction and thin generation:

- The extraction prompt asks for broad requirements and still outputs pricing-related requirements, even though tender does not handle pricing.
- Requirement grouping collapses quality, schedule, safety, construction method, personnel, and SGCC-specific technical obligations into coarse buckets.
- A versioned `tender_constraint_set` exists, but outline planning and chapter generation still read raw `project_requirement` rows.
- Template-vs-tender precedence is not explicit enough: the user-provided business/technical bid directory templates should be executed by default, and only explicit tender-document conflicts should modify them.
- Technical chapter generation is deterministic requirement echoing, not chapter writing.
- Tender facts, scoring criteria, standard clauses, company assets, personnel/equipment selections, and chart assets are available in the system but are not assembled into chapter-level writing context.
- Chart generation exists as backend infrastructure, but technical chapters do not automatically request chart assets or insert chart placeholders.
- Multiple downstream services still read raw `project_requirement` rows directly, including business assembly, compliance checks, compliance matrix, submission checklist, delivery package traceability, and older workflow steps.
- Compatibility endpoints and legacy workflows can still bypass the intended AI extraction and confirmed-constraint workflow.
- Export gates expose chart approval from the backend, but frontend types and UI do not show it; backend format gate is still a hard-coded pass.
- Template package rendering catches item-level failures and returns a partial package, but final export/delivery does not consistently elevate failed required template items to blocking issues.

---

## Full-Project Review Addendum

Additional issues found during implementation-prep review:

- [x] `backend/tender_backend/api/tender_documents.py` still has a synchronous compatibility requirement extraction path that calls rule-based `extract_requirements_from_source_chunks`; it must be aligned with the new scoped extraction policy or deprecated behind a compatibility flag.
- [x] `backend/tender_backend/workflows/generate_section.py` still contains placeholder outline/content generation and writes `uuid4().hex`; it must not be used as a production generation path until replaced or disabled.
- [~] `backend/tender_backend/services/business_bid_assembler.py` builds missing materials and response matrix from raw requirements; it must consume confirmed constraints.
- [~] `backend/tender_backend/services/compliance_check_service.py`, `submission_checklist_service.py`, `delivery_package.py`, and `review_service/compliance_matrix.py` still evaluate raw requirements; they must consume confirmed constraints and conflict decisions.
- [x] `backend/tender_backend/api/exports.py` blocks on every unapproved chart asset, not only referenced chart placeholders; it also returns `format_passed=true` without running a real format check.
- [x] `frontend/src/lib/api.ts` omits `charts_approved` and `unapproved_chart_count` from `ExportGates`, so `ExportGateContent` cannot show the chart gate.
- [x] `frontend/src/modules/authoring/EditorContent.tsx` exposes "重新规划目录", which conflicts with the template-first rule unless renamed and guarded as conflict-aware remapping.
- [ ] `frontend/src/modules/authoring/EditorContent.tsx` only creates a hard-coded organization chart and does not expose `generateChartAsset()` or chart types needed by quality, safety, schedule, risk, and responsibility chapters.
- [ ] `frontend/src/modules/authoring/RequirementsContent.tsx` can bulk-confirm requirement packages, but it does not make a confirmed constraint set the visible and required next-step artifact before outline/generation.
- [~] Template package rendering returns partial success with failed items; required template item failures must be visible and block final export/delivery.

---

## Target Outcomes

- [~] Tender analysis output is a short, prioritized, bid-writing-oriented constraint set.
- [x] Pricing-only and cost/commercial quotation content is ignored by default and never blocks drafting or export.
- [~] Business constraints focus on qualification, performance, legal/validity, evidence, and submission format.
- [x] Technical constraints focus on personnel quantity/qualification, quality targets, progress targets, safety and civilized construction, SGCC construction requirements, scoring response, and mandatory technical documents.
- [~] Confirmed `tender_constraint_set` becomes the primary downstream input for outline planning, chapter generation, compliance review, and export gates.
- [ ] Business and technical bid directory templates are preserved by default; any directory change must be justified by a traceable tender-document conflict and confirmed before drafting.
- [x] Technical chapters contain structured, substantial content with measures, standards, responsibilities, inspection points, resources, process controls, risks, and innovations.
- [x] Chart assets are generated or proposed for chart-worthy chapters and inserted into drafts through `{{chart:*}}` placeholders.
- [~] Review gates verify substantive coverage, not only text presence.

---

## Scope Decisions

- [x] The first-stage product remains non-pricing. Pricing files may be archived as external attachments, but pricing content is not extracted into writing constraints.
- [x] Tender extracted requirements remain traceable, but confirmed constraint packages are the generation source of truth.
- [x] User-provided business and technical bid directory templates are authoritative by default.
- [x] If parsed tender documents conflict with the directory templates, the tender documents take precedence, but the system must present the conflict, source evidence, proposed change, and user confirmation before applying the directory change.
- [x] If there is no explicit conflict, the system must execute the existing template directory without automatic chapter add/delete/rename/reorder.
- [x] AI may propose content and chart specs, but backend validation and deterministic assembly decide what is persisted.
- [x] SGCC technical bid quality depends on domain structures: quality, schedule, safety, construction organization, personnel, equipment, standards, scoring, and charts must be explicit inputs.
- [x] Existing migrations must not be modified. Add new migrations for schema changes.

---

## Phase 1: Extraction Scope Refocus (P0)

**Objective:** Stop noisy extraction at the source and align extracted output with actual bid-writing needs.

- [x] Replace broad extraction rules with a first-stage scope policy:
  - business: qualification, performance, company certificates, legal validity, evidence, submission/signature/seal/format.
  - technical: personnel quantity and qualifications, project team roles, quality target, progress target, safety/civilized construction, SGCC technical requirements, scoring criteria, mandatory technical documents.
  - universal: veto/rejection clauses and file format requirements.
  - ignored: pricing, quotation, bill of quantities, control price, unit price, total price, bid bond amount except submission-readiness metadata.
- [x] Update `ai_requirements_extractor.py` prompt rules so pricing-only content is not output unless it contains a non-pricing hard constraint.
- [x] Remove `pricing_reference` and `报价` as positive extraction signals for writing constraints; keep them only in tender summary or external-attachment metadata.
- [x] Update `requirements_extractor.py` keyword fallback to use the same scope policy.
- [x] Align or deprecate the compatibility extraction endpoint that calls `extract_requirements_from_source_chunks` directly; it must not create a broader active requirement set than the async AI extraction workflow.
- [x] Add an extraction-mode marker to persisted requirements and constraint sets, so downstream services can reject stale legacy extraction output if it predates the new scope policy.
- [ ] Add `ignored_reason` or metadata equivalent for pricing-only and background-only dropped content so omissions remain auditable.
- [x] Add `EXTRACTION_SCOPE_POLICY=strict|legacy` with persisted `extraction_mode_marker` values `scoped_v1` and `legacy_v0`.
- [x] Add tests proving pricing-only chunks produce no active requirement, while mixed chunks preserve non-pricing qualification/personnel/format obligations.
- [x] Add tests proving sync compatibility extraction and async AI extraction agree on core pricing, qualification, personnel, safety, quality, progress, format, and veto samples where the policy is deterministic.
- [ ] Add tests proving rule fallback active decisions are a subset of scoped policy/AI active decisions and never broaden the active set.
- [ ] Acceptance: rule fallback does not broaden the active writing-constraint set; pricing-only and background-only content remains ignored under strict/scoped mode.

---

## Phase 2: Constraint Taxonomy And Priority Model (P0)

**Objective:** Replace coarse categories with a bid-writing taxonomy that can drive outline mapping and chapter writing.

- [x] Add or normalize constraint subtypes in `tender_constraint_item.constraint_subtype`:
  - `qualification_certificate`
  - `performance_threshold`
  - `personnel_count`
  - `personnel_certificate`
  - `quality_target`
  - `schedule_target`
  - `safety_civilized`
  - `sgcc_standard_compliance`
  - `construction_method`
  - `technical_scoring_response`
  - `submission_format`
  - `signature_seal`
  - `veto_rejection`
  - `mandatory_attachment`
  - `pricing_ignored`
- [~] Extend extraction schema metadata with `constraint_subtype`, `target_value`, `evidence_need`, `chapter_hint`, `severity`, and `source_confidence_reason`; on constraint-set creation, copy subtype into the physical column.
- [x] Update `requirement_grouping_service.py` so quality, schedule, safety, personnel, construction method, and SGCC standards do not collapse into one `technical` package.
- [ ] Add key-field conflict detection for personnel count, certificate grade, performance count, quality target, schedule duration, file count, file size, deadline, and signature/seal requirement.
- [x] Add tests for grouping separate quality/schedule/safety/personnel packages even when all contain generic technical words.
- [ ] Acceptance: the workbench shows short prioritized packages by engineering topic, not a flat or over-merged requirement list.

---

## Phase 3: Confirmed Constraint Set And Template Conflict Policy (P0)

**Objective:** Make user-confirmed constraints govern generation, review, and export while preserving the user-provided directory templates unless tender-document conflicts require changes.

- [x] Add repository/service methods to fetch the latest confirmed or accepted `tender_constraint_item` rows.
- [ ] Add lifecycle statuses for constraint sets: `draft`, `reviewing`, `confirmed`, `superseded`.
- [ ] Update `TenderConstraintService` to persist grouped package metadata, confirmation decisions, ignored reasons, conflict fields, and representative conclusion text.
- [ ] Add a template conflict policy: `template_default`, `tender_conflict_override`, `manual_override`.
- [ ] Detect explicit conflicts between confirmed tender constraints and the business/technical directory templates only through rule-based triggers: missing mandatory attachments/sections, "独立成册/单独密封/单独提交/按顺序装订/另册" submission anchors, uncovered veto/rejection clauses, and explicit tender-required chapter/file names absent from the template. AI may draft descriptions but must not trigger conflicts.
- [ ] For each conflict, persist source evidence, affected template chapter, proposed action, reason, and confirmation status.
- [~] Update outline planning to consume confirmed constraint items and conflict decisions instead of raw `project_requirement` rows.
- [x] Update technical chapter generation to consume confirmed constraint items and retain links back to source requirements.
- [~] Update `BusinessBidAssembler` to consume confirmed qualification/business constraints and evidence needs, not raw `project_requirement` rows.
- [x] Update `ComplianceCheckService`, `SubmissionChecklistService`, `DeliveryPackage`, and `ComplianceMatrix` to consume confirmed constraints and conflict decisions.
- [~] Add a compatibility guard that blocks generation/export when no current confirmed constraint set exists, except for projects with `project.metadata_json.legacy_pre_constraint_set = true`.
- [x] Update review engine to check confirmed constraints first and raw requirements only as diagnostic fallback.
- [~] Update export gates so unresolved critical constraint packages block export, while ignored pricing packages do not.
- [ ] Add tests proving rejected/ignored raw requirements cannot leak into generated chapters once the constraint set is confirmed.
- [x] Add tests proving business assembly, compliance matrix, submission checklist, delivery package traceability, and export gates use confirmed constraint items.
- [ ] Add tests proving no directory chapter is added, deleted, renamed, or moved when no tender-document conflict exists.
- [ ] Add tests proving an explicit tender-document conflict can modify the template only after the conflict decision is confirmed.
- [ ] Acceptance: after constraint confirmation, changing raw extraction rows does not alter drafting until a new constraint set version is built and confirmed; template directories remain unchanged unless a confirmed tender conflict overrides them.

---

## Phase 4: Template-Constrained Outline Mapping (P0)

**Objective:** Map bid-writing topics into the existing business/technical directory templates accurately, with tender-document conflicts handled as explicit overrides.

- [x] Replace category-only `CATEGORY_CHAPTER` mapping with subtype and keyword-aware mapping that targets existing template chapters first.
- [x] Remove `CATEGORY_CHAPTER` from the normal outline planner. Any category-only fallback must live behind an explicit legacy compatibility branch.
- [x] Add a hard rule: do not add, delete, rename, or reorder template chapters unless a confirmed `tender_conflict_override` requires it.
- [x] Rename user-facing "生成/重新规划目录" actions to template-first language such as "按模板生成目录映射" or "检查模板冲突", so users do not think the system is free-form rewriting the directory.
- [ ] Add conflict-resolution records for any proposed chapter change, including original template node, tender source locator, proposed operation, and confirmation actor.
- [~] Map `schedule_target` to `3 工期响应` and `10.3 工程进度计划及保证措施`.
- [x] Map `personnel_count` and `personnel_certificate` to `6 项目团队情况`.
- [x] Map `quality_target` and quality-control requirements to `10.1 质量保证措施`.
- [x] Map `safety_civilized` to `10.2 安全和绿色施工保障措施`.
- [ ] Map `construction_method` and SGCC technical requirements to `8.1 施工组织设计`, `8.2 施工技术措施`, and `13 技术规范书规定的其他应提交的文件`.
- [ ] Map `technical_scoring_response` to `12 技术评分标准涉及的支撑材料` and the relevant content chapter.
- [ ] Keep veto/rejection clauses in the template's existing deviation/response/check chapters and also link them to affected chapters; create new chapters only when tender documents explicitly require a separate section/file.
- [ ] Add mapping reason strings that explain why each constraint goes to each chapter.
- [~] Add tests for quality, schedule, safety, personnel, construction method, SGCC standard, and scoring mappings inside the fixed template.
- [x] Add tests for tender-conflict override behavior when the tender requires a missing mandatory chapter or different separate file.
- [ ] Acceptance: the confirmed outline preserves the business/technical template directory by default and shows topic-specific requirement counts in the correct existing chapters; any template change has tender evidence and confirmation history.

---

## Phase 5: Technical Chapter Writing Context Builder (P1)

**Objective:** Build a rich, structured context per technical chapter before writing.

- [x] Create `TechnicalChapterContextBuilder`.
- [x] Load confirmed constraints mapped to the chapter.
- [x] Load tender summary fields: project location, construction period, quality requirement, bid deadline, tenderer, and raw facts where useful.
- [x] Load scoring criteria relevant to the chapter and convert them into response obligations.
- [x] Load matched standard clauses with clause number, standard name, title, and usable clause text.
- [x] Load personnel selections for personnel/team chapters from existing `project_personnel_selection`.
- [x] Load equipment selections for construction method, safety, quality, and progress chapters from existing `project_equipment_selection`.
- [ ] Load company assets, certifications, evidence, performance records, and reusable method statements where relevant.
- [x] Load existing chart assets and recommended chart specs for the chapter.
- [x] Produce a normalized context object persisted in `bid_generation_run.prompt_inputs_json`.
- [~] Add tests for context assembly with no data, partial data, and full project data.
- [x] Acceptance: each technical generation run stores a traceable chapter context that explains what facts, constraints, standards, people, equipment, scoring items, and charts were available.

---

## Phase 6: Technical Chapter Strategy Templates (P1)

**Objective:** Replace generic requirement echoing with chapter-specific technical writing structures.

- [x] Add strategy templates under `backend/tender_backend/services/technical_chapter_strategies/*.py` for:
  - `construction_organization_design`
  - `construction_technical_measures`
  - `quality_assurance`
  - `safety_green_construction`
  - `schedule_assurance`
  - `project_team`
  - `technical_scoring_materials`
  - `sgcc_technical_spec_response`
- [x] Each strategy must define:
  - chapter purpose
  - required sections
  - required facts
  - required standards
  - required charts/tables
  - innovation slots
  - self-check rules
  - forbidden content such as pricing
- [~] Quality chapter must include quality target response, organization, inspection system, control points, material/equipment quality control, process acceptance, issue closure, and SGCC standard compliance.
- [x] Schedule chapter must include milestone decomposition, critical path, resource guarantee, coordination mechanism, delay warning, corrective measures, and schedule chart placeholder.
- [x] Safety chapter must include safety organization, risk identification, civilized construction, temporary power/fire/work-at-height controls where relevant, emergency response, and safety chart placeholder.
- [x] Construction method chapters must include workflow, key process controls, equipment/tools, personnel allocation, acceptance criteria, risk controls, and SGCC-specific measures.
- [x] Add tests that generated markdown contains required section skeletons and excludes pricing terms.
- [x] Acceptance: generated chapters are structurally complete even before AI prose expansion.

---

## Phase 7: AI-Assisted Substantial Drafting (P1)

**Objective:** Use AI to turn structured context into substantial, chapter-specific prose while preserving deterministic guardrails.

- [x] Replace or disable `workflows/generate_section.py` placeholder generation path before production use; the workflow must call the same `TechnicalChapterContextBuilder` and drafting service as the API path.
- [x] Replace `uuid4().hex` writes in production DB paths with UUID objects for consistency with the rest of the codebase.
- [ ] Add a technical drafting prompt that accepts only the normalized chapter context and strategy template.
- [~] Require AI output in structured markdown with fixed headings, response matrix, measures, standards table, and chart placeholders when applicable.
- [ ] Require the model to cite source constraint ids, standard clause ids, scoring ids, personnel ids, equipment ids, and chart placeholder keys in metadata blocks or hidden trace sections.
- [x] Add deterministic fallback by rendering the Phase 6 strategy template directly when AI Gateway is unavailable; do not create a second fallback skeleton implementation.
- [~] Add post-generation sanitizer to remove pricing terms and unsupported claims.
- [x] Add `rewrite_note` support as an additive instruction while keeping confirmed constraints mandatory.
- [~] Persist generation model, prompt version, context hash, and self-check result.
- [~] Add tests for AI unavailable fallback, pricing sanitization, required heading coverage, and trace metadata preservation.
- [x] Acceptance: one click on a technical chapter produces a substantial draft aligned to chapter strategy and confirmed constraints.

---

## Phase 8: Chart Integration Into Technical Writing (P1)

**Objective:** Move charts from optional manual assets into automatic technical chapter content.

- [x] Define chart recommendations per chapter:
  - `6 项目团队情况`: `org_chart`, `responsibility_matrix`
  - `8.1 施工组织设计`: `construction_flow`
  - `10.1 质量保证措施`: `quality_system`, optional quality control flow
  - `10.2 安全和绿色施工保障措施`: `safety_system`, `risk_matrix`, optional `emergency_org`
  - `10.3 工程进度计划及保证措施`: `schedule_gantt`
- [x] Extend `TechnicalBidWriter` to request chart specs for chart-worthy chapters through `ChartGenerationService`; generated assets start as `draft`.
- [x] Build chart context from confirmed constraints, tender facts, personnel/equipment selections, and chapter strategy.
- [x] Insert `{{chart:<placeholder_key>}}` into generated chapter drafts only when a chart asset exists or is created.
- [x] Mark generated chart assets as `draft` and require approval before formal export.
- [x] Update export gate to block only unapproved chart assets referenced by current drafts/templates, not every unapproved chart in the project.
- [x] Add backend helper to scan current drafts and templates for `{{chart:*}}` placeholders and return referenced placeholder keys.
- [x] Persist draft-time references in `chapter_draft.referenced_chart_keys` and use that column in gate queries before falling back to scan.
- [ ] Add frontend controls for chart type selection, `generateChartAsset()`-backed generation, regenerate, preview, approve, and insert placeholder into current draft.
- [x] Update `frontend/src/lib/api.ts` and export gate UI to include and display chart gate fields: `charts_approved` and `unapproved_chart_count`.
- [~] Add tests for automatic placeholder insertion, approval gate by referenced placeholders, and DOCX injection.
- [ ] Acceptance: chart-worthy technical chapters include usable chart placeholders and formal export injects approved chart images with captions.

---

## Phase 9: Review And Quality Gates (P0/P1)

**Objective:** Detect thin, generic, or non-compliant technical chapters before export.

- [~] Extend review engine to check confirmed constraints, strategy-required sections, scoring responses, standard clause usage, chart placeholders, and traceability.
- [ ] Add chapter quality metrics:
  - required section coverage
  - confirmed constraint coverage
  - scoring item coverage
  - standard clause support
  - chart/table presence
  - pricing-term absence
  - generic phrase density
  - minimum substantive paragraph count by chapter type
- [~] Add SGCC-specific checks for quality, safety, progress, personnel, and construction-method chapters.
- [~] Add review issues for missing chart approval, missing chapter strategy sections, missing standards, unsupported claims, and stale context.
- [x] Replace the hard-coded `format_passed=true` export gate with a real format-validation result or an explicit warning-only state that cannot be confused with a completed check. P0 accepts `format_status = warning_not_checked` with `format_passed = false`.
- [~] Add export/delivery blocking rules for failed required template item rendering, unresolved P0/P1 review issues, stale confirmed constraint sets, stale outlines, stale chapters, and unapproved referenced charts.
- [x] Ensure delivery package creation uses the same gate logic as export creation; it must not rely only on existing P0 compliance findings.
- [ ] Update frontend review dashboard to show topic-level quality issues instead of only raw requirement coverage.
- [~] Update frontend export gate dashboard to show veto, review, format, referenced chart approval, template-render health, stale artifact status, and final delivery readiness.
- [~] Add tests for thin chapter detection and standards/chart/scoring coverage gates.
- [ ] Add tests proving failed required template items and unresolved P1 blocking issues prevent final export/delivery.
- [x] Acceptance: a chapter that only says "我方将严格响应" fails review.

---

## Phase 10: Frontend Workflow Changes (P1/P2)

**Objective:** Make the improved workflow usable by bid engineers.

- [ ] Update requirements workspace to present grouped constraint packages by lane:
  - project basics
  - veto/rejection red lines
  - qualification and performance
  - personnel requirements
  - quality target
  - schedule target
  - safety/civilized construction
  - SGCC technical requirements
  - format/submission
  - ignored pricing/archive
- [ ] Add confirmation actions for accept, reject, merge, split, mark pricing ignored, promote critical, and confirm constraint set.
- [ ] Make confirmed constraint set creation/confirmation a visible required milestone before template conflict checking, outline confirmation, business assembly, or technical generation.
- [ ] Update editor workspace to show per-chapter generation context: constraints, scoring items, standards, people, equipment, charts, and missing inputs.
- [ ] Add chart management panel with supported chart types, generated specs, rendered previews, approval, regenerate, and insert-placeholder actions.
- [ ] Add technical writing quality panel showing review metrics and blocking issues.
- [ ] Add clear states for stale chapter, stale chart, stale constraint set, and stale outline.
- [~] Rename "提纲/大纲" screens to emphasize "目录模板映射" and "招标冲突确认" where appropriate.
- [ ] Add UI for template conflict records: original template chapter, tender source evidence, proposed action, accept/reject decision, and audit trail.
- [ ] Add frontend tests for grouped workbench, chart workflow, and generation gating.
- [ ] Acceptance: a user can move from extraction to confirmed constraints to technical chapter generation without editing raw noisy requirement rows.

---

## Phase 11: Data Migration And Compatibility (P0)

**Objective:** Add the new workflow without breaking existing projects.

- [x] Add new migration for `tender_constraint_item.constraint_subtype`, `project.metadata_json`, and `chapter_draft.referenced_chart_keys`.
- [ ] Add schema support for template conflict records if they cannot be stored safely in existing outline metadata.
- [ ] Add new migration for generation context versioning if existing `bid_generation_run.prompt_inputs_json` is insufficient.
- [ ] Add indexes for constraint set lookup, constraint item subtype lookup, template conflict lookup, stale artifact lookup, and referenced chart placeholder lookup if needed.
- [ ] Backfill existing requirements into draft constraint sets with conservative statuses and `constraint_subtype` copied from metadata where available.
- [ ] Backfill existing confirmed outlines as `template_default` conflict policy artifacts unless a known tender override exists.
- [ ] Backfill existing chart assets with placeholder keys where missing.
- [ ] Backfill or mark legacy projects with `project.metadata_json.legacy_pre_constraint_set = true` and mark legacy generated drafts with context version `legacy_raw_requirement_generation` so review can require regeneration before final export where needed.
- [x] Keep old API responses compatible until frontend migration is complete.
- [~] Add compatibility tests for projects without confirmed constraint sets.
- [ ] Acceptance: legacy projects still open and can regenerate a new constraint set.

---

## Phase 12: Verification And Acceptance Suite (P0/P1/P2)

**Objective:** Prove the full remediation works end to end.

- [x] Add unit tests for extraction scope decisions.
- [x] Add unit tests for constraint subtype classification and grouping.
- [x] Add unit tests for confirmed constraint set source-of-truth behavior.
- [x] Add unit tests for outline mapping by subtype.
- [x] Add unit tests for technical context builder.
- [x] Add unit tests for chapter strategy skeletons.
- [~] Add unit tests for chart recommendation and placeholder insertion.
- [x] Add unit tests for export gate checking only referenced chart assets.
- [x] Add unit tests for sync compatibility extraction matching the new extraction scope.
- [x] Add unit tests for template conflict records and no-conflict template preservation.
- [x] Add unit tests for business assembly, compliance matrix, submission checklist, delivery package, and export gates reading confirmed constraints.
- [~] Add unit tests for real format-gate states and failed required template item blocking.
- [ ] Add frontend tests for export gate chart fields, format state, template conflict UI, and confirmed-constraint milestone.
- [ ] Add integration test from source chunks to confirmed constraints to outline to generated technical chapter.
- [ ] Add integration test for chart generation, approval, DOCX export, and caption injection.
- [~] Add integration test proving delivery package uses the same final gate logic as export.
- [ ] Add regression fixture with noisy pricing content and verify pricing does not appear in active constraints or technical draft.
- [ ] Add regression fixture with quality/schedule/safety/personnel requirements and verify they map to the correct SGCC chapters.
- [ ] Add regression fixture proving the user-provided business/technical directory template remains byte-for-byte structurally unchanged when tender documents do not contain an explicit directory conflict.
- [ ] Add regression fixture proving a tender-required directory change is applied only through a confirmed conflict decision with source evidence.
- [ ] Acceptance: the acceptance suite catches all root causes listed in this document.

---

## Definition Of Done

- [x] Pricing-only content is not included in active constraints, outline mappings, generated technical drafts, review gates, or export blockers.
- [~] Confirmed constraint sets are the primary input for outline, generation, review, and export.
- [ ] User-provided business and technical directory templates are preserved by default.
- [ ] Tender-document conflicts override templates only after source-backed conflict detection and confirmation.
- [~] No production generation/export/review path consumes raw `project_requirement` rows as the source of truth after a confirmed constraint set exists.
- [x] Quality, schedule, safety, personnel, construction method, SGCC standard, and scoring obligations are separately classified and mapped.
- [x] Technical chapter generation uses structured chapter context, not only mapped raw requirements.
- [x] Generated technical chapters contain chapter-specific sections, measures, standards, resources, risks, and innovation content.
- [x] Chart-worthy chapters create or reuse chart assets and include placeholders in generated drafts.
- [ ] Formal DOCX export injects approved referenced charts and captions.
- [~] Export and delivery gates show and enforce review, format, referenced chart, required-template-item, stale-artifact, and confirmed-constraint readiness.
- [~] Legacy/compatibility extraction and placeholder workflow paths are either aligned with the new services or disabled for production.
- [x] Review fails thin generic chapters and missing referenced chart approvals.
- [ ] Frontend supports constraint confirmation, chapter context inspection, chart approval, and quality remediation.

---

## Implementation Order

1. P0: Phase 1, Phase 2 subtype column, Phase 3 confirmed constraints/conflict policy, Phase 4 template-preserving mapping, Phase 9 export gate truthfulness, Phase 11 migrations, and the matching Phase 12 regression tests.
2. P1: Phase 5 context builder, Phase 6 strategy modules, Phase 7 AI drafting/fallback reuse, Phase 8 chart automation, and the first frontend workflow updates.
3. P2: broader dashboard polish, long-running shadow comparison, and expanded end-to-end acceptance fixtures.

---

## Product Decisions

- [x] Bid bond amount remains in project summary/submission checklist metadata only. It becomes an active non-pricing constraint only when the source text also imposes signature, format, deadline, validity, seal, or submission-readiness obligations.
- [x] Technical chapters generate recommended chart placeholders and draft chart assets by default. Users approve referenced charts before formal export.

- [x] Generated technical drafts store source trace in generation metadata/review panels; prose does not include visible trace tables by default.
- [x] SGCC standard compliance uses the local standards library as the authoritative source; AI-suggested standards require later user confirmation before use.
