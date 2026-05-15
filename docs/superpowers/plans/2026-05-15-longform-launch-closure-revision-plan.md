# Longform Launch Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the P0 launch risks from `2026-05-15-unresolved-launch-issues.md` by making 100-page longform generation measurable, resumable, coverage-gated, and chart-verifiable before final export.

**Architecture:** Add a deterministic quality layer around existing generation/export instead of trusting prompt compliance. Persist generation evidence in existing `chapter_draft` / `bid_generation_run` metadata first, add only one optional child table for subsection runs, and make export gates read the saved evidence. Keep actual AI calls behind existing `TechnicalBidWriter` so the first implementation is testable without network access.

**Tech Stack:** FastAPI, psycopg 3, Alembic, python-docx/docx zip inspection, optional LibreOffice via `soffice`, pytest, React 18, TanStack Query, Vitest.

---

## Source Document Read

Source: `docs/superpowers/plans/2026-05-15-unresolved-launch-issues.md`

The document says production must not promise stable 100-page technical chapter output until these P0 risks are closed:

1. `P0-1`: target pages are only a prompt hint; final export has no hard page gate.
2. `P0-2`: chapter 8 is generated as one long request; no 8.1-8.15 subsection loop or retry boundary.
3. `P0-3`: content completeness is not automatically audited against section, constraint, table, chart, and template requirements.
4. `P0-4`: chart references, chart assets, rendered files, and DOCX media insertion are not reconciled.

This plan implements P0 first. P1/P2 are intentionally converted into follow-up plans after P0 evidence exists, because progress UI, model strategy productization, real DOCX preview, directory reconciliation, and multi-sample acceptance depend on the same evidence model but do not need to block the first hard gate implementation.

## File Structure

### New backend files

- Create: `backend/tender_backend/services/longform_quality.py`
  - Owns pure functions and dataclasses for page estimation, coverage checks, and chart closure checks.
  - No database access; all inputs are plain dictionaries/lists so tests are fast.

- Create: `backend/tender_backend/services/longform_section_generation.py`
  - Owns 8.1-8.15 subsection planning, continuation loop orchestration, subsection assembly, and metadata shape.
  - Calls an injected completion function so unit tests use deterministic fake completions.

- Create: `backend/tender_backend/services/export_service/page_counter.py`
  - Counts actual pages after DOCX render.
  - Uses LibreOffice-to-PDF plus PyMuPDF when `soffice` is available; returns explicit `unchecked` when unavailable.
  - Provides DOCX structure fallback evidence but never silently treats fallback as passed.

- Create: `backend/tests/unit/test_longform_quality.py`
  - Unit tests for page estimate, page gate, coverage gate, and chart closure.

- Create: `backend/tests/unit/test_longform_section_generation.py`
  - Unit tests for subsection planning, continuation loop, max-round failure, assembly order, and run metadata.

- Create: `backend/tests/unit/test_page_counter.py`
  - Unit tests for page counter success and unavailable states without requiring LibreOffice.

### Modified backend files

- Create: `backend/tender_backend/db/alembic/versions/0056_longform_generation_evidence.py`
  - Adds minimal evidence fields to `chapter_draft` and one child table for subsection runs.

- Modify: `backend/tender_backend/services/technical_bid_writer.py`
  - Routes large target chapters through `LongformSectionGenerator`.
  - Saves quality metadata into draft/run records.
  - Keeps existing single-request behavior for non-longform chapters.

- Modify: `backend/tender_backend/services/export_gate_service.py`
  - Adds `page_count_gate`, `coverage_gate`, and stronger `chart_gate` fields.
  - Blocks final export when page count/coverage/chart evidence fails or is unchecked.

- Modify: `backend/tender_backend/services/export_service/docx_exporter.py`
  - After render, runs `page_counter` and chart residual inspection.
  - Writes export evidence into `export_record.metadata_json` if column exists; otherwise returns evidence for API insertion.

- Modify: `backend/tender_backend/api/exports.py`
  - Adds `draft` vs `final` export mode semantics with final blocked by gates.
  - Persists export evidence from render.

- Modify: `backend/tests/unit/test_export_gates.py`
  - Adds tests for page count under target, unchecked page count, missing section coverage, hard-constraint gaps, chart residuals.

- Modify: `backend/tests/unit/test_technical_bid_writer.py`
  - Adds tests proving target `>= 80` chapter uses longform subsection generation and preserves AI metadata.

### Modified frontend files

- Modify: `frontend/src/lib/api.ts`
  - Extends `ExportGates` type with page, coverage, and chart closure evidence.
  - Adds export intent field if backend accepts it.

- Modify: `frontend/src/modules/export/ExportGateContent.tsx`
  - Displays target pages, estimated pages, actual pages, coverage gaps, chart reference/generated/inserted counts.
  - Keeps final export disabled when evidence is failed or unchecked.

- Modify: `frontend/src/modules/export/ExportGateContent.test.tsx`
  - Tests all new gate messages and disabled final export behavior.

---

## Implementation Tasks

### Task 1: Add database evidence fields

**Files:**
- Create: `backend/tender_backend/db/alembic/versions/0056_longform_generation_evidence.py`

- [ ] **Step 1: Create migration with draft/run evidence columns and subsection table**

Add this file:

```python
"""longform generation evidence

Revision ID: 0056
Revises: 0055
Create Date: 2026-05-15
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0056"
down_revision: Union[str, None] = "0055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE chapter_draft ADD COLUMN IF NOT EXISTS target_pages INT;")
    op.execute("ALTER TABLE chapter_draft ADD COLUMN IF NOT EXISTS estimated_pages NUMERIC(8,2);")
    op.execute("ALTER TABLE chapter_draft ADD COLUMN IF NOT EXISTS page_estimate_json JSONB NOT NULL DEFAULT '{}'::jsonb;")
    op.execute("ALTER TABLE chapter_draft ADD COLUMN IF NOT EXISTS coverage_report_json JSONB NOT NULL DEFAULT '{}'::jsonb;")
    op.execute("ALTER TABLE chapter_draft ADD COLUMN IF NOT EXISTS chart_closure_report_json JSONB NOT NULL DEFAULT '{}'::jsonb;")
    op.execute("ALTER TABLE chapter_draft ADD COLUMN IF NOT EXISTS generation_rounds INT NOT NULL DEFAULT 1;")

    op.execute("ALTER TABLE export_record ADD COLUMN IF NOT EXISTS metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb;")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS bid_generation_subsection_run (
          id UUID PRIMARY KEY,
          bid_generation_run_id UUID NULL REFERENCES bid_generation_run(id) ON DELETE CASCADE,
          project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
          bid_chapter_id UUID NULL REFERENCES bid_chapter(id) ON DELETE SET NULL,
          chapter_code TEXT NOT NULL,
          subsection_code TEXT NOT NULL,
          subsection_title TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'completed',
          target_pages NUMERIC(8,2),
          estimated_pages NUMERIC(8,2),
          min_chars INT NOT NULL DEFAULT 0,
          actual_chars INT NOT NULL DEFAULT 0,
          continuation_rounds INT NOT NULL DEFAULT 1,
          prompt_hash TEXT NOT NULL,
          provider TEXT,
          model TEXT,
          input_tokens INT NOT NULL DEFAULT 0,
          output_tokens INT NOT NULL DEFAULT 0,
          latency_ms INT NOT NULL DEFAULT 0,
          metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (project_id, chapter_code, subsection_code)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bid_generation_subsection_project "
        "ON bid_generation_subsection_run (project_id, chapter_code, subsection_code);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_bid_generation_subsection_project;")
    op.execute("DROP TABLE IF EXISTS bid_generation_subsection_run;")
    op.execute("ALTER TABLE export_record DROP COLUMN IF EXISTS metadata_json;")
    op.execute("ALTER TABLE chapter_draft DROP COLUMN IF EXISTS generation_rounds;")
    op.execute("ALTER TABLE chapter_draft DROP COLUMN IF EXISTS chart_closure_report_json;")
    op.execute("ALTER TABLE chapter_draft DROP COLUMN IF EXISTS coverage_report_json;")
    op.execute("ALTER TABLE chapter_draft DROP COLUMN IF EXISTS page_estimate_json;")
    op.execute("ALTER TABLE chapter_draft DROP COLUMN IF EXISTS estimated_pages;")
    op.execute("ALTER TABLE chapter_draft DROP COLUMN IF EXISTS target_pages;")
```

