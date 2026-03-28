# Single Standard Parse Quality Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the parsing pipeline so `GB 50148-2010` reaches near-human quality with clause-number completeness as the primary success metric.

**Architecture:** Keep MinerU as the OCR/layout base, but move clause-boundary recovery out of large chapter-scope LLM extraction. Add deterministic single-document block segmentation, split normative/commentary/table parsing into separate channels, harden deduplication, and only use AI for medium/low-confidence blocks and best-effort repair.

**Tech Stack:** Python 3.12, psycopg, structlog, pytest, Docker Compose, MinerU parse assets, DeepSeek/Qwen via AI Gateway

---

## File Map

- Create: `backend/tender_backend/services/norm_service/block_segments.py`
- Create: `backend/tests/unit/test_block_segments.py`
- Create: `backend/tests/integration/test_gb50148_acceptance.py`
- Create: `docs/reports/2026-03-25-gb-50148-2010-acceptance-checklist.md`
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py`
- Modify: `backend/tender_backend/services/norm_service/scope_splitter.py`
- Modify: `backend/tender_backend/services/norm_service/structural_nodes.py`
- Modify: `backend/tender_backend/services/norm_service/ast_builder.py`
- Modify: `backend/tender_backend/services/norm_service/document_assets.py`
- Modify: `backend/tender_backend/services/norm_service/prompt_builder.py`
- Modify: `backend/tests/integration/test_standard_mineru_batch_flow.py`
- Modify: `backend/tests/unit/test_document_assets.py`
- Modify: `backend/tests/unit/test_structural_nodes.py`
- Modify: `backend/tests/unit/test_validation.py`

## Chunk 1: Lock Single-Document Acceptance

### Task 1: Write the acceptance checklist for `GB 50148-2010`

**Files:**
- Create: `docs/reports/2026-03-25-gb-50148-2010-acceptance-checklist.md`
- Create: `backend/tests/integration/test_gb50148_acceptance.py`

- [ ] **Step 1: Write the failing acceptance test skeleton**

Create a new integration test module that asserts the final single-document summary exposes:
- total clause count
- must-have clause numbers
- commentary separation
- table provenance checks

- [ ] **Step 2: Run the new acceptance test to verify it fails**

Run: `pytest backend/tests/integration/test_gb50148_acceptance.py -q`
Expected: FAIL because the acceptance fixture and helper assertions do not exist yet.

- [ ] **Step 3: Add the document-specific checklist**

Write `docs/reports/2026-03-25-gb-50148-2010-acceptance-checklist.md` with:
- target document ids and source PDF
- must-have clause regions:
  - `4.1.x`
  - `4.2.x`
  - `4.12.x`
  - `5.3.x`
  - `A.0.x`
- must-have table:
  - `表 4.2.4`
- acceptable residual warnings:
  - numbering-only warnings are allowed temporarily
- rejection criteria:
  - commentary mixed into normative path
  - missing critical clause ranges
  - broken table provenance

- [ ] **Step 4: Add the minimal acceptance assertions**

Implement the test helper with the smallest fixed expectations:
- stable lower-bound clause count above current persisted `360`
- must-have clause numbers present
- required table title/source_ref present

- [ ] **Step 5: Re-run the acceptance test**

Run: `pytest backend/tests/integration/test_gb50148_acceptance.py -q`
Expected: still FAIL, but now on real acceptance conditions rather than missing file/import errors.

- [ ] **Step 6: Commit the acceptance scaffold**

Run:
```bash
git add docs/reports/2026-03-25-gb-50148-2010-acceptance-checklist.md \
  backend/tests/integration/test_gb50148_acceptance.py
git commit -m "test: add GB50148 single-document acceptance scaffold"
```

## Chunk 2: Add Deterministic Block Segmentation

### Task 2: Introduce single-document semantic blocks before AI extraction

**Files:**
- Create: `backend/tender_backend/services/norm_service/block_segments.py`
- Create: `backend/tests/unit/test_block_segments.py`
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py`

- [ ] **Step 1: Write failing unit tests for block segmentation**

Cover:
- numbered normative clause blocks
- commentary blocks
- appendix blocks
- heading-only blocks
- table requirement blocks adjacent to `表 4.2.4`

- [ ] **Step 2: Run the segmentation tests to verify they fail**

Run: `pytest backend/tests/unit/test_block_segments.py -q`
Expected: FAIL because the block segmentation helper does not exist yet.

- [ ] **Step 3: Implement the smallest block model and builder**

Add `block_segments.py` with:
- a dataclass for block metadata
- deterministic scanners for:
  - chapter headings
  - clause numbers like `4.2.3`
  - list-item prefixes like `1、` and `1)`
  - commentary markers
  - appendix markers
  - table-title proximity

- [ ] **Step 4: Wire block building into `norm_processor.py` without changing final persistence yet**

Add a helper such as:
- `build_single_standard_blocks(...)`

