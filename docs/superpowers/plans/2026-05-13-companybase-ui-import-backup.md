# Companybase UI Import Backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a testable frontend workflow for company/personnel资料包校验、dry-run 导入、确认导入和备份下载。

**Architecture:** Backend exposes a focused companybase API under `/api/master-data/companybase/*`, backed by a service that parses XLSX sheets and upserts only MVP data: 公司主体、公司资料、人员资料、附件索引 validation. Frontend adds a `companybase` tab in 投标资料库 with upload, report, import and backup actions.

**Tech Stack:** FastAPI, psycopg, openpyxl, React 18, Vite, Vitest.

---

### Task 1: Backend service and API

**Files:**
- Create: `backend/tender_backend/services/companybase_import_service.py`
- Create: `backend/tender_backend/api/companybase.py`
- Modify: `backend/tender_backend/api/master_data.py`
- Test: `backend/tests/unit/test_companybase_import_service.py`
- Test: `backend/tests/integration/test_companybase_api.py`

Steps: write failing parser/import tests; implement workbook parsing, issue reporting, dry-run safe behavior, and upserts for library company/company profile/person profile; expose validate/import/backup endpoints.

### Task 2: Frontend API client and UI

**Files:**
- Modify: `frontend/src/lib/navigation.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/modules/database/DatabaseModule.tsx`
- Create: `frontend/src/modules/database/components/CompanybaseImportWorkbench.tsx`
- Test: `frontend/src/modules/database/components/CompanybaseImportWorkbench.test.tsx`

Steps: write failing UI tests for upload validate/import/backup controls; implement tab, API calls, report rendering, and download handling.

### Task 3: Verification

Run backend targeted tests, frontend component test, backend health and manual curl checks against the running server.
