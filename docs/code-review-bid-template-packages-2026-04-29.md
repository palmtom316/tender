# Code Review — `bid-template-packages` Branch

**Date**: 2026-04-29  
**Branch**: `bid-template-packages` (15 commits ahead of main)  
**Scope**: 31 files, +7964 lines  
**Reviewer**: Automated systematic review  

---

## Summary

| Category | Count |
|----------|-------|
| P0 (Blocking) | 6 |
| P1 (Major) | 7 |
| P2 (Minor) | 6 |
| P3 (Polish) | 4 |
| **Total** | **23** |

**Overall Assessment**: The branch adds substantial, well-structured functionality (template packages, master data APIs, binding rules, DOCX rendering) with generally good patterns. However, there are **6 blocking issues** — mostly security-related — that must be addressed before merge.

---

## Resolution Status (2026-05-01)

Cross-references the remediation report at `docs/code-review-bid-template-packages-remediation-2026-04-29.md`.
Legend: ✅ FIXED · 🛡 VERIFIED (existing behavior is correct) · ⏸ DEFERRED (acknowledged, not blocking) · ❌ NOT FIXED.

| ID | Status | Note |
|---|---|---|
| P0-1 | ✅ FIXED | Path validated against `evidence_upload_dir` in `_validated_asset_source_path` & `_validate_managed_asset_path`. Regression test: `test_path_safety.py`, `test_render_attachment_manifest_rejects_assets_outside_upload_root`. |
| P0-2 | ✅ FIXED | `TEMPLATE_IMPORT_ROOTS` allowlist enforced via `ensure_path_within_roots`. Regression test: `test_build_template_items_from_directory_rejects_path_outside_allowed_roots`. |
| P0-3 | ✅ FIXED | `replace_items` now reuses rows by `relative_path` (UPDATE) instead of delete+insert; bindings preserved. Regression test: `test_bid_template_package_repo_replace_items.py`. |
| P0-4 | ✅ FIXED | `by_id` filters strictly by `record_ids`; `latest` uses `_latest_sort_key` per `source_type`. Regression test: `test_select_records_by_id_requires_record_ids`. |
| P0-5 | ✅ FIXED (re-scoped) | Transaction boundary moved to service layer (`with conn.transaction()` in `import_template_package_from_directory`); repo methods no longer commit. |
| P0-6 | ✅ FIXED | Extension allowlist + magic byte + Content-Type + size limit in `_validate_uploaded_file`. Regression test: `test_master_data_evidence_upload.py` (11 cases). |
| P1-1 | ✅ FIXED | `count_items_by_package` batch query; called from `template_packages.list_template_packages`. |
| P1-2 | ✅ FIXED | `get_current_user` supports both static `dev-token` and DB `user_session` token; all routers register `Depends(get_current_user)`. |
| P1-3 | ✅ FIXED | `_latest_sort_key` defines `latest` semantics per `source_type`. Regression test: `test_select_records_latest_uses_source_specific_sort_keys`. |
| P1-4 | ✅ FIXED | `DatabaseModule.tsx` reduced to 71 lines; workbenches extracted into separate components. |
| P1-5 | ✅ FIXED | `master_data.py` reduced to 90 lines; six per-domain routers (`master_data_companies`, `_people`, `_performances`, `_certificates`, `_financials`, `_evidence`). |
| P1-6 | ✅ FIXED | Suggestions return `confidence` field; frontend renders confidence Badge in `TemplateFieldWorkbench`. |
| P1-7 | ✅ FIXED | New preflight endpoint `GET /template-packages/{package_id}/render-preflight`; frontend surfaces missing bindings, missing assets, unsafe paths. |
| P2-1 | ✅ FIXED | `TEMPLATE_RENDER_ROOT` / `TEMPLATE_BUNDLE_ROOT` injected via `Settings`. `/tmp/...` retained only as dev fallback default. |
| P2-2 | ⏸ DEFERRED | Column constants are module-level literals interpolated via f-string — no user input flows into SQL identifiers, so no injection risk. Migrating to `psycopg.sql.Identifier`/`SQL` is a code-quality refactor, not a correctness fix; tracked for a future cleanup pass. |
| P2-3 | ✅ FIXED | `TemplateFieldWorkbench` defaults `date_format` to `%Y-%m-%d` and `default_value` is normalized only when non-empty. |
| P2-4 | ✅ FIXED | `StandardsWorkbench.tsx` uses `pollingRef` outside the effect dep array, no longer recreating the interval on every render. |
| P2-5 | ✅ FIXED | All `window.confirm()` call-sites replaced with shared `ConfirmDialog` (verified by grep — no `window.confirm` remains). |
| P2-6 | ✅ FIXED | `EvidenceAssetOut` response model no longer exposes `file_path`. |
| P3-1 | ⏸ DEFERRED | `_to_cn_numeral` still capped at 1–20. Real templates today do not exceed 20 sub-items per attachment chapter; if that ever changes we will extend the table. Cost/benefit currently does not justify changing it. |
| P3-2 | ⏸ DEFERRED | Status literal coupling between polling logic and backend was reduced when polling moved into `StandardsWorkbench`, but the literal strings still live there. Acceptable given the small surface; revisit if more processing states are introduced. |
| P3-3 | 🛡 VERIFIED | `0018_bid_template_binding_rules.py:25` defines `template_item_id ... ON DELETE CASCADE`. After P0-3 fix the cascade path is no longer hit during re-import (rows are updated in place). Cascade behavior is intentional for hard-delete cases. |
| P3-4 | ⏸ DEFERRED (partial) | Unit-level coverage added for renderer (`test_package_renderer.py`), preflight, and bundle helpers. End-to-end API integration tests (`test_template_package_api.py`) exist but are skipped without `DATABASE_URL` — need DB-enabled CI to actually exercise them. |