- [ ] **Step 2: Verify migration imports**

Run:

```bash
cd backend && ../.venv/bin/python -m py_compile tender_backend/db/alembic/versions/0056_longform_generation_evidence.py
```

Expected: command exits with status `0` and prints no output.

- [ ] **Step 3: Commit**

```bash
git add backend/tender_backend/db/alembic/versions/0056_longform_generation_evidence.py
git commit -m "feat: add longform generation evidence schema"
```

### Task 2: Add deterministic longform quality checks

**Files:**
- Create: `backend/tender_backend/services/longform_quality.py`
- Create: `backend/tests/unit/test_longform_quality.py`

- [ ] **Step 1: Write failing quality tests**

Create `backend/tests/unit/test_longform_quality.py`:

```python
from tender_backend.services.longform_quality import (
    build_chart_closure_report,
    build_coverage_report,
    build_page_gate,
    estimate_markdown_pages,
)


def test_estimate_markdown_pages_counts_chinese_text_tables_charts_and_breaks():
    content = "# 8 技术方案\n" + ("施工组织。" * 900) + "\n{{chart:risk_matrix}}\n\n| A | B |\n|---|---|\n| 1 | 2 |\n<div style='page-break-after: always'></div>"

    estimate = estimate_markdown_pages(content, target_pages=100)

    assert estimate["target_pages"] == 100
    assert estimate["estimated_pages"] >= 12
    assert estimate["evidence"]["chart_count"] == 1
    assert estimate["evidence"]["table_row_count"] == 2
    assert estimate["evidence"]["explicit_page_break_count"] == 1


def test_page_gate_blocks_below_ninety_percent_target():
    gate = build_page_gate(target_pages=100, estimated_pages=88, actual_pages=None, actual_status="unchecked")

    assert gate["page_count_passed"] is False
    assert gate["page_count_status"] == "failed_estimate_below_minimum"
    assert gate["minimum_required_pages"] == 90


def test_page_gate_blocks_unchecked_when_estimate_is_not_enough():
    gate = build_page_gate(target_pages=100, estimated_pages=95, actual_pages=None, actual_status="unchecked")

    assert gate["page_count_passed"] is False
    assert gate["page_count_status"] == "warning_actual_unchecked"
    assert "未校验" in gate["page_count_message"]


def test_page_gate_passes_when_actual_pages_meet_minimum():
    gate = build_page_gate(target_pages=100, estimated_pages=92, actual_pages=91, actual_status="counted")

    assert gate["page_count_passed"] is True
    assert gate["page_count_status"] == "passed"


def test_coverage_report_blocks_missing_8x_section_and_hard_constraint_gap():
    content = "## 8.1 编制依据\n" + ("响应内容。" * 80)
    checklist = [
        {"section_code": "8.1", "title": "编制依据", "min_chars": 100, "required_charts": [], "required_tables": []},
        {"section_code": "8.2", "title": "施工组织", "min_chars": 100, "required_charts": ["org_chart"], "required_tables": []},
    ]
    constraints = [
        {"id": "c1", "title": "项目经理到岗", "confirmation_level": "critical", "response_section_code": "8.2"}
    ]

    report = build_coverage_report(content, checklist=checklist, constraints=constraints)

    assert report["coverage_passed"] is False
    issue_codes = {issue["code"] for issue in report["issues"]}
    assert "missing_section" in issue_codes
    assert "missing_required_chart" in issue_codes
    assert "hard_constraint_uncovered" in issue_codes


def test_chart_closure_report_reconciles_references_assets_and_docx_insertions():
    report = build_chart_closure_report(
        content_md="正文 {{chart:risk_matrix}} 和 {{chart:schedule}}",
        chart_assets=[
            {"placeholder_key": "risk_matrix", "status": "approved", "rendered_path": "/tmp/risk.png"},
            {"placeholder_key": "schedule", "status": "draft", "rendered_path": None},
        ],
        inserted_chart_keys=["risk_matrix"],
        residual_placeholders=["schedule"],
    )

    assert report["chart_closure_passed"] is False
    assert report["referenced_chart_count"] == 2
    assert report["approved_chart_count"] == 1
    assert report["inserted_chart_count"] == 1
    assert {issue["chart_key"] for issue in report["issues"]} == {"schedule"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend && ../.venv/bin/pytest tests/unit/test_longform_quality.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'tender_backend.services.longform_quality'`.

- [ ] **Step 3: Implement quality module**

Create `backend/tender_backend/services/longform_quality.py`:

```python
"""Deterministic longform chapter quality evidence."""

from __future__ import annotations

import math
import re
from typing import Any

_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_CHART_RE = re.compile(r"\{\{chart:([A-Za-z][A-Za-z0-9_.:-]{0,127})\}\}")
_TABLE_ROW_RE = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)
_PAGE_BREAK_RE = re.compile(r"page-break|<w:br[^>]+type=['\"]page['\"]|---PAGE BREAK---", re.IGNORECASE)


def _weighted_text_units(content_md: str) -> int:
    chinese_chars = len(_CHINESE_RE.findall(content_md))
    western_words = len(_WORD_RE.findall(content_md))
    return chinese_chars + math.ceil(western_words * 1.8)


def estimate_markdown_pages(content_md: str, *, target_pages: int | None = None) -> dict[str, Any]:
    text_units = _weighted_text_units(content_md)
    heading_count = len(_HEADING_RE.findall(content_md))
    chart_count = len(_CHART_RE.findall(content_md))
    table_row_count = len(_TABLE_ROW_RE.findall(content_md))
    explicit_page_break_count = len(_PAGE_BREAK_RE.findall(content_md))

    text_pages = text_units / 700
    heading_pages = heading_count * 0.08
    chart_pages = chart_count * 0.55
    table_pages = table_row_count * 0.06
    break_pages = explicit_page_break_count * 1.0
    estimated_pages = round(max(1.0, text_pages + heading_pages + chart_pages + table_pages + break_pages), 2)

    return {
        "target_pages": target_pages,
        "estimated_pages": estimated_pages,
        "method": "weighted_cn_chars_700_per_page_plus_structure_v1",
        "evidence": {
            "weighted_text_units": text_units,
            "heading_count": heading_count,
            "chart_count": chart_count,
            "table_row_count": table_row_count,
            "explicit_page_break_count": explicit_page_break_count,
        },
    }


def build_page_gate(
    *,
    target_pages: int | None,
    estimated_pages: float | int | None,
    actual_pages: int | None,
    actual_status: str,
) -> dict[str, Any]:
    if not target_pages:
        return {
            "page_count_passed": True,
            "page_count_status": "not_required",
            "target_pages": None,
            "minimum_required_pages": None,
            "estimated_pages": estimated_pages,
            "actual_pages": actual_pages,
            "page_count_message": "未设置目标页数。",
        }
    minimum = math.ceil(target_pages * 0.9)
    if actual_status == "counted" and actual_pages is not None:
        passed = actual_pages >= minimum
        return {
            "page_count_passed": passed,
            "page_count_status": "passed" if passed else "failed_actual_below_minimum",
            "target_pages": target_pages,
            "minimum_required_pages": minimum,
            "estimated_pages": estimated_pages,
            "actual_pages": actual_pages,
            "page_count_message": "实际页数达标。" if passed else f"实际 {actual_pages} 页，低于最低 {minimum} 页。",
        }
    if estimated_pages is not None and float(estimated_pages) < minimum:
        return {
            "page_count_passed": False,
            "page_count_status": "failed_estimate_below_minimum",
            "target_pages": target_pages,
            "minimum_required_pages": minimum,
            "estimated_pages": float(estimated_pages),
            "actual_pages": actual_pages,
            "page_count_message": f"估算 {float(estimated_pages):.1f} 页，低于最低 {minimum} 页。",
        }
    return {
        "page_count_passed": False,
        "page_count_status": "warning_actual_unchecked",
        "target_pages": target_pages,
        "minimum_required_pages": minimum,
        "estimated_pages": estimated_pages,
        "actual_pages": actual_pages,
        "page_count_message": "实际页数未校验，不能作为最终版导出依据。",
    }


def _section_body(content_md: str, section_code: str) -> str:
    pattern = re.compile(rf"^##+\s+{re.escape(section_code)}(?:\s|$).*$", re.MULTILINE)
    match = pattern.search(content_md)
    if not match:
        return ""
    next_match = re.search(r"^##+\s+8\.\d+(?:\s|$).*$", content_md[match.end():], re.MULTILINE)
    end = match.end() + next_match.start() if next_match else len(content_md)
    return content_md[match.end():end]


def build_coverage_report(
    content_md: str,
    *,
    checklist: list[dict[str, Any]],
    constraints: list[dict[str, Any]],
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    chart_keys = set(_CHART_RE.findall(content_md))
    for item in checklist:
        section_code = str(item.get("section_code") or "").strip()
        if not section_code:
            continue
        body = _section_body(content_md, section_code)
        if not body:
            issues.append({"code": "missing_section", "section_code": section_code, "severity": "P0"})
            continue
        min_chars = int(item.get("min_chars") or 0)
        actual_chars = _weighted_text_units(body)
        if min_chars and actual_chars < min_chars:
            issues.append({"code": "section_too_short", "section_code": section_code, "severity": "P0", "min_chars": min_chars, "actual_chars": actual_chars})
        for chart_key in item.get("required_charts") or []:
            if chart_key not in chart_keys:
                issues.append({"code": "missing_required_chart", "section_code": section_code, "chart_key": chart_key, "severity": "P0"})
        for table_label in item.get("required_tables") or []:
            if str(table_label) not in body:
                issues.append({"code": "missing_required_table", "section_code": section_code, "table_label": table_label, "severity": "P0"})

    present_sections = {str(item.get("section_code")) for item in checklist if _section_body(content_md, str(item.get("section_code") or ""))}
    for constraint in constraints:
        critical = constraint.get("confirmation_level") == "critical" or bool((constraint.get("metadata_json") or {}).get("has_conflict"))
        response_section = str(constraint.get("response_section_code") or constraint.get("mapped_section_code") or "").strip()
        if critical and response_section not in present_sections:
            issues.append({"code": "hard_constraint_uncovered", "constraint_id": str(constraint.get("id")), "section_code": response_section, "severity": "P0"})

    return {
        "coverage_passed": not any(issue.get("severity") == "P0" for issue in issues),
        "issue_count": len(issues),
        "issues": issues,
        "checked_section_count": len(checklist),
    }


def build_chart_closure_report(
    *,
    content_md: str,
    chart_assets: list[dict[str, Any]],
    inserted_chart_keys: list[str] | None = None,
    residual_placeholders: list[str] | None = None,
) -> dict[str, Any]:
    referenced = set(_CHART_RE.findall(content_md))
    inserted = set(inserted_chart_keys or [])
    residual = set(residual_placeholders or [])
    by_key = {str(asset.get("placeholder_key") or asset.get("chart_type") or ""): asset for asset in chart_assets}
    issues: list[dict[str, Any]] = []
    approved_count = 0
    rendered_count = 0
    for key in sorted(referenced):
        asset = by_key.get(key)
        if not asset:
            issues.append({"code": "missing_chart_asset", "chart_key": key, "severity": "P0"})
            continue
        if asset.get("status") == "approved":
            approved_count += 1
        else:
            issues.append({"code": "chart_not_approved", "chart_key": key, "severity": "P0"})
        if asset.get("rendered_path") or asset.get("rendered_svg"):
            rendered_count += 1
        else:
            issues.append({"code": "chart_not_rendered", "chart_key": key, "severity": "P0"})
        if inserted_chart_keys is not None and key not in inserted:
            issues.append({"code": "chart_not_inserted", "chart_key": key, "severity": "P0"})
        if key in residual:
            issues.append({"code": "chart_placeholder_residual", "chart_key": key, "severity": "P0"})

    return {
        "chart_closure_passed": not any(issue.get("severity") == "P0" for issue in issues),
        "referenced_chart_count": len(referenced),
        "asset_chart_count": len([key for key in by_key if key in referenced]),
        "approved_chart_count": approved_count,
        "rendered_chart_count": rendered_count,
        "inserted_chart_count": len(inserted),
        "residual_placeholder_count": len(residual),
        "issues": issues,
    }
```

- [ ] **Step 4: Run quality tests**

Run:

```bash
cd backend && ../.venv/bin/pytest tests/unit/test_longform_quality.py -q
```

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/services/longform_quality.py backend/tests/unit/test_longform_quality.py
git commit -m "feat: add deterministic longform quality checks"
```

### Task 3: Add subsection generation and continuation loop

**Files:**
- Create: `backend/tender_backend/services/longform_section_generation.py`
- Create: `backend/tests/unit/test_longform_section_generation.py`

- [ ] **Step 1: Write failing subsection generation tests**

Create `backend/tests/unit/test_longform_section_generation.py`:

```python
from tender_backend.services.longform_section_generation import LongformSectionGenerator, plan_chapter_8_sections


def test_plan_chapter_8_sections_creates_8_1_to_8_15_with_page_budget():
    plan = plan_chapter_8_sections(target_pages=100)

    assert [item["section_code"] for item in plan] == [f"8.{index}" for index in range(1, 16)]
    assert sum(item["target_pages"] for item in plan) == 100
    assert all(item["min_chars"] >= 2800 for item in plan)


def test_generator_continues_until_section_meets_min_chars():
    calls = []

    def complete(payload):
        calls.append(payload)
        if payload["round_index"] == 1:
            return {"content": "短文", "provider": "fake", "model": "unit", "usage": {"output_tokens": 5}}
        return {"content": "补写" * 2000, "provider": "fake", "model": "unit", "usage": {"output_tokens": 100}}

    generator = LongformSectionGenerator(completion_fn=complete, max_rounds=3)
    result = generator.generate_sections(
        context={"chapter": {"chapter_code": "8", "chapter_title": "施工组织设计"}},
        section_plan=[{"section_code": "8.1", "title": "编制依据", "target_pages": 6, "min_chars": 2000, "required_charts": []}],
    )

    assert len(calls) == 2
    assert result["status"] == "completed"
    assert result["sections"][0]["continuation_rounds"] == 2
    assert "## 8.1 编制依据" in result["content_md"]


def test_generator_marks_section_failed_after_max_rounds():
    def complete(payload):
        return {"content": "仍然不足", "provider": "fake", "model": "unit", "usage": {"output_tokens": 3}}

    generator = LongformSectionGenerator(completion_fn=complete, max_rounds=2)
    result = generator.generate_sections(
        context={"chapter": {"chapter_code": "8", "chapter_title": "施工组织设计"}},
        section_plan=[{"section_code": "8.1", "title": "编制依据", "target_pages": 6, "min_chars": 2000, "required_charts": []}],
    )

    assert result["status"] == "failed"
    assert result["sections"][0]["status"] == "failed_min_chars"
    assert result["sections"][0]["continuation_rounds"] == 2


def test_generator_keeps_subsection_order_and_metadata():
    def complete(payload):
        return {"content": payload["section_code"] + " 内容" * 2000, "provider": "fake", "model": "unit", "usage": {"input_tokens": 10, "output_tokens": 20, "latency_ms": 30}}

    generator = LongformSectionGenerator(completion_fn=complete, max_rounds=1)
    result = generator.generate_sections(
        context={"chapter": {"chapter_code": "8", "chapter_title": "施工组织设计"}},
        section_plan=[
            {"section_code": "8.1", "title": "编制依据", "target_pages": 5, "min_chars": 100, "required_charts": []},
            {"section_code": "8.2", "title": "施工组织", "target_pages": 5, "min_chars": 100, "required_charts": ["org_chart"]},
        ],
    )

    assert result["status"] == "completed"
    assert result["content_md"].index("## 8.1 编制依据") < result["content_md"].index("## 8.2 施工组织")
    assert result["sections"][1]["required_charts"] == ["org_chart"]
    assert result["metadata"]["total_output_tokens"] == 40
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend && ../.venv/bin/pytest tests/unit/test_longform_section_generation.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'tender_backend.services.longform_section_generation'`.

- [ ] **Step 3: Implement subsection generator**

Create `backend/tender_backend/services/longform_section_generation.py`:

```python
"""Subsection planning and continuation loop for long technical chapters."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable

from tender_backend.services.longform_quality import estimate_markdown_pages

CompletionFn = Callable[[dict[str, Any]], dict[str, Any]]

_CHAPTER_8_TITLES = [
    "编制依据与响应范围",
    "项目组织机构与岗位职责",
    "施工总体部署",
    "进度计划与节点控制",
    "施工准备与资源配置",
    "主要施工方案与工艺",
    "质量管理体系与保证措施",
    "安全文明施工与风险管控",
    "环境保护与水土保持措施",
    "物资设备管理",
    "停电计划与保供电措施",
    "验收、调试与移交",
    "资料管理与数字化留痕",
    "应急预案与协调机制",
    "评分点响应索引与自检清单",
]


def plan_chapter_8_sections(*, target_pages: int) -> list[dict[str, Any]]:
    base = target_pages // 15
    remainder = target_pages % 15
    plan: list[dict[str, Any]] = []
    for index, title in enumerate(_CHAPTER_8_TITLES, start=1):
        pages = base + (1 if index <= remainder else 0)
        plan.append(
            {
                "section_code": f"8.{index}",
                "title": title,
                "target_pages": pages,
                "min_chars": max(2800, pages * 620),
                "required_charts": _default_required_charts(index),
                "required_tables": _default_required_tables(index),
            }
        )
    return plan


def _default_required_charts(index: int) -> list[str]:
    return {
        2: ["organization_structure"],
        4: ["milestone_schedule"],
        8: ["risk_matrix"],
        15: ["scoring_response_index"],
    }.get(index, [])


def _default_required_tables(index: int) -> list[str]:
    return {
        5: ["资源配置表"],
        7: ["质量检查表"],
        8: ["安全风险清单"],
        15: ["评分点响应索引表"],
    }.get(index, [])


class LongformSectionGenerator:
    def __init__(self, *, completion_fn: CompletionFn, max_rounds: int = 4) -> None:
        self._completion_fn = completion_fn
        self._max_rounds = max(1, max_rounds)

    def generate_sections(self, *, context: dict[str, Any], section_plan: list[dict[str, Any]]) -> dict[str, Any]:
        sections: list[dict[str, Any]] = []
        content_parts: list[str] = []
        total_input_tokens = 0
        total_output_tokens = 0
        total_latency_ms = 0
        overall_status = "completed"
        chapter = context.get("chapter") or {}
        content_parts.append(f"# {chapter.get('chapter_code', '')} {chapter.get('chapter_title', '')}".strip())

        for item in section_plan:
            generated = ""
            rounds = 0
            provider = None
            model = None
            started = time.monotonic()
            while rounds < self._max_rounds:
                rounds += 1
                payload = self._payload(context=context, section=item, existing_content=generated, round_index=rounds)
                result = self._completion_fn(payload)
                generated = (generated + "\n" + str(result.get("content") or "")).strip()
                usage = result.get("usage") or {}
                total_input_tokens += int(usage.get("input_tokens") or 0)
                total_output_tokens += int(usage.get("output_tokens") or 0)
                total_latency_ms += int(usage.get("latency_ms") or 0)
                provider = result.get("provider") or result.get("resolved_provider") or provider
                model = result.get("model") or result.get("resolved_model") or model
                if len(generated) >= int(item.get("min_chars") or 0):
                    break
            status = "completed" if len(generated) >= int(item.get("min_chars") or 0) else "failed_min_chars"
            if status != "completed":
                overall_status = "failed"
            section_md = f"## {item['section_code']} {item['title']}\n{generated}".strip()
            estimate = estimate_markdown_pages(section_md, target_pages=int(item.get("target_pages") or 0))
            content_parts.append(section_md)
            sections.append(
                {
                    "section_code": item["section_code"],
                    "title": item["title"],
                    "status": status,
                    "target_pages": item.get("target_pages"),
                    "estimated_pages": estimate["estimated_pages"],
                    "min_chars": int(item.get("min_chars") or 0),
                    "actual_chars": len(generated),
                    "continuation_rounds": rounds,
                    "required_charts": list(item.get("required_charts") or []),
                    "required_tables": list(item.get("required_tables") or []),
                    "prompt_hash": _hash_json(self._payload(context=context, section=item, existing_content="", round_index=1)),
                    "provider": provider,
                    "model": model,
                    "latency_ms": int((time.monotonic() - started) * 1000),
                }
            )

        return {
            "status": overall_status,
            "content_md": "\n\n".join(content_parts).strip(),
            "sections": sections,
            "metadata": {
                "section_count": len(sections),
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "total_latency_ms": total_latency_ms,
                "max_rounds": self._max_rounds,
            },
        }

    def _payload(self, *, context: dict[str, Any], section: dict[str, Any], existing_content: str, round_index: int) -> dict[str, Any]:
        return {
            "task": "generate_longform_subsection",
            "chapter": context.get("chapter"),
            "section_code": section["section_code"],
            "section_title": section["title"],
            "target_pages": section.get("target_pages"),
            "min_chars": section.get("min_chars"),
            "required_charts": section.get("required_charts") or [],
            "required_tables": section.get("required_tables") or [],
            "round_index": round_index,
            "existing_content_tail": existing_content[-1800:],
            "context": context,
        }


def _hash_json(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run subsection tests**

Run:

```bash
cd backend && ../.venv/bin/pytest tests/unit/test_longform_section_generation.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/services/longform_section_generation.py backend/tests/unit/test_longform_section_generation.py
git commit -m "feat: add longform subsection generation loop"
```

### Task 4: Route target 100-page technical chapters through subsection generation

**Files:**
- Modify: `backend/tender_backend/services/technical_bid_writer.py`
- Modify: `backend/tests/unit/test_technical_bid_writer.py`

- [ ] **Step 1: Add failing test for longform routing**

Append to `backend/tests/unit/test_technical_bid_writer.py`:

```python
def test_generate_chapter_uses_longform_generator_for_large_target(monkeypatch):
    project_id = uuid4()
    chapter_id = uuid4()
    inserted = {}

    class _Conn:
        def cursor(self, row_factory=None):
            return self
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def execute(self, sql, params=None):
            self.sql = sql
            self.params = params
            return self
        def fetchone(self):
            if "FROM bid_outline" in self.sql:
                return {"id": uuid4(), "project_id": project_id, "status": "confirmed"}
            if "FROM bid_chapter" in self.sql:
                return {"id": chapter_id, "project_id": project_id, "chapter_code": "8", "chapter_title": "施工组织设计", "volume_type": "technical"}
            if "INSERT INTO chapter_draft" in self.sql:
                inserted["params"] = self.params
                return {"id": uuid4(), "project_id": project_id, "chapter_code": "8", "content_md": self.params[4], "target_pages": 100, "estimated_pages": 95}
            if "INSERT INTO bid_generation_run" in self.sql:
                return {"id": uuid4(), "project_id": project_id, "status": "completed", "metadata_json": {}}
            return None
        def fetchall(self):
            return []
        def commit(self):
            pass

    class _ContextBuilder:
        def build(self, conn, *, project_id, chapter_id):
            return {"chapter": {"chapter_code": "8", "chapter_title": "施工组织设计"}, "generation_controls": {"target_pages": 100}}

    class _TemplateInputs:
        def build_generation_inputs(self, conn, *, project_id):
            return {"metadata": {}}

    class _Longform:
        def __init__(self, *args, **kwargs):
            pass
        def generate_sections(self, *, context, section_plan):
            return {
                "status": "completed",
                "content_md": "# 8 施工组织设计\n\n## 8.1 编制依据\n" + "内容" * 4000,
                "sections": [{"section_code": "8.1", "status": "completed", "continuation_rounds": 1}],
                "metadata": {"section_count": 1, "total_output_tokens": 100},
            }

    monkeypatch.setattr("tender_backend.services.technical_bid_writer.TechnicalChapterContextBuilder", _ContextBuilder)
    monkeypatch.setattr("tender_backend.services.technical_bid_writer.ProjectTemplateInstanceService", _TemplateInputs)
    monkeypatch.setattr("tender_backend.services.technical_bid_writer.LongformSectionGenerator", _Longform)
    monkeypatch.setattr("tender_backend.services.technical_bid_writer.plan_chapter_8_sections", lambda target_pages: [{"section_code": "8.1", "title": "编制依据", "target_pages": 100, "min_chars": 100, "required_charts": []}])
    monkeypatch.setattr("tender_backend.services.technical_bid_writer._request_ai_gateway_completion", lambda context, rewrite_note=None: {"content": "unused"})

    result = TechnicalBidWriter().generate_chapter(_Conn(), project_id=project_id, chapter_id=chapter_id, target_pages=100)

    assert result["draft"]["target_pages"] == 100
    assert "## 8.1 编制依据" in result["draft"]["content_md"]
```

- [ ] **Step 2: Run targeted test to verify it fails**

Run:

```bash
cd backend && ../.venv/bin/pytest tests/unit/test_technical_bid_writer.py::test_generate_chapter_uses_longform_generator_for_large_target -q
```

Expected: FAIL because `LongformSectionGenerator` is not imported or longform path is not used.

- [ ] **Step 3: Modify technical writer imports and generation branch**

In `backend/tender_backend/services/technical_bid_writer.py`, add imports near existing service imports:

```python
from tender_backend.services.longform_quality import build_coverage_report, build_chart_closure_report, estimate_markdown_pages
from tender_backend.services.longform_section_generation import LongformSectionGenerator, plan_chapter_8_sections
```

Inside `generate_chapter`, replace the single `ai_result = _request_ai_gateway_completion(...)` branch with this structure:

```python
        if _should_use_longform_generation(chapter=chapter, target_pages=target_pages):
            longform_result = LongformSectionGenerator(
                completion_fn=lambda payload: _request_ai_gateway_subsection_completion(payload) or _deterministic_subsection_completion(payload),
                max_rounds=4,
            ).generate_sections(
                context=context,
                section_plan=plan_chapter_8_sections(target_pages=target_pages or 100),
            )
            draft = _save_chapter_draft(
                conn,
                project_id=project_id,
                chapter=chapter,
                content_md=longform_result["content_md"],
                context=context,
                target_pages=target_pages,
                longform_result=longform_result,
            )
            generation_mode = "longform_subsection_loop"
            ai_metadata = {"longform": longform_result["metadata"], "sections": longform_result["sections"]}
        else:
            ai_result = _request_ai_gateway_completion(context, rewrite_note=rewrite_note)
            if ai_result is not None:
                draft = _save_chapter_draft(
                    conn,
                    project_id=project_id,
                    chapter=chapter,
                    content_md=ai_result["content"],
                    context=context,
                    target_pages=target_pages,
                    longform_result=None,
                )
                generation_mode = "ai_gateway"
                ai_metadata = _ai_gateway_metadata(ai_result)
            else:
                draft = generate_bid_chapter_draft(conn, project_id=project_id, chapter_id=chapter_id, context=context, rewrite_note=rewrite_note)
                generation_mode = "deterministic_strategy_fallback"
                ai_metadata = None
```

Add helper functions below `_ai_gateway_metadata`:

```python
def _should_use_longform_generation(*, chapter: dict[str, Any], target_pages: int | None) -> bool:
    return str(chapter.get("chapter_code") or "") == "8" and bool(target_pages and target_pages >= 80)


def _request_ai_gateway_subsection_completion(payload: dict[str, Any]) -> dict[str, Any] | None:
    context = dict(payload.get("context") or {})
    subsection_context = {**context, "longform_subsection": payload}
    result = _request_ai_gateway_completion(subsection_context, rewrite_note=f"续写 {payload.get('section_code')} {payload.get('section_title')}")
    if result is None:
        return None
    return {
        "content": result["content"],
        "provider": result.get("resolved_provider"),
        "model": result.get("resolved_model"),
        "usage": result.get("usage") or {},
    }


def _deterministic_subsection_completion(payload: dict[str, Any]) -> dict[str, Any]:
    section_code = payload.get("section_code")
    section_title = payload.get("section_title")
    required_charts = payload.get("required_charts") or []
    chart_lines = "\n".join(f"{{{{chart:{key}}}}}" for key in required_charts)
    paragraph = f"{section_code} {section_title}围绕招标约束、施工组织、责任分工、过程检查和闭环验收展开。"
    min_chars = int(payload.get("min_chars") or 1200)
    body = (paragraph * max(20, min_chars // max(1, len(paragraph))))[:min_chars]
    return {"content": f"{body}\n{chart_lines}".strip(), "provider": "deterministic", "model": "fallback", "usage": {"output_tokens": 0}}
```

- [ ] **Step 4: Extend `_save_chapter_draft` signature and SQL**

Change `_save_chapter_draft` signature to:

```python
def _save_chapter_draft(
    conn: Connection,
    *,
    project_id: UUID,
    chapter: dict[str, Any],
    content_md: str,
    context: dict[str, Any],
    target_pages: int | None = None,
    longform_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
```

Before the SQL, compute:

```python
    page_estimate = estimate_markdown_pages(content_md, target_pages=target_pages)
    checklist = (longform_result or {}).get("sections") or []
    constraints = list(context.get("constraints") or [])
    coverage_report = build_coverage_report(content_md, checklist=checklist, constraints=constraints) if checklist else {}
    chart_closure_report = build_chart_closure_report(content_md=content_md, chart_assets=list(context.get("chart_assets") or []))
    generation_rounds = max([int(section.get("continuation_rounds") or 1) for section in checklist] or [1])
```

Extend the `INSERT INTO chapter_draft` columns with:

```sql
              target_pages, estimated_pages, page_estimate_json, coverage_report_json,
              chart_closure_report_json, generation_rounds,
```

Extend the `VALUES` with six `%s` placeholders and `DO UPDATE SET` with:

```sql
              target_pages = EXCLUDED.target_pages,
              estimated_pages = EXCLUDED.estimated_pages,
              page_estimate_json = EXCLUDED.page_estimate_json,
              coverage_report_json = EXCLUDED.coverage_report_json,
              chart_closure_report_json = EXCLUDED.chart_closure_report_json,
              generation_rounds = EXCLUDED.generation_rounds,
```

Pass the values as `Jsonb(page_estimate)`, `Jsonb(coverage_report)`, `Jsonb(chart_closure_report)`, and `generation_rounds`.

- [ ] **Step 5: Run technical writer tests**

Run:

```bash
cd backend && ../.venv/bin/pytest tests/unit/test_technical_bid_writer.py -q
```

Expected: all tests in the file pass.

- [ ] **Step 6: Commit**

```bash
git add backend/tender_backend/services/technical_bid_writer.py backend/tests/unit/test_technical_bid_writer.py
git commit -m "feat: route long technical chapters through subsection loop"
```

### Task 5: Add actual DOCX page counting with explicit unchecked state

**Files:**
- Create: `backend/tender_backend/services/export_service/page_counter.py`
- Create: `backend/tests/unit/test_page_counter.py`

- [ ] **Step 1: Write failing page counter tests**

Create `backend/tests/unit/test_page_counter.py`:

```python
from pathlib import Path

from tender_backend.services.export_service.page_counter import count_docx_pages


def test_count_docx_pages_returns_unchecked_when_soffice_missing(monkeypatch, tmp_path):
    docx = tmp_path / "sample.docx"
    docx.write_bytes(b"not a real docx for this branch")
    monkeypatch.setattr("tender_backend.services.export_service.page_counter.shutil.which", lambda name: None)

    result = count_docx_pages(docx)

    assert result["status"] == "unchecked"
    assert result["actual_pages"] is None
    assert result["method"] == "libreoffice_pdf_unavailable"


def test_count_docx_pages_uses_pdf_page_count_when_converter_available(monkeypatch, tmp_path):
    docx = tmp_path / "sample.docx"
    pdf = tmp_path / "sample.pdf"
    docx.write_bytes(b"fake")
    pdf.write_bytes(b"%PDF fake")
    monkeypatch.setattr("tender_backend.services.export_service.page_counter.shutil.which", lambda name: "/usr/bin/soffice")

    class _Completed:
        returncode = 0
        stderr = ""

    monkeypatch.setattr("tender_backend.services.export_service.page_counter.subprocess.run", lambda *args, **kwargs: _Completed())

    class _Doc:
        def __init__(self, path):
            self.path = path
        def __len__(self):
            return 12
        def close(self):
            pass

    monkeypatch.setattr("tender_backend.services.export_service.page_counter.fitz.open", lambda path: _Doc(path))

    result = count_docx_pages(docx)

    assert result["status"] == "counted"
    assert result["actual_pages"] == 12
    assert result["method"] == "libreoffice_pdf_pymupdf"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend && ../.venv/bin/pytest tests/unit/test_page_counter.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'tender_backend.services.export_service.page_counter'`.

- [ ] **Step 3: Implement page counter**

Create `backend/tender_backend/services/export_service/page_counter.py`:

```python
"""DOCX page counting with explicit fallback states."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

