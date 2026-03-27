# Single Standard Parse Quality Design

**Date:** 2026-03-25

**Target Document:** `GB 50148-2010`

**Goal**

Rework the standard parsing pipeline so that `GB 50148-2010` reaches near-human parsing quality, prioritizing clause-number completeness first, then hierarchy correctness, commentary separation, and table attribution.

**Non-Goals**

- Do not generalize for all future standards in this phase.
- Do not replace MinerU.
- Do not optimize for shortest end-to-end runtime before quality stabilizes.
- Do not build a full gold-set framework yet.

## Current Problem

The current pipeline still treats the LLM as a primary extractor over large chapter scopes. That causes four persistent failure modes:

1. Large normative scopes time out, then recursively rebalance, which dominates runtime.
2. Clause boundaries are decided too late by the LLM instead of earlier by deterministic structure recovery.
3. Minor OCR/layout drift is amplified downstream into missing clauses, duplicate clauses, or wrong hierarchy.
4. Repair is currently an enhancement layer, but until recently it could still block successful persistence.

Observed evidence from real reruns of `GB 50148-2010`:

- Successful runs can still vary significantly in total clauses (`360`, `369`, `375`).
- The slowest part is always `4 电力变压器、油浸电抗器`, where retries and scope splitting dominate.
- Recent fixes improved resilience, but they did not change the architecture that creates the bottleneck.

## Design Direction

The pipeline should move from `chapter-scope LLM extraction` to `rule-first structural recovery with AI fallback`.

This is not “just add more rules”. The core change is to move responsibility:

- MinerU remains responsible for OCR, page blocks, and base layout.
- Deterministic logic becomes responsible for clause-boundary recovery.
- The LLM is reduced to low-confidence normalization and selective repair.

## Success Criteria For This Single Document

The experiment is considered successful when all of the following are true for `GB 50148-2010`:

1. Clause-number completeness is materially higher than the current persisted baseline (`360`) and stable across reruns.
2. Critical regions are structurally correct:
   - `4.1.x`
   - `4.2.x`
   - `4.12.x`
   - `5.3.x`
   - `A.0.x`
3. Commentary is separated from normative clauses instead of being mixed into the same extraction path.
4. Key tables remain attributable to the correct page and nearby clause context.
5. A repair timeout does not fail the entire ingestion run.

## Proposed Pipeline

### 1. OCR And Asset Normalization

Keep MinerU as the OCR/layout base. Continue using the current page/table reconciliation work:

- normalize page payloads
- reconcile raw tables to `table:<id>`
- infer page/title for tables when missing

No attempt is made here to directly infer the final clause tree.

### 2. Deterministic Structural Segmentation

Add a new pre-extraction phase that turns normalized sections into candidate semantic blocks before any LLM call.

Block types:

- `normative_clause_block`
- `commentary_block`
- `table_requirement_block`
- `appendix_block`
- `heading_only_block`

Deterministic signals used here:

- `section_code`
- heading text
- line prefixes such as `1.0.1`, `4.2.3`, `1、`, `1)`, `a)`
- known commentary markers
- appendix markers
- local table-title proximity

This layer should prefer false-positive block creation over false-negative clause loss. Ambiguous blocks can be downgraded to low confidence later.

### 3. Three Independent Extraction Channels

Split extraction into three channels instead of letting one LLM prompt handle everything:

1. Normative channel
   - Input: one clause block or a very small batch of adjacent clause blocks
   - Output: normalized clause nodes and item/subitem children

2. Commentary channel
   - Input: commentary-only blocks
   - Output: commentary nodes linked to nearby or explicit clause numbers

3. Table channel
   - Input: table assets plus nearby headings and local page context
   - Output: requirement clauses extracted from tabular content only

This separation is required because commentary and tables have very different error modes from normative prose.

### 4. Confidence Routing

Each candidate block should be assigned a structural confidence score:

- `high`
  - strong numbering pattern
  - clear parent heading
  - stable page anchor
  - no conflicting duplicates nearby

- `medium`
  - likely clause boundary, but missing one signal

- `low`
  - ambiguous numbering
  - broken OCR line joins
  - uncertain table-to-clause mapping

Routing:

- `high`: deterministic parse first, no immediate LLM extraction
- `medium`: LLM normalization on block-sized input
- `low`: LLM fallback or targeted repair

This is the main quality and speed lever. It removes the need to run the LLM over every large chapter chunk.

### 5. Conservative Deduplication

Deduplication must move away from “same clause number means same node”.

New dedupe identity should combine:

- `clause_type`
- normalized `clause_no`
- `parent_key` or inferred parent clause number
- `source_ref`
- normalized `clause_text` hash

This preserves legitimate repeated numbering contexts while still dropping repeated ancestor nodes emitted by neighboring scopes.

### 6. Post-Extraction Validation And Best-Effort Repair

Validation remains mandatory:

- numbering gaps
- non-monotonic local ordering
- implied parent existence
- missing source/page anchors
- table provenance integrity

Repair becomes best-effort only:

- repair failures append warnings
- repair does not block persistence
- repaired output is revalidated before final save

This keeps the run usable even when VL repair is unstable.

## Scope Reduction Strategy

The current bottleneck is the LLM receiving chapter-level scope text. The new design replaces that with:

- clause-sized or small-batch normative blocks
- commentary-only blocks
- table-only blocks

The expected effect is:

- fewer retries
- less recursive rebalancing
- fewer malformed or partial JSON responses
- smaller variance between reruns

## Acceptance Method For This Phase

Before building a general gold-set, use a single-document acceptance checklist for `GB 50148-2010`.

The checklist should contain:

- must-have clause numbers in the critical regions
- expected commentary separation behavior
- must-have tables such as `表 4.2.4`
- clause-count target band based on repeated stable reruns
- explicitly known numbering-only warnings that remain acceptable

This keeps scope tight while still giving a concrete finish line.

## Files Likely To Change

- `backend/tender_backend/services/norm_service/norm_processor.py`
- `backend/tender_backend/services/norm_service/scope_splitter.py`
- `backend/tender_backend/services/norm_service/structural_nodes.py`
- `backend/tender_backend/services/norm_service/ast_builder.py`
- `backend/tender_backend/services/norm_service/document_assets.py`
- `backend/tests/integration/test_standard_mineru_batch_flow.py`
- possibly new focused helpers under `backend/tender_backend/services/norm_service/`

## Risks

1. Rule-first segmentation may initially over-split.
   Mitigation: allow merge heuristics and confidence downgrade.

2. Single-document optimization may encode assumptions too specific to this one file.
   Mitigation: isolate document-shape heuristics behind explicit helpers and keep them measurable.

3. Table attribution may remain the hardest part.
   Mitigation: keep table extraction independent from normative extraction and verify provenance separately.

## Recommendation

Proceed with a single-document experimental refactor in this order:

1. deterministic block segmentation
2. commentary/normative/table channel split
3. dedupe identity hardening
4. confidence routing
5. rerun and compare against the single-document acceptance checklist

This is the shortest path to getting `GB 50148-2010` near human quality without prematurely building a generalized benchmark system.
