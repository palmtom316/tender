from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row


@dataclass(frozen=True)
class Project:
    id: UUID
    name: str


class ProjectRepository:
    def create(self, conn: Connection, *, name: str) -> Project:
        project_id = uuid4()
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                "INSERT INTO project (id, name) VALUES (%s, %s) RETURNING id, name",
                (project_id, name),
            ).fetchone()
        conn.commit()
        assert row is not None
        return Project(id=row["id"], name=row["name"])

    def list(self, conn: Connection) -> list[Project]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute("SELECT id, name FROM project ORDER BY created_at DESC").fetchall()
        return [Project(id=r["id"], name=r["name"]) for r in rows]