### Open follow-ups

1. Stand up a `DATABASE_URL`-enabled CI lane to actually execute the integration suite (`test_master_data_api.py`, `test_template_package_api.py`, `test_template_binding_api.py`) instead of skipping them.
2. Migrate the deferred P2-2 / P3-1 / P3-2 items into the backlog; they are not merge-blocking but should not be lost.

---

## P0 — Blocking (must fix before merge)

### [P0-1] Arbitrary file read via evidence asset `file_path` — path traversal

**Status (2026-05-01)**: ✅ FIXED.

- **Location**: `backend/tender_backend/services/template_service/package_renderer.py:127-141`, `_copy_attachment_file()`
- **Category**: Security
- **Impact**: When rendering a package bundle, `_copy_attachment_file` reads `asset["file_path"]` from the database and copies it with `shutil.copy2()`. While `_safe_relative_path()` guards item `relative_path`, there is **no validation** that `asset["file_path"]` is within an allowed directory. An attacker who can create or modify an evidence asset record (via the API) can set `file_path` to `/etc/passwd` or any other server file, and it will be copied into the render bundle output directory.

```python
# package_renderer.py:128
source_path = Path(str(asset["file_path"])).expanduser()
if not source_path.is_file():
    raise FileNotFoundError(...)
# No check that source_path is within allowed upload directory
```

- **Recommendation**: Validate that `source_path` is within the configured upload directory (`_UPLOAD_DIR` or similar). Use `Path.resolve()` and check the resolved path starts with the allowed base directory. Apply this validation in `_copy_attachment_file` AND in `_embed_asset_preview`.

---

### [P0-2] Unrestricted server-side directory traversal via import API

**Status (2026-05-01)**: ✅ FIXED.

- **Location**: `backend/tender_backend/api/template_packages.py:145-164`, `backend/tender_backend/services/template_service/package_importer.py:86-120`
- **Category**: Security
- **Impact**: The `POST /template-packages/import` endpoint accepts a `source_dir` string from the client and passes it to `Path(source_dir).expanduser().resolve()`. While `resolve()` normalizes the path, there is no check that the resolved path is within an allowed directory. Any authenticated user can import template items that enumerate `.docx` files from any directory the server process can read, including configuration directories, source trees, or mounted volumes.

```python
# template_packages.py:150-151
imported = import_template_package_from_directory(
    conn, source_dir=payload.source_dir.strip(), ...
)
# package_importer.py:87-89
root = Path(source_dir).expanduser().resolve()
if not root.exists():
    raise FileNotFoundError(...)
# No allowlist check
```

- **Recommendation**: Maintain a configurable allowlist of import source directories (e.g., an env var `TEMPLATE_IMPORT_ROOTS`). Reject any path outside those roots. At minimum, validate that the resolved path is under a known template storage location.

---

### [P0-3] `replace_items` silently destroys binding rule data — no FK cascade verification

**Status (2026-05-01)**: ✅ FIXED.

