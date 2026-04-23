---
name: standard-parse-recovery
description: Use when standard document parsing quality regresses in this repo, especially for MinerU parse drift, table provenance/page anchor issues, AI scope timeout failures, or validation-count regressions in tender backend norm_service.
---

# Standard Parse Recovery

Use this skill for parsing-quality incidents in this repository.

Typical triggers:
- Uploaded standard files parse with missing or noisy clauses
- `page.missing_anchor` or `table.missing_source_ref` appears
- Scope processing times out in `process_standard_ai()`
- Real-sample clause counts or validation counts regress
- MinerU payload shape changes break section/page/table recovery

## Scope

This skill is specific to:
- `backend/tender_backend/services/norm_service/`
- `backend/tests/integration/test_standard_mineru_batch_flow.py`
- `backend/tests/unit/test_document_assets.py`
- `backend/tests/unit/test_structural_nodes.py`
- `backend/tests/unit/test_validation.py`

## Workflow

1. Reproduce before fixing.
2. Identify whether the failure is in:
   - MinerU payload normalization
   - document asset reconciliation
   - scope construction / splitting
   - AI response parsing
   - validation / repair
3. Add the smallest failing test first.
4. Implement the minimal fix.
5. Run focused regression tests.
6. Re-run a real sample in Docker, preferably inside `tmux`.
7. Compare final counts, warnings, and validation issues.

## Investigation Map

Read these files first:
- `backend/tender_backend/services/norm_service/norm_processor.py`
- `backend/tender_backend/services/norm_service/document_assets.py`
- `backend/tender_backend/services/norm_service/scope_splitter.py`
- `backend/tender_backend/services/norm_service/structural_nodes.py`
- `backend/tender_backend/services/norm_service/validation.py`

Use these questions to narrow the problem:
- Are sections normalized correctly, or is TOC/noise leaking in?
- Does `DocumentAsset` preserve page text and table provenance?
- Are table assets mapped to `table:<id>` with usable `page_start/page_end`?
- Are long scopes being retried and rebalanced instead of failing outright?
- Is `_parse_llm_json()` dropping valid content because of wrapper text or malformed fences?
- Are remaining issues true data problems, or missing normalization/repair?

## Test-First Targets

Add or update tests in:
- `backend/tests/integration/test_standard_mineru_batch_flow.py`
- `backend/tests/unit/test_document_assets.py`
- `backend/tests/unit/test_structural_nodes.py`
- `backend/tests/unit/test_validation.py`

Good test targets:
- Raw MinerU pages with layout-block payloads
- Raw tables without page/title metadata
- HTML/image-path reconciliation to `table:<id>`
- Table page backfill from nearby page title/order
- Timeout retry, rebalance, and nested rebalance behavior
- LLM JSON extraction with leading/trailing prose or fenced output

## Verification Commands

Focused regression:

```bash
.venv/bin/pytest \
  backend/tests/integration/test_standard_mineru_batch_flow.py \
  backend/tests/unit/test_document_assets.py \
  backend/tests/unit/test_validation.py \
  backend/tests/unit/test_structural_nodes.py -q
```

Real-sample rerun in `tmux`:

```bash
tmux new-session -d -s tender_verify_real "docker compose --env-file infra/.env -f infra/docker-compose.yml exec -T backend python - <<'PY' > /tmp/tender_verify_real.log 2>&1
import json
import os
from uuid import UUID
import psycopg
from tender_backend.services.norm_service.norm_processor import process_standard_ai

standard_id = UUID('ff2ddb6c-ba8e-4e42-862f-e75d5824437a')
document_id = 'e3003181-042a-44da-ad67-44615d7d25f2'
conn = psycopg.connect(os.environ['DATABASE_URL'])
try:
    summary = process_standard_ai(conn, standard_id=standard_id, document_id=document_id)
    conn.commit()
    print(json.dumps(summary, ensure_ascii=False))
finally:
    conn.close()
PY
"
tmux ls
```

Watch progress:

```bash
tail -n 120 /tmp/tender_verify_real.log
```

## Real-Sample Checks

After a rerun, verify:
- `status == completed`
- `issues_after_repair`
- whether `page.missing_anchor` still exists
- whether `table.missing_source_ref` still exists
- clause counts vs previous known-good runs

Useful inspections:
- rebuilt `DocumentAsset.tables`
- rebuilt table scopes and `source_refs`
- validation issue list in returned summary
- persisted `standard_clause` counts by clause type

## Practical Heuristics

- Prefer fixing provenance and scope construction before relaxing validation.
- If a scope is small and still times out, add raw retry before more aggressive splitting.
- If a raw table lacks page/title, reconcile via HTML/image-path first, then infer page/title from page text order.
- If the LLM returns almost-correct JSON, salvage it with targeted extraction rather than treating the whole scope as empty.
- Keep frontend or unrelated lockfile changes out of parsing commits.

## Done Criteria

Only call the incident fixed when all are true:
- focused regression tests pass
- real-sample rerun completes
- table/page provenance regressions are gone
- remaining validation issues are understood and documented
- commit excludes unrelated files

## Packaging Note

This is a repo-local draft skill.
To activate it in Codex globally later, copy this folder into `~/.codex/skills/standard-parse-recovery/`.
