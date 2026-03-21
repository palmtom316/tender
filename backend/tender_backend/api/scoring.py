"""API routes for scoring criteria."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection

from tender_backend.core.security import CurrentUser, get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.scoring_repo import ScoringRepository

router = APIRouter(tags=["scoring"])
_repo = ScoringRepository()


@router.get("/projects/{project_id}/scoring-criteria")
async def list_scoring_criteria(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    return _repo.list_by_project(conn, project_id=project_id)


@router.post("/scoring-criteria/{criteria_id}/confirm")
async def confirm_scoring_criteria(
    criteria_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    row = _repo.confirm(conn, criteria_id=criteria_id, confirmed_by=user.display_name)
    if row is None:
        raise HTTPException(status_code=404, detail="scoring criteria not found")
    return row
