from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


@dataclass(frozen=True)
class ChartAssetRow:
    id: UUID
    project_id: UUID
    outline_node_id: UUID | None
    chart_type: str
    title: str
    spec_json: dict[str, Any]
    rendered_svg: str | None
    rendered_path: str | None
    placeholder_key: str | None
    mermaid_source: str | None
    rendered_png_path: str | None
    status: str
    version: int
    template_instance_id: UUID | None
    template_revision_no: int | None
    is_stale_by_template: bool
    stale_by_template_revision_no: int | None
    stale_by_template_block_id: UUID | None
    template_stale_reason: str | None
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


_COLUMNS = (
    "id, project_id, outline_node_id, chart_type, title, spec_json, rendered_svg, rendered_path, "
    "placeholder_key, mermaid_source, rendered_png_path, status, version, template_instance_id, template_revision_no, "
    "is_stale_by_template, stale_by_template_revision_no, stale_by_template_block_id, template_stale_reason, metadata_json, created_at, updated_at"
)


def _to_row(row: dict[str, Any]) -> ChartAssetRow:
    return ChartAssetRow(
        id=row["id"],
        project_id=row["project_id"],
        outline_node_id=row["outline_node_id"],
        chart_type=row["chart_type"],
        title=row["title"],
        spec_json=dict(row["spec_json"] or {}),
        rendered_svg=row["rendered_svg"],
        rendered_path=row["rendered_path"],
        placeholder_key=row.get("placeholder_key"),
        mermaid_source=row.get("mermaid_source"),
        rendered_png_path=row.get("rendered_png_path"),
        status=row["status"],
        version=row["version"],
        template_instance_id=row.get("template_instance_id"),
        template_revision_no=row.get("template_revision_no"),
        is_stale_by_template=bool(row.get("is_stale_by_template", False)),
        stale_by_template_revision_no=row.get("stale_by_template_revision_no"),
        stale_by_template_block_id=row.get("stale_by_template_block_id"),
        template_stale_reason=row.get("template_stale_reason"),
        metadata_json=dict(row["metadata_json"] or {}),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class ChartAssetRepository:
    def create(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        chart_type: str,
        title: str,
        spec_json: dict[str, Any],
        rendered_svg: str | None,
        rendered_png_path: str | None,
        placeholder_key: str | None,
        mermaid_source: str | None,
        status: str,
        template_instance_id: UUID | None = None,
        template_revision_no: int | None = None,
        is_stale_by_template: bool = False,
        metadata_json: dict[str, Any] | None = None,
        outline_node_id: UUID | None = None,
    ) -> ChartAssetRow:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                INSERT INTO chart_asset (
                  id, project_id, outline_node_id, chart_type, title, spec_json, rendered_svg,
                  placeholder_key, mermaid_source, rendered_png_path, status, template_instance_id,
                  template_revision_no, is_stale_by_template, stale_by_template_revision_no,
                  stale_by_template_block_id, template_stale_reason, metadata_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL, NULL, %s)
                ON CONFLICT (project_id, placeholder_key) WHERE placeholder_key IS NOT NULL
                DO UPDATE SET
                  outline_node_id = EXCLUDED.outline_node_id,
                  chart_type = EXCLUDED.chart_type,
                  title = EXCLUDED.title,
                  spec_json = EXCLUDED.spec_json,
                  rendered_svg = EXCLUDED.rendered_svg,
                  rendered_path = NULL,
                  mermaid_source = EXCLUDED.mermaid_source,
                  rendered_png_path = EXCLUDED.rendered_png_path,
                  status = EXCLUDED.status,
                  template_instance_id = EXCLUDED.template_instance_id,
                  template_revision_no = EXCLUDED.template_revision_no,
                  is_stale_by_template = EXCLUDED.is_stale_by_template,
                  stale_by_template_revision_no = NULL,
                  stale_by_template_block_id = NULL,
                  template_stale_reason = NULL,
                  metadata_json = EXCLUDED.metadata_json,
                  version = chart_asset.version + 1,
                  updated_at = now()
                RETURNING {_COLUMNS}
                """,
                (
                    uuid4(),
                    project_id,
                    outline_node_id,
                    chart_type,
                    title,
                    _jsonb(spec_json),
                    rendered_svg,
                    placeholder_key,
                    mermaid_source,
                    rendered_png_path,
                    status,
                    template_instance_id,
                    template_revision_no,
                    is_stale_by_template,
                    _jsonb(metadata_json or {}),
                ),
            ).fetchone()
        conn.commit()
        assert row is not None
        return _to_row(row)

    def list_by_project(self, conn: Connection, *, project_id: UUID) -> list[ChartAssetRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"""
                SELECT {_COLUMNS}
                FROM chart_asset
                WHERE project_id = %s
                ORDER BY chart_type, created_at DESC
                """,
                (project_id,),
            ).fetchall()
        return [_to_row(row) for row in rows]

    def get_by_id(self, conn: Connection, *, asset_id: UUID) -> ChartAssetRow | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(f"SELECT {_COLUMNS} FROM chart_asset WHERE id = %s", (asset_id,)).fetchone()
        return _to_row(row) if row else None

    def find_for_placeholder(self, conn: Connection, *, project_id: UUID, key: str) -> list[ChartAssetRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"""
                SELECT {_COLUMNS}
                FROM chart_asset
                WHERE project_id = %s
                  AND (placeholder_key = %s OR chart_type = %s)
                ORDER BY
                  CASE WHEN placeholder_key = %s THEN 0 ELSE 1 END,
                  CASE WHEN status = 'approved' THEN 0 WHEN status = 'draft' THEN 1 ELSE 2 END,
                  created_at DESC
                """,
                (project_id, key, key, key),
            ).fetchall()
        return [_to_row(row) for row in rows]

    def approve(self, conn: Connection, *, asset_id: UUID, approved_by: str | None = None) -> ChartAssetRow | None:
        with conn.cursor(row_factory=dict_row) as cur:
            current = cur.execute(f"SELECT {_COLUMNS} FROM chart_asset WHERE id = %s", (asset_id,)).fetchone()
            if current is None:
                return None
            metadata = dict(current["metadata_json"] or {})
            metadata["approved_by"] = approved_by
            metadata["approved_at"] = datetime.utcnow().isoformat() + "Z"
            row = cur.execute(
                f"""
                UPDATE chart_asset
                SET status = 'approved', metadata_json = %s, updated_at = now()
                WHERE id = %s
                RETURNING {_COLUMNS}
                """,
                (_jsonb(metadata), asset_id),
            ).fetchone()
        conn.commit()
        return _to_row(row) if row else None


def chart_asset_to_dict(row: ChartAssetRow) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "outline_node_id": str(row.outline_node_id) if row.outline_node_id else None,
        "chart_type": row.chart_type,
        "title": row.title,
        "spec_json": row.spec_json,
        "rendered_svg": row.rendered_svg,
        "rendered_path": row.rendered_path,
        "placeholder_key": row.placeholder_key,
        "mermaid_source": row.mermaid_source,
        "rendered_png_path": row.rendered_png_path,
        "status": row.status,
        "version": row.version,
        "template_instance_id": str(getattr(row, "template_instance_id", None)) if getattr(row, "template_instance_id", None) else None,
        "template_revision_no": getattr(row, "template_revision_no", None),
        "is_stale_by_template": bool(getattr(row, "is_stale_by_template", False)),
        "stale_by_template_revision_no": getattr(row, "stale_by_template_revision_no", None),
        "stale_by_template_block_id": str(getattr(row, "stale_by_template_block_id", None)) if getattr(row, "stale_by_template_block_id", None) else None,
        "template_stale_reason": getattr(row, "template_stale_reason", None),
        "metadata_json": row.metadata_json,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _jsonb(value: Any) -> Jsonb:
    return Jsonb(json.loads(json.dumps(value, ensure_ascii=False, default=str)))
