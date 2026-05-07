# Bid Generation Workflow Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a confirmed, traceable electric-power construction bid document workflow from project setup through tender analysis, outline reconciliation, qualification/business assembly, technical drafting, compliance checks, review, final export, submission-preparation checklist, archive, and post-bid retrospective.

**Revision Basis:** Aligns with the revised spec and the 2026-05-07 review reports. ECP is treated as one tender-platform adapter, not the sole product boundary. The first stage does not promise direct parsing of private `.sgcc` binaries; it uses readable PDF/DOCX/XLSX inputs, platform-exported attachments, manual completion, and platform-rule checks.

**Architecture:** Extend the current project, tender extraction, template package, bid outline, chapter generation, review, and delivery-package modules. Introduce explicit workflow states, electric-power project metadata, platform rule metadata, versioned constraints, confirmed outline gates, volume/chapter structure, separate qualification-business and technical generation services, deterministic compliance checking, structured chart assets, review/revision tracking, submission-preparation exports, and post-bid archival data.

**Tech Stack:** FastAPI backend, PostgreSQL/Alembic, existing repository/service patterns under `backend/tender_backend`, existing template rendering and DOCX export services, frontend project workbench components, AI extraction/generation workers.

---

## Tracking Legend

- `[ ]` Not started
- `[~]` In progress
- `[x]` Completed
- `[!]` Blocked or needs product decision

---

## Scope Decisions Already Confirmed

- [x] Treat ECP as one platform adapter among several platform types.
- [x] Do not promise direct parsing of private `.sgcc` binary packages in the first stage.
- [x] Reserve batch/section/lot fields in the first stage, without building a full batch tender workspace.
- [x] Reserve consortium modeling and protocol generation, with single-company bidding as the first-stage default path.
- [x] Support external pricing files as upload/archive/package attachments only; do not generate pricing content or promise complex PDF pagination merge.
- [x] Default ordinary extracted clauses to auto-accepted with sampling review only.
- [x] Merge similar clauses conservatively; date, amount, copy count, certificate grade, social-security month count, file-size, and other key-field conflicts must require human confirmation.

---

## File Map

Likely backend files to create:

- `backend/tender_backend/services/project_setup_service.py`: project metadata, platform fields, and workflow-state transitions.
- `backend/tender_backend/services/template_selection_service.py`: multi-factor template package selection.
- `backend/tender_backend/services/tender_constraint_service.py`: unified tender, standard, platform, template, and user-confirmed constraints.
- `backend/tender_backend/services/requirement_grouping_service.py`: conservative grouping, confirmation-level assignment, duplicate handling, and conflict detection for extracted clauses.
- `backend/tender_backend/services/clarification_merge_service.py`: Q&A, addendum, clarification version chain and impact analysis.
- `backend/tender_backend/services/outline_reconciliation_service.py`: template outline and tender requirements fusion.
- `backend/tender_backend/services/business_bid_assembler.py`: deterministic qualification-business bid assembly.
- `backend/tender_backend/services/technical_bid_writer.py`: chapter-level technical bid planning, generation, and self-check.
- `backend/tender_backend/services/chart_generation_service.py`: chart specification, validation, rendering handoff.
- `backend/tender_backend/services/compliance_check_service.py`: deterministic rejection-risk and submission-readiness rule engine.
- `backend/tender_backend/services/submission_checklist_service.py`: signature, seal, file, copy-count, package, and platform manual-upload checklist generation.
- `backend/tender_backend/services/post_bid_review_service.py`: bid outcome, opening, evaluation, clarification, and retrospective records.
- `backend/tender_backend/db/repositories/bid_workflow_repo.py`: workflow-state persistence and event log.
- `backend/tender_backend/db/repositories/tender_constraint_repo.py`: versioned constraint records.
- `backend/tender_backend/db/repositories/requirement_group_repo.py`: grouped requirement packages, source members, confirmation level, and conflict fields.
- `backend/tender_backend/db/repositories/clarification_repo.py`: addendum and clarification version records.
- `backend/tender_backend/db/repositories/chart_asset_repo.py`: chart specs and rendered asset records.
- `backend/tender_backend/db/repositories/compliance_check_repo.py`: compliance check runs and rule findings.
- `backend/tender_backend/db/repositories/post_bid_review_repo.py`: post-bid result and lessons learned.

