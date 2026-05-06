# Code Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the highest-risk security, resource-exhaustion, and operability findings from the full-project review without broad unrelated refactors.

**Architecture:** The remediation is split into independently verifiable batches: route authorization, project access foundations, AI gateway hardening, archive resource limits, frontend auth behavior, and dev/prod runtime separation. The first pass favors minimal API-compatible changes; deeper multi-tenant membership is isolated behind a schema-backed access layer so later feature work can adopt it consistently.

**Tech Stack:** FastAPI, Pydantic Settings, psycopg, Alembic, pytest, React 18, TanStack Query, Vite, Vitest, Docker Compose.

---

## Scope And Sequencing

This plan implements the P0/P1 review findings first. Execute tasks in order unless a task explicitly states it can be parallelized.

- Task 1 blocks unauthenticated user/project/parse access.
- Task 2 introduces schema-backed project membership and owner assignment.
- Task 3 locks down AI Gateway access and provider override safety.
- Task 4 adds ZIP decompression resource limits.
- Task 5 makes frontend development auth explicit and production-safe.
- Task 6 separates development runtime defaults from production-safe container defaults.
- Task 7 runs full verification and records residual risks.

## Files Overview

- Modify: `backend/tender_backend/core/security.py` to tighten development token behavior and role checks if needed.
- Modify: `backend/tender_backend/api/users.py` to require admin access for user management.
- Modify: `backend/tender_backend/api/projects.py` to require authentication, role-aware creation/deletion, and membership assignment.
- Modify: `backend/tender_backend/api/parse.py` to require authentication and resource project access checks.
- Modify: `backend/tender_backend/core/project_access.py` to support membership-backed project access while preserving admin access.
- Create: `backend/tender_backend/db/alembic/versions/0036_project_membership.py` for project membership schema.
- Modify: `backend/tender_backend/db/repositories/project_repository.py` to create/list/delete through membership-aware methods.
- Modify: `backend/tender_backend/db/repositories/user_repository.py` only if current user identity needs stable `user_id`.
- Modify: `ai_gateway/tender_ai_gateway/core/config.py`, `ai_gateway/tender_ai_gateway/api/chat.py`, and `ai_gateway/tender_ai_gateway/fallback.py` for shared-secret auth and override allowlists.
- Modify: backend AI gateway callers in `backend/tender_backend/services/**` and `backend/tender_backend/workers/tasks_extract.py` to send gateway auth headers.
- Modify: `backend/tender_backend/services/tender_document_ingestion.py` for ZIP limits.
- Modify: `frontend/src/lib/api.ts` and relevant auth/settings tests for explicit dev token behavior and better 401 handling.
- Modify: `backend/Dockerfile`, `ai_gateway/Dockerfile`, and `infra/docker-compose.yml` for dev/prod command separation.
- Test: Add or update focused pytest/vitest tests alongside the existing suites listed in each task.

---

### Task 1: Protect User, Project, And Legacy Parse APIs

**Files:**
- Modify: `backend/tender_backend/api/users.py`
- Modify: `backend/tender_backend/api/projects.py`
- Modify: `backend/tender_backend/api/parse.py`
- Test: `backend/tests/unit/test_security.py`
- Test: `backend/tests/integration/test_master_data_api.py`
- Create or modify: `backend/tests/integration/test_authz_routes.py`

- [x] **Step 1: Add failing authz tests for user management**

Add tests showing anonymous users cannot manage `/api/users`, and non-admin users get 403 for management writes. Use `SyncASGIClient` and existing DB schema helpers where possible.

```python
def test_user_management_requires_admin(client):
    anonymous = SyncASGIClient(app)
    assert anonymous.get("/api/users").status_code == 401
    assert anonymous.post("/api/users", json={
        "username": "xuser",
        "password": "secret123",
        "display_name": "X User",
        "role": "editor",
    }).status_code == 401

    editor = SyncASGIClient(app)
    editor.headers.update({"Authorization": "Bearer editor-token"})
    assert editor.get("/api/users").status_code == 403
    assert editor.post("/api/users", json={
        "username": "xuser",
        "password": "secret123",
        "display_name": "X User",
        "role": "editor",
    }).status_code == 403
```

Run: `cd backend && ../.venv/bin/pytest tests/integration/test_authz_routes.py -q`

Expected before implementation: tests fail because `/users` currently permits unauthenticated access.

- [x] **Step 2: Require admin role for all `/users` routes**

Update `backend/tender_backend/api/users.py` so the router requires authentication and each endpoint requires admin.

Implementation direction:

