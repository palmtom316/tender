from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from tender_backend.core.security import CurrentUser, Role


@dataclass(frozen=True)
class Project:
    id: UUID
    name: str
    created_at: datetime | None = None
    status: str | None = None
    tender_no: str | None = None
    project_type: str | None = None
    industry: str | None = None
    business_line: str | None = None
    sub_type: str | None = None
    employer_name: str | None = None
    employer_type: str | None = None
    evaluation_method: str | None = None
    evaluation_detail: dict[str, Any] | None = None
    qualification_review_type: str | None = None
    submission_deadline: datetime | None = None
    bid_opening_time: datetime | None = None
    bid_validity_period: int | None = None
    bid_bond_amount: str | None = None
    bid_bond_form: str | None = None
    bid_bond_deadline: datetime | None = None
    voltage_level: list[str] | None = None
    project_scope: list[str] | None = None
    tender_platform: str | None = None
    submission_target: str | None = None
    procurement_type: str | None = None
    section_name: str | None = None
    lot_name: str | None = None
    selected_template_package_id: UUID | None = None
    workflow_status: str | None = None


PROJECT_COLUMNS = """
id, name, created_at,
COALESCE(status, workflow_status, 'created') AS status,
tender_no, project_type, industry, business_line, sub_type, employer_name, employer_type,
evaluation_method, evaluation_detail, qualification_review_type, submission_deadline,
bid_opening_time, bid_validity_period, bid_bond_amount, bid_bond_form, bid_bond_deadline,
voltage_level, project_scope, tender_platform, submission_target, procurement_type,
section_name, lot_name, selected_template_package_id, workflow_status
"""

PROJECT_COLUMNS_P = """
p.id, p.name, p.created_at,
COALESCE(p.status, p.workflow_status, 'created') AS status,
p.tender_no, p.project_type, p.industry, p.business_line, p.sub_type, p.employer_name, p.employer_type,
p.evaluation_method, p.evaluation_detail, p.qualification_review_type, p.submission_deadline,
p.bid_opening_time, p.bid_validity_period, p.bid_bond_amount, p.bid_bond_form, p.bid_bond_deadline,
p.voltage_level, p.project_scope, p.tender_platform, p.submission_target, p.procurement_type,
p.section_name, p.lot_name, p.selected_template_package_id, p.workflow_status
"""


def _to_project(row: dict) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        created_at=row.get("created_at"),
        status=row.get("status"),
        tender_no=row.get("tender_no"),
        project_type=row.get("project_type"),
        industry=row.get("industry"),
        business_line=row.get("business_line"),
        sub_type=row.get("sub_type"),
        employer_name=row.get("employer_name"),
        employer_type=row.get("employer_type"),
        evaluation_method=row.get("evaluation_method"),
        evaluation_detail=dict(row.get("evaluation_detail") or {}),
        qualification_review_type=row.get("qualification_review_type"),
        submission_deadline=row.get("submission_deadline"),
        bid_opening_time=row.get("bid_opening_time"),
        bid_validity_period=row.get("bid_validity_period"),
        bid_bond_amount=row.get("bid_bond_amount"),
        bid_bond_form=row.get("bid_bond_form"),
        bid_bond_deadline=row.get("bid_bond_deadline"),
        voltage_level=list(row.get("voltage_level") or []),
        project_scope=list(row.get("project_scope") or []),
        tender_platform=row.get("tender_platform"),
        submission_target=row.get("submission_target"),
        procurement_type=row.get("procurement_type"),
        section_name=row.get("section_name"),
        lot_name=row.get("lot_name"),
        selected_template_package_id=row.get("selected_template_package_id"),
        workflow_status=row.get("workflow_status"),
    )


