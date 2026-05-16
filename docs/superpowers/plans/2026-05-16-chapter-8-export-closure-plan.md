# Chapter 8 Export Closure Plan (Trackable)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make chapter 8 (`project_id=c42f62a8-7e48-4514-ad01-d509088bee9c`) reach `can_export=true` with auditable evidence on **2026-05-16**.

**Architecture:** Split execution into two phases. Phase A closes delivery blockers (stale runs, single clean async run, chart/coverage/page-count gates). Phase B fixes root causes (concurrency guard + stale-run timeout) so the same failure pattern does not recur.

**Tech Stack:** FastAPI bid-generation API, `workflow_run` / `chapter_draft` / `export_record` tables, `TechnicalBidWriter`, export gate service, pytest.

---

## Current Baseline (2026-05-16 15:07 CST)

- Latest completed run: `d8d469a9-ad3f-4389-b1fe-f1b91334e731` (15/15, 100%).
- Stale running runs: `85cf7bd8-b89a-4816-aa9d-b04464ab13de`, `1fe239b8-7312-4f9c-9911-93ec69ed0426`, `3f92bc4f-4767-4db1-9976-422fdcd2b2f6`.
- Latest draft: `9552059d-647e-4c3a-be00-b98ad208ca1f`.
- Export gate: `can_export=false`.
  - `page_count_passed=false`
  - `coverage_passed=false` (17 P0)
  - `chart_closure_passed=false` (14 P0)

---

## Success Criteria (hard stop)

- [ ] `GET /export-gates` returns all true:
  - [ ] `page_count_passed=true`
  - [ ] `coverage_passed=true` (P0 gap = 0)
  - [ ] `chart_closure_passed=true` (residual chart issues = 0)
- [ ] `can_export=true`
- [ ] Evidence file saved under `docs/acceptance/2026-05-16-chapter-8-real-sample-evidence.json`
- [ ] One final acceptance note appended to `docs/acceptance/2026-05-15-longform-launch-closure.md`

---

## Phase A — Delivery Closure (today)

### Task A1: Freeze one authoritative run lane

**Files:**
- Modify: none (ops only)
- Evidence: `docs/acceptance/2026-05-16-chapter-8-run-cleanup.md`

- [ ] **Step 1: Snapshot current run states**

Run:
```bash
cd backend && ../.venv/bin/python - <<'PY'
from tender_backend.core.config import get_settings
import psycopg
from psycopg.rows import dict_row
q='''
SELECT id,state,current_step,created_at,updated_at,context_json
FROM workflow_run
WHERE workflow_name='generate_section_async'
ORDER BY created_at DESC LIMIT 20
'''
with psycopg.connect(get_settings().database_url) as conn:
  with conn.cursor(row_factory=dict_row) as cur:
    rows=cur.execute(q).fetchall()
for r in rows:
  print(r['id'], r['state'], r['current_step'], r['updated_at'])
PY
```
Expected: find stale `running` runs older than 30 minutes.

- [ ] **Step 2: Cancel stale runs (keep latest completed as reference only)**

Run:
```bash
cd backend && ../.venv/bin/python - <<'PY'
from tender_backend.core.config import get_settings
import psycopg
STALE=[
'85cf7bd8-b89a-4816-aa9d-b04464ab13de',
'1fe239b8-7312-4f9c-9911-93ec69ed0426',
'3f92bc4f-4767-4db1-9976-422fdcd2b2f6',
]
with psycopg.connect(get_settings().database_url) as conn:
  with conn.cursor() as cur:
    cur.execute("""
      UPDATE workflow_run
      SET state='cancelled',
          error_message='cancelled during chapter-8 closure to remove stale running lane',
          updated_at=now()
      WHERE id = ANY(%s::uuid[])
    """, (STALE,))
  conn.commit()
print('cancelled', len(STALE))
PY
```
Expected: exactly 3 runs moved to `cancelled`.

- [ ] **Step 3: Save cleanup evidence markdown**
  - Record run IDs before/after state transition.

---

### Task A2: Launch one clean async generation run

**Files:**
- Modify: none (ops via API)
- Evidence: append `docs/acceptance/2026-05-16-chapter-8-run-cleanup.md`

- [ ] **Step 1: Submit async run with strict rewrite guidance**

Run (replace host/token):
```bash
curl -sS -X POST "http://127.0.0.1:8000/api/projects/c42f62a8-7e48-4514-ad01-d509088bee9c/technical-bid/chapters/<CHAPTER_8_ID>/generate-async" \
  -H "Authorization: Bearer dev-token" \
  -H "Content-Type: application/json" \
  -d '{
    "target_pages": 100,
    "rewrite_note": "必须补齐8.8质量控制点表、8.11工期保证措施表、8.12重点难点应对表；各子节满足最小字数；保持章节边界不跨章复写。"
  }'
```
Expected: `202` + `run_id`.

- [ ] **Step 2: Poll until terminal state**

Run:
```bash
curl -sS "http://127.0.0.1:8000/api/projects/c42f62a8-7e48-4514-ad01-d509088bee9c/technical-bid/generation-runs/<RUN_ID>" \
  -H "Authorization: Bearer dev-token"
```
Expected: final `state=completed`; if `failed`, capture error and stop to RCA.