- **Location**: `backend/tender_backend/db/repositories/bid_template_package_repo.py:217-254`
- **Category**: Data Integrity
- **Impact**: `replace_items()` executes `DELETE FROM bid_template_item WHERE package_id = %s` then re-inserts items with new UUIDs. If `bid_template_binding_rule.template_item_id` has a `FOREIGN KEY ... ON DELETE CASCADE`, all binding rules for that package are **silently destroyed**. If there is NO cascade, the DELETE will fail with a foreign key violation, and the method will crash with an unhandled exception (no try/except, and `conn.commit()` is called after). Either way, this is data-loss or crash behavior that the caller (`package_importer.py:153`) does not handle.

```python
# bid_template_package_repo.py:225
cur.execute("DELETE FROM bid_template_item WHERE package_id = %s", (package_id,))
# Then inserts new items with new UUIDs...
```

- **Recommendation**: Before deleting items, explicitly delete or reassign related binding rules. If re-import is intended to be destructive, document it and handle cascade explicitly. Better: use the `ON CONFLICT` upsert pattern (like `upsert_package` does) for items too, keyed by `(package_id, relative_path)` to preserve item IDs and their bindings across re-imports.

---

### [P0-4] `selection_mode: "by_id"` is dead code — identical to "first"

**Status (2026-05-01)**: ✅ FIXED.

- **Location**: `backend/tender_backend/services/template_service/context_preview.py:168-179`, `_select_records()`
- **Category**: Correctness
- **Impact**: The `by_id` selection mode is accepted as valid input (in `_VALID_SELECTION_MODES`), the API validates it, and the frontend offers it as an option — but it **never actually filters by ID**. It falls through to `return records[0]`, which is identical to `"first"`. Users who configure `by_id` and specify record IDs in filters will get completely wrong data (a random first record instead of the one they specified).

```python
# context_preview.py:175-178
if selection_mode == "latest":
    return records[0]          # Should select most recent
if selection_mode == "by_id":
    return records[0]          # BUG: never filters by ID
```

- **Recommendation**: The `_matches_filters` function already supports `record_ids` filter. For `by_id` mode: extract IDs from `source_filters.record_ids`, filter to only those records, then return the first match. Alternatively, remove `by_id` from valid modes if it's not implemented yet.

---

### [P0-5] `upsert_package` never calls `conn.commit()` — inconsistent transaction handling

**Status (2026-05-01)**: ✅ FIXED (re-scoped) — transaction now lives at the service boundary.

- **Location**: `backend/tender_backend/db/repositories/bid_template_package_repo.py:176-215`
- **Category**: Data Integrity
- **Impact**: Every other create/update/delete method in the repository layer calls `conn.commit()` explicitly. `upsert_package` does not. It relies on the caller (or FastAPI middleware) to commit. If the API handler that calls it adds an additional write in the same request lifecycle before the implicit commit, data could be lost. This inconsistency is a latent bug waiting to be triggered.

```python
# Compare:
# create_library_company (master_data_repo.py:341): conn.commit()  ✓
# create (binding_repo.py:133):        conn.commit()  ✓
# upsert_package:                      NO conn.commit() ✗
```

- **Recommendation**: Add `conn.commit()` after the INSERT in `upsert_package()`, consistent with all other repository methods.

---

### [P0-6] File upload has no content-type validation or malware scanning

**Status (2026-05-01)**: ✅ FIXED.

- **Location**: `backend/tender_backend/api/master_data.py:733-776`, `upload_evidence_asset()`
- **Category**: Security
- **Impact**: The upload endpoint accepts arbitrary files and saves them to `_UPLOAD_DIR` using only the file extension from the filename. No content-type validation, no magic byte checking, no size limits. An attacker can upload executable files, HTML with XSS, or arbitrarily large files to exhaust disk space.

```python
# master_data.py:752-757
suffix = Path(file.filename or "").suffix
local_name = f"{uuid4()}{suffix}"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
local_path = _UPLOAD_DIR / local_name
content = await file.read()      # No size limit
local_path.write_bytes(content)  # No content validation
```

- **Recommendation**: 
  1. Add file size limit (e.g., 50MB) via FastAPI or application-level check
  2. Validate content type against an allowlist (PDF, common image formats)
  3. Use `python-magic` or at minimum check magic bytes to verify the file matches its claimed type
  4. Store files with a flat structure or sanitized names to avoid filesystem issues with many files

---

## P1 — Major

