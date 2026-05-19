#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import psycopg
from psycopg.rows import dict_row

from tender_backend.core.config import get_settings
from tender_backend.services.template_service.package_importer import import_template_package_from_directory


DEFAULT_PACKAGE_KEY = "sgcc_distribution_business_v1"
DEFAULT_DISPLAY_NAME = "国网配网工程商务标"
DEFAULT_CATEGORY_CODE = "sgcc_distribution"


def _set_template_import_root(sample_docx: Path) -> str | None:
    previous = os.environ.get("TEMPLATE_IMPORT_ROOTS")
    sample_root = str(sample_docx.parent)
    if previous:
        roots = [part for part in previous.split(os.pathsep) if part]
        if sample_root not in roots:
            roots.append(sample_root)
        os.environ["TEMPLATE_IMPORT_ROOTS"] = os.pathsep.join(roots)
    else:
        os.environ["TEMPLATE_IMPORT_ROOTS"] = sample_root
    get_settings.cache_clear()
    return previous


def _restore_template_import_root(previous: str | None) -> None:
    if previous is None:
        os.environ.pop("TEMPLATE_IMPORT_ROOTS", None)
    else:
        os.environ["TEMPLATE_IMPORT_ROOTS"] = previous
    get_settings.cache_clear()


def _verify_imported_items(conn: psycopg.Connection, *, package_key: str, limit: int = 12) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT i.item_code, i.source_kind, i.render_mode, i.relative_path
            FROM bid_template_package p
            JOIN bid_template_item i ON i.package_id = p.id
            WHERE p.package_key = %s
            ORDER BY string_to_array(i.item_code, '.')::int[] NULLS LAST, i.sort_order, i.relative_path
            LIMIT %s
            """,
            (package_key, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def _verification_passed(rows: list[dict[str, Any]]) -> bool:
    return bool(rows) and all(
        row.get("source_kind") == "docx"
        and row.get("render_mode") == "single_docx_section"
        and "#" in str(row.get("relative_path") or "")
        for row in rows
    )


def import_and_verify(
    conn: psycopg.Connection,
    *,
    sample_docx: str | Path,
    package_key: str = DEFAULT_PACKAGE_KEY,
    display_name: str = DEFAULT_DISPLAY_NAME,
    category_code: str | None = DEFAULT_CATEGORY_CODE,
) -> dict[str, Any]:
    sample_path = Path(sample_docx).expanduser().resolve()
    if not sample_path.exists():
        raise FileNotFoundError(f"sample DOCX not found: {sample_path}")
    if sample_path.suffix.lower() != ".docx":
        raise ValueError(f"sample path must be a DOCX file: {sample_path}")

    previous_root = _set_template_import_root(sample_path)
    try:
        imported = import_template_package_from_directory(
            conn,
            source_dir=sample_path,
            package_key=package_key,
            display_name=display_name,
            package_type="business",
            category_code=category_code,
        )
    finally:
        _restore_template_import_root(previous_root)

    sample_rows = _verify_imported_items(conn, package_key=package_key)
    return {
        "sample_docx": str(sample_path),
        "package_id": imported.package_id,
        "package_key": imported.package_key,
        "display_name": imported.display_name,
        "package_type": imported.package_type,
        "source_root": imported.source_root,
        "item_count": imported.item_count,
        "verified_sample_items": sample_rows,
        "verification_passed": _verification_passed(sample_rows),
        "text_redaction": "template text is intentionally omitted",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a confidential merged business DOCX template package.")
    parser.add_argument("--sample-docx", required=True, help="Merged confidential single DOCX path")
    parser.add_argument("--package-key", default=DEFAULT_PACKAGE_KEY, help="Target bid_template_package.package_key")
    parser.add_argument("--display-name", default=DEFAULT_DISPLAY_NAME, help="Target package display name")
    parser.add_argument("--category-code", default=DEFAULT_CATEGORY_CODE, help="Target template package category code")
    parser.add_argument("--evidence-output", required=True, help="Sanitized import evidence JSON path")
    args = parser.parse_args()

    database_url = get_settings().database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required to import the confidential business template package")

    with psycopg.connect(database_url) as conn:
        evidence = import_and_verify(
            conn,
            sample_docx=args.sample_docx,
            package_key=args.package_key,
            display_name=args.display_name,
            category_code=args.category_code or None,
        )

    evidence_output = Path(args.evidence_output).expanduser().resolve()
    evidence_output.parent.mkdir(parents=True, exist_ok=True)
    evidence_output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Wrote sanitized import evidence to {evidence_output}")
    return 0 if evidence["verification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
