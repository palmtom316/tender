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
from docx import Document
from psycopg.rows import dict_row

from tender_backend.core.config import get_settings
from tender_backend.services.business_bid_assembler import BusinessBidAssembler
from tender_backend.services.export_service.docx_exporter import render_volume_docx


CRITICAL_CHAPTER_CODES = {"1", "2", "5", "6", "8", "10", "23", "24"}


def _set_docxtpl_enabled(enabled: bool) -> str | None:
    previous = os.environ.get("BUSINESS_BID_DOCXTPL_ENABLED")
    os.environ["BUSINESS_BID_DOCXTPL_ENABLED"] = "true" if enabled else "false"
    get_settings.cache_clear()
    return previous


def _restore_docxtpl_enabled(previous: str | None) -> None:
    if previous is None:
        os.environ.pop("BUSINESS_BID_DOCXTPL_ENABLED", None)
    else:
        os.environ["BUSINESS_BID_DOCXTPL_ENABLED"] = previous
    get_settings.cache_clear()


def _load_business_chapter_rows(conn: psycopg.Connection, *, project_id: UUID) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT chapter_code, rendered_docx_path, rendered_artifact_json
            FROM chapter_draft
            WHERE project_id = %s AND volume_type = 'business'
            ORDER BY string_to_array(chapter_code, '.')::int[]
            """,
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _chapter_evidence(row: dict) -> dict:
    artifact = row.get("rendered_artifact_json") or {}
    rendered_docx_path = row.get("rendered_docx_path")
    path = Path(str(rendered_docx_path)) if rendered_docx_path else None
    placeholder_status = artifact.get("placeholder_status") or {}
    missing_materials = artifact.get("missing_materials") or []
    size_bytes = path.stat().st_size if path and path.exists() else 0
    size_kb = round(size_bytes / 1024, 2) if size_bytes else 0
    return {
        "chapter_code": str(row.get("chapter_code") or ""),
        "rendered": bool(path and path.exists() and size_bytes > 0),
        "rendered_docx_path": str(path) if path else None,
        "missing_material_count": len(missing_materials),
        "placeholder_unfilled_count": int(placeholder_status.get("unfilled_count") or 0),
        "size_kb": max(size_kb, 0.01) if size_bytes else 0,
    }


def _docx_openable(path: Path) -> bool:
    try:
        Document(str(path))
    except Exception:
        return False
    return True


def _hard_stop_failures(*, chapters: list[dict], output_docx: Path) -> list[str]:
    failures: list[str] = []
    chapter_by_code = {chapter["chapter_code"]: chapter for chapter in chapters}
    top_level_codes = {chapter["chapter_code"] for chapter in chapters if "." not in chapter["chapter_code"]}
    expected_top_level_codes = {str(index) for index in range(1, 25)}
    missing_top_level = sorted(expected_top_level_codes - top_level_codes, key=lambda value: int(value))
    if missing_top_level:
        failures.append("missing top-level business chapters: " + ", ".join(missing_top_level))
    for code in sorted(CRITICAL_CHAPTER_CODES, key=lambda value: int(value)):
        chapter = chapter_by_code.get(code)
        if chapter is None:
            failures.append(f"critical chapter {code} missing")
            continue
        if chapter["placeholder_unfilled_count"] > 0:
            failures.append(f"critical chapter {code} has unfilled placeholders")
    if not output_docx.exists() or output_docx.stat().st_size == 0:
        failures.append("business volume DOCX is empty or missing")
    elif not _docx_openable(output_docx):
        failures.append("business volume DOCX cannot be opened by python-docx")
    return failures


def run_acceptance(
    conn: psycopg.Connection,
    *,
    project_id: UUID,
    company_id: UUID,
    output_dir: Path,
    enable_docxtpl: bool,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    previous_docxtpl = _set_docxtpl_enabled(enable_docxtpl)
    try:
        assembly = BusinessBidAssembler().assemble(conn, project_id=project_id, created_by="business_bid_acceptance")
        output_docx = output_dir / f"business-bid-{project_id}.docx"
        render_volume_docx(conn, project_id=project_id, volume_type="business", output_path=output_docx)
    finally:
        _restore_docxtpl_enabled(previous_docxtpl)

    chapters = [_chapter_evidence(row) for row in _load_business_chapter_rows(conn, project_id=project_id)]
    failures = _hard_stop_failures(chapters=chapters, output_docx=output_docx)
    return {
        "project_id": str(project_id),
        "company_id": str(company_id),
        "docxtpl_enabled": enable_docxtpl,
        "output_docx": str(output_docx),
        "assembly": assembly,
        "chapters": chapters,
        "hard_stop_passed": not failures,
        "hard_stop_failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run business bid DOCX acceptance and collect evidence.")
    parser.add_argument("--project-id", required=True, help="Project UUID")
    parser.add_argument("--company-id", required=True, help="Company UUID")
    parser.add_argument("--output-dir", required=True, help="Directory for rendered DOCX and evidence JSON")
    parser.add_argument("--enable-docxtpl", action="store_true", help="Enable BUSINESS_BID_DOCXTPL rendering for this run")
    parser.add_argument("--evidence-output", help="Optional evidence JSON path; defaults under --output-dir")
    args = parser.parse_args()

    project_id = UUID(args.project_id)
    company_id = UUID(args.company_id)
    output_dir = Path(args.output_dir)
    evidence_path = Path(args.evidence_output) if args.evidence_output else output_dir / "business-bid-24-chapter-evidence.json"

    settings = get_settings()
    database_url = settings.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required to run business bid acceptance")

    with psycopg.connect(database_url) as conn:
        evidence = run_acceptance(
            conn,
            project_id=project_id,
            company_id=company_id,
            output_dir=output_dir,
            enable_docxtpl=args.enable_docxtpl,
        )

    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Wrote business bid acceptance evidence to {evidence_path}")
    return 0 if evidence["hard_stop_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
