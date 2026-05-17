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


def _load_chapter_8_evidence(conn: psycopg.Connection, *, project_id: UUID) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """
            SELECT chapter_code, target_pages, estimated_pages, page_estimate_json,
                   coverage_report_json, chart_closure_report_json
            FROM chapter_draft
            WHERE project_id = %s AND chapter_code = '8'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        export_row = cur.execute(
            """
            SELECT id, template_name, status, metadata_json, created_at
            FROM export_record
            WHERE project_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()

    return {
        "chapter_draft": dict(row) if row else None,
        "latest_export_record": dict(export_row) if export_row else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect chapter 8 acceptance evidence.")
    parser.add_argument("--project-id", required=True, help="Project UUID")
    parser.add_argument("--output", required=True, help="Output JSON path")
    args = parser.parse_args()

    project_id = UUID(args.project_id)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    settings = get_settings()
    database_url = settings.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required to collect acceptance evidence")

    with psycopg.connect(database_url) as conn:
        evidence = _load_chapter_8_evidence(conn, project_id=project_id)
        evidence["project_id"] = str(project_id)
        evidence["export_gate"] = build_export_gate_state(conn, project_id=project_id)

    output_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Wrote chapter 8 acceptance evidence to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
