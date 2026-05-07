"""Tender requirement priority helpers.

Tender document extraction is the authoritative source for bid content and
format constraints. Template defaults are only fallbacks.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row


CONTENT_CATEGORIES = {
    "project_info",
    "schedule",
    "qualification",
    "performance",
    "project_team",
    "technical",
    "business",
    "scoring",
    "veto",
    "contract",
    "special",
}
FORMAT_CATEGORIES = {"format"}
PRIORITY_POLICY = "tender_extracted_requirements_override_template"


def load_tender_requirement_overrides(conn: Connection, *, project_id: UUID) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT *
            FROM project_requirement
            WHERE project_id = %s
              AND COALESCE(ignored_for_pricing, false) = false
              AND COALESCE(is_stale, false) = false
              AND COALESCE(review_status, 'pending') <> 'rejected'
            ORDER BY category, created_at
            """,
            (project_id,),
        ).fetchall()

    requirements = [dict(row) for row in rows]
    content_requirements = [
        row for row in requirements
        if row.get("category") in CONTENT_CATEGORIES
    ]
    format_requirements = [
        row for row in requirements
        if row.get("category") in FORMAT_CATEGORIES
    ]
    return {
        "priority_policy": PRIORITY_POLICY,
        "content_requirements": content_requirements,
        "format_requirements": format_requirements,
        "all_requirements": requirements,
        "summary": {
            "content_requirement_count": len(content_requirements),
            "format_requirement_count": len(format_requirements),
            "total_requirement_count": len(requirements),
        },
    }


def apply_tender_requirement_context(context: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(context)
    merged["tender_requirements"] = overrides["all_requirements"]
    merged["tender_content_requirements"] = overrides["content_requirements"]
    merged["tender_format_requirements"] = overrides["format_requirements"]
    merged["tender_requirement_priority"] = {
        "policy": PRIORITY_POLICY,
        "description": "招标文件 AI 解析出的内容与格式要求优先于模板默认内容；如有冲突，按解析结果覆盖或修订模板输出。",
        **overrides["summary"],
    }
    return merged
