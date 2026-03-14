from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row


@dataclass(frozen=True)
class ParseJob:
    id: UUID
    document_id: UUID
    provider: str
    provider_job_id: str | None
    status: str
    error: str | None


ACTIVE_STATUSES = {"queued", "submitted", "processing"}


class ParseJobRepository:
    def create(
        self,
        conn: Connection,
        *,
        document_id: UUID,
        provider: str = "mineru",
        status: str = "queued",
    ) -> ParseJob:
        job_id = uuid4()
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO parse_job (id, document_id, status, provider, provider_job_id, error)
                VALUES (%s, %s, %s, %s, NULL, NULL)
                RETURNING id, document_id, provider, provider_job_id, status, error
                """,
                (job_id, document_id, status, provider),
            ).fetchone()
        conn.commit()
        assert row is not None
        return ParseJob(
            id=row["id"],
            document_id=row["document_id"],
            provider=row["provider"],
            provider_job_id=row["provider_job_id"],
            status=row["status"],
            error=row["error"],
        )

    def latest_for_document(self, conn: Connection, *, document_id: UUID) -> ParseJob | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                SELECT id, document_id, provider, provider_job_id, status, error
                FROM parse_job
                WHERE document_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (document_id,),
            ).fetchone()
        if row is None:
            return None
        return ParseJob(
            id=row["id"],
            document_id=row["document_id"],
            provider=row["provider"],
            provider_job_id=row["provider_job_id"],
            status=row["status"],
            error=row["error"],
        )

    def find_active_for_document(self, conn: Connection, *, document_id: UUID) -> ParseJob | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                SELECT id, document_id, provider, provider_job_id, status, error
                FROM parse_job
                WHERE document_id = %s AND status = ANY(%s::text[])
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (document_id, list(ACTIVE_STATUSES)),
            ).fetchone()
        if row is None:
            return None
        return ParseJob(
            id=row["id"],
            document_id=row["document_id"],
            provider=row["provider"],
            provider_job_id=row["provider_job_id"],
            status=row["status"],
            error=row["error"],
        )

    def get(self, conn: Connection, *, parse_job_id: UUID) -> ParseJob | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                SELECT id, document_id, provider, provider_job_id, status, error
                FROM parse_job
                WHERE id = %s
                """,
                (parse_job_id,),
            ).fetchone()
        if row is None:
            return None
        return ParseJob(
            id=row["id"],
            document_id=row["document_id"],
            provider=row["provider"],
            provider_job_id=row["provider_job_id"],
            status=row["status"],
            error=row["error"],
        )
