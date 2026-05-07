from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from psycopg import Connection

from tender_backend.core.project_access import require_project_access
from tender_backend.core.security import CurrentUser, get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.services.post_bid_review_service import PostBidReviewService


router = APIRouter(tags=["post-bid"])
_service = PostBidReviewService()


class PostBidReviewBody(BaseModel):
    bid_result: str = "unknown"
    ranking: int | None = None
    score: float | None = None
    price_metadata: dict[str, Any] | None = None
    competitor_notes: str | None = None
    win_loss_reasons: str | None = None
    reusable_lessons: str | None = None
    opening_record_json: dict[str, Any] | None = None
    clarification_json: list[dict[str, Any]] | None = None
    notice_json: dict[str, Any] | None = None
    contract_status: str | None = None


@router.get("/projects/{project_id}/post-bid-review")
async def get_post_bid_review(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    return _service.get(conn, project_id=project_id) or {"project_id": str(project_id), "bid_result": "unknown"}


@router.put("/projects/{project_id}/post-bid-review")
async def upsert_post_bid_review(
    project_id: UUID,
    payload: PostBidReviewBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    return _service.upsert(conn, project_id=project_id, fields=payload.model_dump(exclude_unset=True))


@router.get("/post-bid-review/analytics")
async def get_post_bid_review_analytics(
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    return _service.analytics(conn)
