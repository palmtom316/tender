from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row


@dataclass(frozen=True)
class ProjectEquipmentSelectionRow:
    id: UUID
    project_id: UUID
    asset_id: UUID
    asset_type: str
    intended_role: str | None
    snapshot_json: dict[str, Any] | None
    display_order: int
    confirmed: bool
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime


_SELECTION_COLUMNS = (
    "id, project_id, asset_id, asset_type, intended_role, snapshot_json, display_order, "
    "confirmed, confirmed_at, created_at, updated_at"
)


def _to_selection(row: dict[str, Any]) -> ProjectEquipmentSelectionRow:
    return ProjectEquipmentSelectionRow(
        id=row["id"],
        project_id=row["project_id"],
        asset_id=row["asset_id"],
        asset_type=row["asset_type"],
        intended_role=row["intended_role"],
        snapshot_json=dict(row["snapshot_json"] or {}) if row["snapshot_json"] is not None else None,
        display_order=row["display_order"],
        confirmed=row["confirmed"],
        confirmed_at=row["confirmed_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class ProjectEquipmentSelectionRepository:
    def list_assets(
        self,
        conn: Connection,
        *,
        asset_type: str | None = None,
        q: str | None = None,
        status: str | None = None,
        valid_only: bool = False,
    ) -> list[dict[str, Any]]:
        clauses = ["1 = 1"]
        values: list[Any] = []
        if asset_type:
            clauses.append("asset_type = %s")
            values.append(asset_type)
        if status:
            clauses.append("status = %s")
            values.append(status)
        if q:
            clauses.append("(name ILIKE %s OR COALESCE(spec_model, '') ILIKE %s OR COALESCE(serial_no, '') ILIKE %s)")
            needle = f"%{q.strip()}%"
            values.extend([needle, needle, needle])
        if valid_only:
            clauses.append("(expires_at IS NULL OR expires_at >= CURRENT_DATE)")
        where_sql = " AND ".join(clauses)
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"""
                SELECT
                  id, library_company_id, asset_type, name, spec_model, serial_no, manufacturer,
                  quantity, unit, ownership, acquired_at, expires_at, technical_condition, status,
                  location, extras, notes, created_at, updated_at
                FROM company_asset
                WHERE {where_sql}
                ORDER BY asset_type, status, updated_at DESC, created_at DESC
                """,
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def list_selections(self, conn: Connection, *, project_id: UUID) -> list[ProjectEquipmentSelectionRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"""
                SELECT {_SELECTION_COLUMNS}
                FROM project_equipment_selection
                WHERE project_id = %s
                ORDER BY asset_type, display_order, created_at
                """,
                (project_id,),
            ).fetchall()
        return [_to_selection(row) for row in rows]

    def create_selection(self, conn: Connection, *, project_id: UUID, asset_id: UUID) -> ProjectEquipmentSelectionRow:
        with conn.cursor(row_factory=dict_row) as cur:
            asset = cur.execute(
                """
                SELECT asset_type
                FROM company_asset
                WHERE id = %s
                """,
                (asset_id,),
            ).fetchone()
            if asset is None:
                raise ValueError("company asset not found")
            existing = cur.execute(
                f"""
                SELECT {_SELECTION_COLUMNS}
                FROM project_equipment_selection
                WHERE project_id = %s AND asset_id = %s
                """,
                (project_id, asset_id),
            ).fetchone()
            if existing is not None:
                return _to_selection(existing)
            order_row = cur.execute(
                "SELECT COALESCE(MAX(display_order), 0) AS max_order FROM project_equipment_selection WHERE project_id = %s AND asset_type = %s",
                (project_id, asset["asset_type"]),
            ).fetchone()
            row = cur.execute(
                f"""
                INSERT INTO project_equipment_selection (
                  id, project_id, asset_id, asset_type, display_order
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (project_id, asset_id) DO UPDATE
                SET updated_at = project_equipment_selection.updated_at
                RETURNING {_SELECTION_COLUMNS}
                """,
                (
                    uuid4(),
                    project_id,
                    asset_id,
                    asset["asset_type"],
                    int(order_row["max_order"] or 0) + 1,
                ),
            ).fetchone()
        conn.commit()
        assert row is not None
        return _to_selection(row)

    def update_selection(self, conn: Connection, record_id: UUID, **fields: Any) -> ProjectEquipmentSelectionRow | None:
        sets: list[str] = []
        values: list[Any] = []
        for key in ("intended_role", "display_order"):
            if key in fields:
                sets.append(f"{key} = %s")
                values.append(fields[key])
        if "snapshot_json" in fields:
            sets.append("snapshot_json = %s::jsonb")
            values.append(json.dumps(fields["snapshot_json"] or {}, ensure_ascii=False))
        if "confirmed" in fields:
            sets.append("confirmed = %s")
            values.append(fields["confirmed"])
        if "confirmed_at" in fields:
            sets.append("confirmed_at = %s")
            values.append(fields["confirmed_at"])
        if not sets:
            return self.get_selection(conn, record_id)
        sets.append("updated_at = now()")
        values.append(record_id)
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                UPDATE project_equipment_selection
                SET {", ".join(sets)}
                WHERE id = %s
                RETURNING {_SELECTION_COLUMNS}
                """,
                values,
            ).fetchone()
        conn.commit()
        return _to_selection(row) if row else None

    def get_selection(self, conn: Connection, record_id: UUID) -> ProjectEquipmentSelectionRow | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"SELECT {_SELECTION_COLUMNS} FROM project_equipment_selection WHERE id = %s",
                (record_id,),
            ).fetchone()
        return _to_selection(row) if row else None

    def delete_selection(self, conn: Connection, record_id: UUID) -> bool:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM project_equipment_selection WHERE id = %s", (record_id,))
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted

    def confirm_project_selections(self, conn: Connection, *, project_id: UUID) -> list[ProjectEquipmentSelectionRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT
                  pes.id AS selection_id,
                  pes.asset_type,
                  ca.id AS asset_id,
                  ca.name,
                  ca.spec_model,
                  ca.serial_no,
                  ca.manufacturer,
                  ca.quantity,
                  ca.unit,
                  ca.ownership,
                  ca.acquired_at,
                  ca.expires_at,
                  ca.technical_condition,
                  ca.status,
                  ca.location,
                  ca.extras,
                  ca.notes
                FROM project_equipment_selection pes
                JOIN company_asset ca ON ca.id = pes.asset_id
                WHERE pes.project_id = %s
                ORDER BY pes.asset_type, pes.display_order, pes.created_at
                """,
                (project_id,),
            ).fetchall()
            selection_ids: list[UUID] = []
            for row in rows:
                snapshot = {
                    "asset_id": str(row["asset_id"]),
                    "asset_type": row["asset_type"],
                    "name": row["name"],
                    "spec_model": row["spec_model"],
                    "serial_no": row["serial_no"],
                    "manufacturer": row["manufacturer"],
                    "quantity": row["quantity"],
                    "unit": row["unit"],
                    "ownership": row["ownership"],
                    "acquired_at": row["acquired_at"].isoformat() if row["acquired_at"] else None,
                    "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
                    "technical_condition": row["technical_condition"],
                    "status": row["status"],
                    "location": row["location"],
                    "extras": dict(row["extras"] or {}),
                    "notes": row["notes"],
                }
                cur.execute(
                    """
                    UPDATE project_equipment_selection
                    SET snapshot_json = %s::jsonb,
                        confirmed = TRUE,
                        confirmed_at = now(),
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (json.dumps(snapshot, ensure_ascii=False, default=str), row["selection_id"]),
                )
                selection_ids.append(row["selection_id"])
            if not selection_ids:
                conn.commit()
                return []
            confirmed_rows = cur.execute(
                f"""
                SELECT {_SELECTION_COLUMNS}
                FROM project_equipment_selection
                WHERE id = ANY(%s)
                ORDER BY asset_type, display_order, created_at
                """,
                (selection_ids,),
            ).fetchall()
        conn.commit()
        return [_to_selection(row) for row in confirmed_rows]