### [P1-1] N+1 query in `list_template_packages` — counts items per package individually

**Status (2026-05-01)**: ✅ FIXED.

- **Location**: `backend/tender_backend/api/template_packages.py:119-121`
- **Category**: Performance
- **Impact**: For N packages, this makes N+1 queries to count items. With 20 packages, that's 21 queries. Scales linearly with package count.

```python
# template_packages.py:119-121
items_by_package = {
    package.id: len(_repo.list_items(conn, package_id=package.id))
    for package in packages
}
```

- **Recommendation**: Add a `count_items_by_package` method to the repository using `SELECT package_id, COUNT(*) FROM bid_template_item GROUP BY package_id`, or join in the original query.

---

### [P1-2] No authorization checks on any new API endpoint

**Status (2026-05-01)**: ✅ FIXED.

- **Location**: All new API routers (`master_data.py`, `template_bindings.py`, `template_packages.py`)
- **Category**: Security
- **Impact**: There appear to be no authentication/authorization decorators or middleware checks on the new endpoints. If other API endpoints in the project use auth (check `main.py` for middleware), these new endpoints may be unintentionally public.

- **Recommendation**: Verify that all new endpoints are protected by the same auth middleware as existing endpoints. Check `main.py` to confirm the router registration includes auth dependencies.

---

### [P1-3] `_select_records` sorts `filtered` but `records` are unsorted — "latest" is unreliable

**Status (2026-05-01)**: ✅ FIXED.

- **Location**: `backend/tender_backend/services/template_service/context_preview.py:168-179`
- **Category**: Correctness
- **Impact**: `selection_mode == "latest"` returns `records[0]`, but there is no guarantee the records are sorted by date descending. The calling code in `_resolve_binding_payloads` filters records but doesn't sort them. The source data from repository methods may or may not be sorted (e.g., `list_certificates` sorts by `valid_to DESC`, but `list_evidence_assets` sorts by `owner_type, sort_order`). "Latest" will return inconsistent results depending on which entity type is queried.

```python
# context_preview.py:175-176
if selection_mode == "latest":
    return records[0]  # What does "latest" mean? No date sort applied
```

- **Recommendation**: Sort records by a relevant date field (e.g., `created_at` descending) before selecting the "latest" one. Add a `sort_key` parameter to `_select_records` or pre-sort before calling it.

---

### [P1-4] `DatabaseModule.tsx` is 873 lines — too large, mixes 4 distinct workbenches

**Status (2026-05-01)**: ✅ FIXED.

- **Location**: `frontend/src/modules/database/DatabaseModule.tsx`
- **Category**: Maintainability
- **Impact**: One file contains `StandardsWorkbench`, `UploadForm`, `CompanyLibraryWorkbench`, `PersonnelLibraryWorkbench`, and the routing `DatabaseModule`. Each workbench has its own state, API calls, and JSX. This makes the file hard to navigate, test, and review.

- **Recommendation**: Extract each workbench into its own component file:
  - `StandardsWorkbench.tsx`
  - `CompanyLibraryWorkbench.tsx`
  - `PersonnelLibraryWorkbench.tsx`
  - `UploadForm.tsx`
  Keep `DatabaseModule.tsx` as a thin router.

---

### [P1-5] `master_data.py` is 795 lines — monolithic API file with 7 entity CRUDs

**Status (2026-05-01)**: ✅ FIXED.

- **Location**: `backend/tender_backend/api/master_data.py`
- **Category**: Maintainability
- **Impact**: One API file handles: library companies, company profiles, people, project performances, certificates, financial statements, and evidence assets. Each has ~100 lines of Pydantic models + endpoint functions. The file is repetitive and hard to extend.

- **Recommendation**: Split by domain:
  - `api/routes/library_companies.py`
  - `api/routes/company_profiles.py`
  - `api/routes/people.py`
  - `api/routes/project_performances.py`
  - `api/routes/certificates.py`
  - `api/routes/financial_statements.py`
  - `api/routes/evidence_assets.py`
  Or at minimum group related entities (companies + profiles; people; performances + certificates; financials; evidence).

---

### [P1-6] `suggest_field_mappings` uses fragile keyword matching in Chinese

**Status (2026-05-01)**: ✅ FIXED — `confidence` field added.