Likely backend files to modify:

- `backend/tender_backend/api/projects.py`: project creation fields and workflow status APIs.
- `backend/tender_backend/api/tender_documents.py`: link analysis completion to constraint confirmation and readable input boundaries.
- `backend/tender_backend/api/bid_outline.py`: outline reconciliation, diff preview, volume/chapter confirmation endpoints.
- `backend/tender_backend/api/templates.py`: expose eligible template packages and selection results.
- `backend/tender_backend/api/bid_generation.py`: separate qualification-business and technical generation commands.
- `backend/tender_backend/api/review.py`: review issue lifecycle, scoring review, deviation tables, revision tracking.
- `backend/tender_backend/api/delivery.py`: final package archive, split download, external pricing attachment, submission checklist, final confirmation.
- `backend/tender_backend/services/bid_outline_planner.py`: reuse as one input to reconciliation rather than sole outline builder.
- `backend/tender_backend/services/bid_chapter_generation.py`: keep common generation utilities, move business/technical strategy out.
- `backend/tender_backend/services/review_service/review_engine.py`: add score-aligned review and traceability checks.
- `backend/tender_backend/services/delivery_package.py`: include final versions, split files, review reports, compliance reports, external attachments, and archive metadata.
- `backend/tender_backend/services/export_service/docx_exporter.py`: support scoring-response index, chart assets, signature placeholders, and final pagination pass.

Service placeholders to document but not implement in the first stage:

- `BidPricingService`: future pricing/economic-bid generation.
- `PlatformIntegrationService`: future direct platform upload/download integration.

Likely database migrations:

- Add project metadata: `industry`, `business_line`, `sub_type`, `employer_name`, `employer_type`, `tender_no`, `evaluation_method`, `evaluation_detail`, `qualification_review_type`, `submission_deadline`, `bid_opening_time`, `bid_validity_period`, `bid_bond_amount`, `bid_bond_form`, `bid_bond_deadline`, `voltage_level`, `project_scope`, `is_live_work_required`, `controlled_price`, `is_subcontract_allowed`, `is_consortium_allowed`, `tender_platform`, `submission_target`, `platform_file_rules`, `procurement_type`, `parent_project_id`, `section_name`, `lot_name`, `selected_template_package_id`, `workflow_status`.
- Add workflow event log.
- Add `bid_volume` and connect chapters to volumes.
- Add versioned constraint set and constraint items.
- Add requirement group/package records with source requirement members, similarity metadata, confirmation level, merge status, conflict fields, user decision, and audit timestamps.
- Add clarification/addendum version chain and impact records.
- Add outline reconciliation diff and confirmed outline version metadata.
- Add generation run records for business/technical chapters.
- Add chart asset records.
- Add compliance check run and finding records.
- Add external attachment records for pricing and platform files if no suitable table exists.
- Add review revision tracking, deviation table, and scoring review records.
- Add final bid package archive and post-bid review records.

Migration cautions:

- [ ] Use nullable fields or safe defaults for existing projects; do not force immediate data completion on legacy rows.
- [ ] Backfill `workflow_status` conservatively, for example `constraints_pending_confirmation` or `drafting` based on available artifacts.
- [ ] Update project response schemas and frontend callers in the same phase as project fields.

Likely frontend areas to modify:

- Project creation wizard.
- Tender analysis and constraint confirmation screen.
- Critical-clause confirmation workbench with grouped clauses, auto-accepted sampling queue, source trace panel, and batch actions.
- Platform rule and manual-upload requirements panel.
- Template selection and outline reconciliation screen.
- Volume/chapter outline editor.
- Qualification-business workspace.
- Technical bid workspace.
- Chart preview/editor.
- Compliance check dashboard.
- Review, deviation table, and revision tracking workspace.
- Final export/archive/submission-checklist screen.
- Post-bid retrospective form.

