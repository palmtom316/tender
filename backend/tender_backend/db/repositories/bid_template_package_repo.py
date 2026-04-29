from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row


@dataclass(frozen=True)
class BidTemplatePackageRow:
    id: UUID
    package_key: str
    display_name: str
    package_type: str
    source_root: str
    source_manifest: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class BidTemplateItemRow:
    id: UUID
    package_id: UUID
    item_code: str | None
    item_name: str
    filename: str
    relative_path: str
    source_kind: str
    item_type: str
    render_mode: str
    is_required: bool
    sort_order: int
    created_at: datetime


@dataclass(frozen=True)
class BidTemplateItemCreate:
    item_code: str | None
    item_name: str
    filename: str
    relative_path: str
    source_kind: str
    item_type: str
    render_mode: str
    is_required: bool
    sort_order: int


_PACKAGE_COLUMNS = (
    "id, package_key, display_name, package_type, source_root, "
    "source_manifest, created_at, updated_at"
)
_ITEM_COLUMNS = (
    "id, package_id, item_code, item_name, filename, relative_path, source_kind, "
    "item_type, render_mode, is_required, sort_order, created_at"
)


def _to_package(row: dict[str, Any]) -> BidTemplatePackageRow:
    return BidTemplatePackageRow(
        id=row["id"],
        package_key=row["package_key"],
        display_name=row["display_name"],
        package_type=row["package_type"],
        source_root=row["source_root"],
        source_manifest=dict(row["source_manifest"] or {}),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_item(row: dict[str, Any]) -> BidTemplateItemRow:
    return BidTemplateItemRow(
        id=row["id"],
        package_id=row["package_id"],
        item_code=row["item_code"],
        item_name=row["item_name"],
        filename=row["filename"],
        relative_path=row["relative_path"],
        source_kind=row["source_kind"],
        item_type=row["item_type"],
        render_mode=row["render_mode"],
        is_required=row["is_required"],
        sort_order=row["sort_order"],
        created_at=row["created_at"],
    )


class BidTemplatePackageRepository:
    def list_all(self, conn: Connection) -> list[BidTemplatePackageRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"SELECT {_PACKAGE_COLUMNS} FROM bid_template_package ORDER BY display_name"
            ).fetchall()
        return [_to_package(row) for row in rows]

    def get_by_id(self, conn: Connection, *, package_id: UUID) -> BidTemplatePackageRow | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"SELECT {_PACKAGE_COLUMNS} FROM bid_template_package WHERE id = %s",
                (package_id,),
            ).fetchone()
        return _to_package(row) if row else None

    def get_by_key(self, conn: Connection, *, package_key: str) -> BidTemplatePackageRow | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"SELECT {_PACKAGE_COLUMNS} FROM bid_template_package WHERE package_key = %s",
                (package_key,),
            ).fetchone()
        return _to_package(row) if row else None

    def list_items(self, conn: Connection, *, package_id: UUID) -> list[BidTemplateItemRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"""
                SELECT {_ITEM_COLUMNS}
                FROM bid_template_item
                WHERE package_id = %s
                ORDER BY sort_order, filename
                """,
                (package_id,),
            ).fetchall()
        return [_to_item(row) for row in rows]

    def get_item_by_id(self, conn: Connection, *, item_id: UUID) -> BidTemplateItemRow | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"SELECT {_ITEM_COLUMNS} FROM bid_template_item WHERE id = %s",
                (item_id,),
            ).fetchone()
        return _to_item(row) if row else None

    def upsert_package(
        self,
        conn: Connection,
        *,
        package_key: str,
        display_name: str,
        package_type: str,
        source_root: str,
        source_manifest: dict[str, Any],
    ) -> BidTemplatePackageRow:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                INSERT INTO bid_template_package (
                  id, package_key, display_name, package_type, source_root, source_manifest
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (package_key)
                DO UPDATE SET
                  display_name = EXCLUDED.display_name,
                  package_type = EXCLUDED.package_type,
                  source_root = EXCLUDED.source_root,
                  source_manifest = EXCLUDED.source_manifest,
                  updated_at = now()
                RETURNING {_PACKAGE_COLUMNS}
                """,
                (
                    uuid4(),
                    package_key,
                    display_name,
                    package_type,
                    source_root,
                    json.dumps(source_manifest, ensure_ascii=False),
                ),
            ).fetchone()
        assert row is not None
        return _to_package(row)

    def replace_items(
        self,
        conn: Connection,
        *,
        package_id: UUID,
        items: list[BidTemplateItemCreate],
    ) -> list[BidTemplateItemRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("DELETE FROM bid_template_item WHERE package_id = %s", (package_id,))
            created: list[BidTemplateItemRow] = []
            for item in items:
                row = cur.execute(
                    f"""
                    INSERT INTO bid_template_item (
                      id, package_id, item_code, item_name, filename, relative_path,
                      source_kind, item_type, render_mode, is_required, sort_order
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING {_ITEM_COLUMNS}
                    """,
                    (
                        uuid4(),
                        package_id,
                        item.item_code,
                        item.item_name,
                        item.filename,
                        item.relative_path,
                        item.source_kind,
                        item.item_type,
                        item.render_mode,
                        item.is_required,
                        item.sort_order,
                    ),
                ).fetchone()
                assert row is not None
                created.append(_to_item(row))
        conn.commit()
        return created