- **Location**: `backend/tender_backend/services/template_service/context_preview.py:67-127`
- **Category**: Correctness
- **Impact**: Field mapping suggestions rely on substring matching against `item_name` in Chinese (e.g., `"基本情况表" in item_name`, `"证书" in item_name`). This is fragile — a template item named "资质证书汇总" would not match `"证书"` (it does, actually), but a typo or variant like "资格证" would break it. The `item_code.startswith("5")` heuristic is similarly arbitrary.

```python
# context_preview.py:71
if source_type == "company_profile" and ("基本情况表" in item_name or (item_code or "").startswith("5")):
```

- **Recommendation**: These are heuristics/suggestions, so strict correctness isn't critical — but document this behavior clearly in the API response. Add a `confidence` field to suggestion groups (e.g., 0.8 for keyword match, 0.3 for fallback).

---

### [P1-7] `_render_attachment_item` with empty assets raises `ValueError` but swallows it in bundle render

**Status (2026-05-01)**: ✅ FIXED — preflight endpoint reports issues before render.

- **Location**: `backend/tender_backend/services/template_service/package_renderer.py:387-418, 442-481`
- **Category**: Error Handling
- **Impact**: `_render_attachment_item` raises `ValueError("attachment item has no evidence assets to export")` if there are no assets. The calling loop in `render_template_package_bundle` catches `Exception` and adds it to `item_results` as `"status": "failed"`. While this prevents crashes, it means a misconfigured template item silently fails in the bundle output — the user sees `failed_count: 1` with an error message but no indication of which asset is missing or how to fix it.

- **Recommendation**: Distinguish between "no assets" (configuration issue, should warn before rendering) and "file not found" (runtime issue). Add a pre-flight validation endpoint that checks all items in a package for renderability without actually rendering.

---

## P2 — Minor

### [P2-1] Hard-coded `/tmp` render paths — not configurable, not container-friendly

**Status (2026-05-01)**: ✅ FIXED.

- **Location**: `docx_renderer.py:14` (`_RENDER_ROOT`), `package_renderer.py:21` (`_RENDER_BUNDLE_ROOT`)
- **Category**: Configuration
- **Impact**: Render output always goes to `/tmp/tender_template_renders` and `/tmp/tender_template_bundles`. In containerized environments, `/tmp` may be memory-backed (tmpfs) and limited in size. On multi-worker deployments, each worker writes to the same path, risking conflicts.
- **Recommendation**: Make these paths configurable via environment variables (e.g., `TEMPLATE_RENDER_ROOT`, `TEMPLATE_BUNDLE_ROOT`) with `/tmp/...` as defaults.

---

### [P2-2] SQL column strings interpolated with f-strings — not injection but fragile

**Status (2026-05-01)**: ⏸ DEFERRED — column constants are module-level literals; no user input flows into SQL identifiers, so no injection risk. Migrating to `psycopg.sql.Identifier`/`SQL` is a code-quality refactor, tracked for a future cleanup pass.

- **Location**: `master_data_repo.py` (all query methods), `bid_template_binding_repo.py`, `bid_template_package_repo.py`
- **Category**: Code Quality
- **Impact**: Column lists are stored in module-level constants and interpolated via f-string. While there's no direct injection risk (they're constants), it's a pattern that could be copied to places where user input is interpolated. It also means any column rename requires updating both the constant AND the `_to_row()` mapper.
- **Recommendation**: Use an ORM pattern or at minimum use `psycopg.sql.Identifier` / `psycopg.sql.SQL` for dynamic SQL composition.

---

### [P2-3] `draftFromBinding` loses `date_format`, `decimals`, `join_with` if not present

**Status (2026-05-01)**: ✅ FIXED.

- **Location**: `frontend/src/modules/database/components/TemplateFieldWorkbench.tsx:120-132`
- **Category**: Correctness (Frontend)
- **Impact**: When editing an existing binding, `draftFromBinding` copies `rule.field_mappings` directly. If a mapping has implicit defaults (e.g., `transform: "date"` without explicit `date_format`), the UI won't show the default format string, but saving will send `undefined` — which the backend may or may not handle. The backend's `_apply_field_mapping_to_record` defaults to `%Y-%m-%d` for dates, so it's safe, but the UI is misleading.

- **Recommendation**: Normalize field mappings in `draftFromBinding` the same way `normalizeFieldMappings` does — ensure all transforms have their default parameters populated.

---

### [P2-4] Polling effect in `StandardsWorkbench` recreates interval on every standards change

**Status (2026-05-01)**: ✅ FIXED.