---

## Phase 1: Project Setup, Platform Metadata, And Workflow State

**Objective:** Make project metadata and workflow state explicit so the rest of the pipeline has a stable contract.

- [ ] Add or verify project fields listed in the migration section, including power-business metadata, tender-platform metadata, and batch/section/lot reservation fields.
- [ ] Add `bid_workflow_event` table with project id, previous status, next status, actor, reason, and timestamp.
- [ ] Implement `ProjectSetupService` with guarded transitions for upload, analysis, confirmation, drafting, compliance check, final layout, package, seal, submit, open, evaluate, award/loss, contract, and archive.
- [ ] Add pre-qualification substatus support for qualification-precheck projects.
- [ ] Extend project creation API to accept business line, voltage level, tender platform, submission deadline, opening time, bid validity period, bid bond fields, and employer metadata.
- [ ] Add backend tests proving invalid transitions are rejected, for example `outline_pending_confirmation` cannot jump directly to `final_packaged`.
- [ ] Add frontend project creation fields and show current workflow status in the project workspace.
- [ ] Acceptance: a newly created project has complete first-stage metadata, visible workflow status, and persisted event logs; legacy projects still load.

---

## Phase 2: Template Auto Selection

**Objective:** Automatically select the correct bid template package according to electric-power business factors while preserving user override.

- [ ] Update template package metadata to support `industry + sub_type`, business line, voltage level, employer type, evaluation method, qualification review type, and tender platform tags where available.
- [ ] Implement `TemplateSelectionService` using weighted factors: business line, voltage level, evaluation method, qualification review type, employer type, tender platform, consortium flag, subcontract flag.
- [ ] Filter candidate templates by enabled status, category, version, and applicable metadata.
- [ ] Persist selected template package id and selection rationale on the project.
- [ ] Add API to preview eligible template packages and confirm or override the recommended package.
- [ ] Add tests for exact business-line match, voltage-level mismatch warning, multiple candidates, no candidates, disabled package exclusion, and manual override.
- [ ] Update frontend to show recommended template, match rationale, and mismatch warnings.
- [ ] Acceptance: after project setup, system recommends one template package when possible and blocks silent fallback when no package matches.

---

## Phase 3: Tender Constraint Workspace And Clarification Merge

**Objective:** Convert AI extraction, standards parsing, platform rules, template requirements, clarification files, and user edits into a versioned constraint set.

- [ ] Create `tender_constraint_set` and `tender_constraint_item` tables.
- [ ] Normalize extracted requirements into categories: `qualification`, `business`, `technical`, `scoring`, `substantive_response`, `legal_rejection`, `rejection_clause`, `disqualification_pre`, `disqualification_post`, `seal_signature`, `validity`, `ecp_format`, `ca_signature`, `pricing_constraint`, `formatting`, `delivery`, `standard`, `attachment`.
- [ ] Treat `ecp_format` as a platform-file-rule category that can also store non-ECP platform requirements; keep the name only for compatibility with reviewed terminology.
- [ ] Link constraints to source document id, page, chunk, extracted requirement id, standard clause id, template item id, platform rule id, or manual entry where available.
- [ ] Add statuses `draft`, `accepted`, `rejected`, `merged`, `needs_review`.
- [ ] Implement `TenderConstraintService` to build a constraint set after extraction completes.
- [ ] Implement `ClarificationMergeService` for multi-round Q&A, addendum, and clarification version chains.
- [ ] Add impact analysis: later clarification changes scoring, deadline, qualification, format, or technical requirements and marks affected constraints, outline nodes, and generated chapters stale.
- [ ] Add `.sgcc` boundary handling: store uploaded `.sgcc` files as raw attachments only; do not mark them as structured parse sources.
- [ ] Add API for list, filter, accept, reject, merge, edit, version constraint sets, and review clarification impact.
- [ ] Add frontend confirmation workspace with filters for low confidence, scoring items, rejection clauses, signature/seal items, validity items, and platform-file rules.
- [ ] Acceptance: users can confirm the constraints that govern outline generation and drafting; all confirmed constraints have source traceability or explicit manual origin.

