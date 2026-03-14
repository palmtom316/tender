from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row


@dataclass(frozen=True)
class ProjectFile:
    id: UUID
    project_id: UUID
    filename: str
    content_type: str
    size_bytes: int
    storage_key: str | None


class FileRepository:
    def create(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        filename: str,
        content_type: str,
        size_bytes: int,
        storage_key: str | None = None,
    ) -> ProjectFile:
        file_id = uuid4()
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO project_file (
                  id, project_id, filename, content_type, size_bytes, storage_key
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, project_id, filename, content_type, size_bytes, storage_key
                """,
                (file_id, project_id, filename, content_type, size_bytes, storage_key),
            ).fetchone()
        conn.commit()
        assert row is not None
        return ProjectFile(
            id=row["id"],
            project_id=row["project_id"],
            filename=row["filename"],
            content_type=row["content_type"],
            size_bytes=row["size_bytes"],
            storage_key=row["storage_key"],
        )

    def list(self, conn: Connection, *, project_id: UUID) -> list[ProjectFile]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT id, project_id, filename, content_type, size_bytes, storage_key
                FROM project_file
                WHERE project_id = %s
                ORDER BY created_at DESC
                """,
                (project_id,),
            ).fetchall()
        return [
            ProjectFile(
                id=r["id"],
                project_id=r["project_id"],
                filename=r["filename"],
                content_type=r["content_type"],
                size_bytes=r["size_bytes"],
                storage_key=r["storage_key"],
            )
            for r in rows
        ]

