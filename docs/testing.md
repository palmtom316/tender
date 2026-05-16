# Testing

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