---

## Phase 3-bis: Requirement Grouping And Critical Confirmation Workbench

**Objective:** Reduce operator confirmation load by showing投标工程师 only critical clauses and conflicts, while ordinary clauses are auto-accepted and kept available for sampling review.

- [ ] Implement `RequirementGroupingService` after extraction and before outline reconciliation.
- [ ] Add `confirmation_level` values: `critical`, `review`, `auto_accept`, `ignored`.
- [ ] Default ordinary technical, contract, and general-format clauses to `auto_accept`; keep them traceable and available in a sampling-review queue.
- [ ] Assign `critical` to rejection/veto clauses, substantive responses, qualification hard gates, personnel certificate/social-security requirements, performance thresholds, bid validity, bid bond, signature/seal, copy-count, delivery/platform-file rules, and clarification conflicts.
- [ ] Assign `review` to low-confidence, unclear-source, or strategy-sensitive clauses that are not direct red lines.
- [ ] Assign `ignored` to pricing-only content outside first-stage scope, irrelevant background text, and user-marked duplicates.
- [ ] Group identical or similar requirements into a requirement package with source members, source files, pages, locators, and original text snippets preserved.
- [ ] Use conservative merge rules: do not auto-merge into one conclusion when date, amount, copy count, certificate grade, social-security month count, performance count, file-size limit, deadline, or other key fields conflict.
- [ ] Mark key-field conflicts as `critical` and require human confirmation before they can feed outline or compliance gates.
- [ ] Add APIs for grouped requirement list, critical queue, sampling queue, group detail, batch confirm, downgrade to ordinary, promote to critical, split group, mark duplicate, ignore pricing-related content, and view audit history.
- [ ] Delete the top global scrolling notification bar from the app shell; replace global notices with contextual status panels inside the relevant workspace.
- [ ] Rebuild the requirements frontend as a critical-clause workbench: project brief at top, work lanes for project basics, rejection red lines, qualification-business hard gates, technical response priorities, submission checklist, and auto-accepted sampling.
- [ ] Show grouped clauses as clause packages rather than flat extraction rows; each package shows system conclusion, confidence, confirmation level, source count, conflict fields, blocking status, and recommended action.
- [ ] Add right-side source trace panel with original text, file, page/locator, merge members, user decisions, and audit trail.
- [ ] Add batch actions for confirm package, confirm all non-conflicting critical packages in current lane, downgrade to sampling, promote to critical, split package, mark duplicate, and ignore out-of-scope pricing content.
- [ ] Add tests for ordinary clauses auto-accepted by default, critical clauses blocking, conservative duplicate merge, key-field conflict detection, batch confirmation audit records, and global marquee removal.
- [ ] Acceptance: after AI extraction, users primarily handle a short critical queue and conflict queue; ordinary clauses remain traceable without requiring line-by-line confirmation.

---

## Phase 4: Volume Model, Outline Reconciliation, And Confirmation Gate

**Objective:** Fuse template outline and tender constraints into a reviewable candidate volume/chapter outline, then freeze a confirmed outline version.

- [ ] Create `bid_volume` table with volume types `business`, `technical`, `pricing`, `qualification`, and `attachments`.
- [ ] Connect `bid_chapter.volume_id` to `bid_volume.id` and migrate existing chapters where needed.
- [ ] Create or extend data model for outline reconciliation diff records.
- [ ] Implement `OutlineReconciliationService` that takes selected template package, confirmed constraints, scoring items, legal/rejection clauses, and existing outline planner output.
- [ ] Use grouped requirement packages as the primary input, not the raw flat extraction rows; `auto_accept` packages can feed outline generation, while unresolved `critical` conflicts block confirmation.
- [ ] Produce diff entries with operations `add`, `remove`, `rename`, `move`, `keep`, `mark_manual_required`, `mark_external_attached`.
- [ ] Attach each outline node to relevant tender constraints, scoring criteria, standard clauses, legal/rejection clauses, and generation strategy.
- [ ] Ensure mandatory files such as bid letter, bid-letter appendix, authorization, undertakings, deviation tables, qualification forms, and submission attachments are represented.
- [ ] Add API to preview candidate outline, accept/reject individual diffs, reorder nodes, and confirm outline.
- [ ] Enforce drafting gate: business/technical generation cannot start unless an outline version is confirmed.
- [ ] Add tests for mandatory tender chapters, scoring coverage, rejection-clause priority, external pricing placeholder, and confirmed-outline immutability.
- [ ] Update frontend with template-vs-tender diff view, volume tree, and confirmation controls.
- [ ] Acceptance: users see how the system adjusted the template outline and must confirm before drafting begins.

