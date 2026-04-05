# MinerU Doc Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the standard PDF MinerU integration with the latest MinerU docs, make OCR request parameters configurable, and downgrade local VL repair into an optional configurable fallback.

**Architecture:** Keep `norm_processor._parse_via_mineru()` as the production OCR entrypoint and adjust only its request contract and settings surface. Keep local vision repair in place, but gate it behind settings and remove hardcoded model overrides so repair remains a bounded fallback instead of a second document-wide parsing pipeline.

**Tech Stack:** Python, FastAPI settings, pytest, httpx, MinerU commercial API, AI Gateway.

---

### Task 1: MinerU OCR request alignment

**Files:**
- Modify: `backend/tender_backend/core/config.py`
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py`
- Test: `backend/tests/integration/test_standard_mineru_batch_flow.py`
- Test: `backend/tests/unit/test_vision_settings.py`

- [ ] Add failing tests that assert the batch request payload matches the documented shape and that OCR defaults are exposed through settings.
- [ ] Update backend settings with explicit MinerU OCR options (`model_version`, `language`, `enable_table`).
- [ ] Change `_parse_via_mineru()` to read those settings and move `is_ocr` into each file item.
- [ ] Run the focused tests and keep the rest of the flow unchanged.

### Task 2: Optional local VL repair

**Files:**
- Modify: `backend/tender_backend/core/config.py`
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py`
- Modify: `backend/tender_backend/services/vision_service/repair_service.py`
- Test: `backend/tests/integration/test_standard_mineru_batch_flow.py`
- Test: `backend/tests/unit/test_repair_service.py`
- Test: `backend/tests/unit/test_vision_settings.py`

- [ ] Add failing tests that prove repair can be disabled and that repair overrides use configured models instead of hardcoded ones.
- [ ] Add settings for `standard_repair_enabled` and consume them before dispatching repair tasks.
- [ ] Remove hardcoded repair model names from `repair_service.py` and derive overrides from stored agent configuration when present.
- [ ] Run the focused tests and confirm repair remains a bounded fallback.