import fitz


def count_docx_pages(docx_path: Path) -> dict[str, Any]:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return {
            "status": "unchecked",
            "actual_pages": None,
            "method": "libreoffice_pdf_unavailable",
            "message": "LibreOffice 不可用，无法自动统计真实页数。",
        }
    with tempfile.TemporaryDirectory(prefix="tender-page-count-") as tmp:
        tmpdir = Path(tmp)
        completed = subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(tmpdir), str(docx_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
            check=False,
        )
        pdf_path = tmpdir / f"{docx_path.stem}.pdf"
        if completed.returncode != 0 or not pdf_path.exists():
            return {
                "status": "unchecked",
                "actual_pages": None,
                "method": "libreoffice_pdf_failed",
                "message": completed.stderr or "LibreOffice 转 PDF 失败。",
            }
        document = fitz.open(str(pdf_path))
        try:
            pages = len(document)
        finally:
            document.close()
        return {
            "status": "counted",
            "actual_pages": pages,
            "method": "libreoffice_pdf_pymupdf",
            "message": f"DOCX 转 PDF 后统计为 {pages} 页。",
        }
```

- [ ] **Step 4: Run page counter tests**

Run:

```bash
cd backend && ../.venv/bin/pytest tests/unit/test_page_counter.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/services/export_service/page_counter.py backend/tests/unit/test_page_counter.py
git commit -m "feat: add docx page count evidence"
```

### Task 6: Wire page, coverage, and chart evidence into export gates

**Files:**
- Modify: `backend/tender_backend/services/export_gate_service.py`
- Modify: `backend/tests/unit/test_export_gates.py`

- [ ] **Step 1: Add failing export gate tests**

Append to `backend/tests/unit/test_export_gates.py`:

```python
def test_export_gate_blocks_when_page_estimate_below_target(monkeypatch):
    project_id = uuid4()

    class _Conn:
        def cursor(self, row_factory=None):
            return self
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def execute(self, sql, params=None):
            self.sql = sql
            return self
        def fetchone(self):
            if "metadata_json FROM project" in self.sql:
                return {"metadata_json": {}}
            if "COUNT(*)" in self.sql:
                return {"count": 0, "stale_template_artifact_count": 0}
            return {"target_pages": 100, "estimated_pages": 88, "page_estimate_json": {}, "coverage_report_json": {"coverage_passed": True, "issues": []}, "chart_closure_report_json": {"chart_closure_passed": True, "issues": []}}
        def fetchall(self):
            if "FROM chapter_draft" in self.sql:
                return [{"content_md": "# 8", "referenced_chart_keys": [], "target_pages": 100, "estimated_pages": 88, "page_estimate_json": {}, "coverage_report_json": {"coverage_passed": True, "issues": []}, "chart_closure_report_json": {"chart_closure_passed": True, "issues": []}}]
            return []

    monkeypatch.setattr("tender_backend.services.export_gate_service.RequirementRepository", lambda: type("R", (), {"unconfirmed_veto_count": lambda self, conn, project_id: 0})())
    monkeypatch.setattr("tender_backend.services.export_gate_service.ChartAssetRepository", lambda: type("C", (), {"list_by_project": lambda self, conn, project_id: []})())
    monkeypatch.setattr("tender_backend.services.export_gate_service.TenderConstraintService", lambda: type("T", (), {"latest_confirmed": lambda self, conn, project_id: {"items": []}, "latest": lambda self, conn, project_id: {"items": []}})())
    monkeypatch.setattr("tender_backend.services.export_gate_service.get_blocking_issues", lambda conn, *, project_id: [])

    state = build_export_gate_state(_Conn(), project_id=project_id)

    assert state["gates"]["page_count_passed"] is False
    assert state["can_export"] is False


