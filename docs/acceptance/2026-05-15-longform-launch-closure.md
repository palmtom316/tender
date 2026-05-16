# 2026-05-15 Longform Launch Closure Acceptance

## Scope

This report verifies the P0 closure work for long technical bid chapter generation.

## Automated Checks

- Backend longform quality tests: pass after running `cd backend && ../.venv/bin/python -m pytest tests/unit/test_longform_quality.py tests/unit/test_longform_section_generation.py tests/unit/test_page_counter.py tests/unit/test_export_gates.py tests/unit/test_technical_bid_writer.py tests/unit/test_docx_exporter.py -q`.
- Frontend export gate tests: pass after running `npm --prefix frontend run test -- src/modules/export/ExportGateContent.test.tsx`.
- Frontend build: pass after running `npm --prefix frontend run build`.

## Real Sample Evidence

The first real chapter 8 sample must record:

- Target pages: 100.
- Minimum accepted pages: 90.
- Estimated pages from `chapter_draft.estimated_pages`.
- Actual pages from `export_record.metadata_json.render_evidence.page_count`.
- Coverage report from `chapter_draft.coverage_report_json`.
- Chart closure report from `chapter_draft.chart_closure_report_json`.
- Export gate response from `GET /projects/{project_id}/export-gates`.

## Launch Decision Rule

Do not promise production-grade 100-page chapter generation until the real sample evidence shows:

1. `page_count_passed = true` with actual counted pages, not only estimate.
2. `coverage_passed = true` with zero P0 gaps.
3. `chart_closure_passed = true` with zero residual `{{chart:*}}` placeholders.
4. Final export succeeds without bypassing gates.
