"""Deterministic compliance checks for bid readiness."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


CRITICAL_CATEGORIES = {"veto", "qualification", "performance", "project_team", "personnel"}
SIGNATURE_WORDS = ("签章", "盖章", "签字", "CA", "电子签名")
BOND_WORDS = ("保证金", "投标担保", "保函")


class ComplianceCheckService:
    def run(self, conn: Connection, *, project_id: UUID, created_by: str | None = None) -> dict[str, Any]:
        findings = self._build_findings(conn, project_id=project_id)
        severity_counts = {severity: sum(1 for item in findings if item["severity"] == severity) for severity in ["P0", "P1", "P2", "P3"]}
        with conn.cursor(row_factory=dict_row) as cur:
            run = cur.execute(
                """
                INSERT INTO compliance_check_run (id, project_id, status, summary_json, created_by)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    uuid4(),
                    project_id,
                    "blocked" if severity_counts["P0"] else "completed",
                    Jsonb({"severity_counts": severity_counts, "finding_count": len(findings)}),
                    created_by,
                ),
            ).fetchone()
            if run is None:
                raise RuntimeError("failed to create compliance check run")
            persisted: list[dict[str, Any]] = []
            for finding in findings:
                row = cur.execute(
                    """
                    INSERT INTO compliance_check_finding (
                      id, run_id, project_id, severity, rule_code, title, detail, requirement_id, status, metadata_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        uuid4(),
                        run["id"],
                        project_id,
                        finding["severity"],
                        finding["rule_code"],
                        finding["title"],
                        finding.get("detail") or "",
                        finding.get("requirement_id"),
                        "open",
                        Jsonb(finding.get("metadata_json") or {}),
                    ),
                ).fetchone()
                if row:
                    persisted.append(dict(row))
        conn.commit()
        result = dict(run)
        result["findings"] = persisted
        return result

    def latest(self, conn: Connection, *, project_id: UUID) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            run = cur.execute(
                """
                SELECT * FROM compliance_check_run
                WHERE project_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
            if run is None:
                return None
            findings = cur.execute(
                """
                SELECT * FROM compliance_check_finding
                WHERE run_id = %s
                ORDER BY severity, created_at
                """,
                (run["id"],),
            ).fetchall()
        result = dict(run)
        result["findings"] = [dict(row) for row in findings]
        return result

    def update_finding_decision(
        self,
        conn: Connection,
        *,
        finding_id: UUID,
        decision: str,
        actor: str | None = None,
    ) -> dict[str, Any] | None:
        if decision not in {"waived", "closed"}:
            raise ValueError("unsupported compliance finding decision")
        if decision == "waived":
            fields = "status = 'waived', user_decision = 'waived_by_user', waived_by = %s, waived_at = now()"
            params: tuple[Any, ...] = (actor, finding_id)
        else:
            fields = "status = 'closed', user_decision = 'closed_after_remediation', closed_at = now()"
            params = (finding_id,)
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"UPDATE compliance_check_finding SET {fields} WHERE id = %s RETURNING *",
                params,
            ).fetchone()
        conn.commit()
        return dict(row) if row else None

    def blocking_findings(self, conn: Connection, *, project_id: UUID) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT *
                FROM compliance_check_finding
                WHERE project_id = %s
                  AND severity = 'P0'
                  AND status NOT IN ('closed', 'waived')
                ORDER BY created_at
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _build_findings(self, conn: Connection, *, project_id: UUID) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            project = cur.execute("SELECT * FROM project WHERE id = %s", (project_id,)).fetchone()
            requirements = cur.execute(
                """
                SELECT * FROM project_requirement
                WHERE project_id = %s
                  AND COALESCE(is_stale, false) = false
                  AND COALESCE(review_status, 'pending') <> 'rejected'
                ORDER BY created_at
                """,
                (project_id,),
            ).fetchall()
            attachments = cur.execute(
                "SELECT COUNT(*) AS c FROM external_bid_attachment WHERE project_id = %s",
                (project_id,),
            ).fetchone()
        findings: list[dict[str, Any]] = []
        project_dict = dict(project or {})
        if not project_dict.get("submission_deadline"):
            findings.append({"severity": "P1", "rule_code": "missing_submission_deadline", "title": "递交截止时间未维护"})
        if not project_dict.get("bid_validity_period"):
            findings.append({"severity": "P2", "rule_code": "missing_bid_validity", "title": "投标有效期未维护"})
        if not project_dict.get("selected_template_package_id"):
            findings.append({"severity": "P2", "rule_code": "missing_template_selection", "title": "尚未确认模板包"})
        if project_dict.get("submission_target") == "platform_manual_upload" and not project_dict.get("platform_file_rules"):
            findings.append({"severity": "P1", "rule_code": "missing_platform_rules", "title": "平台上传规则未维护"})
        if project_dict.get("procurement_type") in {"batch", "framework"} and not (project_dict.get("section_name") or project_dict.get("lot_name")):
            findings.append({"severity": "P2", "rule_code": "missing_lot_metadata", "title": "批次/框架项目缺少标段或标包信息"})
        if (attachments or {}).get("c", 0) == 0:
            findings.append({"severity": "P3", "rule_code": "no_external_attachment", "title": "尚未挂载外部报价或平台附件"})

        for row in requirements:
            text = " ".join(str(row.get(key) or "") for key in ["title", "requirement_text", "source_text"])
            if (row.get("is_veto") or row.get("category") in CRITICAL_CATEGORIES) and not row.get("human_confirmed"):
                findings.append({
                    "severity": "P0",
                    "rule_code": "unconfirmed_critical_requirement",
                    "title": f"关键条款未确认：{row.get('title')}",
                    "requirement_id": row.get("id"),
                })
            if any(word in text for word in SIGNATURE_WORDS) and not row.get("human_confirmed"):
                findings.append({
                    "severity": "P0",
                    "rule_code": "signature_requirement_unconfirmed",
                    "title": "签章/盖章要求未确认",
                    "requirement_id": row.get("id"),
                })
            if any(word in text for word in BOND_WORDS) and not project_dict.get("bid_bond_deadline"):
                findings.append({
                    "severity": "P1",
                    "rule_code": "bid_bond_deadline_missing",
                    "title": "保证金要求存在但到账截止未维护",
                    "requirement_id": row.get("id"),
                })
        return findings


__all__ = ["ComplianceCheckService"]