- **Location**: `frontend/src/modules/database/DatabaseModule.tsx:263-277`
- **Category**: Performance (Frontend)
- **Impact**: The `useEffect` for polling depends on `[standards]`. When `setStandards` is called inside the interval callback, it triggers a re-render, which creates a new `standards` array reference, which triggers the effect cleanup and recreation. In practice, this means the 5-second interval is constantly being cleared and recreated.

```typescript
// DatabaseModule.tsx:263-277
useEffect(() => {
    const shouldPoll = standards.some(...)
    if (!shouldPoll) return undefined;
    pollingRef.current = window.setInterval(() => {
        listStandards().then(setStandards).catch(...)
    }, 5000);
    return () => { ... };
}, [standards]);  // <-- This dependency causes constant recreation
```

- **Recommendation**: Use `useRef` to track the latest standards without making it a dependency, or use `setStandards((prev) => ...)` with a functional update and remove `standards` from the dependency array.

---

### [P2-5] `window.confirm()` used for destructive actions — unstyled, non-localized

**Status (2026-05-01)**: ✅ FIXED.

- **Location**: `frontend/src/modules/database/DatabaseModule.tsx:364`, `frontend/src/modules/database/components/TemplateFieldWorkbench.tsx:541`
- **Category**: UX (Frontend)
- **Impact**: `window.confirm()` is unstyled, blocks the main thread, and renders differently across browsers. It breaks the visual consistency of the app.
- **Recommendation**: Build a simple `ConfirmDialog` component using the clay design system, or at minimum use a controlled modal.

---

### [P2-6] Exported `EvidenceAsset` response includes `file_path` — information disclosure

**Status (2026-05-01)**: ✅ FIXED.

- **Location**: `backend/tender_backend/api/master_data.py:504-524` (`_evidence_asset_out()`)
- **Category**: Security
- **Impact**: The `GET /master-data/evidence-assets` endpoint returns `file_path` for every asset, exposing server filesystem paths to the frontend. This is unnecessary for the UI and aids attackers in path traversal attempts.
- **Recommendation**: Remove `file_path` from the API response, or return only a relative path from the upload root. The frontend should never need absolute server paths.

---

## P3 — Polish

### [P3-1] `_to_cn_numeral` only supports 1-20 — silently returns Arabic for larger values

**Status (2026-05-01)**: ⏸ DEFERRED — no current template exceeds 20 sub-items per attachment chapter. Will revisit if a real template hits the limit.

- **Location**: `backend/tender_backend/services/template_service/package_renderer.py:30-53`
- **Category**: Edge Case
- **Impact**: For template items with more than 20 sub-items, the Chinese numeral rendering silently falls back to Arabic numerals. The output will mix "（二十一）" (desired) with "（21）" (actual), looking inconsistent.
- **Recommendation**: Add handling for numbers > 20 by composing tens + ones, or fall back more gracefully.

---

### [P3-2] `_is_active_status` defined but uses string literals — fragile to backend changes

**Status (2026-05-01)**: ⏸ DEFERRED — small surface area after polling moved into `StandardsWorkbench`; revisit if backend introduces additional processing states.

- **Location**: `frontend/src/modules/database/DatabaseModule.tsx:58-60`
- **Category**: Maintainability
- **Impact**: The polling logic checks hard-coded status strings. If the backend adds a new processing status or renames one, the frontend will stop polling prematurely.
- **Recommendation**: Use an enum or at minimum export the status list as a constant shared between polling and display logic.

---

### [P3-3] Migration `0019_evidence_assets.py` and `0020_binding_field_mappings.py` — verify FK cascade behavior

**Status (2026-05-01)**: 🛡 VERIFIED — `0018_bid_template_binding_rules.py:25` defines `template_item_id ... ON DELETE CASCADE`. After the P0-3 fix the cascade path is no longer hit during re-import (rows are updated in place). Cascade behavior remains intentional for hard-delete flows.

- **Location**: `backend/tender_backend/db/alembic/versions/0019_evidence_assets.py`, `0020_binding_field_mappings.py`
- **Category**: Schema Design
- **Impact**: The `replace_items` issue (P0-3) depends on whether these migrations use `ON DELETE CASCADE`. Need to verify.
- **Recommendation**: Read the migration files and confirm cascade behavior. Document the intended behavior in a comment.

---

### [P3-4] No integration tests for DOCX rendering or bundle export

