from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class ExternalAttachmentRepository:
    def create(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        filename: str,
        volume_type: str = "pricing",
        attachment_type: str = "external_pricing",
        file_path: str | None = None,
        content_type: str | None = None,
        size_bytes: int | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO external_bid_attachment (
                  id, project_id, volume_type, attachment_type, filename, file_path, content_type, size_bytes, metadata_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (uuid4(), project_id, volume_type, attachment_type, filename, file_path, content_type, size_bytes, Jsonb(metadata_json or {})),
            ).fetchone()
        conn.commit()
        return dict(row) if row else {}

    def list_by_project(self, conn: Connection, *, project_id: UUID) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                "SELECT * FROM external_bid_attachment WHERE project_id = %s ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]


__all__ = ["ExternalAttachmentRepository"]
