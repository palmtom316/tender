"""Repository helpers for uploaded tender documents and extracted files."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb
from psycopg.rows import dict_row


class TenderDocumentRepository:
    def create_document(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        original_filename: str,
        upload_type: str,
        status: str,
        content_type: str,
        size_bytes: int,
        storage_key: str,
        file_sha256: str,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO tender_document (
                  id, project_id, original_filename, upload_type, status,
                  content_type, size_bytes, storage_key, file_sha256, metadata_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    uuid4(),
                    project_id,
                    original_filename,
                    upload_type,
                    status,
                    content_type,
                    size_bytes,
                    storage_key,
                    file_sha256,
                    Jsonb(metadata_json or {}),
                ),
            ).fetchone()
        conn.commit()
        assert row is not None
        return dict(row)

    def update_document_status(
        self,
        conn: Connection,
        *,
        tender_document_id: UUID,
        status: str,
        error: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                UPDATE tender_document
                SET status = %s,
                    error = %s,
                    metadata_json = COALESCE(%s, metadata_json),
                    updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (status, error, Jsonb(metadata_json) if metadata_json is not None else None, tender_document_id),
            ).fetchone()
        conn.commit()
        return dict(row) if row else None

    def get_document(self, conn: Connection, *, tender_document_id: UUID) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                "SELECT * FROM tender_document WHERE id = %s",
                (tender_document_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_documents(self, conn: Connection, *, project_id: UUID) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT td.*,
                       COALESCE(file_counts.file_count, 0) AS file_count
                FROM tender_document td
                LEFT JOIN (
                  SELECT tender_document_id, count(*) AS file_count
                  FROM tender_document_file
                  GROUP BY tender_document_id
                ) file_counts ON file_counts.tender_document_id = td.id
                WHERE td.project_id = %s
                ORDER BY td.created_at DESC
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_file(
        self,
        conn: Connection,
        *,
        tender_document_id: UUID,
        parent_file_id: UUID | None,
        filename: str,
        relative_path: str,
        storage_key: str,
        content_type: str,
        size_bytes: int,
        file_type: str,
        classification: str,
        depth: int,
        is_archive: bool,
        is_parsable: bool,
        parse_status: str = "pending",
        error: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO tender_document_file (
                  id, tender_document_id, parent_file_id, filename, relative_path,
                  storage_key, content_type, size_bytes, file_type, classification,
                  depth, is_archive, is_parsable, parse_status, error, metadata_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    uuid4(),
                    tender_document_id,
                    parent_file_id,
                    filename,
                    relative_path,
                    storage_key,
                    content_type,
                    size_bytes,
                    file_type,
                    classification,
                    depth,
                    is_archive,
                    is_parsable,
                    parse_status,
                    error,
                    Jsonb(metadata_json or {}),
                ),
            ).fetchone()
        conn.commit()
        assert row is not None
        return dict(row)

    def list_files(self, conn: Connection, *, tender_document_id: UUID) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT *
                FROM tender_document_file
                WHERE tender_document_id = %s
                ORDER BY depth, relative_path, created_at
                """,
                (tender_document_id,),
            ).fetchall()
        return [dict(row) for row in rows]