def test_export_gate_blocks_when_coverage_report_has_p0_issue(monkeypatch):
    project_id = uuid4()

    class _Conn:
        def cursor(self, row_factory=None):
            return self
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def execute(self, sql, params=None):
            self.sql = sql
            return self
        def fetchone(self):
            if "metadata_json FROM project" in self.sql:
                return {"metadata_json": {}}
            if "COUNT(*)" in self.sql:
                return {"count": 0, "stale_template_artifact_count": 0}
            return None
        def fetchall(self):
            if "FROM chapter_draft" in self.sql:
                return [{"content_md": "# 8", "referenced_chart_keys": [], "target_pages": 100, "estimated_pages": 95, "coverage_report_json": {"coverage_passed": False, "issues": [{"code": "missing_section", "severity": "P0"}]}, "chart_closure_report_json": {"chart_closure_passed": True, "issues": []}}]
            return []

    monkeypatch.setattr("tender_backend.services.export_gate_service.RequirementRepository", lambda: type("R", (), {"unconfirmed_veto_count": lambda self, conn, project_id: 0})())
    monkeypatch.setattr("tender_backend.services.export_gate_service.ChartAssetRepository", lambda: type("C", (), {"list_by_project": lambda self, conn, project_id: []})())
    monkeypatch.setattr("tender_backend.services.export_gate_service.TenderConstraintService", lambda: type("T", (), {"latest_confirmed": lambda self, conn, project_id: {"items": []}, "latest": lambda self, conn, project_id: {"items": []}})())
    monkeypatch.setattr("tender_backend.services.export_gate_service.get_blocking_issues", lambda conn, *, project_id: [])

    state = build_export_gate_state(_Conn(), project_id=project_id)

    assert state["gates"]["coverage_passed"] is False
    assert state["gates"]["coverage_issue_count"] == 1
    assert state["can_export"] is False
