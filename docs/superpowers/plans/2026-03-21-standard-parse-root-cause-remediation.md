# Standard Parse Root-Cause Remediation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize standard PDF parsing by preserving MinerU structure, separating OCR from AI clause extraction, and reducing clause-extraction scope size and noise.

**Architecture:** Keep `MinerU` as the hosted OCR/parser provider, but stop degrading standard parsing to `full.md`-only processing. Add a standard-oriented parse asset layer for page/table/raw payload persistence, then split AI extraction into `normalize -> segment -> extract -> validate` stages with table/body separation and per-scope retries.

**Tech Stack:** FastAPI, psycopg, Alembic, PostgreSQL JSONB, pytest, structlog

---

## File Map

- Modify: `backend/tender_backend/db/alembic/versions/0001_initial_schema.py` or add a new follow-up migration for parse asset columns/tables
- Modify: `backend/tender_backend/services/parse_service/parser.py` - persist raw pages/tables/sections for standards
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py` - split OCR asset loading, normalization, segmentation, AI extraction, validation
- Modify: `backend/tender_backend/services/norm_service/scope_splitter.py` - add explicit body/table segmentation helpers
- Modify: `backend/tender_backend/db/repositories/standard_repo.py` - read parse assets for viewer/debug/repair flows
- Modify: `backend/tender_backend/services/norm_service/standard_processing_scheduler.py` - preserve OCR/AI split and enable AI-only retry semantics
- Modify: `backend/tender_backend/workflows/standard_ingestion.py` - orchestrate `ensure_standard_ocr -> build_segments -> extract_clauses -> index`
- Test: `backend/tests/integration/test_standard_mineru_batch_flow.py`
- Test: `backend/tests/integration/test_standard_processing_scheduler.py`
- Test: `backend/tests/integration/test_standard_repo.py`
- Test: `backend/tests/unit/test_standard_tree_builder.py`

## Chunk 1: Persist Standard Parse Assets

### Task 1: Add migration for raw parse assets

**Files:**
- Create: `backend/tender_backend/db/alembic/versions/0011_standard_parse_assets.py`
- Modify: `backend/tests/integration/test_standard_repo.py`

- [ ] Add a failing repository/integration test that expects standard parse data to retain:
  - raw page payload
  - page text/markdown
  - table raw json
  - parser source metadata
- [ ] Run the focused failing test.
- [ ] Create `0011_standard_parse_assets.py` with the smallest schema needed:
  - add `parser_name`, `parser_version`, `raw_payload` to `document`
  - add `raw_json`, `text_source`, `sort_order` to `document_section`
  - add `table_html`, `page_start`, `page_end`, `table_title` to `document_table`
  - create `document_page_asset` if current `document_section`/`document_table` is too cramped for page-level payloads
- [ ] Run migration tests or schema bootstrap tests.
- [ ] Commit migration and test.

### Task 2: Persist MinerU page and table structure instead of only `full.md`

**Files:**
- Modify: `backend/tender_backend/services/parse_service/parser.py`
- Modify: `backend/tests/integration/test_standard_mineru_batch_flow.py`

- [ ] Add a failing test proving `_parse_via_mineru()` persists page/table/raw payloads for standards, not just normalized sections.
- [ ] Run the focused failing test.
- [ ] Extend persistence helpers so standard parsing writes:
  - normalized sections for downstream compatibility
  - raw page assets for debugging and repair
  - table assets with original `raw_json` and, when available, html/markdown fragments
- [ ] Keep existing callers working for tender document parsing.
- [ ] Re-run the focused test and existing MinerU batch flow tests.
- [ ] Commit parser persistence changes.

## Chunk 2: Refactor `norm_processor` Into Stages

### Task 3: Split OCR loading from AI extraction

**Files:**
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py`
- Modify: `backend/tests/integration/test_standard_mineru_batch_flow.py`

- [ ] Add failing tests for two invariants:
  - existing OCR assets skip MinerU re-run
  - AI retry can run from persisted OCR assets only
- [ ] Run the focused failing tests.
- [ ] Extract helpers from `norm_processor.py`:
  - `load_standard_parse_assets(...)`
  - `normalize_standard_sections(...)`
  - `build_standard_segments(...)`
  - `extract_clause_entries_from_segments(...)`
  - `persist_standard_clauses(...)`
- [ ] Keep `ensure_standard_ocr()` responsible only for OCR presence.
- [ ] Keep `process_standard_ai()` responsible only for AI-stage extraction over stored assets.
- [ ] Re-run `test_standard_mineru_batch_flow.py`.
- [ ] Commit the staged refactor.

### Task 4: Separate body segments from table segments

