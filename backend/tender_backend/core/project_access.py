from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from psycopg import Connection
from psycopg.rows import dict_row

from tender_backend.core.security import CurrentUser, Role


def require_project_access(conn: Connection, *, project_id: UUID, user: CurrentUser) -> None:
    """Central project access gate.

    The current schema has no project membership table, so every authenticated
    role may access existing projects. Keeping the check centralized gives the
    future member/owner policy one place to land.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute("SELECT id FROM project WHERE id = %s", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    if user.role not in {Role.ADMIN, Role.EDITOR, Role.REVIEWER}:
        raise HTTPException(status_code=403, detail="project access denied")


def project_id_for_resource(
    conn: Connection,
    *,
    resource_id: UUID,
    query: str,
    not_found_detail: str,
) -> UUID:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(query, (resource_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=not_found_detail)
    return row["project_id"]


def require_resource_project_access(
    conn: Connection,
    *,
    resource_id: UUID,
    query: str,
    not_found_detail: str,
    user: CurrentUser,
) -> UUID:
    project_id = project_id_for_resource(
        conn,
        resource_id=resource_id,
        query=query,
        not_found_detail=not_found_detail,
    )
    require_project_access(conn, project_id=project_id, user=user)
    return project_id
