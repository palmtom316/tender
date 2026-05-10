"""Shared export gate evaluation for API exports and delivery packages."""

from __future__ import annotations

import re
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from tender_backend.db.repositories.chart_asset_repo import ChartAssetRepository
from tender_backend.db.repositories.requirement_repo import RequirementRepository
from tender_backend.services.review_service.review_engine import get_blocking_issues
from tender_backend.services.tender_constraint_service import TenderConstraintService

_CHART_PLACEHOLDER_RE = re.compile(r"\{\{chart:([A-Za-z][A-Za-z0-9_.:-]{0,127})\}\}")


def _referenced_chart_placeholders(conn: Connection, *, project_id: UUID) -> set[str]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT content_md, referenced_chart_keys
            FROM chapter_draft
            WHERE project_id = %s
            """,
            (project_id,),
        ).fetchall()
    placeholders: set[str] = set()
    for row in rows:
        persisted = row.get("referenced_chart_keys") or []
        if persisted:
            placeholders.update(str(key) for key in persisted if key)
        else:
            placeholders.update(_CHART_PLACEHOLDER_RE.findall(str(row.get("content_md") or "")))
    return placeholders


def _unapproved_referenced_chart_count(chart_assets: list, referenced_placeholders: set[str]) -> int:
    if not referenced_placeholders:
        return 0
    count = 0
    for asset in chart_assets:
        key = asset.placeholder_key or asset.chart_type
        if key in referenced_placeholders and asset.status != "approved":
            count += 1
    return count


def _format_gate_state() -> dict[str, str | bool]:
    return {
        "format_passed": False,
        "format_status": "warning_not_checked",
        "format_message": "格式校验尚未接入自动检查，导出前需人工复核。",
    }


def _is_legacy_pre_constraint_project(conn: Connection, *, project_id: UUID) -> bool:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute("SELECT metadata_json FROM project WHERE id = %s", (project_id,)).fetchone()
    metadata = dict((row or {}).get("metadata_json") or {})
    return bool(metadata.get("legacy_pre_constraint_set"))


def build_export_gate_state(conn: Connection, *, project_id: UUID) -> dict:
    req_repo = RequirementRepository()
    unconfirmed_veto = req_repo.unconfirmed_veto_count(conn, project_id=project_id)
    blocking_issues = get_blocking_issues(conn, project_id=project_id)
    chart_assets = ChartAssetRepository().list_by_project(conn, project_id=project_id)
    referenced_chart_placeholders = _referenced_chart_placeholders(conn, project_id=project_id)
    unapproved_chart_count = _unapproved_referenced_chart_count(chart_assets, referenced_chart_placeholders)
    format_gate = _format_gate_state()
    constraint_set = TenderConstraintService().latest_confirmed(conn, project_id=project_id)
    legacy_project = _is_legacy_pre_constraint_project(conn, project_id=project_id)
    constraints_confirmed = constraint_set is not None or legacy_project

    gates = {
        "veto_confirmed": unconfirmed_veto == 0,
        "unconfirmed_veto_count": unconfirmed_veto,
        "review_passed": len(blocking_issues) == 0,
        "blocking_issue_count": len(blocking_issues),
        "charts_approved": unapproved_chart_count == 0,
        "unapproved_chart_count": unapproved_chart_count,
        "referenced_chart_count": len(referenced_chart_placeholders),
        "constraints_confirmed": constraints_confirmed,
        "legacy_pre_constraint_set": legacy_project,
        **format_gate,
    }
    return {
        "project_id": str(project_id),
        "gates": gates,
        "can_export": (
            gates["veto_confirmed"]
            and gates["review_passed"]
            and gates["charts_approved"]
            and gates["constraints_confirmed"]
        ),
    }

