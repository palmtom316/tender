# MinerU Standard Bundle Skill Design

## Background

The `tender` repo now has enough deterministic building blocks to normalize modern MinerU outputs without invoking another model:

- `normalize_mineru_payload()` converts MinerU `2.7.x` `hybrid/vlm` `pdf_info -> para_blocks` payloads into canonical `raw_payload`.
- `_mineru_to_sections()` can derive section rows from canonical page markdown.
- `build_document_asset()` and `serialize_document_asset()` can assemble a document bundle close to `/parse-assets`.

Recent work on `GB50147-2010` and `GB50150-2016` also exposed a repeated workflow that is currently too manual:

1. Read local `pdf + md + json`.
2. Normalize into canonical assets.
3. Evaluate OCR/structure quality.
4. Clean deterministic noise such as TOC sections, cover-page false headings, suspicious year-like section codes, and recoverable page anchors.
5. Compare multiple standards with the same metrics.

This workflow should become a repo-local draft skill so future sessions can trigger it directly and reuse one command surface instead of rebuilding ad hoc scripts.

## Goal

Create a repo-local draft skill for the `tender` repository that:

- is specialized to MinerU `2.7.x` `hybrid/vlm` outputs only;
- converts standard document `pdf + md + json` inputs into canonical `raw_payload` and parse-asset-like bundles;
- runs deterministic quality evaluation on a single standard;
- runs deterministic cross-standard comparison on multiple standards;
- performs a first-pass deterministic cleanup that makes the bundle closer to formal ingestion quality;
- provides a single executable entrypoint so the workflow is repeatable.

## Non-Goals

- No support for MinerU legacy `pipeline` backend or historical mixed payload shapes.
- No direct database write, SQL import, API upload, or production ingestion side effects.
- No model-based repair or classification.
- No attempt to solve final clause extraction quality end to end.
- No generic packaging for all repositories in the first version.

## Scope Decision

The skill will combine:

- bundle generation;
- single-document evaluation;
- deterministic cleaning;
- multi-document comparison.

It will not include:

- DB persistence;
- migration helpers;
- import jobs;
- generic OCR backend abstraction.

This keeps the skill narrow enough to stay reliable while still covering the repeated analysis loop the repo currently needs.

## Recommended Approach

Adopt a single skill plus a single executable script with subcommands:

- `evaluate`
- `clean`
- `compare`

This is preferred over a documentation-only skill because the current workflow is repetitive and easy to drift. It is preferred over a multi-script toolbox because the first version benefits more from one stable interface than from early decomposition.

## Skill Placement

The first version will be a repo-local draft skill:

- `docs/skills/mineru-standard-bundle/SKILL.md`
- `docs/skills/mineru-standard-bundle/scripts/run_mineru_standard_bundle.py`

Optional references may be added only if the main skill document starts getting too large:

- `docs/skills/mineru-standard-bundle/references/schema.md`

The repo-local location is intentional. It allows iteration alongside the codebase and sample documents before promoting the skill into a global `~/.codex/skills` installation.

## Triggering Conditions

The skill description should be written to trigger when a user wants any of the following inside this repository:

- convert MinerU standard outputs into a system-usable structured bundle;
- evaluate parse quality of a standard from local `pdf + md + json` files;
- compare parse quality across standards using the same metrics;
- clean deterministic noise from a MinerU standard bundle before downstream ingestion.

The description must clearly state that the skill is for:

- this `tender` repo;
- standard-document workflows;
- MinerU `2.7.x` `hybrid/vlm` outputs.

The description must also explicitly say it should not be used for:

- legacy pipeline payloads;
- arbitrary OCR formats;
- tender file ingestion;
- DB import tasks.

## Input Contract

The script and skill will assume local files, not remote URLs:

- `--pdf <path>`
- `--md <path>`
- `--json <path>`

For comparison mode, the script should accept repeated sample groups via either:

- repeated flags per sample; or
- a manifest JSON file.

The recommended first version is a manifest file for `compare`, because it is simpler to validate and easier to reuse in tests.

Example conceptual compare manifest:

```json
[
  {
    "name": "GB50147-2010",
    "pdf": "/abs/path/GB 50147-2010.pdf",
    "md": "/abs/path/MinerU_markdown_GB50147_2010.md",
    "json": "/abs/path/MinerU_GB50147_2010.json"
  },
  {
    "name": "GB50150-2016",
    "pdf": "/abs/path/50150.pdf",
    "md": "/abs/path/GB_50150.md",
    "json": "/abs/path/GB 50150.json"
  }
]
```

## Output Contract

For a single sample, the workflow will produce three base artifacts:

1. `raw-payload.json`
2. `system-bundle.json`
3. `summary.json`

After cleaning, it will also produce:

4. `cleaned-system-bundle.json`
5. `cleaned-summary.json`

For comparisons, it will produce:

6. `compare-summary.json`
7. `compare-report.md`

The canonical output directory should be user-configurable, with a stable default under repo-local temp output, for example:

- `tmp/mineru_standard_bundle/<sample-name>/`

## Bundle Shapes

### Raw Payload

This is the canonical MinerU payload used by current `document.raw_payload` consumers:

- `parser_version`
- `pages`
- `tables`
- `full_markdown`

### System Bundle

This is the parse-asset-like bundle intended for local review and future import adaptation:

- `source_files`
- `document`
- `sections`
- `tables`

`document.raw_payload.pages` should include the enriched page objects produced by `serialize_document_asset()`:

- `page_number`
- `markdown`
- `raw_page`
- `source_ref`

`document.raw_payload.tables` should include:

- `source_ref`
- `page_start`
- `page_end`
- `table_title`
- `table_html`
- `raw_json`