---

## Phase 5: Qualification-Business Bid Assembly

**Objective:** Generate qualification-business drafts using deterministic data insertion and evidence mapping, with AI only for controlled summaries and response text.

- [ ] Define chapter strategies: `data_insert`, `template_render`, `ai_summary`, `manual_required`, `external_attached`.
- [ ] Implement `BusinessBidAssembler` to select company qualifications, certificates, assets, performance records, proof files, personnel qualifications, personnel performance, and legal documents according to confirmed constraints.
- [ ] Add one-paper supplier qualification proof management: proof metadata, effective period, coverage matching, simplified response branch, and full-qualification fallback branch.
- [ ] Add certificate-expiry validation against `submission_deadline + bid_validity_period`.
- [ ] Add personnel certificate and social-security validation with configurable continuous-month count, deadline rule, and branch/subsidiary recognition flag.
- [ ] Add 3+1 performance-material detection: notice of award, contract, completion acceptance proof, and optional owner evaluation/performance proof depending on tender requirements.
- [ ] Add missing-material detection for required qualification, proof, certificate expiry, personnel role mismatch, special-operation certificate gaps, and project performance mismatch.
- [ ] Add consortium-reservation support: lead member, member division of work, and multi-company evidence selection model if `is_consortium_allowed` is true; first-stage UI may still default to single-company path.
- [ ] Generate business response matrix mapping tender requirements and scoring items to chapters and evidence.
- [ ] Add controlled AI summary generation for company overview, capability statement, and response notes using only approved evidence.
- [ ] Add tests preventing AI-generated unsupported certificate numbers, project amounts, personnel titles, dates, and one-paper-proof claims.
- [ ] Add frontend business workspace for evidence selection, missing-material warnings, one-paper-proof branch, and generated response matrix.
- [ ] Acceptance: qualification-business chapters are generated from structured company evidence, and every factual claim is traceable to a stored asset or user-confirmed input.

---

## Phase 5-bis: External Pricing File Attachment

**Objective:** Preserve the boundary that pricing/economic bid is external in the first stage while allowing complete package management.

- [ ] Add or reuse attachment records for external pricing PDF/XLSX/ZIP/platform-tool files.
- [ ] Allow pricing volume nodes to use `external_attached` strategy.
- [ ] Include external pricing attachments in final package metadata and archive.
- [ ] Add warnings that pricing content is not generated, parsed, validated, or priced by tender in the first stage.
- [ ] Do not promise automatic PDF page merge, directory page-number reconciliation, or pricing-form validation in this phase.
- [ ] Acceptance: users can attach and archive external pricing files as part of a bid package without confusing this with pricing generation.

---

## Phase 6: Technical Bid Writing

**Objective:** Generate technical bid chapters through plan-generate-check-revise loops tied to tender constraints, scoring criteria, and electric-power business-line templates.