class ProjectRepository:
    def create(self, conn: Connection, *, name: str) -> Project:
        project_id = uuid4()
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"INSERT INTO project (id, name) VALUES (%s, %s) RETURNING {PROJECT_COLUMNS}",
                (project_id, name),
            ).fetchone()
        conn.commit()
        assert row is not None
        return _to_project(dict(row))

    def create_for_user(self, conn: Connection, *, name: str, user_id: UUID | None, metadata: dict[str, Any] | None = None) -> Project:
        project_id = uuid4()
        metadata = metadata or {}
        allowed = {
            "tender_no", "project_type", "industry", "business_line", "sub_type", "employer_name", "employer_type",
            "evaluation_method", "evaluation_detail", "qualification_review_type", "submission_deadline", "bid_opening_time",
            "bid_validity_period", "bid_bond_amount", "bid_bond_form", "bid_bond_deadline", "voltage_level", "project_scope",
            "is_live_work_required", "controlled_price", "is_subcontract_allowed", "is_consortium_allowed", "tender_platform",
            "submission_target", "platform_file_rules", "procurement_type", "parent_project_id", "section_name", "lot_name",
            "selected_template_package_id", "workflow_status",
        }
        values = {key: value for key, value in metadata.items() if key in allowed and value is not None}
        values.setdefault("workflow_status", "created")
        columns = ["id", "name", *values.keys()]
        params = [project_id, name]
        for key, value in values.items():
            params.append(Jsonb(value) if key in {"evaluation_detail", "platform_file_rules"} else value)
        placeholders = ", ".join(["%s"] * len(columns))
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"INSERT INTO project ({', '.join(columns)}) VALUES ({placeholders}) RETURNING {PROJECT_COLUMNS}",
                params,
            ).fetchone()
            if user_id is not None:
                cur.execute(
                    "INSERT INTO project_member (project_id, user_id, role) VALUES (%s, %s, %s) "
                    "ON CONFLICT (project_id, user_id) DO NOTHING",
                    (project_id, user_id, "owner"),
                )
        conn.commit()
        assert row is not None
        return _to_project(dict(row))

    def list(self, conn: Connection) -> list[Project]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(f"SELECT {PROJECT_COLUMNS} FROM project ORDER BY created_at DESC").fetchall()
        return [_to_project(dict(r)) for r in rows]

    def list_for_user(self, conn: Connection, *, user: CurrentUser) -> list[Project]:
        if user.role == Role.ADMIN:
            return self.list(conn)
        if user.user_id is None:
            return []
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"SELECT {PROJECT_COLUMNS_P} "
                "FROM project p "
                "JOIN project_member pm ON pm.project_id = p.id "
                "WHERE pm.user_id = %s "
                "ORDER BY p.created_at DESC",
                (user.user_id,),
            ).fetchall()
        return [_to_project(dict(r)) for r in rows]

    def update(self, conn: Connection, *, project_id: UUID, fields: dict[str, Any]) -> Project | None:
        allowed = {
            "name", "tender_no", "project_type", "industry", "business_line", "sub_type", "employer_name", "employer_type",
            "evaluation_method", "evaluation_detail", "qualification_review_type", "submission_deadline", "bid_opening_time",
            "bid_validity_period", "bid_bond_amount", "bid_bond_form", "bid_bond_deadline", "voltage_level", "project_scope",
            "is_live_work_required", "controlled_price", "is_subcontract_allowed", "is_consortium_allowed", "tender_platform",
            "submission_target", "platform_file_rules", "procurement_type", "parent_project_id", "section_name", "lot_name",
            "selected_template_package_id", "workflow_status", "status",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return self.get(conn, project_id=project_id)
        sets: list[str] = []
        values: list[Any] = []
        for key, value in updates.items():
            sets.append(f"{key} = %s")
            values.append(Jsonb(value) if key in {"evaluation_detail", "platform_file_rules"} else value)
        values.append(project_id)
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"UPDATE project SET {', '.join(sets)} WHERE id = %s RETURNING {PROJECT_COLUMNS}",
                values,
            ).fetchone()
        conn.commit()
        return _to_project(dict(row)) if row else None

    def get(self, conn: Connection, *, project_id: UUID) -> Project | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(f"SELECT {PROJECT_COLUMNS} FROM project WHERE id = %s", (project_id,)).fetchone()
        return _to_project(dict(row)) if row else None

    def delete(self, conn: Connection, *, project_id: UUID) -> bool:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                "DELETE FROM project WHERE id = %s RETURNING id",
                (project_id,),
            ).fetchone()
        conn.commit()
        return row is not None
