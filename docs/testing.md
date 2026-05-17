# Testing

## Local Development Smoke Test

Run the local doctor before UI debugging:

```bash
./scripts/doctor_local.sh
```

It verifies:

1. Docker compose is reachable.
2. Frontend is reachable on `FRONTEND_PORT`.
3. Backend `/api/health` is reachable on `BACKEND_PORT`.
4. Local `dev-token` authentication works.
5. The `sgcc_distribution` template package list is non-empty.

For local Docker debugging, `infra/.env` must include:

```env
VITE_ENABLE_DEV_AUTH=true
VITE_DEV_AUTH_TOKEN=dev-token
```

For production deployment, keep dev auth disabled:

```env
VITE_ENABLE_DEV_AUTH=false
```

Do not treat "template package count is 0" or any `401` API response as a successful deployment.

## E2E Testing Prerequisites

Before running chapter 8 end-to-end tests:

1. Verify acceptance closure: `./scripts/check_acceptance_before_test.sh`
2. Ensure longform closure has been merged into the current HEAD
3. Ensure real-sample evidence exists under `docs/acceptance/`

## Chapter 8 Acceptance Evidence

Collect chapter 8 evidence with:

```bash
python scripts/run_chapter_8_acceptance.py \
  --project-id <project-uuid> \
  --output docs/acceptance/2026-05-16-chapter-8-real-sample-evidence.json
```

This captures:

- `chapter_draft` page/coverage/chart-closure evidence
- latest `export_record` metadata snapshot
- current `export_gate` state

## Multi-Chapter Longform Acceptance Evidence

Collect chapter 8/9/10.x evidence with:

```bash
python scripts/run_longform_multi_chapter_acceptance.py \
  --project-id <project-uuid> \
  --output docs/acceptance/2026-MM-DD-longform-8-9-10-evidence.json
```

This captures:

- per-chapter `chapter_draft` page/coverage/chart-closure evidence
- per-chapter longform `model_usage`
- latest `export_record` metadata snapshot
- current `export_gate` state