## Deterministic Cleaning Rules

The first version should only implement rules that are deterministic, auditable, and directly motivated by observed `GB50150-2016` noise.

### Rule Group 1: TOC Noise Removal

Drop or mark sections as noise when they are clearly TOC-derived. Signals include:

- the source page is a TOC page such as `目次` or `Contents`;
- section title ends with a page reference like `(68)`;
- section body is empty and the title matches a TOC entry pattern;
- many sibling headings are emitted from the same TOC page with empty text.

### Rule Group 2: Cover and Front-Matter False Headings

Drop or mark false headings caused by cover/front matter when:

- they are title-only fragments on the cover or publication pages;
- they carry no useful body text;
- they duplicate nearby cover titles;
- they represent publication metadata rather than normative document structure.

### Rule Group 3: Suspicious Year-like Section Codes

Drop or rewrite sections where `section_code` is a publication year-like integer from front matter, such as `2010` or `2016`, when the surrounding page indicates publisher metadata rather than chapter numbering.

This rule must not remove genuine normative numbering. Therefore it should be constrained by front-matter evidence and not rely on the numeric pattern alone.

### Rule Group 4: Recoverable Page Anchor Backfill

When a section has `page_start = null` but can be matched deterministically to a page using its heading or body snippet, backfill:

- `page_start`
- `page_end`
- `raw_json`

Matching must remain deterministic and conservative. If there is no confident unique match, leave the anchor unset.

## Metrics

The skill will standardize a small set of metrics so all comparisons use the same vocabulary.

Required evaluation metrics:

- `pdf_pages`
- `canonical_pages`
- `page_coverage_ratio`
- `tables`
- `sections`
- `sections_with_page`
- `section_page_coverage_ratio`
- `empty_text_sections`
- `toc_noise_count`
- `front_matter_noise_count`
- `suspicious_section_code_count`
- `backfilled_anchor_count`
- `clause_like_lines`
- `clause_like_unique`

Comparison reports should present both raw and cleaned metrics where applicable.

## Script Commands

### `evaluate`

Purpose:

- normalize one sample;
- build parse-asset-like outputs;
- compute quality metrics;
- emit base artifacts.

### `clean`

Purpose:

- run deterministic cleanup on one evaluated sample;
- emit cleaned bundle and cleaned summary;
- report what was removed and what was backfilled.

### `compare`

Purpose:

- evaluate multiple samples with the same metrics;
- optionally clean them first;
- emit comparison JSON and Markdown.

The script may internally share one orchestration path, but the command surface should stay explicit because users think in these three tasks.

## Implementation Plan for the Script

The script should be organized as a thin CLI over repo functions plus small deterministic helpers.

Recommended internal structure:

1. CLI argument parsing
2. input loading and validation
3. canonical normalization
4. bundle assembly
5. metric computation
6. cleaning pass
7. comparison aggregation
8. file output

The script should import and reuse:

- `tender_backend.services.parse_service.mineru_normalizer.normalize_mineru_payload`
- `tender_backend.services.norm_service.norm_processor._mineru_to_sections`
- `tender_backend.services.norm_service.document_assets.build_document_asset`
- `tender_backend.services.norm_service.document_assets.serialize_document_asset`

The script should not duplicate this repo logic unless a helper is clearly CLI-specific.

## Testing Strategy

This work should follow test-first development.

### Unit Tests

Add focused tests for deterministic cleanup rules using a real-shape but minimal fixture set.

Target behaviors:

- TOC sections are removed from cleaned output;
- suspicious `2010/2016` front-matter section codes are removed or neutralized;
- recoverable page anchors are backfilled;
- legitimate clause sections are preserved;
- compare metrics remain stable and deterministic.

### Script Smoke Tests

Add CLI-level tests that run the script against small fixtures and verify:

- expected files are written;
- output JSON shape is valid;
- cleaned metrics improve in the intended direction.

### Real-Sample Verification

Use `GB50147-2010` and `GB50150-2016` as real-sample checks after implementation.

The first acceptance target for `GB50150-2016` is not “formal ingestion quality.” It is narrower:

- fewer TOC-derived empty sections;
- fewer suspicious front-matter false headings;
- improved section page anchor coverage;
- no regression in canonical page/table recovery.

## Acceptance Criteria

The first draft is acceptable when all of the following are true:

- the repo contains the draft skill under `docs/skills/mineru-standard-bundle/`;
- the script supports `evaluate`, `clean`, and `compare`;
- the script only accepts MinerU `2.7.x` `hybrid/vlm` shape and rejects unsupported backends;
- unit and smoke tests pass;
- real-sample reruns for `GB50147-2010` and `GB50150-2016` complete successfully;
- `GB50150-2016` cleaned output shows lower TOC noise and suspicious section-code counts than the raw output;
- `GB50150-2016` cleaned output shows improved or unchanged page anchor coverage;
- no DB writes or model calls are introduced.

## Risks

### Over-Cleaning

Aggressive TOC/front-matter cleanup could remove real headings. This is why the first version should prefer conservative rules and measurable deltas.

### Tight Coupling to Current Helpers

The skill intentionally depends on current repo helpers such as `_mineru_to_sections()`. This is acceptable for a repo-local draft skill, but should be revisited before global promotion.

### False Confidence From Bundle Quality

Cleaner bundles do not mean final clause extraction is solved. The skill should explicitly communicate that it improves upstream assets, not the full downstream parse pipeline.

## Migration Path

If the draft skill proves stable, the next phase can:

1. promote the skill into `~/.codex/skills/`;
2. split heavy references into `references/`;
3. extract reusable deterministic cleanup helpers into backend modules;
4. add optional import-pack generation in a separate follow-up skill or subcommand.