- [ ] Implement `TechnicalBidWriter` with chapter writing plan generation.
- [ ] Store chapter generation runs with prompt inputs, model metadata, outline node id, constraint ids, and output version.
- [ ] Generate technical chapter drafts using confirmed outline node, tender constraints, standard clauses, project context, company capability snippets, business-line template, and preceding chapter summaries.
- [ ] Add business-line specific section templates for substation labor/professional subcontracting, 10kV projects, power O&M, and user high/low-voltage distribution.
- [ ] Include green construction and low-carbon management section in first-stage technical templates.
- [ ] Add self-check pass per chapter for missing requirements, contradiction, unsupported claims, scoring weakness, and business-line mismatch.
- [ ] Add technical response matrix mapping scoring criteria to chapters.
- [ ] Add integration points for chart specs referenced by technical chapters, especially organization chart, schedule, site layout, quality system, and safety system.
- [ ] Add tests ensuring a chapter cannot be generated without confirmed outline and constraint context.
- [ ] Add frontend technical workspace with writing plan preview, regenerate chapter, compare versions, and accept chapter.
- [ ] Acceptance: technical bid text is generated chapter-by-chapter, with visible source constraints and revision history.

---

## Phase 7: Structured Chart Generation

**Objective:** Generate organization charts and related diagrams as structured specs that can be previewed, edited, rendered, and embedded.

- [ ] Create `chart_asset` table with project id, outline node id, chart type, spec json, rendered path, status, and version.
- [ ] Define JSON schemas for `org_chart`, `construction_flow`, `schedule_gantt`, `schedule_network`, `responsibility_matrix`, `risk_matrix`, `site_layout`, `quality_system`, `safety_system`, and `emergency_org`.
- [ ] Reserve `single_line_diagram` as manual-upload/reference-only in the first stage.
- [ ] Implement `ChartGenerationService` to create chart specs from constraints, personnel, schedule, roles, and user edits.
- [ ] Add validation that org chart roles required by tender constraints are present or explicitly marked unavailable.
- [ ] Add deterministic SVG rendering for first-stage chart types.
- [ ] Add DOCX embedding support through the export pipeline.
- [ ] Add frontend chart preview/editor with node text, role, edge, schedule, layout, and style editing.
- [ ] Acceptance: project organization chart and core construction diagrams are generated from editable structured specs, not opaque AI images.

---

## Phase 8-pre: Compliance Check / Rejection-Risk Scan

**Objective:** Add a deterministic compliance gate before AI review and final layout.

- [ ] Implement `ComplianceCheckService` using rule definitions, regex, thresholds, structured metadata, and explicit manual confirmations.
- [ ] Add compliance rules for bid-document composition, mandatory legal files, signature/seal placeholders, authorization validity, bid bond amount/form/deadline, qualification hard gates, certificate validity, one-paper-proof validity, personnel certificate/social-security requirements, special-operation certificates, performance 3+1 materials, substantive responses, deviation tables, copy counts, sealing requirements, platform file format, file size, naming rules, and upload-window reminders.
- [ ] Distinguish `legal_rejection`, `rejection_clause`, and discretionary risks in findings.
- [ ] Block `final_layout` while unresolved P0 findings exist.
- [ ] Require explicit user waiver for unresolved P1 findings.
- [ ] Store compliance check runs, rule versions, findings, user decisions, and closure timestamps.
- [ ] Add frontend compliance dashboard with red-line risks, evidence links, waiver controls, and rerun action.
- [ ] Add tests for P0 blocking, P1 waiver, certificate expiry using `submission_deadline + bid_validity_period`, one-paper-proof expiry, and platform file-size rule failures.
- [ ] Acceptance: critical rejection risks are deterministically detected and block downstream finalization until resolved or formally waived where allowed.

---

## Phase 8: Review, Scoring, Deviation Tables, And Revision Tracking

**Objective:** Turn AI/rule review into a closed-loop issue and scoring workflow after deterministic compliance checks.

