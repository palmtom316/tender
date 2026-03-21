"""API routes for compliance matrix."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from psycopg import Connection

from tender_backend.core.security import CurrentUser, get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.services.review_service.compliance_matrix import build_compliance_matrix

router = APIRouter(tags=["compliance"])


@router.get("/projects/{project_id}/compliance-matrix")
async def get_compliance_matrix(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    entries = build_compliance_matrix(conn, project_id=project_id)
    return [
        {
            "requirement_id": e.requirement_id,
            "requirement_title": e.requirement_title,
            "category": e.category,
            "chapter_code": e.chapter_code,
            "coverage": e.coverage,
        }
        for e in entries
    ]