**Status (2026-05-01)**: ⏸ DEFERRED (partial) — unit-level coverage added (`test_package_renderer.py`, `test_template_docx_renderer.py`), and `test_template_package_api.py` exists. The latter is skipped without `DATABASE_URL`; full integration runs require a DB-enabled CI lane.

- **Location**: Test directory — `test_template_binding_api.py` (432 lines), but no tests for `render_template_item_docx` or `render_template_package_bundle`
- **Category**: Test Coverage
- **Impact**: The most complex logic (DOCX generation, asset embedding, PDF-to-image conversion, ZIP bundling) has no API-level integration tests.
- **Recommendation**: Add at minimum:
  1. A test that renders a template item with mock context data and verifies the DOCX is valid
  2. A test that renders a bundle with mock evidence assets and verifies the output structure

---

## Patterns & Cross-Cutting Concerns

### Strengths

1. **Consistent data access pattern**: All repository methods use the same `dict_row` cursor + `_to_*()` mapper pattern. Clean and predictable.

2. **Proper validation layering**: Pydantic models validate shape → endpoint validators validate domain rules → service validators validate business logic. Clear separation.

3. **Race-condition handling in viewer**: `viewerRequestRef` counter + `AbortController` pattern in StandardsWorkbench correctly handles rapid successive requests.

4. **Well-typed frontend API client**: All new types in `api.ts` have proper TypeScript interfaces matching backend Pydantic models.

5. **Sensible use of lazy loading**: `DatabaseModule` is the heaviest module and correctly uses `React.lazy()`.

6. **Good error classification**: Backend consistently distinguishes `LookupError` (404) from `ValueError` (400).

### Concerns

1. **Dual source of validation truth**: Field mapping validators exist in `context_preview.py` (called by service layer) AND are re-validated in `template_bindings.py` (API layer). The validators are imported from one place, but the `_validate_payload` in the API duplicates the orchestration logic.

2. **Commit inconsistency**: Some repo methods commit, others don't. This is systemic — need a clear policy (commit at repo layer vs commit at API layer).

3. **Chinese text hard-coded in Python**: `suggest_field_mappings` and `docx_renderer.py` have hard-coded Chinese strings for matching and rendering. This is necessary for domain logic but makes internationalization impossible later.

4. **Frontend `TemplateFieldWorkbench` is complex but well-structured**: At 904 lines, it's large but uses hooks well and has clear data flow. The main issue is the number of controlled form fields that could benefit from a reducer pattern.

---

## Recommended Action Order

1. **[P0-1, P0-2] Fix path traversal** in evidence asset handling and template import — highest risk
2. **[P0-3] Fix `replace_items` data loss** — verify FK cascade, add explicit binding cleanup
3. **[P0-4] Implement or remove `by_id` selection mode** — users will configure it and get wrong results
4. **[P0-5] Add `conn.commit()` to `upsert_package`** — simple fix, latent bug
5. **[P0-6] Add file upload validation** — size limits, type checking
6. **[P1-1] Fix N+1 query** — minor code change, big performance impact
7. **[P1-2] Verify auth coverage** on all new endpoints
8. **[P1-4, P1-5] Split large files** — `DatabaseModule.tsx` and `master_data.py`
9. **[P1-7] Improve attachment render error handling** — pre-flight validation endpoint
10. **[P2-5] Replace `window.confirm()`** with styled dialog

---

## Test Coverage Summary

| Area | Tests | Coverage |
|------|-------|----------|
| Master Data API | `test_master_data_api.py` (332 lines) | Good |
| Template Binding API | `test_template_binding_api.py` (432 lines) | Good |
| Template Package API | `test_template_package_api.py` (120 lines) | Basic |
| Package Importer | `test_bid_template_package_importer.py` (37 lines) | Minimal |
| Package Renderer | `test_package_renderer.py` (175 lines) | OK |
| Context Preview | `test_template_context_preview.py` (142 lines) | OK |
| DOCX Renderer | `test_template_docx_renderer.py` (168 lines) | OK |
| **Bundle Export** | **None** | **Missing** |
| **DOCX to API** | **None** | **Missing** |
| **Evidence Asset Upload** | **None** | **Missing** |
| **Frontend Components** | **None** | **Missing** |

---

## Verdict

**DO NOT MERGE** until the 6 P0 issues are resolved. The path traversal and data integrity issues are real risks. The overall architecture is solid and the feature set is impressive — the issues are fixable and mostly localized.