- [ ] **Step 3: Verify progress reached 15/15**
  - Confirm `progress.completed_sections=15`, `progress.percent=100`, `last_section_code=8.15`.

---

### Task A3: Close chart and coverage gates

**Files:**
- Modify: operational data + chapter content
- Evidence: `docs/acceptance/2026-05-16-chapter-8-real-sample-evidence.json`

- [ ] **Step 1: Recompute export gate state**

Run:
```bash
cd backend && ../.venv/bin/python - <<'PY'
from tender_backend.core.config import get_settings
from tender_backend.services.export_gate_service import build_export_gate_state
import psycopg, json
pid='c42f62a8-7e48-4514-ad01-d509088bee9c'
with psycopg.connect(get_settings().database_url) as conn:
  gate=build_export_gate_state(conn, project_id=pid)
print(json.dumps(gate, ensure_ascii=False, default=str, indent=2))
PY
```
Expected: see remaining blocking issue list.

- [ ] **Step 2: Resolve all unapproved/unrendered chart keys**
  - Required keys: `closure_flow`, `construction_flow`, `equipment_table`, `quality_system`, `risk_matrix`, `safety_system`, `schedule_gantt`.
  - For each key: generate/render -> mark approved -> recheck gate.

- [ ] **Step 3: Resolve all coverage P0 items**
  - Priority order: missing required tables first, then short sections.
  - Re-run chapter regeneration only if targeted edits cannot close all P0.

- [ ] **Step 4: Capture acceptance evidence JSON**

Run:
```bash
cd backend && DATABASE_URL="$(../.venv/bin/python - <<'PY'
from tender_backend.core.config import get_settings
print(get_settings().database_url or '')
PY
)" ../.venv/bin/python ../scripts/run_chapter_8_acceptance.py \
  --project-id c42f62a8-7e48-4514-ad01-d509088bee9c \
  --output ../docs/acceptance/2026-05-16-chapter-8-real-sample-evidence.json
```
Expected: JSON contains latest `chapter_draft`, `export_record`, `export_gate`.

---

### Task A4: Final acceptance decision

**Files:**
- Modify: `docs/acceptance/2026-05-15-longform-launch-closure.md`

- [ ] **Step 1: Add dated decision block**
  - Include exact timestamp: `2026-05-16`.
  - Include final values for page count / coverage / chart closure.

- [ ] **Step 2: State Go/No-Go explicitly**
  - Go only if three hard gates all true.

- [ ] **Step 3: Commit evidence/docs**

```bash
git add docs/acceptance/2026-05-16-chapter-8-real-sample-evidence.json \
        docs/acceptance/2026-05-15-longform-launch-closure.md \
        docs/acceptance/2026-05-16-chapter-8-run-cleanup.md
git commit -m "docs: record chapter 8 export closure evidence"
```

---

## Phase B — Root Cause Hardening (prevent recurrence)

### Task B1: Add chapter-level concurrency guard for async submit

**Files:**
- Modify: `backend/tender_backend/services/technical_generation_async.py`
- Modify: `backend/tender_backend/api/bid_generation.py`
- Test: `backend/tests/unit/test_technical_generation_async.py`
- Test: `backend/tests/unit/test_bid_generation_api.py`

- [ ] **Step 1: Add failing test — reject new run when same project+chapter has active (`pending|running`) run**
- [ ] **Step 2: Implement guard in service before `create_run`**
- [ ] **Step 3: API maps guard failure to `409` with actionable message**
- [ ] **Step 4: Run targeted tests**

```bash
cd backend && PYTHONPATH=. ../.venv/bin/pytest \
  tests/unit/test_technical_generation_async.py \
  tests/unit/test_bid_generation_api.py -q
```

---

### Task B2: Add stale-run timeout and safe auto-cancel

**Files:**
- Modify: `backend/tender_backend/services/technical_generation_async.py`
- Test: `backend/tests/unit/test_technical_generation_async.py`

- [ ] **Step 1: Add failing test — run with no progress heartbeat > timeout marked cancelled/failed**
- [ ] **Step 2: Implement timeout check in status loader and/or worker watchdog path**
- [ ] **Step 3: Ensure status API returns explicit stale reason**
- [ ] **Step 4: Run tests + commit**

---

### Task B3: Tighten acceptance tooling

**Files:**
- Modify: `scripts/run_chapter_8_acceptance.py`
- Modify: `docs/testing.md`
- Test: `backend/tests/unit/test_longform_quality.py` (if needed)

- [ ] **Step 1: Remove dependency on externally exported `DATABASE_URL` (read app settings fallback robustly)**
- [ ] **Step 2: Add explicit fail output when `actual_pages` is missing**
- [ ] **Step 3: Update docs with one-command acceptance flow**
- [ ] **Step 4: Commit**

---

## Risk Controls

- [ ] Never run two chapter-8 async jobs in parallel.
- [ ] Every gate check must include exact timestamp + run_id.
- [ ] If any P0 issue remains, stop and log No-Go (no manual bypass).

## Reporting Cadence

- [ ] Update plan checkboxes after each completed step.
- [ ] Post 3 checkpoints:
  1. Run-lane cleaned
  2. New run completed
  3. Final gate decision
