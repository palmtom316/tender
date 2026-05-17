"""Dump real issue distribution for chapter-8 live test (2026-05-16)."""

from __future__ import annotations

import json
import os
import sys

import psycopg
from psycopg.rows import dict_row


DRAFT_ID = "0e5514d1-eab6-44ad-ba9b-e23d96761179"
PROJECT_ID = "d3ed99c0-1d79-4fad-bd4b-6a77a08cc530"
CHAPTER_ID = "bb832f27-5c8c-4951-9f66-84faf4ac3b77"
RUN_ID = "113ece1d-f548-4a74-bfd4-80c5e44f9909"


def main(output_path: str) -> None:
    dsn = os.environ.get("DATABASE_URL") or "postgresql://tender:change-me@127.0.0.1:5432/tender"
    snapshot: dict = {
        "generated_at": "2026-05-16",
        "draft_id": DRAFT_ID,
        "project_id": PROJECT_ID,
        "chapter_id": CHAPTER_ID,
        "run_id": RUN_ID,
        "draft": {},
        "coverage": {"by_code": {}, "issues": []},
        "chart_closure": {"by_code": {}, "issues": []},
        "chart_assets": [],
        "constraints_summary": {},
    }

    with psycopg.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, chapter_code, target_pages, estimated_pages,
                       length(content_md) AS md_bytes,
                       coverage_report_json,
                       chart_closure_report_json,
                       referenced_chart_keys,
                       page_estimate_json,
                       generation_rounds,
                       updated_at
                FROM chapter_draft
                WHERE id = %s
                """,
                (DRAFT_ID,),
            )
            draft = cur.fetchone()
            if not draft:
                print("DRAFT_NOT_FOUND")
                sys.exit(2)

            snapshot["draft"] = {
                "chapter_code": draft["chapter_code"],
                "target_pages": draft["target_pages"],
                "estimated_pages": draft["estimated_pages"],
                "md_bytes": draft["md_bytes"],
                "referenced_chart_keys": list(draft.get("referenced_chart_keys") or []),
                "generation_rounds": draft["generation_rounds"],
                "page_estimate": draft.get("page_estimate_json") or {},
                "updated_at": str(draft["updated_at"]),
            }

            cov = draft.get("coverage_report_json") or {}
            issues = cov.get("issues") or []
            snapshot["coverage"]["passed"] = cov.get("coverage_passed")
            snapshot["coverage"]["issue_count"] = cov.get("issue_count") or len(issues)
            snapshot["coverage"]["issues"] = issues
            bucket: dict[str, list] = {}
            for issue in issues:
                bucket.setdefault(str(issue.get("code")), []).append(issue)
            snapshot["coverage"]["by_code"] = {code: len(items) for code, items in bucket.items()}

            chart_report = draft.get("chart_closure_report_json") or {}
            chart_issues = chart_report.get("issues") or []
            snapshot["chart_closure"]["passed"] = chart_report.get("chart_closure_passed")
            snapshot["chart_closure"]["referenced_chart_count"] = chart_report.get("referenced_chart_count")
            snapshot["chart_closure"]["asset_chart_count"] = chart_report.get("asset_chart_count")
            snapshot["chart_closure"]["approved_chart_count"] = chart_report.get("approved_chart_count")
            snapshot["chart_closure"]["rendered_chart_count"] = chart_report.get("rendered_chart_count")
            snapshot["chart_closure"]["inserted_chart_count"] = chart_report.get("inserted_chart_count")
            snapshot["chart_closure"]["residual_placeholder_count"] = chart_report.get("residual_placeholder_count")
            snapshot["chart_closure"]["issues"] = chart_issues
            chart_bucket: dict[str, list] = {}
            for issue in chart_issues:
                chart_bucket.setdefault(str(issue.get("code")), []).append(issue)
            snapshot["chart_closure"]["by_code"] = {code: len(items) for code, items in chart_bucket.items()}

            cur.execute(
                """
                SELECT id, placeholder_key, chart_type, title, status,
                       (rendered_svg IS NOT NULL) AS has_svg,
                       (rendered_png_path IS NOT NULL) AS has_png,
                       rendered_png_path,
                       metadata_json
                FROM chart_asset
                WHERE project_id = %s
                ORDER BY chart_type, placeholder_key
                """,
                (PROJECT_ID,),
            )
            for row in cur.fetchall():
                meta = row.get("metadata_json") or {}
                snapshot["chart_assets"].append(
                    {
                        "id": str(row["id"]),
                        "placeholder_key": row["placeholder_key"],
                        "chart_type": row["chart_type"],
                        "title": row["title"],
                        "status": row["status"],
                        "has_svg": bool(row["has_svg"]),
                        "has_png": bool(row["has_png"]),
                        "rendered_png_path": row.get("rendered_png_path"),
                        "metadata": {
                            "validation": meta.get("validation"),
                            "provenance": meta.get("provenance"),
                            "blind_bid_scan": meta.get("blind_bid_scan"),
                            "source_kind": meta.get("source_kind"),
                            "render_engine": meta.get("render_engine"),
                        },
                    }
                )

            cur.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE confirmation_level = 'critical') AS critical_count,
                    COUNT(*) FILTER (WHERE (metadata_json->>'has_conflict')::bool IS TRUE) AS conflict_count,
                    COUNT(*) FILTER (WHERE metadata_json ? 'response_section_code' OR metadata_json ? 'mapped_section_code') AS with_mapped_section,
                    COUNT(*) FILTER (WHERE metadata_json->>'mapped_section_code' LIKE '8%%' OR metadata_json->>'response_section_code' LIKE '8%%') AS mapped_to_ch8
                FROM tender_constraint_item
                WHERE constraint_set_id IN (
                    SELECT id FROM tender_constraint_set WHERE project_id = %s ORDER BY updated_at DESC LIMIT 1
                )
                """,
                (PROJECT_ID,),
            )
            summary = cur.fetchone() or {}
            snapshot["constraints_summary"] = {k: int(v or 0) for k, v in summary.items()}

            cur.execute(
                """
                SELECT id, confirmation_level, status,
                       metadata_json->'response_section_code' AS resp_sec,
                       metadata_json->'mapped_section_code' AS map_sec,
                       (metadata_json->>'has_conflict')::bool AS has_conflict,
                       left(title, 40) AS title_preview
                FROM tender_constraint_item
                WHERE constraint_set_id IN (
                    SELECT id FROM tender_constraint_set WHERE project_id = %s ORDER BY updated_at DESC LIMIT 1
                )
                  AND (confirmation_level = 'critical' OR (metadata_json->>'has_conflict')::bool IS TRUE)
                LIMIT 30
                """,
                (PROJECT_ID,),
            )
            snapshot["critical_constraints_sample"] = [
                {
                    "id": str(row["id"]),
                    "confirmation_level": row["confirmation_level"],
                    "status": row["status"],
                    "response_section_code": row["resp_sec"],
                    "mapped_section_code": row["map_sec"],
                    "has_conflict": row["has_conflict"],
                    "title": row["title_preview"],
                }
                for row in cur.fetchall()
            ]

    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, ensure_ascii=False, indent=2, default=str)

    print(f"WROTE: {output_path}")
    print("=" * 70)
    print(f"Draft: {snapshot['draft']['chapter_code']}, target {snapshot['draft']['target_pages']}p, est {snapshot['draft']['estimated_pages']}p, {snapshot['draft']['md_bytes']} bytes, gen_rounds {snapshot['draft']['generation_rounds']}")
    print(f"\nCoverage (passed={snapshot['coverage']['passed']}, count={snapshot['coverage']['issue_count']}):")
    for code, n in sorted(snapshot["coverage"]["by_code"].items(), key=lambda kv: -kv[1]):
        print(f"  {code}: {n}")
    print(f"\nChart closure (passed={snapshot['chart_closure']['passed']}, referenced={snapshot['chart_closure']['referenced_chart_count']}, rendered={snapshot['chart_closure']['rendered_chart_count']}):")
    for code, n in sorted(snapshot["chart_closure"]["by_code"].items(), key=lambda kv: -kv[1]):
        print(f"  {code}: {n}")
    print(f"\nChart assets: {len(snapshot['chart_assets'])} rows")
    for asset in snapshot["chart_assets"]:
        print(f"  type={asset['chart_type']:24s} key={(asset['placeholder_key'] or '-'):24s} status={asset['status']:14s} svg={asset['has_svg']} png={asset['has_png']}")
    print(f"\nConstraints summary: {snapshot['constraints_summary']}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "docs/acceptance/2026-05-16-chapter-8-issue-distribution.json"
    main(out)
