# Cross-Standard Parse Quality Closure Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Continue parse-quality closure using a cross-standard acceptance loop that keeps the valid lessons from the GB50148 documents while replacing the outdated single-document count-first rubric.

**Architecture:** Reuse the existing `norm_service` parsing pipeline, GB50148 acceptance scaffolding, and DB inspection loop, but shift the current closure criteria from raw `total_count` to structural consistency: OCR section shape vs persisted clause shape, anchor/provenance integrity, dedup correctness, and scope-local anomalies. Keep low-risk global stabilizers from the GB50148 documents (`temperature=0.0`, stronger dedupe identity) and apply TDD only to demonstrated cross-standard defects.

**Tech Stack:** Python 3.12, pytest, psycopg/PostgreSQL, Docker Compose, existing `norm_service` pipeline, persisted real-sample inspection SQL

---

## Effective Material Extracted From The Two 2026-03-31 Documents

Keep and reuse:
- repeatable DB inspection and persisted-acceptance loop
- block-path and structural-routing mindset
- page-anchor / table-provenance guardrails
- low-risk stability work: `temperature -> 0.0`
- stronger dedupe identity using more than `{clause_type}:{node_key}`

Do not carry forward as primary closure criteria:
- `GB50148` single-document total-count target bands
- commentary target counts as a project-wide finish line
- treating `214` or similar historical totals from other standards as generic baselines

Current evidence that changes the plan:
- `GB50147` latest `429` includes real cleanup of prior misattached clauses; raw count alone is no longer a reliable failure signal
- `GB50150` latest `844` is structurally explainable by OCR `document_section` shape (`350` clause-like sections + `657` numbered-item sections); `214` is not a trustworthy target
- current project-level closure should focus on true anomalies: missing anchors, null clause numbers, wrong `source_label`/scope attachment, appendix/table-only false extraction, and duplicate identity collisions

## Chunk 1: Replace Count-First Acceptance With Structural Acceptance

### Task 1: Create a cross-standard persisted acceptance scaffold

**Files:**
- Create: `backend/tests/integration/test_parse_quality_persisted_acceptance.py`
- Create: `docs/reports/2026-03-31-parse-quality-closure-checklist.md`

- [ ] **Step 1: Write the failing persisted acceptance test scaffold**

Add snapshot-style assertions for the currently active closure standards:

```python
def assert_standard_shape(snapshot: dict) -> None:
    assert snapshot["missing_anchor_count"] == 0
    assert snapshot["table_missing_source_ref_count"] == 0
    assert snapshot["null_clause_no_count"] <= snapshot["null_clause_no_budget"]
    assert snapshot["duplicate_identity_count"] <= snapshot["duplicate_identity_budget"]
```

```python
def test_gb50147_persisted_shape() -> None:
    snapshot = load_snapshot("GB 50147-2010")
    assert_standard_shape(snapshot)
    assert "5.1.4" in snapshot["must_have_clause_nos"]
```

```python
def test_gb50150_persisted_shape() -> None:
    snapshot = load_snapshot("GB 50150-2016")
    assert_standard_shape(snapshot)
    assert snapshot["ocr_clause_like_sections"] >= 300
```

- [ ] **Step 2: Run the new test file to verify it fails**

Run:

```bash
/home/palmtom/projects/tender/.venv/bin/python -m pytest \
  backend/tests/integration/test_parse_quality_persisted_acceptance.py -q
```

Expected: FAIL because the acceptance helper and persisted fixtures do not exist yet.

- [ ] **Step 3: Add the minimal persisted fixtures and helper**

Encode the current known-good structural checks instead of raw total targets:
- `missing_anchor_count`
- `table_missing_source_ref_count`
- `null_clause_no_count`
- OCR section shape summary
- must-have representative clause numbers
- top heavy `source_label` list for anomaly review

- [ ] **Step 4: Re-run the test to verify the failure is meaningful**

Run the same command from Step 2.

Expected: FAIL on the actual structural anomaly budget, not on missing fixtures/imports.

### Task 2: Document the reproducible inspection loop for current closure work

**Files:**
- Modify: `docs/reports/2026-03-31-parse-quality-closure-checklist.md`

- [ ] **Step 1: Add the exact SQL checks used in current triage**

