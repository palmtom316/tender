from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from psycopg import Connection
from psycopg.rows import dict_row

from tender_backend.core.security import CurrentUser, Role


def require_project_access(conn: Connection, *, project_id: UUID, user: CurrentUser) -> None:
    """Central project access gate.

    Admins may access every existing project. Other roles require an explicit
    project_member row tied to the authenticated DB user.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute("SELECT id FROM project WHERE id = %s", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    if user.role == Role.ADMIN:
        return
    if user.role not in {Role.EDITOR, Role.REVIEWER} or user.user_id is None:
        raise HTTPException(status_code=403, detail="project access denied")
    with conn.cursor(row_factory=dict_row) as cur:
        membership = cur.execute(
            "SELECT project_id FROM project_member WHERE project_id = %s AND user_id = %s",
            (project_id, user.user_id),
        ).fetchone()
    if membership is None:
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