Keep this phase read-only for downstream callers:
- build blocks
- log counts by block type
- do not yet replace the old extraction path

- [ ] **Step 5: Re-run the focused unit tests**

Run:
```bash
pytest backend/tests/unit/test_block_segments.py -q
pytest backend/tests/integration/test_standard_mineru_batch_flow.py -q -k "gb50148 or scope"
```
Expected: unit tests pass, integration tests still reveal old extraction behavior.

- [ ] **Step 6: Commit the segmentation layer**

Run:
```bash
git add backend/tender_backend/services/norm_service/block_segments.py \
  backend/tests/unit/test_block_segments.py \
  backend/tender_backend/services/norm_service/norm_processor.py
git commit -m "feat: add deterministic block segmentation for single-standard parsing"
```

## Chunk 3: Split Normative, Commentary, and Table Channels

### Task 3: Separate the extraction path by block type

**Files:**
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py`
- Modify: `backend/tender_backend/services/norm_service/prompt_builder.py`
- Modify: `backend/tender_backend/services/norm_service/scope_splitter.py`
- Modify: `backend/tests/integration/test_standard_mineru_batch_flow.py`

- [ ] **Step 1: Write failing integration tests for three independent channels**

Cover:
- normative blocks no longer mixed with commentary blocks
- commentary blocks keep `commentary` type
- table blocks use table-specific extraction path

- [ ] **Step 2: Run the focused integration tests to verify they fail**

Run:
```bash
pytest backend/tests/integration/test_standard_mineru_batch_flow.py -q -k "commentary or table or channel"
```
Expected: FAIL because extraction is still chapter-scope oriented.

- [ ] **Step 3: Implement channel-specific dispatch**

In `norm_processor.py`:
- route `normative_clause_block` to normative extraction
- route `commentary_block` to commentary extraction
- route `table_requirement_block` to table extraction

In `prompt_builder.py`:
- keep prompt templates separate
- shrink normative prompt input to a block or a very small batch

In `scope_splitter.py`:
- ensure table scopes never merge back into paragraph scopes

- [ ] **Step 4: Re-run the focused integration tests**

Run:
```bash
pytest backend/tests/integration/test_standard_mineru_batch_flow.py -q -k "commentary or table or channel"
```
Expected: PASS with independent channel behavior.

- [ ] **Step 5: Commit the channel split**

Run:
```bash
git add backend/tender_backend/services/norm_service/norm_processor.py \
  backend/tender_backend/services/norm_service/prompt_builder.py \
  backend/tender_backend/services/norm_service/scope_splitter.py \
  backend/tests/integration/test_standard_mineru_batch_flow.py
git commit -m "feat: split single-standard extraction into normative commentary and table channels"
```

## Chunk 4: Add Confidence Routing And Shrink AI Scope

### Task 4: Route high-confidence blocks away from heavy AI extraction

**Files:**
- Modify: `backend/tender_backend/services/norm_service/block_segments.py`
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py`
- Modify: `backend/tests/unit/test_block_segments.py`
- Modify: `backend/tests/integration/test_standard_mineru_batch_flow.py`

- [ ] **Step 1: Write failing tests for confidence routing**

Cover:
- high-confidence numbered blocks parsed without chapter-scope AI
- medium-confidence blocks still sent to AI
- low-confidence blocks remain eligible for repair

- [ ] **Step 2: Run the focused tests to verify they fail**

Run:
```bash
pytest backend/tests/unit/test_block_segments.py backend/tests/integration/test_standard_mineru_batch_flow.py -q -k "confidence or routing"
```
Expected: FAIL because no routing layer exists yet.

- [ ] **Step 3: Implement block confidence**

Add a simple confidence model based on:
- clear clause numbering
- stable page anchors
- heading-parent availability
- lack of local duplicate conflicts

Routing rules:
- `high`: deterministic parse first
- `medium`: small-block LLM normalization
- `low`: LLM fallback plus optional repair

- [ ] **Step 4: Replace large chapter-scope extraction in the single-document path**

In `norm_processor.py`, for the experimental path:
- stop constructing AI scopes from whole chapter text
- iterate over block-sized units instead
- keep retry behavior local to a block, not a chapter

- [ ] **Step 5: Re-run the focused routing tests**

Run:
```bash
pytest backend/tests/unit/test_block_segments.py backend/tests/integration/test_standard_mineru_batch_flow.py -q -k "confidence or routing"
```
Expected: PASS and visibly smaller extraction units in logs.

- [ ] **Step 6: Commit the confidence routing**

Run:
```bash
git add backend/tender_backend/services/norm_service/block_segments.py \
  backend/tender_backend/services/norm_service/norm_processor.py \
  backend/tests/unit/test_block_segments.py \
  backend/tests/integration/test_standard_mineru_batch_flow.py
git commit -m "feat: add confidence routing for single-standard parse blocks"
```