Document compact, repeatable commands for:
- latest `standard` row lookup by code
- persisted clause metrics by `standard_id`
- OCR `document_section` shape summary
- top heavy `source_label` scopes
- duplicate `(clause_no, node_type, node_label)` rows

- [ ] **Step 2: Record the current interpretation rules**

Write explicit notes:
- `total_count` is secondary evidence only
- `GB50147` requires “real loss vs corrected redistribution” analysis
- `GB50150` must be compared against OCR section shape, not the old `214` baseline

- [ ] **Step 3: Verify the checklist is enough to rerun the analysis**

Run the documented SQL once and confirm the output format is reusable without session-specific context.

## Chunk 2: Apply The Two Still-Valid Low-Risk Stabilizers

### Task 3: Reduce LLM variance and strengthen dedupe identity

**Files:**
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py`
- Modify: `backend/tender_backend/services/norm_service/ast_builder.py`
- Modify: `backend/tests/integration/test_standard_mineru_batch_flow.py`
- Modify: `backend/tests/unit/test_ast_builder.py`

- [ ] **Step 1: Write the failing tests**

Add one test for each stabilizer:

```python
def test_call_ai_gateway_uses_zero_temperature(...) -> None:
    payload = capture_gateway_payload(...)
    assert payload["temperature"] == 0.0
```

```python
def test_deduplicate_entries_distinguishes_same_node_key_from_different_source_labels() -> None:
    entries = [
        {"clause_type": "normative", "node_key": "A.0.1", "source_label": "附录A", ...},
        {"clause_type": "normative", "node_key": "A.0.1", "source_label": "正文引用", ...},
    ]
    assert len(deduplicate_entries(entries)) == 2
```

- [ ] **Step 2: Run only the new targeted tests**

Run:

```bash
/home/palmtom/projects/tender/.venv/bin/python -m pytest \
  backend/tests/unit/test_ast_builder.py \
  backend/tests/integration/test_standard_mineru_batch_flow.py -q
```

Expected: FAIL on the new assertions.

- [ ] **Step 3: Implement the minimal code changes**

Apply exactly these changes:
- set `_call_ai_gateway()` payload `temperature` from `0.1` to `0.0`
- include `source_label` in dedupe identity in `deduplicate_entries()`
- include the same dimension anywhere nested AST dedupe still collapses cross-scope nodes

- [ ] **Step 4: Re-run the targeted tests to verify they pass**

Run the same command from Step 2.

Expected: PASS.

## Chunk 3: Lock One Demonstrated Cross-Standard Defect At A Time

### Task 4: Fix one real GB50147 anomaly using TDD, not count chasing

**Files:**
- Modify: `backend/tests/integration/test_standard_mineru_batch_flow.py`
- Modify: one of:
  - `backend/tender_backend/services/norm_service/block_segments.py`
  - `backend/tender_backend/services/norm_service/norm_processor.py`
  - `backend/tender_backend/services/norm_service/outline_rebuilder.py`
  - `backend/tender_backend/services/norm_service/structural_nodes.py`

- [ ] **Step 1: Choose one anomaly that is still wrong after redistribution review**

Valid candidates:
- clause content attached to the wrong `source_label`
- parent clause replaced by child clauses when the parent should remain
- numbered list items promoted across chapter boundaries
- appendix/table-derived rows leaking into unrelated clauses

Do not choose “count went down” by itself.

- [ ] **Step 2: Write the smallest failing regression test**

Example shape:

```python
def test_single_standard_blocks_do_not_merge_items_from_following_chapter_into_previous_clause() -> None:
    sections = [...]
    blocks = build_single_standard_blocks(sections, [])
    assert blocks_for("5.1.4") == expected_items
```

or

```python
def test_outline_marker_filter_does_not_drop_real_leaf_scope_after_list_context() -> None:
    markers = collect_outline_markers_from_pages(pages)
    assert [m.section_code for m in markers] == [...]
```

- [ ] **Step 3: Run the targeted failing test**

Run only the new regression test with:

```bash
/home/palmtom/projects/tender/.venv/bin/python -m pytest \
  backend/tests/integration/test_standard_mineru_batch_flow.py -q
