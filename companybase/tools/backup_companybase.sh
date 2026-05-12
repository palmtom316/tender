#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="$ROOT/backups"
NAME="companybase_${STAMP}"
ARCHIVE="$OUT_DIR/${NAME}.tar.gz"

mkdir -p "$OUT_DIR"

tar \
  --exclude="backups" \
  --exclude="templates/.xlsx_work" \
  -czf "$ARCHIVE" \
  -C "$(dirname "$ROOT")" \
  "$(basename "$ROOT")/README.md" \
  "$(basename "$ROOT")/docs" \
  "$(basename "$ROOT")/templates" \
  "$(basename "$ROOT")/imports" \
  "$(basename "$ROOT")/exports" \
  "$(basename "$ROOT")/files" \
  "$(basename "$ROOT")/tools"

shasum -a 256 "$ARCHIVE" > "$ARCHIVE.sha256"
echo "$ARCHIVE"
echo "$ARCHIVE.sha256"
