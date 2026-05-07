"""API routes for review issues."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection
from psycopg.rows import dict_row
from pydantic import BaseModel

from tender_backend.core.project_access import require_project_access, require_resource_project_access
from tender_backend.core.security import CurrentUser, get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.services.review_service.review_engine import build_project_review, persist_review_issues

router = APIRouter(tags=["review"])
_REVIEW_ISSUE_PROJECT_QUERY = "SELECT project_id FROM review_issue WHERE id = %s"


class ReviewIssueDecisionBody(BaseModel):
    lifecycle_status: str
    user_decision: str | None = None


@router.get("/projects/{project_id}/review-issues")
async def list_review_issues(
    project_id: UUID,
    severity: str | None = None,
    resolved: bool | None = None,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    require_project_access(conn, project_id=project_id, user=user)
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
async def resolve_issue(
    issue_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_resource_project_access(
        conn,
        resource_id=issue_id,
        query=_REVIEW_ISSUE_PROJECT_QUERY,
        not_found_detail="issue not found",
        user=user,
    )
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            "UPDATE review_issue SET resolved = TRUE WHERE id = %s RETURNING *",
            (issue_id,),
        ).fetchone()
    conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="issue not found")
    return row


@router.post("/review-issues/{issue_id}/decision")
async def update_review_issue_decision(
    issue_id: UUID,
    payload: ReviewIssueDecisionBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_resource_project_access(
        conn,
        resource_id=issue_id,
        query=_REVIEW_ISSUE_PROJECT_QUERY,
        not_found_detail="issue not found",
        user=user,
    )
    allowed = {"accepted_for_fix", "fixed", "waived_by_user", "verified", "closed"}
    if payload.lifecycle_status not in allowed:
        raise HTTPException(status_code=400, detail="unsupported review issue lifecycle status")
    resolved = payload.lifecycle_status in {"waived_by_user", "verified", "closed"}
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """
            UPDATE review_issue
            SET lifecycle_status = %s,
                user_decision = %s,
                resolved = %s,
                closed_at = CASE WHEN %s THEN now() ELSE closed_at END
            WHERE id = %s
            RETURNING *
            """,
            (
                payload.lifecycle_status,
                payload.user_decision or payload.lifecycle_status,
                resolved,
                resolved,
                issue_id,
            ),
        ).fetchone()
    conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="issue not found")
    return row


@router.post("/projects/{project_id}/bid-review")
async def run_bid_review(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    issues = build_project_review(conn, project_id=project_id)
    persisted_count = persist_review_issues(conn, project_id=project_id, issues=issues)
    blocking = [issue for issue in issues if issue.severity in {"P0", "P1"}]
    return {
        "project_id": str(project_id),
        "issue_count": len(issues),
        "persisted_count": persisted_count,
        "blocking_issue_count": len(blocking),
        "can_export": len(blocking) == 0,
        "issues": [issue.__dict__ for issue in issues],
    }
