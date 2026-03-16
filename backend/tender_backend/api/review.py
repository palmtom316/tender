"""API routes for review issues."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection
from psycopg.rows import dict_row

from tender_backend.core.security import CurrentUser, get_current_user
from tender_backend.db.deps import get_db_conn

router = APIRouter(tags=["review"])


@router.get("/projects/{project_id}/review-issues")
def list_review_issues(
    project_id: UUID,
    severity: str | None = None,
    resolved: bool | None = None,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    query = "SELECT * FROM review_issue WHERE project_id = %s"
    params: list = [project_id]
    if severity:
        query += " AND severity = %s"
        params.append(severity)
    if resolved is not None:
        query += " AND resolved = %s"
        params.append(resolved)
    query += " ORDER BY severity, created_at"
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(query, params).fetchall()


@router.post("/review-issues/{issue_id}/resolve")
def resolve_issue(
    issue_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            "UPDATE review_issue SET resolved = TRUE WHERE id = %s RETURNING *",
            (issue_id,),
        ).fetchone()
    conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="issue not found")
    return row
