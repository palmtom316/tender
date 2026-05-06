# 2026-05-06 Remediation Verification

## Commands Run

- `npm run test:backend`
- `npm run test:ai-gateway`
- `cd frontend && npm run test`
- `npm run build:frontend`
- `npm run verify:compose`
- `docker compose --env-file infra/.env -f infra/docker-compose.yml --profile app config`

## Results

- Backend: `529 passed, 49 skipped, 5 warnings`.
- AI Gateway: `20 passed`.
- Frontend tests: `10 files passed, 20 tests passed`.
- Frontend build: TypeScript build and Vite production build completed successfully.
- Compose base config: parsed successfully.
- Compose app profile config: parsed successfully, including explicit development `--reload` commands in compose while Dockerfile defaults remain production-safe.

## Skips And Warnings

- Backend integration skips are expected in this environment because `DATABASE_URL` is not set for DB-backed integration suites.
- PyMuPDF/SWIG deprecation warnings are pre-existing test-environment warnings and were not introduced by this remediation.
- Vite test warnings about deprecated `esbuild` plugin options are pre-existing frontend toolchain warnings.

## Residual Risks

- Repository-wide transaction ownership remains mixed between API/service and repository layers. This is intentionally deferred to a separate transaction-boundary refactor.
- `project_member` is a project-level access foundation, not a full organization/tenant model.
- Password lifecycle hardening remains deferred: lockout, reset, rotation, audit logs, and forced default-password changes require product decisions.
- Compose verification used local `infra/.env`; secret values were not recorded in this report.
