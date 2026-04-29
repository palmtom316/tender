from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row


@dataclass(frozen=True)
class BidTemplateBindingRuleRow:
    id: UUID
    template_item_id: UUID
    binding_name: str
    source_type: str
    selection_mode: str
    source_filters: dict[str, Any]
    field_mappings: list[dict[str, Any]]
    field_mapping_mode: str
    output_key: str
    required: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


_COLUMNS = (
    "id, template_item_id, binding_name, source_type, selection_mode, "
    "source_filters, field_mappings, field_mapping_mode, output_key, required, sort_order, created_at, updated_at"
)
_ALIASED_COLUMNS = (
    "r.id, r.template_item_id, r.binding_name, r.source_type, r.selection_mode, "
    "r.source_filters, r.field_mappings, r.field_mapping_mode, r.output_key, r.required, r.sort_order, r.created_at, r.updated_at"
)


def _to_row(row: dict[str, Any]) -> BidTemplateBindingRuleRow:
    return BidTemplateBindingRuleRow(
        id=row["id"],
        template_item_id=row["template_item_id"],
        binding_name=row["binding_name"],
        source_type=row["source_type"],
        selection_mode=row["selection_mode"],
        source_filters=dict(row["source_filters"] or {}),
        field_mappings=list(row["field_mappings"] or []),
        field_mapping_mode=row["field_mapping_mode"],
        output_key=row["output_key"],
        required=row["required"],
        sort_order=row["sort_order"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class BidTemplateBindingRepository:
    def list_by_item(self, conn: Connection, *, template_item_id: UUID) -> list[BidTemplateBindingRuleRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"""
                SELECT {_COLUMNS}
                FROM bid_template_binding_rule
                WHERE template_item_id = %s
                ORDER BY sort_order, created_at
                """,
                (template_item_id,),
            ).fetchall()
        return [_to_row(row) for row in rows]

    def list_by_package(self, conn: Connection, *, package_id: UUID) -> list[BidTemplateBindingRuleRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"""
                SELECT {_ALIASED_COLUMNS}
                FROM bid_template_binding_rule r
                JOIN bid_template_item i ON i.id = r.template_item_id
                WHERE i.package_id = %s
                ORDER BY i.sort_order, r.sort_order, r.created_at
                """,
                (package_id,),
            ).fetchall()
        return [_to_row(row) for row in rows]

    def get(self, conn: Connection, *, rule_id: UUID) -> BidTemplateBindingRuleRow | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"SELECT {_COLUMNS} FROM bid_template_binding_rule WHERE id = %s",
                (rule_id,),
            ).fetchone()
        return _to_row(row) if row else None

    def create(
        self,
        conn: Connection,
        *,
        template_item_id: UUID,
        binding_name: str,
        source_type: str,
        selection_mode: str,
        source_filters: dict[str, Any],
        field_mappings: list[dict[str, Any]],
        field_mapping_mode: str,
        output_key: str,
        required: bool,
        sort_order: int,
    ) -> BidTemplateBindingRuleRow:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                INSERT INTO bid_template_binding_rule (
                  id, template_item_id, binding_name, source_type, selection_mode,
                  source_filters, field_mappings, field_mapping_mode, output_key, required, sort_order
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s)
                RETURNING {_COLUMNS}
                """,
                (
                    uuid4(),
                    template_item_id,
                    binding_name,
                    source_type,
                    selection_mode,
                    json.dumps(source_filters or {}, ensure_ascii=False),
                    json.dumps(field_mappings or [], ensure_ascii=False),
                    field_mapping_mode,
                    output_key,
                    required,
                    sort_order,
                ),
            ).fetchone()
        conn.commit()
        assert row is not None
        return _to_row(row)

    def update(self, conn: Connection, *, rule_id: UUID, **fields: Any) -> BidTemplateBindingRuleRow | None:
        allowed = {
            "binding_name",
            "source_type",
            "selection_mode",
            "source_filters",
            "field_mappings",
            "field_mapping_mode",
            "output_key",
            "required",
            "sort_order",
        }
        sets: list[str] = []
        values: list[Any] = []
        for field in allowed:
            if field not in fields:
                continue
            value = fields[field]
            if field in {"source_filters", "field_mappings"}:
                sets.append(f"{field} = %s::jsonb")
                if field == "source_filters":
                    values.append(json.dumps(value or {}, ensure_ascii=False))
                else:
                    values.append(json.dumps(value or [], ensure_ascii=False))
            else:
                sets.append(f"{field} = %s")
                values.append(value)

        if not sets:
            return self.get(conn, rule_id=rule_id)

        sets.append("updated_at = now()")
        values.append(rule_id)
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                UPDATE bid_template_binding_rule
                SET {", ".join(sets)}
                WHERE id = %s
                RETURNING {_COLUMNS}
                """,
                values,
            ).fetchone()
        conn.commit()
        return _to_row(row) if row else None

    def delete(self, conn: Connection, *, rule_id: UUID) -> bool:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM bid_template_binding_rule WHERE id = %s", (rule_id,))
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted
