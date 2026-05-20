"""Shared export gate evaluation for API exports and delivery packages."""

from __future__ import annotations

import re
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from tender_backend.db.repositories.chart_asset_repo import ChartAssetRepository
from tender_backend.db.repositories.requirement_repo import RequirementRepository
from tender_backend.services.longform_quality import build_page_gate
from tender_backend.services.review_service.review_engine import get_blocking_issues
from tender_backend.services.ad_hoc_chapter_task_card import BLOCKING_STATUSES
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


def _format_gate_state(conn: Connection | None = None, *, project_id: UUID | None = None) -> dict[str, str | bool | int | list]:
    if conn is None or project_id is None:
        return {
            "format_passed": False,
            "format_status": "warning_not_checked",
            "format_message": "格式校验尚未接入自动检查，导出前需人工复核。",
            "format_issue_count": 0,
            "format_issues": [],
        }
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """
            SELECT metadata_json
            FROM export_record
            WHERE project_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
    metadata = dict((row or {}).get("metadata_json") or {})
    render_evidence = metadata.get("render_evidence") if isinstance(metadata.get("render_evidence"), dict) else {}
    format_check = render_evidence.get("format_check") if isinstance(render_evidence.get("format_check"), dict) else {}
    if not format_check:
        return {
            "format_passed": False,
            "format_status": "warning_not_checked",
            "format_message": "格式校验尚未接入自动检查，导出前需人工复核。",
            "format_issue_count": 0,
            "format_issues": [],
        }
    issues = list(format_check.get("issues") or [])
    return {
        "format_passed": bool(format_check.get("format_passed")),
        "format_status": str(format_check.get("format_status") or "unchecked"),
        "format_message": str(format_check.get("format_message") or ""),
        "format_issue_count": len(issues),
        "format_issues": issues[:20],
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


def _stale_template_artifact_count(conn: Connection, *, project_id: UUID) -> int:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """
            SELECT (
              (SELECT COUNT(*) FROM chapter_draft WHERE project_id = %s AND COALESCE(is_stale_by_template, false) = true)
              + (SELECT COUNT(*) FROM chart_asset WHERE project_id = %s AND COALESCE(is_stale_by_template, false) = true)
            ) AS stale_template_artifact_count
            """,
            (project_id, project_id),
        ).fetchone()
    return int((row or {}).get("stale_template_artifact_count") or 0)


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



def _draft_quality_evidence(conn: Connection, *, project_id: UUID) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT chapter_code, target_pages, estimated_pages, page_estimate_json,
                   coverage_report_json, chart_closure_report_json
            FROM chapter_draft
            WHERE project_id = %s
            """,
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _ad_hoc_task_card_gate(conn: Connection, *, project_id: UUID) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT
              bc.chapter_code,
              bc.chapter_title,
              bc.metadata_json,
              cd.id AS draft_id,
              cd.coverage_report_json
            FROM bid_chapter bc
            LEFT JOIN chapter_draft cd
              ON cd.project_id = bc.project_id
             AND cd.volume_type = bc.volume_type
             AND cd.chapter_code = bc.chapter_code
            WHERE bc.project_id = %s
              AND (
                bc.metadata_json ? 'ad_hoc_task_card'
                OR COALESCE((bc.metadata_json ->> 'ad_hoc_required')::boolean, false) = true
                OR bc.metadata_json ->> 'template_match_status' = 'missing'
              )
            """,
            (project_id,),
        ).fetchall()
    issues = []
    for row in rows:
        metadata = row.get("metadata_json") or {}
        card = metadata.get("ad_hoc_task_card") or {}
        status = str(card.get("status") or "")
        coverage = row.get("coverage_report_json") or {}
        ready = status == "draft_ready" and bool(row.get("draft_id")) and bool(coverage.get("coverage_passed"))
        if ready:
            continue
        if status in BLOCKING_STATUSES or status != "draft_ready" or not row.get("draft_id") or not coverage.get("coverage_passed"):
            issues.append(
                {
                    "chapter_code": row.get("chapter_code"),
                    "chapter_title": row.get("chapter_title"),
                    "message": "新增章节任务卡未完成",
                    "hint": "请先补充信息、确认大纲并生成正文。",
                }
            )
    return {
        "ad_hoc_task_cards_ready": not issues,
        "ad_hoc_task_card_issue_count": len(issues),
        "ad_hoc_task_card_issues": issues,
    }


def _longform_quality_gates(drafts: list[dict]) -> dict:
    page_gates = []
    coverage_issues = []
    chart_issues = []
    for row in drafts:
        page_estimate_json = row.get("page_estimate_json") or {}
        if row.get("target_pages"):
            actual_status = page_estimate_json.get("actual_status") or page_estimate_json.get("status") or "unchecked"
            page_gates.append(
                build_page_gate(
                    target_pages=int(row.get("target_pages")),
                    estimated_pages=row.get("estimated_pages"),
                    actual_pages=page_estimate_json.get("actual_pages"),
                    actual_status=str(actual_status),
                )
            )
        coverage = row.get("coverage_report_json") or {}
        chart = row.get("chart_closure_report_json") or {}
        coverage_issues.extend(coverage.get("issues") or [])
        chart_issues.extend(chart.get("issues") or [])

    failed_page_gate = next((gate for gate in page_gates if not gate.get("page_count_passed")), None)
    page_passed = failed_page_gate is None
    return {
        "page_count_passed": page_passed,
        "page_count_status": "passed" if page_passed else failed_page_gate.get("page_count_status", "failed"),
        "page_count_evidence": page_gates,
        "coverage_passed": not any(issue.get("severity") == "P0" for issue in coverage_issues),
        "coverage_issue_count": len(coverage_issues),
        "coverage_issues": coverage_issues[:20],
        "chart_closure_passed": not any(issue.get("severity") == "P0" for issue in chart_issues),
        "chart_closure_issue_count": len(chart_issues),
        "chart_closure_issues": chart_issues[:20],
    }


def build_export_gate_state(conn: Connection, *, project_id: UUID) -> dict:
    req_repo = RequirementRepository()
    unconfirmed_veto = req_repo.unconfirmed_veto_count(conn, project_id=project_id)
    blocking_issues = get_blocking_issues(conn, project_id=project_id)
    chart_assets = ChartAssetRepository().list_by_project(conn, project_id=project_id)
    referenced_chart_placeholders = _referenced_chart_placeholders(conn, project_id=project_id)
    unapproved_chart_count = _unapproved_referenced_chart_count(chart_assets, referenced_chart_placeholders)
    format_gate = _format_gate_state(conn, project_id=project_id)
    constraint_service = TenderConstraintService()
    constraint_set = constraint_service.latest_confirmed(conn, project_id=project_id)
    latest_constraint_set = constraint_service.latest(conn, project_id=project_id) if hasattr(constraint_service, "latest") else constraint_set
    project_metadata = _project_metadata(conn, project_id=project_id)
    legacy_project = bool(project_metadata.get("legacy_pre_constraint_set"))
    constraints_confirmed = constraint_set is not None or legacy_project
    template_gate = _template_render_gate(project_metadata)
    stale_artifact_count = _stale_artifact_count(conn, project_id=project_id)
    stale_template_artifact_count = _stale_template_artifact_count(conn, project_id=project_id)
    unresolved_critical_constraint_count = _unresolved_critical_constraint_count(latest_constraint_set)
    quality_gates = _longform_quality_gates(_draft_quality_evidence(conn, project_id=project_id))
    ad_hoc_gate = _ad_hoc_task_card_gate(conn, project_id=project_id)

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
        "template_stale_artifacts_clear": stale_template_artifact_count == 0,
        "stale_template_artifact_count": stale_template_artifact_count,
        **template_gate,
        **quality_gates,
        **ad_hoc_gate,
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
            and gates["template_stale_artifacts_clear"]
            and gates["page_count_passed"]
            and gates["coverage_passed"]
            and gates["chart_closure_passed"]
            and gates["ad_hoc_task_cards_ready"]
        ),
    }
