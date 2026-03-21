# AI Parse Throughput Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce local PDF AI parsing latency by increasing standard-level AI worker concurrency and cutting unnecessary per-scope wait time, while keeping fallback behavior observable and safe.

**Architecture:** Backend scheduler becomes configurable for OCR/AI worker counts, the norm processor reads configurable AI gateway timeout and scope delay settings, and the AI gateway gets task-level timeout/retry tuning for `tag_clauses`. Verification focuses on regression tests around scheduler behavior and provider client configuration.

**Tech Stack:** FastAPI, psycopg, Pydantic Settings, Docker Compose, pytest

---

## Chunk 1: Backend Scheduling And Throttling

### Task 1: Add backend settings for scheduler and scope timing

**Files:**
- Modify: `backend/tender_backend/core/config.py`
- Test: `backend/tests/integration/test_standard_mineru_batch_flow.py`

- [ ] Add `standard_ocr_worker_count`, `standard_ai_worker_count`, `standard_ai_scope_delay_ms`, `standard_ai_scope_delay_jitter_ms`, and `standard_ai_gateway_timeout_seconds` settings with conservative defaults.
- [ ] Add a regression test proving `_call_ai_gateway()` respects the configured backend timeout.
- [ ] Run: `docker compose --env-file infra/.env -f infra/docker-compose.yml exec -T backend python -m pytest tests/integration/test_standard_mineru_batch_flow.py -q`

### Task 2: Make scheduler worker counts configurable

**Files:**
- Modify: `backend/tender_backend/services/norm_service/standard_processing_scheduler.py`
- Test: `backend/tests/integration/test_standard_processing_scheduler.py`

- [ ] Add constructor fields for `ocr_worker_count` and `ai_worker_count`.
- [ ] Update `ensure_started()` to spawn configurable numbers of OCR and AI loops.
- [ ] Add a regression test asserting multiple AI loop threads are created when configured.
- [ ] Run: `docker compose --env-file infra/.env -f infra/docker-compose.yml exec -T backend python -m pytest tests/integration/test_standard_processing_scheduler.py -q`

### Task 3: Replace fixed 2-second scope delay with configurable jitter

**Files:**
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py`
- Test: `backend/tests/integration/test_standard_mineru_batch_flow.py`

- [ ] Read the new scope delay settings from backend config.
- [ ] Replace fixed `time.sleep(2)` with a helper that sleeps `delay + jitter`, while allowing `0` to disable waiting.
- [ ] Add a regression test proving a non-default shorter delay is used.
- [ ] Run: `docker compose --env-file infra/.env -f infra/docker-compose.yml exec -T backend python -m pytest tests/integration/test_standard_mineru_batch_flow.py -q`

## Chunk 2: AI Gateway Task-Level Tuning

### Task 4: Add task-level timeout and retry settings for `tag_clauses`

**Files:**
- Modify: `ai_gateway/tender_ai_gateway/task_profiles.py`
- Modify: `ai_gateway/tender_ai_gateway/fallback.py`
- Test: `ai_gateway/tests/smoke/test_gateway.py`

- [ ] Extend task profiles to carry optional `timeout` and `max_retries`.
- [ ] Make `call_with_fallback()` use task-level timeout/retry values, falling back to global defaults for other task types.
- [ ] Add or update a test proving `tag_clauses` uses its task-level client configuration.
- [ ] Run: `docker compose --env-file infra/.env -f infra/docker-compose.yml exec -T ai-gateway python -m pytest tests/smoke/test_gateway.py -q`

## Chunk 3: Verification

### Task 5: Run targeted regression suite

**Files:**
- Modify: none
- Test: `backend/tests/integration/test_standard_processing_scheduler.py`
- Test: `backend/tests/integration/test_standard_mineru_batch_flow.py`
- Test: `ai_gateway/tests/smoke/test_gateway.py`

- [ ] Run backend scheduler tests.
- [ ] Run backend MinerU/AI gateway integration-style tests.
- [ ] Run ai-gateway smoke tests.
- [ ] Record any required env var defaults for local rollout.

