#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
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
from tender_backend.services.bid_outline_templates import SGCC_DISTRIBUTION_TECHNICAL_CHAPTERS
from tender_backend.services.technical_chapter_strategies.registry import strategy_for_chapter


TECHNICAL_TOP_LEVEL_CHAPTER_CODES = tuple(
    str(chapter["chapter_code"])
    for chapter in SGCC_DISTRIBUTION_TECHNICAL_CHAPTERS
    if "." not in str(chapter["chapter_code"])
)


def _load_chapter_rows(conn: psycopg.Connection, *, project_id: UUID) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT
              bc.chapter_code,
              bc.chapter_title,
              cd.id AS draft_id,
              cd.content_md,
              cd.metadata_json,
              cd.coverage_report_json,
              cd.chart_closure_report_json
            FROM bid_chapter bc
            LEFT JOIN chapter_draft cd
              ON cd.project_id = bc.project_id
             AND cd.volume_type = bc.volume_type
             AND cd.chapter_code = bc.chapter_code
            WHERE bc.project_id = %s
              AND bc.volume_type = 'technical'
              AND bc.chapter_code = ANY(%s)
            ORDER BY string_to_array(bc.chapter_code, '.')::int[]
            """,
            (project_id, list(TECHNICAL_TOP_LEVEL_CHAPTER_CODES)),
        ).fetchall()
    return [dict(row) for row in rows]


def _configured_chapter_titles() -> dict[str, str]:
    return {
        str(chapter["chapter_code"]): str(chapter["chapter_title"])
        for chapter in SGCC_DISTRIBUTION_TECHNICAL_CHAPTERS
        if "." not in str(chapter["chapter_code"])
    }


def _ready_asset_keys(metadata_json: dict) -> set[str]:
    raw_assets = metadata_json.get("required_assets") or metadata_json.get("assets") or []
    ready: set[str] = set()
    for item in raw_assets:
        if isinstance(item, str):
            ready.add(item)
        elif isinstance(item, dict):
            key = item.get("asset_key") or item.get("asset_category") or item.get("asset_type")
            if key and item.get("ready", True):
                ready.add(str(key))
    return ready


def _chapter_evidence(row: dict) -> dict:
    chapter_code = str(row.get("chapter_code") or "")
    strategy = strategy_for_chapter(chapter_code)
    metadata_json = row.get("metadata_json") or {}
    coverage_report_json = row.get("coverage_report_json") or {}
    chart_closure_report_json = row.get("chart_closure_report_json") or {}
    draft_exists = bool(row.get("draft_id") and str(row.get("content_md") or "").strip())
    required_assets = set(strategy.required_assets if strategy else ())
    ready_assets = _ready_asset_keys(metadata_json)
    missing_assets = sorted(required_assets - ready_assets)
    blind_check = metadata_json.get("blind_check") or {}
    blind_check_passed = bool(blind_check.get("passed", True))
    required_charts = set(strategy.required_charts if strategy else ())
    chart_closure_passed = bool(chart_closure_report_json.get("chart_closure_passed", True))
    charts_ready = (not required_charts) or chart_closure_passed
    export_ready = draft_exists and not missing_assets and blind_check_passed and charts_ready
    return {
        "chapter_code": chapter_code,
        "chapter_title": row.get("chapter_title"),
        "draft_exists": draft_exists,
        "required_assets": sorted(required_assets),
        "missing_required_assets": missing_assets,
        "required_assets_ready": not missing_assets,
        "blind_check_passed": blind_check_passed,
        "blind_check_issues": list(blind_check.get("issues") or []),
        "coverage_passed": bool(coverage_report_json.get("coverage_passed", True)),
        "coverage_issues": list(coverage_report_json.get("issues") or []),
        "charts_ready": charts_ready,
        "required_charts": sorted(required_charts),
        "chart_closure_passed": chart_closure_passed,
        "chart_closure_issues": list(chart_closure_report_json.get("issues") or []),
        "export_ready": export_ready,
    }


def _hard_stop_failures(chapters: list[dict]) -> list[str]:
    failures: list[str] = []
    by_code = {chapter["chapter_code"]: chapter for chapter in chapters}
    missing = [code for code in TECHNICAL_TOP_LEVEL_CHAPTER_CODES if code not in by_code]
    if missing:
        failures.append("missing technical chapters: " + ", ".join(missing))
    for code in TECHNICAL_TOP_LEVEL_CHAPTER_CODES:
        chapter = by_code.get(code)
        if chapter is None:
            continue
        if not chapter["draft_exists"]:
            failures.append(f"chapter {code} draft missing")
        if not chapter["required_assets_ready"]:
            failures.append(
                f"chapter {code} missing required assets: "
                + ", ".join(chapter["missing_required_assets"])
            )
        if not chapter["coverage_passed"]:
            failures.append(f"chapter {code} coverage failed")
        if not chapter["blind_check_passed"]:
            failures.append(f"chapter {code} blind check failed")
        if not chapter["charts_ready"]:
            failures.append(f"chapter {code} charts not ready")
    return failures


def collect_evidence(conn: psycopg.Connection, *, project_id: UUID) -> dict:
    configured_titles = _configured_chapter_titles()
    rows_by_code = {str(row.get("chapter_code") or ""): row for row in _load_chapter_rows(conn, project_id=project_id)}
    rows = [
        rows_by_code.get(code)
        or {
            "chapter_code": code,
            "chapter_title": configured_titles.get(code),
            "draft_id": None,
            "content_md": "",
            "metadata_json": {},
            "coverage_report_json": {},
            "chart_closure_report_json": {},
        }
        for code in TECHNICAL_TOP_LEVEL_CHAPTER_CODES
    ]
    chapters = [_chapter_evidence(row) for row in rows]
    failures = _hard_stop_failures(chapters)
    return {
        "project_id": str(project_id),
        "chapter_codes": list(TECHNICAL_TOP_LEVEL_CHAPTER_CODES),
        "chapters": chapters,
        "hard_stop_passed": not failures,
        "hard_stop_failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run full technical bid acceptance and collect evidence.")
    parser.add_argument("--project-id", required=True, help="Project UUID")
    parser.add_argument("--output-dir", required=True, help="Directory for evidence JSON")
    parser.add_argument("--evidence-output", help="Optional evidence JSON path; defaults under --output-dir")
    args = parser.parse_args()

    project_id = UUID(args.project_id)
    output_dir = Path(args.output_dir)
    evidence_path = Path(args.evidence_output) if args.evidence_output else output_dir / "technical-bid-16-chapter-evidence.json"

    settings = get_settings()
    database_url = settings.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required to run technical bid acceptance")

    with psycopg.connect(database_url) as conn:
        evidence = collect_evidence(conn, project_id=project_id)

    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Wrote technical bid acceptance evidence to {evidence_path}")
    return 0 if evidence["hard_stop_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
