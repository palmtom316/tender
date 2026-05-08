from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row


@dataclass(frozen=True)
class CompanyAssetRow:
    id: UUID
    library_company_id: UUID
    asset_type: str
    name: str
    spec_model: str | None
    serial_no: str | None
    manufacturer: str | None
    quantity: Decimal
    unit: str
    ownership: str
    acquired_at: date | None
    expires_at: date | None
    technical_condition: str | None
    status: str
    location: str | None
    extras: dict[str, Any]
    notes: str | None
    created_at: datetime
    updated_at: datetime


_ASSET_COLUMNS = (
    "id, library_company_id, asset_type, name, spec_model, serial_no, manufacturer, quantity, "
    "unit, ownership, acquired_at, expires_at, technical_condition, status, location, extras, "
    "notes, created_at, updated_at"
)


def _to_company_asset(row: dict[str, Any]) -> CompanyAssetRow:
    return CompanyAssetRow(
        id=row["id"],
        library_company_id=row["library_company_id"],
        asset_type=row["asset_type"],
        name=row["name"],
        spec_model=row["spec_model"],
        serial_no=row["serial_no"],
        manufacturer=row["manufacturer"],
        quantity=row["quantity"],
        unit=row["unit"],
        ownership=row["ownership"],
        acquired_at=row["acquired_at"],
        expires_at=row["expires_at"],
        technical_condition=row["technical_condition"],
        status=row["status"],
        location=row["location"],
        extras=dict(row["extras"] or {}),
        notes=row["notes"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class CompanyAssetRepository:
    def list_assets(
        self,
        conn: Connection,
        *,
        library_company_id: UUID,
        asset_type: str | None = None,
        status: str | None = None,
        q: str | None = None,
    ) -> list[CompanyAssetRow]:
        clauses = ["library_company_id = %s"]
        values: list[Any] = [library_company_id]
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
        where_sql = " AND ".join(clauses)
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"""
                SELECT {_ASSET_COLUMNS}
                FROM company_asset
                WHERE {where_sql}
                ORDER BY asset_type, status, updated_at DESC, created_at DESC
                """,
                values,
            ).fetchall()
        return [_to_company_asset(row) for row in rows]

    def get_asset(self, conn: Connection, record_id: UUID) -> CompanyAssetRow | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"SELECT {_ASSET_COLUMNS} FROM company_asset WHERE id = %s",
                (record_id,),
            ).fetchone()
        return _to_company_asset(row) if row else None

    def create_asset(self, conn: Connection, **fields: Any) -> CompanyAssetRow:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                INSERT INTO company_asset (
                  id, library_company_id, asset_type, name, spec_model, serial_no, manufacturer,
                  quantity, unit, ownership, acquired_at, expires_at, technical_condition, status,
                  location, extras, notes
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                RETURNING {_ASSET_COLUMNS}
                """,
                (
                    uuid4(),
                    fields["library_company_id"],
                    fields["asset_type"],
                    fields["name"],
                    fields.get("spec_model"),
                    fields.get("serial_no"),
                    fields.get("manufacturer"),
                    fields.get("quantity", 1),
                    fields["unit"],
                    fields["ownership"],
                    fields.get("acquired_at"),
                    fields.get("expires_at"),
                    fields.get("technical_condition"),
                    fields.get("status", "active"),
                    fields.get("location"),
                    json.dumps(fields.get("extras") or {}, ensure_ascii=False),
                    fields.get("notes"),
                ),
            ).fetchone()
        conn.commit()
        assert row is not None
        return _to_company_asset(row)

    def update_asset(self, conn: Connection, record_id: UUID, **fields: Any) -> CompanyAssetRow | None:
        return self._update_json_record(
            conn,
            table="company_asset",
            record_id=record_id,
            fields=fields,
            allowed_fields={
                "library_company_id",
                "asset_type",
                "name",
                "spec_model",
                "serial_no",
                "manufacturer",
                "quantity",
                "unit",
                "ownership",
                "acquired_at",
                "expires_at",
                "technical_condition",
                "status",
                "location",
                "extras",
                "notes",
            },
            json_fields={"extras"},
            returning=_ASSET_COLUMNS,
            mapper=_to_company_asset,
        )

    def delete_asset(self, conn: Connection, record_id: UUID) -> bool:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM company_asset WHERE id = %s", (record_id,))
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted

    def retire_asset(self, conn: Connection, record_id: UUID) -> CompanyAssetRow | None:
        return self.update_asset(conn, record_id, status="retired")

    def _update_json_record(
        self,
        conn: Connection,
        *,
        table: str,
        record_id: UUID,
        fields: dict[str, Any],
        allowed_fields: set[str],
        json_fields: set[str],
        returning: str,
        mapper,
    ):
        sets: list[str] = []
        values: list[Any] = []
        for field in allowed_fields:
            if field not in fields:
                continue
            value = fields[field]
            if field in json_fields:
                sets.append(f"{field} = %s::jsonb")
                values.append(json.dumps(value or {}, ensure_ascii=False))
            else:
                sets.append(f"{field} = %s")
                values.append(value)

        if not sets:
            with conn.cursor(row_factory=dict_row) as cur:
                row = cur.execute(
                    f"SELECT {returning} FROM {table} WHERE id = %s",
                    (record_id,),
                ).fetchone()
            return mapper(row) if row else None

        sets.append("updated_at = now()")
        values.append(record_id)

        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                UPDATE {table}
                SET {", ".join(sets)}
                WHERE id = %s
                RETURNING {returning}
                """,
                values,
            ).fetchone()
        conn.commit()
        return mapper(row) if row else None
