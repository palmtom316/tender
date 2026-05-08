from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row


_COLUMNS: list[tuple[str, str]] = [
    ("序号", "index"),
    ("姓名", "full_name"),
    ("拟任岗位", "intended_role"),
    ("性别", "gender"),
    ("年龄", "age"),
    ("学历", "education"),
    ("职称", "title"),
    ("专业", "specialty"),
    ("从业年限", "years_experience"),
    ("联系方式", "contact"),
    ("主要证件/附件", "attachments"),
]

_CATEGORY_LABELS = {
    "performance_table": "业绩表",
    "id_card": "身份证",
    "graduation_certificate": "毕业证",
    "title_certificate": "职称证",
    "practice_certificate": "执业资格证",
    "safety_certificate": "安全生产合格证",
    "special_operation_certificate": "特种作业操作证",
    "social_security_proof": "社保参保证明",
    "labor_contract": "劳动合同书",
}


class PersonnelTableRenderer:
    def render_personnel_preview(self, conn: Connection, *, project_id: UUID) -> list[dict[str, str]]:
        rows = self._load_confirmed(conn, project_id=project_id)
        return [self._row_to_preview_row(index + 1, row) for index, row in enumerate(rows)]

    def _load_confirmed(self, conn: Connection, *, project_id: UUID) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT intended_role, snapshot_json, display_order, created_at
                FROM project_personnel_selection
                WHERE project_id = %s AND confirmed = TRUE
                ORDER BY display_order, created_at
                """,
                (project_id,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            snapshot = dict(row["snapshot_json"] or {})
            if row["intended_role"]:
                snapshot["intended_role"] = row["intended_role"]
            result.append(snapshot)
        return result

    def _row_to_preview_row(self, index: int, row: dict[str, Any]) -> dict[str, str]:
        return {label: self._resolve_value(index, row, source) for label, source in _COLUMNS}

    def _resolve_value(self, index: int, row: dict[str, Any], source: str) -> str:
        if source == "index":
            return str(index)
        if source == "contact":
            return str(row.get("phone") or row.get("email") or "—")
        if source == "years_experience":
            value = row.get("years_experience")
            return f"{value}年" if value not in (None, "") else "—"
        if source == "attachments":
            attachments = row.get("attachments")
            if not isinstance(attachments, list) or not attachments:
                return "—"
            labels: list[str] = []
            for asset in attachments:
                if not isinstance(asset, dict):
                    continue
                category = str(asset.get("asset_category") or "")
                label = _CATEGORY_LABELS.get(category, category or "附件")
                expires_on = asset.get("expires_on")
                cert_no = dict(asset.get("metadata_json") or {}).get("cert_no")
                detail = label
                if cert_no:
                    detail += f"({cert_no})"
                if expires_on:
                    detail += f" 有效期至{expires_on}"
                labels.append(detail)
            return "；".join(labels) if labels else "—"
        value = row.get(source)
        return str(value) if value not in (None, "") else "—"
