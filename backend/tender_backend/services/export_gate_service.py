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


def _project_metadata(conn: Connection, *, project_id: UUID) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute("SELECT metadata_json FROM project WHERE id = %s", (project_id,)).fetchone()
    return dict((row or {}).get("metadata_json") or {})


def _template_render_gate(metadata: dict) -> dict[str, int | bool | list]:
    status = metadata.get("template_render_status") if isinstance(metadata, dict) else None
    status = status if isinstance(status, dict) else {}
    required_failed_count = int(status.get("required_failed_count") or 0)
    return {
        "template_required_items_rendered": required_failed_count == 0,
        "required_template_failed_count": required_failed_count,
        "failed_required_template_items": list(status.get("failed_required_items") or []),
    }


def _stale_artifact_count(conn: Connection, *, project_id: UUID) -> int:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """
            SELECT (
              (SELECT COUNT(*) FROM bid_outline WHERE project_id = %s AND COALESCE(is_stale, false) = true)
              + (SELECT COUNT(*) FROM bid_chapter WHERE project_id = %s AND COALESCE(is_stale, false) = true)
              + (SELECT COUNT(*) FROM chapter_draft WHERE project_id = %s AND COALESCE(is_stale, false) = true)
            ) AS count
            """,
            (project_id, project_id, project_id),
        ).fetchone()
    return int((row or {}).get("count") or 0)


def _unresolved_critical_constraint_count(constraint_set: dict | None) -> int:
    if not constraint_set:
        return 0
    count = 0
    for item in constraint_set.get("items") or []:
        metadata = item.get("metadata_json") or {}
        status = item.get("status")
        critical = item.get("confirmation_level") == "critical" or bool(metadata.get("has_conflict"))
        if critical and status not in {"accepted", "confirmed"}:
            count += 1
    return count


def build_export_gate_state(conn: Connection, *, project_id: UUID) -> dict:
    req_repo = RequirementRepository()
    unconfirmed_veto = req_repo.unconfirmed_veto_count(conn, project_id=project_id)
    blocking_issues = get_blocking_issues(conn, project_id=project_id)
    chart_assets = ChartAssetRepository().list_by_project(conn, project_id=project_id)
    referenced_chart_placeholders = _referenced_chart_placeholders(conn, project_id=project_id)
    unapproved_chart_count = _unapproved_referenced_chart_count(chart_assets, referenced_chart_placeholders)
    format_gate = _format_gate_state()
    constraint_service = TenderConstraintService()
    constraint_set = constraint_service.latest_confirmed(conn, project_id=project_id)
    latest_constraint_set = constraint_service.latest(conn, project_id=project_id) if hasattr(constraint_service, "latest") else constraint_set
    project_metadata = _project_metadata(conn, project_id=project_id)
    legacy_project = bool(project_metadata.get("legacy_pre_constraint_set"))
    constraints_confirmed = constraint_set is not None or legacy_project
    template_gate = _template_render_gate(project_metadata)
    stale_artifact_count = _stale_artifact_count(conn, project_id=project_id)
    unresolved_critical_constraint_count = _unresolved_critical_constraint_count(latest_constraint_set)

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
        "critical_constraints_resolved": unresolved_critical_constraint_count == 0,
        "unresolved_critical_constraint_count": unresolved_critical_constraint_count,
        "stale_artifacts_clear": stale_artifact_count == 0,
        "stale_artifact_count": stale_artifact_count,
        **template_gate,
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
            and gates["critical_constraints_resolved"]
            and gates["template_required_items_rendered"]
            and gates["stale_artifacts_clear"]
        ),
    }
