# Bid Generation Workflow Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a confirmed, traceable bid document generation workflow from project setup through tender analysis, outline reconciliation, business/technical drafting, review, final export, archive, and post-bid retrospective.

**Architecture:** Extend the current project, tender extraction, template package, bid outline, chapter generation, review, and delivery-package modules. Introduce explicit workflow states, versioned constraints, confirmed outline gates, separate business/technical generation services, structured chart assets, review/revision tracking, and post-bid archival data.

**Tech Stack:** FastAPI backend, PostgreSQL/Alembic, existing repository/service patterns under `backend/tender_backend`, existing template rendering and DOCX export services, frontend project workbench components, AI extraction/generation workers.

---

## Tracking Legend

- `[ ]` Not started
- `[~]` In progress
- `[x]` Completed
- `[!]` Blocked or needs product decision

---

## File Map

Likely backend files to create:

- `backend/tender_backend/services/project_setup_service.py`: project metadata and workflow-state transitions.
- `backend/tender_backend/services/template_selection_service.py`: project type to template package selection.
- `backend/tender_backend/services/tender_constraint_service.py`: unified tender, standard, template, and user-confirmed constraints.
- `backend/tender_backend/services/outline_reconciliation_service.py`: template outline and tender requirements fusion.
- `backend/tender_backend/services/business_bid_assembler.py`: deterministic business bid assembly.
- `backend/tender_backend/services/technical_bid_writer.py`: chapter-level technical bid planning, generation, and self-check.
- `backend/tender_backend/services/chart_generation_service.py`: chart specification, validation, rendering handoff.
- `backend/tender_backend/services/post_bid_review_service.py`: bid outcome and retrospective records.
- `backend/tender_backend/db/repositories/bid_workflow_repo.py`: workflow-state persistence and event log.
- `backend/tender_backend/db/repositories/tender_constraint_repo.py`: versioned constraint records.
- `backend/tender_backend/db/repositories/chart_asset_repo.py`: chart specs and rendered asset records.
- `backend/tender_backend/db/repositories/post_bid_review_repo.py`: post-bid result and lessons learned.

Likely backend files to modify:

- `backend/tender_backend/api/projects.py`: project creation fields and workflow status APIs.
- `backend/tender_backend/api/tender_documents.py`: link analysis completion to constraint confirmation.
- `backend/tender_backend/api/bid_outline.py`: outline reconciliation, diff preview, and confirmation endpoints.
- `backend/tender_backend/api/templates.py`: expose eligible template packages and selection results.
- `backend/tender_backend/api/bid_generation.py`: separate business and technical generation commands.
- `backend/tender_backend/api/review.py`: review issue lifecycle, scoring review, revision tracking.
- `backend/tender_backend/api/delivery.py`: final package archive, split download, final confirmation.
- `backend/tender_backend/services/bid_outline_planner.py`: reuse as one input to reconciliation rather than sole outline builder.
- `backend/tender_backend/services/bid_chapter_generation.py`: keep common generation utilities, move business/technical strategy out.
- `backend/tender_backend/services/review_service/review_engine.py`: add score-aligned review and traceability checks.
- `backend/tender_backend/services/delivery_package.py`: include final versions, split files, review reports, and archive metadata.
- `backend/tender_backend/services/export_service/docx_exporter.py`: support scoring-response index, chart assets, and final pagination pass.

Likely database migrations:

- Add project metadata and selected template fields if missing.
- Add workflow status and workflow event log.
- Add versioned constraint set and constraint items.
- Add outline reconciliation diff and confirmed outline version metadata.
- Add generation run records for business/technical chapters.
- Add chart asset records.
- Add review revision tracking and scoring review records.
- Add final bid package archive and post-bid review records.

Likely frontend areas to modify:

- Project creation wizard.
- Tender analysis and constraint confirmation screen.
- Template selection and outline reconciliation screen.
- Business bid workspace.
- Technical bid workspace.
- Chart preview/editor.
- Review and revision tracking workspace.
- Final export/archive screen.
- Post-bid retrospective form.

---

## Phase 1: Project Setup And Workflow State

**Objective:** Make project metadata and workflow state explicit so the rest of the pipeline has a stable contract.

