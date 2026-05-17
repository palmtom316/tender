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
from tender_backend.services.export_gate_service import build_export_gate_state

DEFAULT_CHAPTER_CODES = ("8", "9", "10.1", "10.2", "10.3")


def _fetch_latest_export_record(conn: psycopg.Connection, *, project_id: UUID) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """
            SELECT id, template_name, status, metadata_json, created_at
            FROM export_record
            WHERE project_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
    return dict(row) if row else None


def _fetch_chapter_draft(conn: psycopg.Connection, *, project_id: UUID, chapter_code: str) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """
            SELECT chapter_code, target_pages, estimated_pages, page_estimate_json,
                   coverage_report_json, chart_closure_report_json, generation_rounds
            FROM chapter_draft
            WHERE project_id = %s AND chapter_code = %s
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (project_id, chapter_code),
        ).fetchone()
    return dict(row) if row else None


def _fetch_longform_model_usage(conn: psycopg.Connection, *, project_id: UUID, chapter_code: str) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """
            SELECT
              COALESCE(count(*), 0)::int AS subsection_count,
              COALESCE(sum(input_tokens), 0)::int AS input_tokens,
              COALESCE(sum(output_tokens), 0)::int AS output_tokens,
              COALESCE(sum(latency_ms), 0)::int AS latency_ms,
              ARRAY_REMOVE(ARRAY_AGG(DISTINCT provider), NULL) AS providers,
              ARRAY_REMOVE(ARRAY_AGG(DISTINCT model), NULL) AS models
            FROM bid_generation_subsection_run
            WHERE project_id = %s AND chapter_code = %s
            """,
            (project_id, chapter_code),
        ).fetchone()
    usage = dict(row) if row else {}
    return {
        "subsection_count": int(usage.get("subsection_count") or 0),
        "input_tokens": int(usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "latency_ms": int(usage.get("latency_ms") or 0),
        "providers": [item for item in (usage.get("providers") or []) if item],
        "models": [item for item in (usage.get("models") or []) if item],
    }


def _chapter_evidence(conn: psycopg.Connection, *, project_id: UUID, chapter_code: str) -> dict:
    draft = _fetch_chapter_draft(conn, project_id=project_id, chapter_code=chapter_code)
    if not draft:
        return {
            "chapter_code": chapter_code,
            "chapter_draft": None,
            "model_usage": {
                "subsection_count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "latency_ms": 0,
                "providers": [],
                "models": [],
            },
        }

    page_estimate_json = draft.get("page_estimate_json") or {}
    coverage_report_json = draft.get("coverage_report_json") or {}
    chart_closure_report_json = draft.get("chart_closure_report_json") or {}
    return {
        "chapter_code": chapter_code,
        "chapter_draft": draft,
        "section_count": int(coverage_report_json.get("checked_section_count") or 0),
        "generation_rounds": int(draft.get("generation_rounds") or 0),
        "actual_pages": int(page_estimate_json.get("actual_pages") or 0),
        "coverage_passed": bool(coverage_report_json.get("coverage_passed")),
        "coverage_issues": list(coverage_report_json.get("issues") or []),
        "chart_closure_passed": bool(chart_closure_report_json.get("chart_closure_passed")),
        "chart_closure_issues": list(chart_closure_report_json.get("issues") or []),
        "model_usage": _fetch_longform_model_usage(conn, project_id=project_id, chapter_code=chapter_code),
    }


def collect_evidence(conn: psycopg.Connection, *, project_id: UUID, chapter_codes: list[str]) -> dict:
    chapters = [_chapter_evidence(conn, project_id=project_id, chapter_code=chapter_code) for chapter_code in chapter_codes]
    return {
        "project_id": str(project_id),
        "chapter_codes": chapter_codes,
        "chapters": chapters,
        "latest_export_record": _fetch_latest_export_record(conn, project_id=project_id),
        "export_gate": build_export_gate_state(conn, project_id=project_id),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect multi-chapter longform acceptance evidence.")
    parser.add_argument("--project-id", required=True, help="Project UUID")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument(
        "--chapter-code",
        dest="chapter_codes",
        action="append",
        help="Chapter code to collect; may be repeated. Defaults to 8, 9, 10.1, 10.2, 10.3.",
    )
    args = parser.parse_args()

    project_id = UUID(args.project_id)
    chapter_codes = args.chapter_codes or list(DEFAULT_CHAPTER_CODES)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    settings = get_settings()
    database_url = settings.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required to collect acceptance evidence")

    with psycopg.connect(database_url) as conn:
        evidence = collect_evidence(conn, project_id=project_id, chapter_codes=chapter_codes)

    output_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Wrote multi-chapter longform acceptance evidence to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