```python
from tender_backend.core.security import Role, get_current_user, require_role

router = APIRouter(tags=["users"], dependencies=[Depends(get_current_user)])

@router.get("/users", response_model=list[UserOut])
async def list_users(
    conn: Connection = Depends(get_db_conn),
    _admin=Depends(require_role(Role.ADMIN)),
) -> list[UserOut]:
    ...
```

Apply the same `_admin=Depends(require_role(Role.ADMIN))` dependency to create, update, and delete.

- [x] **Step 3: Add failing tests for project route authentication and role policy**

Add tests for:

- Anonymous `GET /api/projects` returns 401.
- Anonymous `POST /api/projects` returns 401.
- Reviewer `POST /api/projects` returns 403.
- Editor/Admin can create projects.
- Reviewer cannot delete projects.

Run: `cd backend && ../.venv/bin/pytest tests/integration/test_authz_routes.py -q`

Expected before implementation: tests fail on anonymous project list/create and reviewer create/delete behavior.

- [x] **Step 4: Enforce project route auth and write roles**

Update `backend/tender_backend/api/projects.py`:

- Router or endpoint requires `get_current_user` for list/create/delete.
- `create_project` allows `Role.EDITOR` and `Role.ADMIN`.
- `delete_project` allows `Role.ADMIN` initially; if project ownership from Task 2 is already complete, allow owner/editor policy there.

Implementation direction:

```python
from tender_backend.core.security import Role, require_role

@router.post("/projects", response_model=ProjectOut)
async def create_project(
    payload: ProjectCreate,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(require_role(Role.EDITOR, Role.ADMIN)),
) -> ProjectOut:
    project = _repo.create(conn, name=payload.name.strip())
    return ProjectOut(id=project.id, name=project.name)
```

- [x] **Step 5: Add failing tests for legacy parse route auth**

Add tests for:

- Anonymous `POST /api/documents/{document_id}/parse-jobs` returns 401.
- Anonymous `GET /api/parse-jobs/{parse_job_id}` returns 401.
- Anonymous `GET /api/documents/{document_id}/parse-result` returns 401.
- Anonymous `POST /api/parse-jobs/{parse_job_id}/retry` returns 401.

Run: `cd backend && ../.venv/bin/pytest tests/integration/test_authz_routes.py -q`

Expected before implementation: tests fail because legacy parse routes are public.

- [x] **Step 6: Add auth and project-resource access to `parse.py`**

Update `backend/tender_backend/api/parse.py`:

- Import `CurrentUser`, `get_current_user`, and `require_resource_project_access`.
- For `document_id` routes, resolve `document -> project_file -> project`.
- For `parse_job_id` routes, resolve `parse_job -> document -> project_file -> project`.

Queries:

```sql
SELECT pf.project_id
FROM document d
JOIN project_file pf ON pf.id = d.project_file_id
WHERE d.id = %s
```

```sql
SELECT pf.project_id
FROM parse_job pj
JOIN document d ON d.id = pj.document_id
JOIN project_file pf ON pf.id = d.project_file_id
WHERE pj.id = %s
```

- [x] **Step 7: Run focused backend authorization tests**

Run:

```bash
cd backend && ../.venv/bin/pytest tests/unit/test_security.py tests/unit/test_project_access.py tests/integration/test_authz_routes.py -q
```

Expected: all pass.

- [x] **Step 8: Commit Task 1**

```bash
git add backend/tender_backend/api/users.py backend/tender_backend/api/projects.py backend/tender_backend/api/parse.py backend/tests/unit/test_security.py backend/tests/integration/test_authz_routes.py
git commit -m "fix: protect management and parse routes"
```

---

### Task 2: Add Project Membership Foundation

**Files:**
- Create: `backend/tender_backend/db/alembic/versions/0036_project_membership.py`
- Modify: `backend/tender_backend/core/security.py`
- Modify: `backend/tender_backend/core/project_access.py`
- Modify: `backend/tender_backend/db/repositories/project_repository.py`
- Modify: `backend/tender_backend/api/projects.py`
- Test: `backend/tests/unit/test_project_access.py`
- Test: `backend/tests/integration/test_authz_routes.py`

- [x] **Step 1: Add failing unit tests for membership-backed access**

Extend `backend/tests/unit/test_project_access.py` with fake connection rows covering:

- Admin can access existing project even without membership.
- Editor/reviewer can access project when membership row exists.
- Editor/reviewer gets 404 or 403 when project exists but membership is absent.

Expected policy for this implementation: return 403 when project exists but user lacks membership.

- [x] **Step 2: Extend `CurrentUser` with optional `user_id`**