- [ ] Add or verify project fields for `project_type`, `employer_name`, `tender_no`, `tender_deadline`, `selected_template_package_id`, `workflow_status`, and workflow metadata.
- [ ] Add `bid_workflow_event` table with project id, previous status, next status, actor, reason, and timestamp.
- [ ] Implement `ProjectSetupService` with guarded transitions for upload, analysis, confirmation, drafting, review, final layout, delivery, and archive.
- [ ] Extend project creation API to accept投标类型、发包人、招标编号、截止时间.
- [ ] Add backend tests proving invalid transitions are rejected, for example `outline_pending_confirmation` cannot jump directly to `delivered`.
- [ ] Add frontend project creation fields and show current workflow status in the project workspace.
- [ ] Acceptance: a newly created project has complete metadata and visible workflow status, and status transitions are persisted with an event log.

---

## Phase 2: Template Auto Selection

**Objective:** Automatically select the correct bid template package according to project type while preserving user override.

- [ ] Implement `TemplateSelectionService` using `project_type -> bid_template_package.package_type`.
- [ ] Filter candidate templates by enabled status, package type, category, version, and optional industry metadata.
- [ ] Persist selected template package id on the project.
- [ ] Add API to preview eligible template packages and confirm or override the recommended package.
- [ ] Add tests for exact match, multiple candidates, no candidates, disabled package exclusion, and manual override.
- [ ] Update frontend to show recommended template and mismatch warnings.
- [ ] Acceptance: after project setup, system recommends one template package when possible and blocks silent fallback when no package matches.

---

## Phase 3: Tender Constraint Workspace

**Objective:** Convert AI extraction, standards parsing, template requirements, and user edits into a versioned constraint set.

- [ ] Create `tender_constraint_set` and `tender_constraint_item` tables.
- [ ] Normalize extracted requirements into categories: qualification, business, technical, scoring, rejection, formatting, delivery, standard, attachment.
- [ ] Link constraints to source document id, page, chunk, extracted requirement id, standard clause id, or template item id where available.
- [ ] Add statuses `draft`, `accepted`, `rejected`, `merged`, `needs_review`.
- [ ] Implement `TenderConstraintService` to build a constraint set after extraction completes.
- [ ] Add API for list, filter, accept, reject, merge, edit, and version constraint sets.
- [ ] Add frontend confirmation workspace with filters for low confidence, scoring items, rejection clauses, and format requirements.
- [ ] Acceptance: users can confirm the constraints that will govern outline generation and drafting; all confirmed constraints have source traceability.

---

## Phase 4: Outline Reconciliation And Confirmation Gate

**Objective:** Fuse template outline and tender constraints into a reviewable candidate outline, then freeze a confirmed outline version.

- [ ] Create or extend data model for outline reconciliation diff records.
- [ ] Implement `OutlineReconciliationService` that takes selected template package, confirmed constraints, scoring items, and existing outline planner output.
- [ ] Produce diff entries with operations `add`, `remove`, `rename`, `move`, `keep`, `mark_manual_required`.
- [ ] Attach each outline node to relevant tender constraints, scoring criteria, standard clauses, and generation strategy.
- [ ] Add API to preview candidate outline, accept/reject individual diffs, reorder nodes, and confirm outline.
- [ ] Enforce drafting gate: business/technical generation cannot start unless an outline version is confirmed.
- [ ] Add tests for mandatory tender chapters, scoring coverage, rejection-clause priority, and confirmed-outline immutability.
- [ ] Update frontend with template-vs-tender diff view and confirmation controls.
- [ ] Acceptance: users see how AI adjusted the template outline and must confirm before drafting begins.

---

## Phase 5: Business Bid Assembly

**Objective:** Generate business bid drafts using deterministic data insertion and evidence mapping, with AI only for controlled summaries and response text.

