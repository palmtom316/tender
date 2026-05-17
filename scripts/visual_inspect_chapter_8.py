#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import psycopg
from psycopg.rows import dict_row

from tender_backend.core.config import get_settings
from tender_backend.services.longform_quality import _weighted_text_units
from tender_backend.services.longform_section_generation import plan_chapter_8_sections

_CHART_RE = re.compile(r"\{\{chart:([A-Za-z][A-Za-z0-9_.:-]{0,127})\}\}")
_SECTION_RE = re.compile(r"^#{2,6}\s+(8\.\d+)\s+(.+)$", re.MULTILINE)


def build_snapshot(conn: psycopg.Connection, *, draft_id: UUID) -> dict:
    draft = _load_draft(conn, draft_id=draft_id)
    if not draft:
        raise SystemExit(f"chapter_draft not found: {draft_id}")
    project_id = draft["project_id"]
    target_pages = int(draft.get("target_pages") or 100)
    section_plan = {section["section_code"]: section for section in plan_chapter_8_sections(target_pages=target_pages)}
    content_md = str(draft.get("content_md") or "")
    page_estimate = draft.get("page_estimate_json") or {}
    chart_closure = draft.get("chart_closure_report_json") or {}
    return {
        "draft_id": str(draft_id),
        "project_id": str(project_id),
        "chapter_code": draft.get("chapter_code"),
        "target_pages": target_pages,
        "actual_pages": page_estimate.get("actual_pages"),
        "actual_status": page_estimate.get("actual_status"),
        "generation_rounds": draft.get("generation_rounds"),
        "updated_at": str(draft.get("updated_at")),
        "sections": _section_snapshots(content_md, section_plan),
        "chart_assets": _load_chart_assets(conn, project_id=project_id),
        "referenced_chart_keys": sorted(set(_CHART_RE.findall(content_md))),
        "residual_chart_placeholders": _residual_placeholders(chart_closure),
        "coverage_issues": list((draft.get("coverage_report_json") or {}).get("issues") or []),
        "chart_closure_issues": list(chart_closure.get("issues") or []),
    }


def _load_draft(conn: psycopg.Connection, *, draft_id: UUID) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """
            SELECT id, project_id, chapter_code, content_md, target_pages, page_estimate_json,
                   coverage_report_json, chart_closure_report_json, generation_rounds, updated_at
            FROM chapter_draft
            WHERE id = %s
            """,
            (draft_id,),
        ).fetchone()
    return dict(row) if row else None


def _load_chart_assets(conn: psycopg.Connection, *, project_id: UUID) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT id, placeholder_key, chart_type, title, status, rendered_png_path, rendered_path
            FROM chart_asset
            WHERE project_id = %s
            ORDER BY chart_type, placeholder_key
            """,
            (project_id,),
        ).fetchall()
    return [
        {
            "id": str(row["id"]),
            "placeholder_key": row.get("placeholder_key"),
            "chart_type": row.get("chart_type"),
            "title": row.get("title"),
            "status": row.get("status"),
            "rendered_png_path": row.get("rendered_png_path"),
            "rendered_path": row.get("rendered_path"),
        }
        for row in rows
    ]


def _section_snapshots(content_md: str, section_plan: dict[str, dict]) -> list[dict]:
    matches = list(_SECTION_RE.finditer(content_md))
    sections = []
    for index, match in enumerate(matches):
        section_code = match.group(1)
        title = match.group(2).strip()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content_md)
        body = content_md[match.end() : end]
        planned = section_plan.get(section_code, {})
        actual_chars = _weighted_text_units(body)
        min_chars = int(planned.get("min_chars") or 0)
        sections.append(
            {
                "section_code": section_code,
                "title": title,
                "actual_chars": actual_chars,
                "min_chars": min_chars,
                "char_passed": actual_chars >= min_chars if min_chars else None,
                "required_charts": list(planned.get("required_charts") or []),
                "referenced_chart_keys": sorted(set(_CHART_RE.findall(body))),
            }
        )
    return sections


def _residual_placeholders(chart_closure: dict) -> list[str]:
    residual = chart_closure.get("residual_placeholders")
    if isinstance(residual, list):
        return [str(item) for item in residual]
    return sorted(
        {
            str(issue.get("chart_key"))
            for issue in chart_closure.get("issues") or []
            if issue.get("code") == "chart_placeholder_residual" and issue.get("chart_key")
        }
    )


def write_outputs(snapshot: dict, *, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    (output_dir / "summary.md").write_text(_summary_markdown(snapshot), encoding="utf-8")


def _summary_markdown(snapshot: dict) -> str:
    lines = [
        f"# Chapter 8 Visual Inspection: {snapshot['draft_id']}",
        "",
        f"- Project: {snapshot['project_id']}",
        f"- Target pages: {snapshot['target_pages']}",
        f"- Actual pages: {snapshot.get('actual_pages') or 'unchecked'}",
        f"- Generation rounds: {snapshot.get('generation_rounds')}",
        "",
        "## Sections",
        "",
        "| Section | Actual chars | Min chars | Charts |",
        "| --- | ---: | ---: | --- |",
    ]
    for section in snapshot["sections"]:
        lines.append(
            f"| {section['section_code']} {section['title']} | {section['actual_chars']} | "
            f"{section['min_chars']} | {', '.join(section['referenced_chart_keys']) or '-'} |"
        )
    lines.extend(["", "## Chart Assets", "", "| Key | Type | Status | PNG |", "| --- | --- | --- | --- |"])
    for asset in snapshot["chart_assets"]:
        lines.append(
            f"| {asset.get('placeholder_key') or '-'} | {asset.get('chart_type') or '-'} | "
            f"{asset.get('status') or '-'} | {asset.get('rendered_png_path') or '-'} |"
        )
    lines.extend(["", "## Residual Placeholders", "", ", ".join(snapshot["residual_chart_placeholders"]) or "None", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump chapter 8 visual inspection materials.")
    parser.add_argument("--draft-id", required=True, help="chapter_draft UUID")
    parser.add_argument("--output-dir", help="Output directory; defaults to outputs/visual-inspect/<draft-id>")
    args = parser.parse_args()

    draft_id = UUID(args.draft_id)
    output_dir = Path(args.output_dir) if args.output_dir else ROOT / "outputs" / "visual-inspect" / str(draft_id)
    settings = get_settings()
    database_url = settings.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    with psycopg.connect(database_url) as conn:
        snapshot = build_snapshot(conn, draft_id=draft_id)
    write_outputs(snapshot, output_dir=output_dir)
    print(f"Wrote visual inspection materials to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
