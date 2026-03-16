"""API routes for export operations."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection
from psycopg.rows import dict_row

from tender_backend.core.security import CurrentUser, Role, get_current_user
from tender_backend.db.deps import get_db_conn

router = APIRouter(tags=["exports"])


@router.get("/projects/{project_id}/exports")
def list_exports(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT * FROM export_record WHERE project_id = %s ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
    return rows


@router.get("/projects/{project_id}/export-gates")
def check_export_gates(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Check all three export gates."""
    from tender_backend.db.repositories.requirement_repo import RequirementRepository
    from tender_backend.services.review_service.review_engine import get_blocking_issues

    req_repo = RequirementRepository()
    unconfirmed_veto = req_repo.unconfirmed_veto_count(conn, project_id=project_id)
    blocking_issues = get_blocking_issues(conn, project_id=project_id)

    return {
        "project_id": str(project_id),
        "gates": {
            "veto_confirmed": unconfirmed_veto == 0,
            "unconfirmed_veto_count": unconfirmed_veto,
            "review_passed": len(blocking_issues) == 0,
            "blocking_issue_count": len(blocking_issues),
            "format_passed": True,  # Phase 1: format check is a warning
        },
        "can_export": unconfirmed_veto == 0 and len(blocking_issues) == 0,
    }
