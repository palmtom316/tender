from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row


@dataclass(frozen=True)
class Document:
    id: UUID
    project_file_id: UUID


class DocumentRepository:
    def create(self, conn: Connection, *, project_file_id: UUID) -> Document:
        document_id = uuid4()
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                "INSERT INTO document (id, project_file_id) VALUES (%s, %s) RETURNING id, project_file_id",
                (document_id, project_file_id),
            ).fetchone()
        conn.commit()
        assert row is not None
        return Document(id=row["id"], project_file_id=row["project_file_id"])

    def get_by_file_id(self, conn: Connection, *, project_file_id: UUID) -> Document | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                "SELECT id, project_file_id FROM document WHERE project_file_id = %s",
                (project_file_id,),
            ).fetchone()
        if row is None:
            return None
        return Document(id=row["id"], project_file_id=row["project_file_id"])

