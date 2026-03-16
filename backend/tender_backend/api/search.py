"""API routes for search (sections, clauses, company docs)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from tender_backend.core.security import CurrentUser, get_current_user
from tender_backend.services.search_service.query_service import (
    search_clauses,
    search_sections,
    search_requirements,
)

router = APIRouter(tags=["search"])


@router.get("/search/sections")
async def api_search_sections(
    q: str = Query(..., min_length=1),
    project_id: str | None = None,
    top_k: int = Query(5, ge=1, le=50),
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    return await search_sections(q, project_id=project_id, top_k=top_k)


@router.get("/search/clauses")
async def api_search_clauses(
    q: str = Query(..., min_length=1),
    specialty: str | None = None,
    top_k: int = Query(5, ge=1, le=50),
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    return await search_clauses(q, specialty=specialty, top_k=top_k)


@router.get("/search/requirements")
async def api_search_requirements(
    q: str = Query(..., min_length=1),
    project_id: str | None = None,
    category: str | None = None,
    top_k: int = Query(5, ge=1, le=50),
    _user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    return await search_requirements(q, project_id=project_id, category=category, top_k=top_k)