- [ ] Extend review issue model with source constraint id, scoring item id, chapter id, revision status, user decision, and before/after version links.
- [ ] Add initial review pass covering omissions, rejection risk references, qualification gaps, standard conflicts, unsupported facts, common-sense issues, and technical-business-line mismatch.
- [ ] Add scoring review pass mapping each scoring item to response chapter, evidence, qualitative risk level, and improvement advice.
- [ ] Generate business deviation table and technical deviation table.
- [ ] Mark substantive deviations separately and require user confirmation.
- [ ] Implement issue lifecycle: open, accepted_for_fix, fixed, waived_by_user, verified, closed.
- [ ] Block final layout when unresolved P0/P1 review issues exist unless user explicitly waives allowed items.
- [ ] Add tests for issue lifecycle, final-layout blocking, score-item mapping, deviation table generation, and user waiver audit trail.
- [ ] Add frontend review dashboard with severity filters, scoring view, deviation tables, revision trace, and user confirmation controls.
- [ ] Acceptance: review findings are traceable, user decisions are recorded, and critical unresolved risks block finalization.

---

## Phase 9: Final Layout, Export, Split, Submission Checklist, And Archive

**Objective:** Produce final DOCX/PDF packages according to template, tender, and platform-manual-upload requirements, with archive metadata.

- [ ] Extend export context with cover data, confirmed outline, volumes, scoring response index, chart assets, evidence attachments, external pricing attachments, compliance closure status, and review closure status.
- [ ] Generate standard table of contents from Word heading styles.
- [ ] Generate scoring-response index after cover using scoring criteria, response chapter anchors, evidence, and final page numbers.
- [ ] Add final pagination/update pass for DOCX fields before PDF conversion.
- [ ] Support split output by volume and by chapter, then ZIP packaging.
- [ ] Generate submission-preparation checklist: file list, signature/seal list, copy-count requirements, sealing notes, platform file rules, suggested manual-upload timing, and bid-bond reminder.
- [ ] Add signature/seal placeholder export or summary report; do not implement CA signing or platform encryption in the first stage.
- [ ] Store final package metadata: template package version, constraint set version, confirmed outline version, compliance report, review report, docx path, pdf path, split package paths, external attachments, checklist path.
- [ ] Add tests for export blocking before confirmed outline, unresolved P0 compliance findings, missing critical review closure, missing required final files, and external pricing attachment inclusion.
- [ ] Add frontend final export screen with package preview, split options, checklist preview, and archive confirmation.
- [ ] Acceptance: final bid package can be downloaded as DOCX/PDF/ZIP, includes the submission-preparation checklist, and stores the exact versions used to produce it.

---

## Phase 10: Post-Bid Retrospective

**Objective:** Capture bid results and lessons learned so future bids improve.

- [ ] Create post-bid review data model with bid result, opening records, ranking, score, price metadata, competitor notes, win/loss reasons, and reusable lessons.
- [ ] Add records for evaluation clarification Q&A, candidate announcement window, complaint/challenge handling, award/loss notice, contract-signing deadline, and performance-bond status where applicable.
- [ ] Implement `PostBidReviewService` and APIs to create, update, and query retrospective records.
- [ ] Link retrospective insights to template package, business line, voltage level, scoring items, technical chapters, and evidence assets where relevant.
- [ ] Add frontend post-bid form after project is opened, submitted, archived, awarded, or not awarded.
- [ ] Add analytics queries for win rate by business line, project type, template package, scoring weakness, and missing materials.
- [ ] Acceptance: after opening, users can record whether the bid won and why, and this information is available for future template and content recommendations.

---

## Phase 11: End-To-End Frontend Workflow

**Objective:** Present the workflow as a guided workbench instead of disconnected tools.

- [ ] Add project workflow stepper: setup, upload, analysis, critical clauses, template, outline, business, technical, charts, compliance, review, export, submit/archive, post-bid.
- [ ] Disable downstream actions until required upstream gates are completed.
- [ ] Add visible counts for unresolved critical clause packages, key-field conflicts, auto-accepted sampling items, clarification impacts, unresolved outline diffs, missing business materials, unaccepted technical chapters, missing charts, unresolved compliance findings, and unresolved review issues.
- [ ] Remove `NotificationMarquee` from the app shell and remove the marquee stylesheet import so the workspace starts directly with navigation and task context.
- [ ] Add project calendar and countdowns for submission deadline, bid bond deadline, bid opening time, and suggested platform manual-upload window.
- [ ] Add business-line workspace switcher where template content differs by business line.
- [ ] Add consistent source-trace panels showing tender page, requirement text, standard clause, scoring item, platform rule, evidence asset, and generated response.
- [ ] Add safe UI state handling for long-running AI jobs and deterministic check reruns.
- [ ] Acceptance: a user can complete the full process from one project workbench without guessing the next required action.

