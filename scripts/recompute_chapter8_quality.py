"""Recompute chapter_draft coverage + chart_closure with the new code logic."""

from __future__ import annotations

import json
import os
import sys
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

sys.path.insert(0, "backend")

from tender_backend.services.longform_quality import (  # noqa: E402
    build_chart_closure_report,
    build_coverage_report,
)
from tender_backend.services.longform_section_generation import plan_chapter_8_sections  # noqa: E402


PROJECT_ID = "d3ed99c0-1d79-4fad-bd4b-6a77a08cc530"
DRAFT_ID = "0e5514d1-eab6-44ad-ba9b-e23d96761179"


def main(commit: bool) -> None:
    dsn = os.environ.get("DATABASE_URL") or "postgresql://tender:change-me@127.0.0.1:5432/tender"
    with psycopg.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                SELECT content_md, target_pages, chapter_code
                FROM chapter_draft WHERE id = %s
                """,
                (DRAFT_ID,),
            ).fetchone()
            if not row:
                print("DRAFT_NOT_FOUND")
                sys.exit(2)

            section_plan = plan_chapter_8_sections(target_pages=int(row["target_pages"] or 100))
            print(f"Re-planning {len(section_plan)} sections with new weights:")
            for s in section_plan[:5]:
                print(f"  {s['section_code']} pages={s['target_pages']} min_chars={s['min_chars']} tables={s['required_tables']}")
            print(f"  ... (total pages = {sum(s['target_pages'] for s in section_plan)})")

            # Pull current chart_assets including rendered_* columns (mirrors A0 fix).
            cur.execute(
                """
                SELECT id, chart_type, placeholder_key, title, status, metadata_json,
                       rendered_svg, rendered_path, rendered_png_path
                FROM chart_asset
                WHERE project_id = %s
                ORDER BY chart_type, created_at DESC
                """,
                (PROJECT_ID,),
            )
            chart_assets = [dict(r) for r in cur.fetchall()]

            # Constraints: same shape as TechnicalChapterContextBuilder feeds.
            cur.execute(
                """
                SELECT id, confirmation_level, status, metadata_json
                FROM tender_constraint_item
                WHERE constraint_set_id IN (
                    SELECT id FROM tender_constraint_set WHERE project_id = %s ORDER BY updated_at DESC LIMIT 1
                )
                """,
                (PROJECT_ID,),
            )
            constraints = [dict(r) for r in cur.fetchall()]
            for c in constraints:
                if isinstance(c["metadata_json"], str):
                    c["metadata_json"] = json.loads(c["metadata_json"])

            coverage = build_coverage_report(
                row["content_md"],
                checklist=section_plan,
                constraints=constraints,
                equipment_data={"vehicle": [], "machine": [], "tool": [], "safety": []},
                personnel_data=[],
                chapter_code=str(row["chapter_code"] or "8"),
            )

            chart_closure = build_chart_closure_report(
                row["content_md"],
                chart_assets=chart_assets,
            )

            print("\n=== NEW coverage report ===")
            print(f"passed: {coverage['coverage_passed']}")
            print(f"issue_count: {coverage['issue_count']}")
            bucket: dict = {}
            for issue in coverage["issues"]:
                bucket.setdefault(issue.get("code"), []).append(issue)
            for code, items in sorted(bucket.items(), key=lambda kv: -len(kv[1])):
                print(f"  {code}: {len(items)}")
                for it in items[:3]:
                    print(f"      {json.dumps(it, ensure_ascii=False)}")

            print("\n=== NEW chart_closure report ===")
            print(f"passed: {chart_closure['chart_closure_passed']}")
            print(f"referenced: {chart_closure['referenced_chart_count']}, rendered: {chart_closure['rendered_chart_count']}, approved: {chart_closure['approved_chart_count']}")
            for issue in chart_closure["issues"]:
                print(f"  {json.dumps(issue, ensure_ascii=False)}")

            if commit:
                cur.execute(
                    """
                    UPDATE chapter_draft
                    SET coverage_report_json = %s,
                        chart_closure_report_json = %s,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (Jsonb(coverage), Jsonb(chart_closure), DRAFT_ID),
                )
                conn.commit()
                print("\nCOMMITTED to DB")
            else:
                print("\nDRY RUN; pass --commit to write back")


if __name__ == "__main__":
    main(commit="--commit" in sys.argv)