**Files:**
- Modify: `backend/tender_backend/services/norm_service/scope_splitter.py`
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py`
- Modify: `backend/tests/integration/test_standard_mineru_batch_flow.py`

- [ ] Add failing tests for:
  - body paragraphs and html tables becoming different segment types
  - large tables splitting by row while preserving valid table wrappers
  - commentary/body separation still working
- [ ] Run the focused failing tests.
- [ ] Introduce explicit segment types:
  - `normative_text`
  - `commentary_text`
  - `table`
- [ ] Ensure `rebalance_scopes()` never merges table segments back into paragraph scopes.
- [ ] Update AI prompts/call path so table segments use a table-specific extraction prompt or bypass path.
- [ ] Re-run segmentation and MinerU flow tests.
- [ ] Commit segment separation changes.

## Chunk 3: Improve Section Normalization And Extraction Stability

### Task 5: Harden preprocessing against TOC/front matter/order drift

**Files:**
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py`
- Modify: `backend/tender_backend/services/norm_service/layout_compressor.py`
- Modify: `backend/tests/integration/test_standard_mineru_batch_flow.py`

- [ ] Add failing tests for:
  - TOC/front matter removal
  - preserving input order when page anchors are missing
  - heading-only nodes surviving normalization
  - clause sentences not becoming chapter boundaries
- [ ] Run the focused failing tests.
- [ ] Tighten normalization rules without dropping legitimate short clauses or units.
- [ ] Preserve page-anchored order when available and ingest order when not.
- [ ] Keep heading-only structural rows so viewer and clause tree can still anchor correctly.
- [ ] Re-run the full MinerU flow test module.
- [ ] Commit preprocessing hardening.

### Task 6: Make AI extraction small-scope and locally retryable

**Files:**
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py`
- Modify: `backend/tests/integration/test_standard_mineru_batch_flow.py`
- Modify: `backend/tests/integration/test_standard_processing_scheduler.py`

- [ ] Add failing tests for:
  - timeout on a large scope causes local rebalance only
  - `502 timeout` from AI gateway causes local rebalance only
  - AI retry does not reset OCR state
- [ ] Run the focused failing tests.
- [ ] Keep current retry entrypoint but persist enough per-scope context to log:
  - source pages
  - segment type
  - retry lineage
  - timeout/error category
- [ ] Ensure scheduler `retry` semantics remain:
  - OCR failure retries from OCR
  - AI failure retries from AI with existing OCR assets
- [ ] Re-run scheduler and MinerU integration tests.
- [ ] Commit AI retry behavior changes.

## Chunk 4: Rewire Workflow And Repository Consumption

### Task 7: Update `standard_ingestion` to use staged parse assets

**Files:**
- Modify: `backend/tender_backend/workflows/standard_ingestion.py`
- Modify: `backend/tests/integration/test_parse_pipeline.py`

- [ ] Add a failing workflow test that expects the standard workflow to distinguish OCR availability from AI extraction.
- [ ] Run the focused failing test.
- [ ] Update workflow steps to reflect the real stages:
  - `ensure_standard_ocr`
  - `load_parse_assets`
  - `build_segments`
  - `tag_clauses`
  - `index_to_opensearch`
- [ ] Keep backward compatibility with the queue scheduler entrypoints.
- [ ] Re-run workflow tests.
- [ ] Commit workflow changes.

### Task 8: Expose parse assets for debugging and viewer alignment

**Files:**
- Modify: `backend/tender_backend/db/repositories/standard_repo.py`
- Modify: `backend/tests/integration/test_standard_repo.py`

- [ ] Add failing tests that expect repository helpers to return:
  - outline from normalized sections
  - raw page/table assets for diagnostics
  - clause/tree nodes with page anchors that match OCR assets
- [ ] Run the focused failing tests.
- [ ] Add read helpers for standard diagnostics without changing current viewer response shape unless needed.
- [ ] Keep outline-first viewer logic working on top of normalized sections.
- [ ] Re-run repository/viewer tests.
- [ ] Commit repository updates.

## Chunk 5: Verification And Rollout Guardrails

### Task 9: Add regression metrics and targeted verification

**Files:**
- Modify: `backend/tests/integration/test_standard_mineru_batch_flow.py`
- Modify: `README.md` or a dedicated ops doc if rollout notes belong elsewhere

- [ ] Add regression fixtures that specifically cover:
  - numeric/unit-heavy clauses
  - mixed TOC/front matter
  - clause-dense chapters
  - large html tables
- [ ] Run:
  - `pytest backend/tests/integration/test_standard_mineru_batch_flow.py -q`
  - `pytest backend/tests/integration/test_standard_processing_scheduler.py -q`
  - `pytest backend/tests/integration/test_standard_repo.py -q`
- [ ] Document rollout switches:
  - any feature flag for new parse-asset path
  - any migration/backfill requirements for old standards
  - how to re-run AI only on existing OCR data
- [ ] Commit verification/docs updates.

## Rollout Notes

- Existing standards already parsed through the old path should not be force-migrated in-place without a backfill strategy.
- The safest rollout is:
  1. deploy migration
  2. write new parse assets for new standards only
  3. enable AI-only retry against new assets
  4. optionally backfill high-value old standards
- Success criteria should be measured on a fixed sample set:
  - clause recall
  - clause numbering completeness
  - numeric/unit fidelity
  - table cell correctness

Plan complete and saved to `docs/superpowers/plans/2026-03-21-standard-parse-root-cause-remediation.md`. Ready to execute?
