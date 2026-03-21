"""API routes for chapter drafts."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection
from psycopg.rows import dict_row
from pydantic import BaseModel

from tender_backend.core.security import CurrentUser, get_current_user
from tender_backend.db.deps import get_db_conn

router = APIRouter(tags=["drafts"])


@router.get("/projects/{project_id}/drafts")
async def list_drafts(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT * FROM chapter_draft WHERE project_id = %s ORDER BY chapter_code",
            (project_id,),
        ).fetchall()
    return rows


@router.get("/drafts/{draft_id}")
async def get_draft(
    draft_id: UUID,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            "SELECT * FROM chapter_draft WHERE id = %s",
            (draft_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="draft not found")
    return row


class UpdateDraftBody(BaseModel):
    content_md: str


@router.put("/drafts/{draft_id}")
async def update_draft(
    draft_id: UUID,
    body: UpdateDraftBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """
            UPDATE chapter_draft SET content_md = %s, updated_at = now()
            WHERE id = %s RETURNING *
            """,
            (body.content_md, draft_id),
        ).fetchone()
    conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="draft not found")
    return row
