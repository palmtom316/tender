# GB50148 Acceptance And Anchor Closure Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn GB50148 parse-quality closure into a measurable loop by first capturing the current real-sample acceptance gap, then fixing the first page-anchor or table-provenance defect exposed by that evidence.

**Architecture:** Reuse the existing single-standard experimental path in `norm_processor.py` and the GB50148 acceptance scaffold, but add a repeatable inspection path for the persisted real sample. Once the top failing quality signal is identified, lock it with a failing test, apply the smallest fix in the norm-service pipeline, and rerun focused regressions.

**Tech Stack:** Python 3.12, psycopg, pytest, existing `norm_service` single-standard path, Docker Compose PostgreSQL/OpenSearch, GB50148 acceptance artifacts

---

## Chunk 1: Capture The Real-Sample Gap

### Task 1: Record current GB50148 persisted acceptance shape

**Files:**
- Create: `backend/tests/integration/test_gb50148_persisted_acceptance.py`
- Modify: `docs/reports/2026-03-25-gb-50148-2010-acceptance-checklist.md`

- [ ] **Step 1: Write the failing persisted acceptance test**

Create a focused integration-style test helper that can validate a persisted GB50148 snapshot shape:

```python
def assert_persisted_gb50148_gap(snapshot: dict) -> None:
    assert snapshot["total_clauses"] >= 370
    assert snapshot["missing_page_anchor_count"] == 0
    assert snapshot["missing_table_source_ref_count"] == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
/home/palmtom/projects/tender/.venv/bin/python -m pytest \
  backend/tests/integration/test_gb50148_persisted_acceptance.py -q
```

Expected: FAIL because the persisted acceptance helper and fixture do not exist yet.

- [ ] **Step 3: Add the minimal persisted acceptance fixture**

Encode the latest known-realistic bad snapshot using the current GB50148 evidence, including:
- total clause count below target when applicable
- missing page anchors
- missing table provenance if present
- critical clause/table presence

- [ ] **Step 4: Re-run the test to verify the failure is meaningful**

Run:

```bash
/home/palmtom/projects/tender/.venv/bin/python -m pytest \
  backend/tests/integration/test_gb50148_persisted_acceptance.py -q
```

Expected: FAIL on the actual acceptance gap, not on import/setup errors.

### Task 2: Add a reproducible DB inspection command for GB50148

**Files:**
- Modify: `docs/reports/2026-03-25-gb-50148-2010-acceptance-checklist.md`
- Modify: `docs/skills/standard-parse-recovery/SKILL.md`

- [ ] **Step 1: Document the exact SQL or CLI inspection recipe**

Add a compact reproducible inspection sequence that reports:
- total clause count
- normative/commentary counts
- clauses with `page_start` missing or invalid
- table clauses with missing `source_ref`
- presence of `4.1.2`, `4.2.4`, `4.12.1`, `5.3.6`, `A.0.2`

- [ ] **Step 2: Verify the documented inspection command works locally**

Run the documented command against the local PostgreSQL container and copy the result pattern into the report note.

Expected: a stable output format that can be reused after each rerun or fix.

## Chunk 2: Fix The First Provenance Defect With TDD

### Task 3: Lock the first real defect with a failing test

**Files:**
- Modify: `backend/tests/unit/test_document_assets.py`
- Modify: `backend/tests/unit/test_validation.py`
- Modify: `backend/tender_backend/services/norm_service/document_assets.py`
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py`

- [ ] **Step 1: Choose the top defect from the DB inspection**

Choose exactly one of:
- missing/invalid `page_start` / `page_end`
- missing table `source_ref`
- wrong page propagation from deterministic block/scope output

- [ ] **Step 2: Write the smallest failing test for that defect**

Example shape:

```python
def test_build_document_asset_backfills_page_anchor_from_matching_page_window() -> None:
    asset = build_document_asset(...)
    assert asset.tables[0].page_start == 18
    assert asset.tables[0].page_end == 18
```

or

```python
def test_process_scope_entries_inherit_valid_scope_anchor_when_entry_anchor_missing() -> None:
    entries = _process_scope_with_retries(...)
    assert entries[0]["page_start"] == 18
```

- [ ] **Step 3: Run the targeted test to verify it fails**

Run only the new failing test with:

```bash
/home/palmtom/projects/tender/.venv/bin/python -m pytest \
  backend/tests/unit/test_document_assets.py -q
```

or:

```bash
/home/palmtom/projects/tender/.venv/bin/python -m pytest \
  backend/tests/unit/test_validation.py -q
```

Expected: FAIL for the exact provenance/anchor defect.

- [ ] **Step 4: Implement the minimal fix**

Apply the smallest change that restores provenance at the source:
- prefer asset/source-ref reconciliation before relaxing validation
- keep changes inside `document_assets.py` or `norm_processor.py` unless the test proves a broader boundary issue
- do not bundle unrelated refactors

- [ ] **Step 5: Re-run the targeted test to verify it passes**

Run the same command from Step 3.

Expected: PASS.

## Chunk 3: Focused Regression And Runtime Check

### Task 4: Verify the fix across the parsing quality slice

**Files:**
- Test: `backend/tests/integration/test_standard_mineru_batch_flow.py`
- Test: `backend/tests/unit/test_document_assets.py`
- Test: `backend/tests/unit/test_structural_nodes.py`
- Test: `backend/tests/unit/test_validation.py`
- Test: `backend/tests/integration/test_gb50148_acceptance.py`
- Test: `backend/tests/integration/test_gb50148_persisted_acceptance.py`

- [ ] **Step 1: Run focused regression**

Run:

```bash
/home/palmtom/projects/tender/.venv/bin/python -m pytest \
  backend/tests/integration/test_standard_mineru_batch_flow.py \
  backend/tests/unit/test_document_assets.py \
  backend/tests/unit/test_structural_nodes.py \
  backend/tests/unit/test_validation.py \
  backend/tests/integration/test_gb50148_acceptance.py \
  backend/tests/integration/test_gb50148_persisted_acceptance.py -q
```

Expected: PASS.

- [ ] **Step 2: Re-run the DB inspection**

Run the documented inspection command from Chunk 1 and compare:
- missing page anchors
- missing table provenance
- clause totals and critical clause/table presence

- [ ] **Step 3: Decide whether to iterate or stop**

If the top defect count drops but acceptance still fails:
- write the next failing test for the next-highest defect
- repeat Chunk 2 with the new single defect

If the persisted acceptance gap is closed enough for this batch:
- record the before/after numbers in the checklist
- stop without opening a broader refactor
