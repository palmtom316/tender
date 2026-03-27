# GB50148 Outline Rebuild Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild a clean normative outline for GB50148 from raw page text so viewer mounting, validation parent codes, and page anchors stop depending on polluted `document_section` rows.

**Architecture:** Add a page-text outline rebuilder that scans normalized page markdown, drops TOC/commentary pages, and extracts only real chapter/section headings. Feed the rebuilt outline into `process_standard_ai()` for validation and into `StandardRepository.get_viewer_tree()` for outline mounting, while keeping `document_section` as the text provenance source.

**Tech Stack:** Python 3.12, pytest, psycopg, existing `norm_service` document asset helpers.

---

## Chunk 1: Outline Rebuilder

### Task 1: Add failing tests for page-text outline extraction

**Files:**
- Create: `backend/tests/unit/test_outline_rebuilder.py`
- Modify: `backend/tender_backend/services/norm_service/outline_rebuilder.py`

- [ ] **Step 1: Write the failing tests**

Add tests covering:
- raw page markdown with clean headings (`1 总则`, `4.8 本体及附件安装`)
- TOC page exclusion
- commentary boundary stop
- item lines like `1 包装及密封应良好。` not being promoted to outline headings

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest backend/tests/unit/test_outline_rebuilder.py -q`

- [ ] **Step 3: Write minimal implementation**

Create a helper module that:
- normalizes page lines
- skips obvious OCR marker lines and footer noise
- ignores TOC/commentary pages
- extracts chapter/section headings with code depth `1` or `2`
- returns deduped outline rows with page anchors

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest backend/tests/unit/test_outline_rebuilder.py -q`

## Chunk 2: Validation and Viewer Wiring

### Task 2: Use rebuilt outline codes in `process_standard_ai`

**Files:**
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py`
- Test: `backend/tests/integration/test_standard_mineru_batch_flow.py`

- [ ] **Step 1: Write the failing test**

Add a test where raw `document_section` codes are polluted or missing, but raw page markdown contains a clean section heading like `4.8 本体及附件安装`; assert `validate_clauses(..., outline_clause_nos=...)` receives `4.8`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest backend/tests/integration/test_standard_mineru_batch_flow.py -k rebuilt_outline -q`

- [ ] **Step 3: Write minimal implementation**

Build a `DocumentAsset` once in `process_standard_ai()`, derive rebuilt outline codes from its pages, and prefer those codes over raw `document_section` codes for validation.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest backend/tests/integration/test_standard_mineru_batch_flow.py -k rebuilt_outline -q`

### Task 3: Use rebuilt outline tree in viewer projection

**Files:**
- Modify: `backend/tender_backend/db/repositories/standard_repo.py`
- Test: `backend/tests/integration/test_standard_repo.py`

- [ ] **Step 1: Write the failing test**

Add a viewer-tree test where `document_section` rows contain only TOC-style or polluted headings, but raw page markdown contains clean body headings; assert viewer roots/sections come from rebuilt outline and mount AI clauses under it.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest backend/tests/integration/test_standard_repo.py -k rebuilt_outline -q`

- [ ] **Step 3: Write minimal implementation**

In `get_viewer_tree()`, build a `DocumentAsset`, derive rebuilt outline rows from page text, and prefer them over polluted `document_section` rows; keep existing fallback behavior when rebuilt outline is empty.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest backend/tests/integration/test_standard_repo.py -k rebuilt_outline -q`

## Chunk 3: Regression and Real Sample

### Task 4: Run focused regression tests

**Files:**
- Test: `backend/tests/unit/test_outline_rebuilder.py`
- Test: `backend/tests/integration/test_standard_mineru_batch_flow.py`
- Test: `backend/tests/integration/test_standard_repo.py`
- Test: `backend/tests/unit/test_ast_builder.py`
- Test: `backend/tests/unit/test_structural_nodes.py`
- Test: `backend/tests/unit/test_validation.py`

- [ ] **Step 1: Run focused regression**

Run:
```bash
.venv/bin/pytest \
  backend/tests/unit/test_outline_rebuilder.py \
  backend/tests/integration/test_standard_mineru_batch_flow.py \
  backend/tests/integration/test_standard_repo.py \
  backend/tests/unit/test_ast_builder.py \
  backend/tests/unit/test_structural_nodes.py \
  backend/tests/unit/test_validation.py -q
```

- [ ] **Step 2: Verify real sample in Docker**

Re-run `process_standard_ai()` for `aca10105-4d82-4c48-a925-1f5b50519695` / `7302f4b0-9ded-4228-83c1-76e0e3fc1e68`, then inspect:
- status
- total clause count
- remaining warnings
- viewer top-level and `4.8/4.10` mounting

- [ ] **Step 3: Iterate if quality still not acceptable**

If real-sample viewer/validation still shows polluted outline or missing section parents, add the next failing test and continue the same TDD loop without waiting for user confirmation.
