---
name: mineru-standard-bundle
description: Use when working in the tender repository with MinerU 2.7.x hybrid/vlm standard-document outputs and you need deterministic bundle generation, quality evaluation, cleanup, or cross-standard comparison from local pdf, md, and json files.
---

# MinerU Standard Bundle

Use this skill for repo-local standard-document workflows that start from local MinerU files:

- `pdf`
- `md`
- `json`

This skill is specific to:

- the `tender` repository
- MinerU `2.7.x`
- `hybrid` and `vlm` backends only
- standard documents, not tender-file ingestion

Do not use this skill for:

- legacy `pipeline` payloads
- arbitrary OCR formats
- database import execution

## Workflow

1. Confirm the input files are local and belong to the same document.
2. Run `evaluate` to emit `raw-payload.json`, `system-bundle.json`, and `summary.json`.
3. Run `clean` when you need to reduce TOC noise, suspicious year-like section codes, and recoverable missing page anchors.
4. Run `compare` with a manifest when you need the same metrics across multiple standards.

## Commands

Single-document evaluation:

```bash
PYTHONPATH=backend ./.venv/bin/python \
  docs/skills/mineru-standard-bundle/scripts/run_mineru_standard_bundle.py evaluate \
  --name GB50150-2016 \
  --pdf /abs/path/50150.pdf \
  --md /abs/path/GB_50150.md \
  --json /abs/path/GB\ 50150.json \
  --output-dir tmp/mineru_standard_bundle/GB50150-2016
```

Deterministic cleanup:

```bash
PYTHONPATH=backend ./.venv/bin/python \
  docs/skills/mineru-standard-bundle/scripts/run_mineru_standard_bundle.py clean \
  --name GB50150-2016 \
  --pdf /abs/path/50150.pdf \
  --md /abs/path/GB_50150.md \
  --json /abs/path/GB\ 50150.json \
  --output-dir tmp/mineru_standard_bundle/GB50150-2016
```

Cross-standard comparison:

```bash
PYTHONPATH=backend ./.venv/bin/python \
  docs/skills/mineru-standard-bundle/scripts/run_mineru_standard_bundle.py compare \
  --manifest /abs/path/compare-manifest.json \
  --output-dir tmp/mineru_standard_bundle/compare
```

## Output Files

- `raw-payload.json`
- `system-bundle.json`
- `summary.json`
- `cleaned-system-bundle.json`
- `cleaned-summary.json`
- `compare-summary.json`
- `compare-report.md`

## Review Focus

After running the workflow, review:

- `page_coverage_ratio`
- `section_page_coverage_ratio`
- `toc_noise_count`
- `suspicious_section_code_count`