```

Expected: FAIL on the exact anomaly.

- [ ] **Step 4: Implement the minimal fix at the source**

Fix the boundary that actually causes the anomaly:
- section normalization
- block merging
- outline leaf construction
- or AST repair

Do not bundle acceptance refactors or unrelated cleanup.

- [ ] **Step 5: Re-run the targeted test and the focused parse slice**

Run:

```bash
/home/palmtom/projects/tender/.venv/bin/python -m pytest \
  backend/tests/integration/test_standard_mineru_batch_flow.py \
  backend/tests/unit/test_structural_nodes.py \
  backend/tests/unit/test_ast_builder.py -q
```

Expected: PASS.

### Task 5: Keep GB50150 on a section-shaped acceptance path

**Files:**
- Modify: `backend/tests/integration/test_parse_quality_persisted_acceptance.py`
- Modify: `docs/reports/2026-03-31-parse-quality-closure-checklist.md`

- [ ] **Step 1: Add GB50150-specific acceptance rules that reflect OCR shape**

Assert:
- no missing anchors
- appendix/table-only empty scopes do not emit parse-failed noise
- `duplicate_identity_count` stays within budget
- top heavy scopes are reviewed explicitly
- persisted clause structure is explainable by OCR sections

Do not assert a raw total near `214`.

- [ ] **Step 2: Record the current heavy-scope review list**

Seed the checklist with currently heavy scopes such as:
- `4 同步发电机及调相机 (1/2)`
- `8 电力变压器 (1/3)`
- `10 互感器 (1/2)`
- `12 六氟化硫断路器`
- `17 电力电缆线路`

- [ ] **Step 3: Only open a code fix if one heavy scope shows a real structural error**

Acceptable reasons to open a fix:
- duplicate children under the same clause with conflicting parentage
- false appendix/table extraction
- wrong clause/source_label attachment
- null clause numbers above the agreed budget

Not acceptable:
- “the total is larger than an old run” without a demonstrated structural fault

## Chunk 4: Verification And Closure Criteria

### Task 6: Verify with focused tests and real reruns

**Files:**
- Test: `backend/tests/integration/test_standard_mineru_batch_flow.py`
- Test: `backend/tests/integration/test_parse_quality_persisted_acceptance.py`
- Test: `backend/tests/unit/test_ast_builder.py`
- Test: `backend/tests/unit/test_structural_nodes.py`
- Test: `backend/tests/unit/test_document_assets.py`
- Test: `backend/tests/unit/test_validation.py`
- Modify: `docs/reports/2026-03-31-parse-quality-closure-checklist.md`

- [ ] **Step 1: Run the focused regression slice**

Run:

```bash
/home/palmtom/projects/tender/.venv/bin/python -m pytest \
  backend/tests/integration/test_standard_mineru_batch_flow.py \
  backend/tests/integration/test_parse_quality_persisted_acceptance.py \
  backend/tests/unit/test_ast_builder.py \
  backend/tests/unit/test_structural_nodes.py \
  backend/tests/unit/test_document_assets.py \
  backend/tests/unit/test_validation.py -q
```

Expected: PASS.

- [ ] **Step 2: Re-run the active real samples**

Re-run:
- `GB 50147-2010`
- `GB 50150-2016`

Prefer Docker + `tmux`, then persist the resulting `standard_id` values in the checklist.

- [ ] **Step 3: Compare rerun output against the structural checklist**

Record:
- `processing_status`
- missing anchors / missing table provenance
- null clause count
- duplicate identity count
- representative clause presence
- heavy-scope review outcome
- whether any remaining anomalies are understood and accepted

- [ ] **Step 4: Stop only when the remaining issues are understood**

Closure for this batch requires all of:
- focused regressions pass
- reruns complete
- no anchor/provenance regressions
- no unexplained structural anomalies in the heavy scopes
- remaining count differences are documented as redistribution, OCR-shape effects, or accepted residual issues

## Not In Scope For This Batch

- generalized prompt redesign for all block types
- removing the single-standard experiment gate
- broad performance optimization
- reintroducing a project-wide count-only acceptance band

Plan complete and saved to `docs/superpowers/plans/2026-03-31-cross-standard-parse-quality-closure-plan.md`. Ready to execute?