- [ ] Define business chapter strategies: `data_insert`, `template_render`, `ai_summary`, `manual_required`.
- [ ] Implement `BusinessBidAssembler` to select company qualifications, assets, performance records, proof files, personnel qualifications, and personnel performance according to confirmed constraints.
- [ ] Add missing-material detection for required qualification, proof, certificate expiry, personnel role mismatch, and project performance mismatch.
- [ ] Generate a business response matrix mapping tender requirements and scoring items to chapters and evidence.
- [ ] Add controlled AI summary generation for company overview, capability statement, and response notes using only approved evidence.
- [ ] Add tests preventing AI-generated unsupported certificate numbers, project amounts, personnel titles, and dates.
- [ ] Add frontend business workspace for evidence selection, missing-material warnings, and generated response matrix.
- [ ] Acceptance: business bid chapters are generated from structured company evidence, and every factual claim is traceable to a stored asset or user-confirmed input.

---

## Phase 6: Technical Bid Writing

**Objective:** Generate technical bid chapters through plan-generate-check-revise loops tied to tender constraints and scoring criteria.

- [ ] Implement `TechnicalBidWriter` with chapter writing plan generation.
- [ ] Store chapter generation runs with prompt inputs, model metadata, outline node id, constraint ids, and output version.
- [ ] Generate technical chapter drafts using confirmed outline node, tender constraints, standard clauses, project context, company capability snippets, and preceding chapter summaries.
- [ ] Add self-check pass per chapter for missing requirements, contradiction, unsupported claims, and scoring weakness.
- [ ] Add technical response matrix mapping scoring criteria to chapters.
- [ ] Add tests ensuring a chapter cannot be generated without confirmed outline and constraint context.
- [ ] Add frontend technical workspace with writing plan preview, regenerate chapter, compare versions, and accept chapter.
- [ ] Acceptance: technical bid text is generated chapter-by-chapter, with visible source constraints and revision history.

---

## Phase 7: Structured Chart Generation

**Objective:** Generate organization charts and related diagrams as structured specs that can be previewed, edited, rendered, and embedded.

- [ ] Create `chart_asset` table with project id, outline node id, chart type, spec json, rendered path, status, and version.
- [ ] Define JSON schemas for `org_chart`, `process_flow`, `schedule_gantt`, `responsibility_matrix`, and `risk_matrix`.
- [ ] Implement `ChartGenerationService` to create chart specs from constraints, personnel, schedule, roles, and user edits.
- [ ] Add validation that org chart roles required by tender constraints are present or explicitly marked unavailable.
- [ ] Add deterministic SVG rendering for first-stage chart types.
- [ ] Add DOCX embedding support through the export pipeline.
- [ ] Add frontend chart preview/editor with node text, role, edge, and style editing.
- [ ] Acceptance: project organization chart and process/schedule diagrams are generated from editable structured specs, not opaque AI images.

---

## Phase 8: Review, Scoring, And Revision Tracking

**Objective:** Turn AI/rule review into a closed-loop issue and scoring workflow.

- [ ] Extend review issue model with source constraint id, scoring item id, chapter id, revision status, user decision, and before/after version links.
- [ ] Add initial review pass covering omissions, rejection risk, qualification gaps, standard conflicts, unsupported facts, and common-sense issues.
- [ ] Add scoring review pass mapping each scoring item to response chapter, evidence, estimated risk, and improvement advice.
- [ ] Implement issue lifecycle: open, accepted_for_fix, fixed, waived_by_user, verified, closed.
- [ ] Block final layout when unresolved P0/P1 issues exist unless user explicitly waives them.
- [ ] Add tests for issue lifecycle, final-layout blocking, and score-item mapping.
- [ ] Add frontend review dashboard with severity filters, scoring view, revision trace, and user confirmation controls.
- [ ] Acceptance: review findings are traceable, user decisions are recorded, and critical unresolved risks block finalization.

---

## Phase 9: Final Layout, Export, Split, And Archive

**Objective:** Produce final DOCX/PDF packages according to template and tender requirements, with archive metadata.

- [ ] Extend export context with cover data, confirmed outline, scoring response index, chart assets, evidence attachments, and review closure status.
- [ ] Generate standard table of contents from Word heading styles.
- [ ] Generate scoring-response index after cover using scoring criteria, response chapter anchors, evidence, and final page numbers.
- [ ] Add final pagination/update pass for DOCX fields before PDF conversion.
- [ ] Support split output by volume and by chapter, then ZIP packaging.
- [ ] Store final package metadata: template package version, constraint set version, confirmed outline version, review report, docx path, pdf path, split package paths.
- [ ] Add tests for export blocking before confirmed outline, missing critical review closure, and missing required final files.
- [ ] Add frontend final export screen with package preview, split options, and archive confirmation.
- [ ] Acceptance: final bid package can be downloaded as DOCX/PDF/ZIP and system stores the exact versions used to produce it.