Update `backend/tender_backend/core/security.py`:

```python
@dataclass(frozen=True)
class CurrentUser:
    token: str
    role: Role
    display_name: str
    user_id: UUID | None = None
```

When resolving DB sessions, set `user_id=session_user.id`. Static `dev-token` remains `None` and is admin-only in development/test.

- [x] **Step 3: Create project membership migration**

Create `backend/tender_backend/db/alembic/versions/0036_project_membership.py`:

```sql
CREATE TABLE IF NOT EXISTS project_member (
  project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  role VARCHAR(20) NOT NULL DEFAULT 'editor',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_project_member_user ON project_member (user_id, project_id);
```

Do not backfill all users to all projects. Existing development usage remains covered by admin `dev-token`; real session users only see projects they own or are assigned to.

- [x] **Step 4: Update project repository for membership-aware create/list/delete**

Add methods:

```python
def create_for_user(self, conn: Connection, *, name: str, user_id: UUID | None) -> Project:
    ...

def list_for_user(self, conn: Connection, *, user: CurrentUser) -> list[Project]:
    ...
```

Policy:

- Admin lists all projects.
- Non-admin with `user.user_id` lists only joined projects.
- Project creation by a DB user inserts `project_member(project_id, user_id, role='owner')` in the same transaction.
- Static development admin creates projects without membership.

- [x] **Step 5: Update `require_project_access` for membership**

Update `backend/tender_backend/core/project_access.py`:

- Confirm project existence first.
- Admin passes.
- Non-admin without `user_id` fails 403.
- Non-admin with a `project_member` row passes.
- Non-admin without membership fails 403.

- [x] **Step 6: Update projects API to use membership-aware methods**

Update `list_projects` to pass `user`. Update `create_project` to call `create_for_user`.

- [x] **Step 7: Run migration and project access tests**

Run:

```bash
cd backend && ../.venv/bin/pytest tests/unit/test_project_access.py tests/integration/test_authz_routes.py -q
```

If `DATABASE_URL` is available, also run:

```bash
cd backend && ../.venv/bin/alembic -c tender_backend/db/alembic.ini upgrade head
```

Expected: tests pass; migration applies cleanly.

- [x] **Step 8: Commit Task 2**

```bash
git add backend/tender_backend/core/security.py backend/tender_backend/core/project_access.py backend/tender_backend/db/repositories/project_repository.py backend/tender_backend/api/projects.py backend/tender_backend/db/alembic/versions/0036_project_membership.py backend/tests/unit/test_project_access.py backend/tests/integration/test_authz_routes.py
git commit -m "feat: add project membership access control"
```

---

### Task 3: Harden AI Gateway Authentication And Provider Overrides

**Files:**
- Modify: `ai_gateway/tender_ai_gateway/core/config.py`
- Modify: `ai_gateway/tender_ai_gateway/api/chat.py`
- Modify: `ai_gateway/tender_ai_gateway/fallback.py`
- Modify: `backend/tender_backend/core/config.py`
- Modify: AI gateway callers in `backend/tender_backend/services/extract_service/ai_requirements_extractor.py`, `backend/tender_backend/services/extract_service/tender_facts_extractor.py`, `backend/tender_backend/services/norm_service/norm_processor.py`, `backend/tender_backend/services/vision_service/repair_service.py`, and `backend/tender_backend/workers/tasks_extract.py`
- Test: `ai_gateway/tests/smoke/test_gateway.py`
- Test: relevant backend unit tests for gateway payload helpers if present

- [x] **Step 1: Add failing AI gateway auth tests**

Add tests:

- `POST /api/ai/chat` with no shared secret returns 401 when `AI_GATEWAY_SHARED_SECRET` is configured.
- Request with `Authorization: Bearer <secret>` succeeds or reaches normal provider/stub behavior.
- In production, override `base_url` not on allowlist returns 400.

Run: `cd ai_gateway && ../.venv/bin/pytest tests/smoke/test_gateway.py -q`

- [x] **Step 2: Add AI Gateway shared secret settings**

Add to `ai_gateway/tender_ai_gateway/core/config.py`:

```python
ai_gateway_shared_secret: str = ""
provider_override_allowed_hosts: str = ""
allow_provider_overrides: bool = True
```

Production behavior:

- If `app_env` is not development/test and `ai_gateway_shared_secret` is empty, reject chat requests with 503 configuration error.
- If secret is configured, require `Authorization: Bearer <secret>`.

- [x] **Step 3: Enforce shared secret in chat route**

Update `ai_gateway/tender_ai_gateway/api/chat.py`:

```python
from fastapi import APIRouter, Header, HTTPException

def _require_gateway_auth(authorization: str | None, settings: Settings) -> None:
    ...
```

Apply this at the start of `chat`.

- [x] **Step 4: Restrict provider overrides**

Update `ai_gateway/tender_ai_gateway/fallback.py`:

- Validate override URLs with `urlparse`.
- Allow only `http`/`https`.
- Reject private, loopback, link-local, multicast, and missing hosts.
- If `provider_override_allowed_hosts` is set, host must be in that comma-separated allowlist.
- If `allow_provider_overrides` is false, reject any override.

Return a client-safe `ValueError` message that `chat.py` maps to 400, not 502.

- [x] **Step 5: Add backend AI gateway shared secret setting**

Add to `backend/tender_backend/core/config.py`:

```python
ai_gateway_shared_secret: str = ""
```

For callers that currently read `AI_GATEWAY_URL` directly from `os.environ`, keep the URL behavior for compatibility but add a small local helper:

```python
def _ai_gateway_headers() -> dict[str, str]:
    secret = get_settings().ai_gateway_shared_secret
    return {"Authorization": f"Bearer {secret}"} if secret else {}
```

Use it in all backend `httpx.post(... /api/ai/chat ...)` calls.

- [x] **Step 6: Run AI gateway and affected backend tests**

Run:

```bash
cd ai_gateway && ../.venv/bin/pytest tests/smoke -q
cd backend && ../.venv/bin/pytest tests/unit/test_ai_requirements_extractor.py tests/unit/test_tender_facts_extractor.py tests/unit/test_norm_processor.py tests/unit/test_repair_service.py -q
```

If any listed backend test file does not exist or has a different name, run the closest existing tests covering that caller.

- [ ] **Step 7: Commit Task 3**

```bash
git add ai_gateway/tender_ai_gateway backend/tender_backend ai_gateway/tests backend/tests
git commit -m "fix: authenticate and constrain ai gateway"
```

---

### Task 4: Add ZIP Decompression Resource Limits

**Files:**
- Modify: `backend/tender_backend/core/config.py`
- Modify: `backend/tender_backend/services/tender_document_ingestion.py`
- Test: `backend/tests/unit/test_tender_document_ingestion.py`
- Test: `backend/tests/integration/test_tender_document_upload.py`

- [ ] **Step 1: Add failing unit tests for ZIP limits**

Add tests for:

- Too many files raises `ValueError`.
- Total uncompressed bytes exceeding limit raises `ValueError`.
- Suspicious compression ratio raises `ValueError`.
- Existing unsafe path tests still pass.

Use small test values by constructing `TenderDocumentIngestionService` with explicit limits or by monkeypatching module constants.

- [ ] **Step 2: Add configurable limits**

Add settings:

```python
tender_zip_max_depth: int = 5
tender_zip_max_files: int = 2000
tender_zip_max_uncompressed_bytes: int = 1024 * 1024 * 1024
tender_zip_max_compression_ratio: float = 100.0
```

Wire these into `TenderDocumentIngestionService`.

- [ ] **Step 3: Enforce limits during ZIP traversal and copy**

Update `_extract_zip`:

- Track total extracted file count and uncompressed bytes across recursive calls.
- Check `member.file_size` before copying.
- During copy, count bytes written and abort if aggregate limit is exceeded.
- Reject entries where `member.file_size / max(member.compress_size, 1)` exceeds configured ratio.
- Preserve existing path safety behavior.

- [ ] **Step 4: Ensure failed ingest cleans up partial extracted files**

Keep the existing `created_document_root` cleanup behavior. Add/extend tests to assert partial roots are removed after a limit error for newly created document roots.

- [ ] **Step 5: Run ingestion tests**

Run:

```bash
cd backend && ../.venv/bin/pytest tests/unit/test_tender_document_ingestion.py tests/integration/test_tender_document_upload.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit Task 4**

```bash
git add backend/tender_backend/core/config.py backend/tender_backend/services/tender_document_ingestion.py backend/tests/unit/test_tender_document_ingestion.py backend/tests/integration/test_tender_document_upload.py
git commit -m "fix: limit tender zip extraction resources"
```

---

### Task 5: Make Frontend Auth Explicit And Robust

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify or create: `frontend/src/lib/api.test.ts`
- Modify: auth-related components if 401 routing requires UI integration

- [ ] **Step 1: Add failing frontend API tests**

Add tests for:

- `getAuthHeaders` does not auto-create `dev-token` unless `VITE_ENABLE_DEV_AUTH=true`.
- When dev auth is enabled, it uses `VITE_DEV_AUTH_TOKEN` if present, otherwise `dev-token`.
- Non-JSON error responses surface a useful error.
- 401 clears `tender_token` and emits a consistent auth error.

Run: `cd frontend && npm run test -- api`

- [ ] **Step 2: Update dev auth behavior**

Change `getToken()`:

```ts
if (import.meta.env.DEV && import.meta.env.VITE_ENABLE_DEV_AUTH === "true") {
  const devToken = import.meta.env.VITE_DEV_AUTH_TOKEN ?? "dev-token";
  localStorage.setItem("tender_token", devToken);
  return devToken;
}
```

Production must never auto-create a token.

- [ ] **Step 3: Harden request error handling**

Update `request<T>`:

- Try JSON error body first.
- Fall back to text body.
- On `401`, remove `tender_token` and throw an error with a stable message such as `登录已失效，请重新登录`.
- Handle `204 No Content` by returning `undefined as T`.

- [ ] **Step 4: Run frontend tests and build**

Run:

```bash
cd frontend && npm run test
npm run build:frontend
```

Expected: tests and build pass.

- [ ] **Step 5: Commit Task 5**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/api.test.ts frontend/src
git commit -m "fix: make frontend auth explicit"
```

---

### Task 6: Separate Development And Production Runtime Defaults

**Files:**
- Modify: `backend/Dockerfile`
- Modify: `ai_gateway/Dockerfile`
- Modify: `infra/docker-compose.yml`
- Modify: `infra/.env.example`
- Test: root `package.json` scripts if compose verification changes

- [ ] **Step 1: Update Dockerfiles to production-safe defaults**

Change default commands to no reload:

```dockerfile
CMD ["uvicorn", "tender_backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```dockerfile
CMD ["uvicorn", "tender_ai_gateway.main:app", "--host", "0.0.0.0", "--port", "8100"]
```

Keep development reload in `infra/docker-compose.yml` service `command`.

- [ ] **Step 2: Add required environment examples**

Update `infra/.env.example`:

- Document `AUTH_TOKENS` or DB login bootstrap expectations.
- Add `AI_GATEWAY_SHARED_SECRET`.
- Add `VITE_ENABLE_DEV_AUTH=false` guidance if frontend env examples exist.
- Warn that default seeded passwords must be changed outside local development.

- [ ] **Step 3: Validate compose config**

Run:

```bash
npm run verify:compose
```

Expected: compose config resolves successfully.

- [ ] **Step 4: Commit Task 6**

```bash
git add backend/Dockerfile ai_gateway/Dockerfile infra/docker-compose.yml infra/.env.example package.json
git commit -m "chore: separate dev and production runtime defaults"
```

---

### Task 7: Full Verification And Residual Risk Report

**Files:**
- Modify: `docs/reviews/2026-05-06-remediation-verification.md`

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
npm run test:backend
```

Expected: pass, or record failing tests with root cause if environment dependencies are missing.

- [ ] **Step 2: Run AI gateway tests**

Run:

```bash
npm run test:ai-gateway
```

Expected: pass.

- [ ] **Step 3: Run frontend tests and build**

Run:

```bash
cd frontend && npm run test
cd .. && npm run build:frontend
```

Expected: pass.

- [ ] **Step 4: Run compose verification**

Run:

```bash
npm run verify:compose
```

Expected: pass.

- [ ] **Step 5: Write verification report**

Create `docs/reviews/2026-05-06-remediation-verification.md` with:

- Commands run.
- Pass/fail output summary.
- Any skipped tests and why.
- Residual risks, especially remaining transaction-boundary refactors not completed in this pass.

- [ ] **Step 6: Commit verification report**

```bash
git add docs/reviews/2026-05-06-remediation-verification.md
git commit -m "docs: record remediation verification"
```

---

## Deferred Work

These items are intentionally deferred because they need broader product or architecture decisions:

- Repository-wide transaction boundary refactor: change all repositories to stop committing internally and make services own transactions. This should be its own plan because it touches most write paths.
- Full organization/tenant model: `project_member` is a foundation, but organization-level billing, invitation, and ownership policies require product decisions.
- Password policy and account lifecycle hardening: lockout, password reset, password rotation, and audit logs should be planned together.
- OpenSearch `verify=False` review: current local OpenSearch calls may be acceptable for development, but production TLS and certificate handling need a deployment-specific decision.

## Approval Gate

Implementation must not start until the plan is approved. Recommended first implementation checkpoint is after Task 1 because it closes the clearest unauthenticated access issues and is low-risk compared with schema and gateway changes.
