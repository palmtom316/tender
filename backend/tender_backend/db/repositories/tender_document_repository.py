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
        if row is None:
            raise RuntimeError("failed to create tender document")
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
        return dict(row) if row else None

    def get_document(self, conn: Connection, *, tender_document_id: UUID) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                "SELECT * FROM tender_document WHERE id = %s",
                (tender_document_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_file(self, conn: Connection, *, tender_document_file_id: UUID) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                "SELECT * FROM tender_document_file WHERE id = %s",
                (tender_document_file_id,),
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
        if row is None:
            raise RuntimeError("failed to create tender document file")
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

    def update_file_classification(
        self,
        conn: Connection,
        *,
        tender_document_file_id: UUID,
        classification: str,
        is_parsable: bool | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                UPDATE tender_document_file
                SET classification = %s,
                    is_parsable = COALESCE(%s, is_parsable),
                    metadata_json = COALESCE(%s, metadata_json),
                    updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (
                    classification,
                    is_parsable,
                    Jsonb(metadata_json) if metadata_json is not None else None,
                    tender_document_file_id,
                ),
            ).fetchone()
        return dict(row) if row else None

    def update_file_parse_status(
        self,
        conn: Connection,
        *,
        tender_document_file_id: UUID,
        parse_status: str,
        error: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                UPDATE tender_document_file
                SET parse_status = %s,
                    error = %s,
                    metadata_json = COALESCE(%s, metadata_json),
                    updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (
                    parse_status,
                    error,
                    Jsonb(metadata_json) if metadata_json is not None else None,
                    tender_document_file_id,
                ),
            ).fetchone()
        return dict(row) if row else None

    def replace_source_chunks(
        self,
        conn: Connection,
        *,
        tender_document_id: UUID,
        tender_document_file_id: UUID,
        chunks: list[dict[str, Any]],
    ) -> int:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM source_chunk WHERE tender_document_file_id = %s",
                (tender_document_file_id,),
            )
            for index, chunk in enumerate(chunks):
                cur.execute(
                    """
                    INSERT INTO source_chunk (
                      id, tender_document_id, tender_document_file_id, chunk_type,
                      source_file, document_type, section_title, source_locator, title,
                      text, table_json, page_start, page_end, sheet_name, row_start,
                      row_end, paragraph_index, sort_order, confidence, metadata_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        uuid4(),
                        tender_document_id,
                        tender_document_file_id,
                        chunk["chunk_type"],
                        chunk["source_file"],
                        chunk.get("document_type"),
                        chunk.get("section_title"),
                        chunk["source_locator"],
                        chunk.get("title"),
                        chunk.get("text"),
                        Jsonb(chunk.get("table_json")) if chunk.get("table_json") is not None else None,
                        chunk.get("page_start"),
                        chunk.get("page_end"),
                        chunk.get("sheet_name"),
                        chunk.get("row_start"),
                        chunk.get("row_end"),
                        chunk.get("paragraph_index"),
                        chunk.get("sort_order", index),
                        chunk.get("confidence", 1.0),
                        Jsonb(chunk.get("metadata_json") or {}),
                    ),
                )
        return len(chunks)

    def list_source_chunks(
        self,
        conn: Connection,
        *,
        tender_document_id: UUID,
        tender_document_file_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT *
            FROM source_chunk
            WHERE tender_document_id = %s
        """
        params: list[Any] = [tender_document_id]
        if tender_document_file_id is not None:
            query += " AND tender_document_file_id = %s"
            params.append(tender_document_file_id)
        query += " ORDER BY source_file, sort_order, created_at"
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def update_source_chunk(
        self,
        conn: Connection,
        *,
        source_chunk_id: UUID,
        fields: dict[str, Any],
    ) -> dict[str, Any] | None:
        allowed = {
            "chunk_type",
            "document_type",
            "section_title",
            "source_locator",
            "title",
            "text",
            "table_json",
            "page_start",
            "page_end",
            "sheet_name",
            "row_start",
            "row_end",
            "paragraph_index",
            "sort_order",
            "confidence",
            "metadata_json",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            with conn.cursor(row_factory=dict_row) as cur:
                row = cur.execute("SELECT * FROM source_chunk WHERE id = %s", (source_chunk_id,)).fetchone()
            return dict(row) if row else None

        sets: list[str] = []
        values: list[Any] = []
        for key, value in updates.items():
            sets.append(f"{key} = %s")
            values.append(Jsonb(value) if key in {"table_json", "metadata_json"} else value)
        values.append(source_chunk_id)

        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                UPDATE source_chunk
                SET {', '.join(sets)}
                WHERE id = %s
                RETURNING *
                """,
                values,
            ).fetchone()
        return dict(row) if row else None