## Chunk 5: Harden Deduplication And Parent Resolution

### Task 5: Stop dropping legitimate clauses in dense regions

**Files:**
- Modify: `backend/tender_backend/services/norm_service/ast_builder.py`
- Modify: `backend/tender_backend/services/norm_service/structural_nodes.py`
- Modify: `backend/tests/integration/test_standard_mineru_batch_flow.py`
- Modify: `backend/tests/unit/test_structural_nodes.py`

- [ ] **Step 1: Write failing tests for dense-region dedupe**

Cover:
- same clause number but different source/text is not dropped
- repeated ancestor headings emitted by adjacent blocks are dropped
- `4.1.x`, `4.2.x`, `5.3.x`, `A.0.x` preserve parent relationships

- [ ] **Step 2: Run the focused tests to verify they fail**

Run:
```bash
pytest backend/tests/unit/test_structural_nodes.py backend/tests/integration/test_standard_mineru_batch_flow.py -q -k "dedupe or parent"
```
Expected: FAIL because current dedupe identity is too coarse.

- [ ] **Step 3: Implement conservative dedupe identity**

Update `ast_builder.py` to combine:
- `clause_type`
- normalized `clause_no`
- inferred parent key or parent clause number
- `source_ref`
- normalized text hash

Update `structural_nodes.py` so parent inference remains stable even when a block starts from a mid-level clause.

- [ ] **Step 4: Re-run the focused dedupe tests**

Run:
```bash
pytest backend/tests/unit/test_structural_nodes.py backend/tests/integration/test_standard_mineru_batch_flow.py -q -k "dedupe or parent"
```
Expected: PASS with fewer false duplicate removals.

- [ ] **Step 5: Commit the dedupe hardening**

Run:
```bash
git add backend/tender_backend/services/norm_service/ast_builder.py \
  backend/tender_backend/services/norm_service/structural_nodes.py \
  backend/tests/unit/test_structural_nodes.py \
  backend/tests/integration/test_standard_mineru_batch_flow.py
git commit -m "fix: harden clause dedupe and parent resolution for dense standard regions"
```

## Chunk 6: Verify Real-Document Acceptance

### Task 6: Run focused regressions and a real rerun against the checklist

**Files:**
- Modify: `backend/tests/integration/test_gb50148_acceptance.py`
- Modify: `docs/reports/2026-03-25-gb-50148-2010-acceptance-checklist.md`

- [ ] **Step 1: Run the focused regression suite**

Run:
```bash
pytest \
  backend/tests/integration/test_standard_mineru_batch_flow.py \
  backend/tests/integration/test_gb50148_acceptance.py \
  backend/tests/unit/test_block_segments.py \
  backend/tests/unit/test_document_assets.py \
  backend/tests/unit/test_structural_nodes.py \
  backend/tests/unit/test_validation.py -q
```
Expected: PASS.

- [ ] **Step 2: Run a real rerun for `GB 50148-2010`**

Run inside `tmux`:
```bash
docker compose --env-file infra/.env -f infra/docker-compose.yml exec -T backend python - <<'PY'
import json
import os
from uuid import UUID
import psycopg
from tender_backend.services.norm_service.norm_processor import process_standard_ai

standard_id = UUID("ff2ddb6c-ba8e-4e42-862f-e75d5824437a")
document_id = "e3003181-042a-44da-ad67-44615d7d25f2"
conn = psycopg.connect(os.environ["DATABASE_URL"])
try:
    summary = process_standard_ai(conn, standard_id=standard_id, document_id=document_id)
    conn.commit()
    print(json.dumps(summary, ensure_ascii=False))
finally:
    conn.close()
PY
```
Expected:
- successful completion
- clause count above the acceptance lower bound
- must-have clause numbers present
- `表 4.2.4` provenance preserved
- repair timeout, if any, does not fail persistence

- [ ] **Step 3: Compare against the acceptance checklist**

Record:
- total clauses
- must-have clause presence
- commentary separation
- table attribution
- residual warnings

- [ ] **Step 4: Update the checklist with the verified achieved baseline**

Refine the document with:
- achieved stable count band
- remaining known warnings
- outstanding failure points, if any

- [ ] **Step 5: Commit the acceptance verification**

Run:
```bash
git add backend/tests/integration/test_gb50148_acceptance.py \
  docs/reports/2026-03-25-gb-50148-2010-acceptance-checklist.md
git commit -m "test: verify GB50148 single-document acceptance"
```

## Rollout Notes

- This plan intentionally optimizes one document first and should stay isolated from broad “all-standard” heuristics until acceptance is met.
- If a helper becomes document-specific, keep it explicit and measurable rather than silently embedding assumptions into generic code paths.
- Do not include unrelated `frontend/package-lock.json` changes in parsing commits.

## Review Note

- Subagent plan review is skipped here because delegation was not explicitly requested in this session.