---

## Phase 12: Verification And Release Gates

**Objective:** Prove the redesigned workflow is safe enough for real bid document generation assistance.

- [ ] Add migration tests for new tables and backward compatibility with existing projects.
- [ ] Add service tests for template selection, constraint confirmation, requirement grouping, critical confirmation levels, clarification merge, outline reconciliation, business assembly, technical generation gates, chart validation, compliance checking, review lifecycle, final export blocking, and final archive.
- [ ] Add API tests for each workflow stage.
- [ ] Add four seeded end-to-end project fixtures, one per first-stage business line.
- [ ] Add a platform-rule fixture for ECP-style manual-upload requirements without `.sgcc` structured parsing.
- [ ] Add tests for legal rejection rule detection, one-paper-proof valid/expired branches, certificate expiry at `submission_deadline + bid_validity_period`, multi-round clarification override, external pricing attachment inclusion, and P0 compliance blocking.
- [ ] Add tests for ordinary clause auto-acceptance, key-field conflict non-merge, duplicate clause grouping, grouped-source traceability, and critical confirmation blocking.
- [ ] Add a consortium fixture as P1/reserved-path coverage if the data model is implemented in Phase 5.
- [ ] Add manual acceptance script documenting the full path from new project to archived final package and submission-preparation checklist.
- [ ] Run backend tests, frontend tests, linting, and one manual export smoke test before release.
- [ ] Acceptance: all automated tests pass, manual smoke test produces a final DOCX/PDF/ZIP package with checklist, and existing template-package workflows still work.

---

## Product Decisions To Confirm Before Implementation

- [ ] Confirm canonical values for the four first-stage `business_line` options and any `sub_type` values.
- [ ] Confirm first-stage template package source for each business line: historical winning bids, expert-authored templates, or existing general templates.
- [ ] Confirm whether projects can have multiple business lines or must choose one primary business line.
- [ ] Confirm supported external pricing file formats: recommended first stage `PDF`, `XLSX`, `ZIP`, and platform-tool exported files as opaque attachments.
- [ ] Confirm social-security data source: manual upload, HR-system import, or warning-only in first stage.
- [ ] Confirm whether missing 3+1 performance materials are blocking or warning by business line and tender requirement.
- [ ] Confirm who can waive P1 findings and who can close P0 findings after remediation.
- [ ] Confirm final archive storage location and retention policy for DOCX/PDF/ZIP and readable archive packages.
- [ ] Confirm whether scoring review should show numeric estimated scores or qualitative risk levels only. Recommended first stage: qualitative risk levels plus improvement suggestions.
- [ ] Confirm platform rule maintenance ownership for ECP, South Grid, provincial platforms, and offline paper bidding.

---

## Suggested Execution Order

1. Phase 1: Project setup, platform metadata, and workflow state
2. Phase 2: Template auto selection
3. Phase 3: Tender constraint workspace and clarification merge
4. Phase 3-bis: Requirement grouping and critical confirmation workbench
5. Phase 4: Volume model, outline reconciliation, and confirmation gate
6. Phase 5: Qualification-business bid assembly
7. Phase 6: Technical bid writing
8. Phase 7: Structured chart generation
9. Phase 8-pre: Compliance check / rejection-risk scan
10. Phase 8: Review, scoring, deviation tables, and revision tracking
11. Phase 9: Final layout, export, split, submission checklist, and archive
12. Phase 10: Post-bid retrospective
13. Phase 11: End-to-end frontend workflow
14. Phase 12: Verification and release gates

Chart generation should move before review because the technical bid often references organization charts, schedule charts, site layout, quality system, and safety system. Post-bid retrospective can move later because it does not block first document generation.