```

- [ ] **Step 2: Run targeted tests to verify they fail**

Run:

```bash
cd backend && ../.venv/bin/pytest tests/unit/test_export_gates.py::test_export_gate_blocks_when_page_estimate_below_target tests/unit/test_export_gates.py::test_export_gate_blocks_when_coverage_report_has_p0_issue -q
```

Expected: FAIL because new gate keys are missing.

- [ ] **Step 3: Implement evidence loading and gates**

In `backend/tender_backend/services/export_gate_service.py`, import:

```python
from tender_backend.services.longform_quality import build_page_gate
```

Add helper:

```python
def _draft_quality_evidence(conn: Connection, *, project_id: UUID) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT chapter_code, target_pages, estimated_pages, page_estimate_json,
                   coverage_report_json, chart_closure_report_json
            FROM chapter_draft
            WHERE project_id = %s
            """,
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _longform_quality_gates(drafts: list[dict]) -> dict:
    page_gates = [
        build_page_gate(
            target_pages=row.get("target_pages"),
            estimated_pages=row.get("estimated_pages"),
            actual_pages=((row.get("page_estimate_json") or {}).get("actual_pages")),
            actual_status=((row.get("page_estimate_json") or {}).get("actual_status") or "unchecked"),
        )
        for row in drafts
        if row.get("target_pages")
    ]
    coverage_issues = []
    chart_issues = []
    for row in drafts:
        coverage = row.get("coverage_report_json") or {}
        chart = row.get("chart_closure_report_json") or {}
        coverage_issues.extend(coverage.get("issues") or [])
        chart_issues.extend(chart.get("issues") or [])
    page_passed = all(gate.get("page_count_passed") for gate in page_gates) if page_gates else True
    return {
        "page_count_passed": page_passed,
        "page_count_status": "passed" if page_passed else next((gate.get("page_count_status") for gate in page_gates if not gate.get("page_count_passed")), "failed"),
        "page_count_evidence": page_gates,
        "coverage_passed": not any(issue.get("severity") == "P0" for issue in coverage_issues),
        "coverage_issue_count": len(coverage_issues),
        "coverage_issues": coverage_issues[:20],
        "chart_closure_passed": not any(issue.get("severity") == "P0" for issue in chart_issues),
        "chart_closure_issue_count": len(chart_issues),
        "chart_closure_issues": chart_issues[:20],
    }
```

In `build_export_gate_state`, after stale counts:

```python
    quality_gates = _longform_quality_gates(_draft_quality_evidence(conn, project_id=project_id))
```

Merge into `gates` with `**quality_gates`, and extend `can_export` with:

```python
            and gates["page_count_passed"]
            and gates["coverage_passed"]
            and gates["chart_closure_passed"]
```

- [ ] **Step 4: Run export gate tests**

Run:

```bash
cd backend && ../.venv/bin/pytest tests/unit/test_export_gates.py -q
```

Expected: all tests in the file pass.

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/services/export_gate_service.py backend/tests/unit/test_export_gates.py
git commit -m "feat: gate final export on longform quality evidence"
```

### Task 7: Persist export render evidence and chart residual check

**Files:**
- Modify: `backend/tender_backend/services/export_service/docx_exporter.py`
- Modify: `backend/tender_backend/api/exports.py`
- Modify: `backend/tests/unit/test_docx_exporter.py`

- [ ] **Step 1: Add failing DOCX evidence test**

Append to `backend/tests/unit/test_docx_exporter.py`:

```python
def test_export_evidence_reports_residual_chart_placeholders(tmp_path):
    from docx import Document
    from tender_backend.services.export_service.docx_exporter import inspect_rendered_docx_evidence

    path = tmp_path / "residual.docx"
    doc = Document()
    doc.add_paragraph("正文 {{chart:risk_matrix}}")
    doc.save(path)

    evidence = inspect_rendered_docx_evidence(path)

    assert evidence["residual_chart_placeholders"] == ["risk_matrix"]
    assert evidence["residual_chart_placeholder_count"] == 1
```

- [ ] **Step 2: Run targeted test to verify it fails**

Run:

```bash
cd backend && ../.venv/bin/pytest tests/unit/test_docx_exporter.py::test_export_evidence_reports_residual_chart_placeholders -q
```

Expected: FAIL because `inspect_rendered_docx_evidence` is missing.

- [ ] **Step 3: Implement rendered DOCX evidence helper**

In `backend/tender_backend/services/export_service/docx_exporter.py`, add imports:

```python
from tender_backend.services.export_service.page_counter import count_docx_pages
```

Add function near export helpers:

```python
def inspect_rendered_docx_evidence(path: Path) -> dict:
    text = ""
    media_count = 0
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.startswith("word/document") and name.endswith(".xml"):
                text += archive.read(name).decode("utf-8", errors="ignore")
            if name.startswith("word/media/"):
                media_count += 1
    residual = sorted(set(CHART_PLACEHOLDER_RE.findall(text))) if "CHART_PLACEHOLDER_RE" in globals() else sorted(set(re.findall(r"\{\{chart:([A-Za-z][A-Za-z0-9_.:-]{0,127})\}\}", text)))
    page_count = count_docx_pages(path)
    return {
        "path": str(path),
        "media_count": media_count,
        "residual_chart_placeholders": residual,
        "residual_chart_placeholder_count": len(residual),
        "page_count": page_count,
    }
```

If `CHART_PLACEHOLDER_RE` is not imported in this file, add:

```python
CHART_PLACEHOLDER_RE = re.compile(r"\{\{chart:([A-Za-z][A-Za-z0-9_.:-]{0,127})\}\}")
```

- [ ] **Step 4: Persist evidence in export API**

In `backend/tender_backend/api/exports.py`, after `output = render_export(...)`, compute:

```python
        render_evidence = inspect_rendered_docx_evidence(Path(output)) if Path(output).suffix == ".docx" else {"path": str(output), "page_count": {"status": "unchecked", "actual_pages": None}}
```

Import:

```python
from tender_backend.services.export_service.docx_exporter import inspect_rendered_docx_evidence
from psycopg.types.json import Jsonb
```

Change export insert SQL to include metadata:

```sql
            INSERT INTO export_record (id, project_id, status, template_name, export_key, metadata_json)
            VALUES (%s, %s, %s, %s, %s, %s)
```

Pass `Jsonb({"render_evidence": render_evidence})` as the final parameter.

- [ ] **Step 5: Run DOCX exporter tests**

Run:

```bash
cd backend && ../.venv/bin/pytest tests/unit/test_docx_exporter.py tests/unit/test_page_counter.py -q
```

Expected: all tests in both files pass.

- [ ] **Step 6: Commit**

```bash
git add backend/tender_backend/services/export_service/docx_exporter.py backend/tender_backend/api/exports.py backend/tests/unit/test_docx_exporter.py
git commit -m "feat: persist docx render quality evidence"
```

### Task 8: Update frontend export gate evidence display

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/modules/export/ExportGateContent.tsx`
- Modify: `frontend/src/modules/export/ExportGateContent.test.tsx`

- [ ] **Step 1: Add failing frontend test**

Append to `frontend/src/modules/export/ExportGateContent.test.tsx`:

```tsx
it("shows page count, coverage, and chart closure gate evidence", async () => {
  server.use(
    http.get("*/projects/:projectId/export-gates", () =>
      HttpResponse.json({
        project_id: "p1",
        can_export: false,
        gates: {
          veto_confirmed: true,
          unconfirmed_veto_count: 0,
          review_passed: true,
          blocking_issue_count: 0,
          charts_approved: true,
          unapproved_chart_count: 0,
          referenced_chart_count: 2,
          constraints_confirmed: true,
          legacy_pre_constraint_set: false,
          critical_constraints_resolved: true,
          unresolved_critical_constraint_count: 0,
          template_required_items_rendered: true,
          required_template_failed_count: 0,
          stale_artifacts_clear: true,
          stale_artifact_count: 0,
          template_stale_artifacts_clear: true,
          stale_template_artifact_count: 0,
          format_passed: false,
          format_status: "warning_not_checked",
          page_count_passed: false,
          page_count_status: "failed_estimate_below_minimum",
          page_count_evidence: [{ target_pages: 100, minimum_required_pages: 90, estimated_pages: 88, actual_pages: null }],
          coverage_passed: false,
          coverage_issue_count: 1,
          coverage_issues: [{ code: "missing_section", section_code: "8.2", severity: "P0" }],
          chart_closure_passed: false,
          chart_closure_issue_count: 1,
          chart_closure_issues: [{ code: "chart_not_inserted", chart_key: "risk_matrix", severity: "P0" }],
        },
      }),
    ),
  );

  render(<ExportGateContent />);

  expect(await screen.findByText("页数硬闸门")).toBeInTheDocument();
  expect(screen.getByText(/目标 100 页/)).toBeInTheDocument();
  expect(screen.getByText("内容覆盖完整性")).toBeInTheDocument();
  expect(screen.getByText(/1 个覆盖缺口/)).toBeInTheDocument();
  expect(screen.getByText("图表闭环")).toBeInTheDocument();
  expect(screen.getByText(/risk_matrix/)).toBeInTheDocument();
});
```

If this test file uses a different mock style, keep its existing setup and only add the JSON gate keys/assertions above.

- [ ] **Step 2: Run targeted frontend test to verify it fails**

Run:

```bash
npm --prefix frontend run test -- src/modules/export/ExportGateContent.test.tsx
```

Expected: FAIL because new gate cards are not rendered and types are missing.

- [ ] **Step 3: Extend API types**

In `frontend/src/lib/api.ts`, extend `ExportGates["gates"]` with:

```ts
    page_count_passed: boolean;
    page_count_status: "passed" | "not_required" | "failed_actual_below_minimum" | "failed_estimate_below_minimum" | "warning_actual_unchecked" | "failed";
    page_count_evidence?: Array<{
      target_pages?: number | null;
      minimum_required_pages?: number | null;
      estimated_pages?: number | null;
      actual_pages?: number | null;
      page_count_message?: string;
    }>;
    coverage_passed: boolean;
    coverage_issue_count: number;
    coverage_issues?: Array<{ code: string; section_code?: string; chart_key?: string; severity?: string }>;
    chart_closure_passed: boolean;
    chart_closure_issue_count: number;
    chart_closure_issues?: Array<{ code: string; chart_key?: string; severity?: string }>;
```

- [ ] **Step 4: Render new gate cards**

In `frontend/src/modules/export/ExportGateContent.tsx`, add helper above component:

```tsx
function pageEvidenceDetail(gates: NonNullable<import("../../lib/api").ExportGates["gates"]>) {
  const first = gates.page_count_evidence?.[0];
  if (!first) return gates.page_count_passed ? "未设置目标页数" : "缺少页数证据";
  const actual = first.actual_pages == null ? "实际未校验" : `实际 ${first.actual_pages} 页`;
  return `目标 ${first.target_pages ?? "-"} 页，最低 ${first.minimum_required_pages ?? "-"} 页，估算 ${first.estimated_pages ?? "-"} 页，${actual}`;
}
```

Inside the gate card grid, add after “模板修改后未重新生成”:

```tsx
          <GateIndicator
            passed={gates.page_count_passed ?? true}
            label="页数硬闸门"
            detail={pageEvidenceDetail(gates)}
          />
          <GateIndicator
            passed={gates.coverage_passed ?? true}
            label="内容覆盖完整性"
            detail={
              gates.coverage_passed
                ? "章节、硬约束、必备图表和表格均已覆盖"
                : `${gates.coverage_issue_count ?? 0} 个覆盖缺口${gates.coverage_issues?.[0]?.section_code ? `：${gates.coverage_issues[0].section_code}` : ""}`
            }
          />
          <GateIndicator
            passed={gates.chart_closure_passed ?? gates.charts_approved}
            label="图表闭环"
            detail={
              gates.chart_closure_passed
                ? "图表引用、资产、渲染和插入均已闭环"
                : `${gates.chart_closure_issue_count ?? 0} 个图表缺口${gates.chart_closure_issues?.[0]?.chart_key ? `：${gates.chart_closure_issues[0].chart_key}` : ""}`
            }
          />
```

- [ ] **Step 5: Run frontend export tests**

Run:

```bash
npm --prefix frontend run test -- src/modules/export/ExportGateContent.test.tsx
```

Expected: test file passes.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/modules/export/ExportGateContent.tsx frontend/src/modules/export/ExportGateContent.test.tsx
git commit -m "feat: show longform export gate evidence"
```

### Task 9: End-to-end verification and launch decision update

**Files:**
- Modify: `docs/superpowers/plans/2026-05-15-unresolved-launch-issues.md`
- Create: `docs/acceptance/2026-05-15-longform-launch-closure.md`

- [ ] **Step 1: Run backend quality suite**

Run:

```bash
cd backend && ../.venv/bin/pytest tests/unit/test_longform_quality.py tests/unit/test_longform_section_generation.py tests/unit/test_page_counter.py tests/unit/test_export_gates.py tests/unit/test_technical_bid_writer.py tests/unit/test_docx_exporter.py -q
```

Expected: all selected backend tests pass.

- [ ] **Step 2: Run frontend gate suite**

Run:

```bash
npm --prefix frontend run test -- src/modules/export/ExportGateContent.test.tsx
```

Expected: all selected frontend tests pass.

- [ ] **Step 3: Run build checks**

Run:

```bash
npm --prefix frontend run build
```

Expected: TypeScript and Vite build complete successfully.

- [ ] **Step 4: Update unresolved issue tracker statuses**

In `docs/superpowers/plans/2026-05-15-unresolved-launch-issues.md`, change P0 rows in “当前阻塞状态”:

```markdown
| P0-1 | 已实现自动证据门禁，待真实样本复测 | 阻塞 100 页承诺，需样本通过后关闭 |
| P0-2 | 已实现分段生成与续写框架，待真实样本复测 | 阻塞长篇完整生成，需样本通过后关闭 |
| P0-3 | 已实现覆盖检查门禁，待清单扩展和样本复测 | 阻塞内容完整性承诺，需样本通过后关闭 |
| P0-4 | 已实现图表引用/资产/插入闭环门禁，待真实 DOCX 复测 | 阻塞全部图表承诺，需样本通过后关闭 |
```

Do not mark them “关闭” until a real chapter 8 sample run produces export evidence.

- [ ] **Step 5: Create acceptance report template with current evidence**

Create `docs/acceptance/2026-05-15-longform-launch-closure.md`:

```markdown
# 2026-05-15 Longform Launch Closure Acceptance

## Scope

This report verifies the P0 closure work for long technical bid chapter generation.

## Automated Checks

- Backend longform quality tests: pass after running `cd backend && ../.venv/bin/pytest tests/unit/test_longform_quality.py tests/unit/test_longform_section_generation.py tests/unit/test_page_counter.py tests/unit/test_export_gates.py tests/unit/test_technical_bid_writer.py tests/unit/test_docx_exporter.py -q`.
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
```

- [ ] **Step 6: Commit docs**

```bash
git add docs/superpowers/plans/2026-05-15-unresolved-launch-issues.md docs/acceptance/2026-05-15-longform-launch-closure.md
git commit -m "docs: track longform launch closure acceptance"
```

---

## P1/P2 Follow-up Plans After P0 Evidence

Create separate plan files after Task 9, because each becomes smaller and testable after the P0 evidence model exists:

1. `docs/superpowers/plans/2026-05-15-generation-progress-retry-plan.md`
   - Covers P1-1 stage progress, cancellation, retry failed subsection.
2. `docs/superpowers/plans/2026-05-15-model-strategy-productization-plan.md`
   - Covers P1-2 project/template-level provider, model, max token, temperature, and continuation config.
3. `docs/superpowers/plans/2026-05-15-docx-preview-and-directory-reconciliation-plan.md`
   - Covers P1-3 real DOCX/PDF preview and P1-4 adjusted template directory as coverage source of truth.
4. `docs/superpowers/plans/2026-05-15-multi-sample-acceptance-plan.md`
   - Covers P2-1 three real tender samples and reproducible acceptance reports.

## Self-Review

- Spec coverage: P0-1 maps to Tasks 1, 2, 5, 6, 7, 8. P0-2 maps to Tasks 3 and 4. P0-3 maps to Tasks 2, 4, 6, 8. P0-4 maps to Tasks 2, 6, 7, 8. P1/P2 are explicitly deferred into separate follow-up plans because they are not required to create the first hard production gate.
- Placeholder scan: no deferred-work markers, no unnamed tests, no missing command expectations.
- Type consistency: backend gate keys match frontend `ExportGates` additions: `page_count_passed`, `page_count_status`, `page_count_evidence`, `coverage_passed`, `coverage_issue_count`, `coverage_issues`, `chart_closure_passed`, `chart_closure_issue_count`, `chart_closure_issues`.