---

## Phase 10: Post-Bid Retrospective

**Objective:** Capture bid results and lessons learned so future bids improve.

- [ ] Create post-bid review data model with bid result, ranking, score, price, competitor notes, win/loss reasons, and reusable lessons.
- [ ] Implement `PostBidReviewService` and APIs to create, update, and query retrospective records.
- [ ] Link retrospective insights to template package, project type, scoring items, technical chapters, and evidence assets where relevant.
- [ ] Add frontend post-bid form after project is archived or delivered.
- [ ] Add analytics queries for win rate by project type, template package, scoring weakness, and missing materials.
- [ ] Acceptance: after opening, users can record whether the bid won and why, and this information is available for future template and content recommendations.

---

## Phase 11: End-To-End Frontend Workflow

**Objective:** Present the workflow as a guided workbench instead of disconnected tools.

- [ ] Add project workflow stepper: setup, upload, analysis, constraints, template, outline, business, technical, review, export, archive.
- [ ] Disable downstream actions until required upstream gates are completed.
- [ ] Add visible counts for unconfirmed constraints, unresolved outline diffs, missing business materials, unaccepted technical chapters, and unresolved review issues.
- [ ] Add consistent source-trace panels showing tender page, requirement text, standard clause, scoring item, and generated response.
- [ ] Add optimistic but safe UI state handling for long-running AI jobs.
- [ ] Acceptance: a user can complete the full process from one project workbench without guessing the next required action.

---

## Phase 12: Verification And Release Gates

**Objective:** Prove the redesigned workflow is safe enough for real bid document generation.

- [ ] Add migration tests for new tables and backward compatibility with existing projects.
- [ ] Add service tests for template selection, constraint confirmation, outline reconciliation, business assembly, technical generation gates, chart validation, review lifecycle, and final export blocking.
- [ ] Add API tests for each workflow stage.
- [ ] Add at least one seeded end-to-end project fixture with ZIP/PDF source, template package, company evidence, confirmed outline, generated draft, review, and final package.
- [ ] Add manual acceptance script documenting the full path from new project to archived final package.
- [ ] Run backend tests, frontend tests, linting, and one manual export smoke test before release.
- [ ] Acceptance: all automated tests pass, manual smoke test produces a final DOCX/PDF package, and existing template-package workflows still work.

---

## Product Decisions To Confirm Before Implementation

- [ ] Confirm the canonical list of投标类型 and how they map to template package types.
- [ ] Confirm first-stage supported business evidence types and required metadata.
- [ ] Confirm whether technical标 first version needs a reusable technical capability library or only project-specific generation.
- [ ] Confirm first-stage chart types. Recommended: organization chart, process flow, schedule gantt.
- [ ] Confirm whether PDF conversion is handled by LibreOffice, existing service, or external conversion service.
- [ ] Confirm final archive storage location and retention policy for DOCX/PDF/ZIP.
- [ ] Confirm whether scoring review should show numeric estimated scores or qualitative risk levels only. Recommended first stage: qualitative risk levels plus improvement suggestions.

---

## Suggested Execution Order

1. Phase 1: Project setup and workflow state
2. Phase 2: Template auto selection
3. Phase 3: Tender constraint workspace
4. Phase 4: Outline reconciliation and confirmation gate
5. Phase 5: Business bid assembly
6. Phase 6: Technical bid writing
7. Phase 8: Review, scoring, and revision tracking
8. Phase 9: Final layout, export, split, and archive
9. Phase 7: Structured chart generation
10. Phase 10: Post-bid retrospective
11. Phase 11: End-to-end frontend workflow
12. Phase 12: Verification and release gates

Chart generation can move earlier if organization架构图 is required for the first production pilot. Post-bid retrospective can move later because it does not block first document generation.

