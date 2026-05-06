from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row

from tender_backend.core.security import CurrentUser, Role


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

    def create_for_user(self, conn: Connection, *, name: str, user_id: UUID | None) -> Project:
        project_id = uuid4()
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                "INSERT INTO project (id, name) VALUES (%s, %s) RETURNING id, name",
                (project_id, name),
            ).fetchone()
            if user_id is not None:
                cur.execute(
                    "INSERT INTO project_member (project_id, user_id, role) VALUES (%s, %s, %s) "
                    "ON CONFLICT (project_id, user_id) DO NOTHING",
                    (project_id, user_id, "owner"),
                )
        conn.commit()
        assert row is not None
        return Project(id=row["id"], name=row["name"])

    def list(self, conn: Connection) -> list[Project]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute("SELECT id, name FROM project ORDER BY created_at DESC").fetchall()
        return [Project(id=r["id"], name=r["name"]) for r in rows]

    def list_for_user(self, conn: Connection, *, user: CurrentUser) -> list[Project]:
        if user.role == Role.ADMIN:
            return self.list(conn)
        if user.user_id is None:
            return []
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                "SELECT p.id, p.name "
                "FROM project p "
                "JOIN project_member pm ON pm.project_id = p.id "
                "WHERE pm.user_id = %s "
                "ORDER BY p.created_at DESC",
                (user.user_id,),
            ).fetchall()
        return [Project(id=r["id"], name=r["name"]) for r in rows]

    def delete(self, conn: Connection, *, project_id: UUID) -> bool:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                "DELETE FROM project WHERE id = %s RETURNING id",
                (project_id,),
            ).fetchone()
        conn.commit()
        return row is not None
