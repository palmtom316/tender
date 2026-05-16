#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ACCEPTANCE_FILE="$ROOT_DIR/docs/acceptance/2026-05-15-longform-launch-closure.md"
EVIDENCE_FILE="$ROOT_DIR/docs/acceptance/2026-05-16-chapter-8-real-sample-evidence.json"

if [ ! -f "$ACCEPTANCE_FILE" ]; then
  echo "ERROR: Acceptance file not found: $ACCEPTANCE_FILE"
  exit 1
fi

if ! grep -q "Launch Decision Rule" "$ACCEPTANCE_FILE"; then
  echo "ERROR: Acceptance file incomplete: missing Launch Decision Rule"
  exit 1
fi

if [ ! -f "$EVIDENCE_FILE" ]; then
  echo "ERROR: Real sample evidence not found: $EVIDENCE_FILE"
  echo "Run scripts/run_chapter_8_acceptance.py before chapter 8 e2e testing."
  exit 1
fi

echo "✓ Acceptance checks passed"
