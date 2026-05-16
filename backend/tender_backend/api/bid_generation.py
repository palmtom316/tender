"""API routes for qualification-business and technical generation gates."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from psycopg import Connection
from pydantic import BaseModel

from tender_backend.core.project_access import require_project_access, require_resource_project_access
from tender_backend.core.security import CurrentUser, get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.services.business_bid_assembler import BusinessBidAssembler
from tender_backend.services.technical_chapter_context import TechnicalChapterContextBuilder
from tender_backend.services.technical_generation_async import (
    enqueue_technical_generation,
    get_technical_generation_run_status,
)
from tender_backend.services.technical_bid_writer import TechnicalBidWriter
from tender_backend.services.project_template_instance_service import ProjectTemplateInstanceService
from tender_backend.db.repositories.project_repository import ProjectRepository


router = APIRouter(tags=["bid-generation"])
_business_assembler = BusinessBidAssembler()
_technical_writer = TechnicalBidWriter()
_context_builder = TechnicalChapterContextBuilder()
_template_instances = ProjectTemplateInstanceService()
_project_repo = ProjectRepository()
_CHAPTER_PROJECT_QUERY = "SELECT project_id FROM bid_chapter WHERE id = %s"


class TechnicalGenerateBody(BaseModel):
    rewrite_note: str | None = None
    target_pages: int | None = None


@router.post("/projects/{project_id}/business-bid/assemble")
async def assemble_business_bid(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    try:
        project = _project_repo.get(conn, project_id=project_id)
        _template_instances.build_generation_inputs(conn, project_id=project_id, submission_deadline=project.submission_deadline if project else None)
        result = _business_assembler.assemble(conn, project_id=project_id, created_by=user.display_name)
        result.setdefault("generation_metadata", _template_instances.build_generation_inputs(conn, project_id=project_id)["metadata"])
        return result
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/projects/{project_id}/technical-bid/writing-plan")
async def get_technical_writing_plan(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    try:
        project = _project_repo.get(conn, project_id=project_id)
        _template_instances.build_generation_inputs(conn, project_id=project_id, submission_deadline=project.submission_deadline if project else None)
        return _technical_writer.create_writing_plan(conn, project_id=project_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/projects/{project_id}/technical-bid/chapters/{chapter_id}/generate")
async def generate_technical_chapter(
    project_id: UUID,
    chapter_id: UUID,
    payload: TechnicalGenerateBody | None = None,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    chapter_project_id = require_resource_project_access(
        conn,
        resource_id=chapter_id,
        query=_CHAPTER_PROJECT_QUERY,
        not_found_detail="bid chapter not found",
        user=user,
    )
    if chapter_project_id != project_id:
        raise HTTPException(status_code=404, detail="bid chapter not found")
    try:
        project = _project_repo.get(conn, project_id=project_id)
        _template_instances.build_generation_inputs(conn, project_id=project_id, submission_deadline=project.submission_deadline if project else None)
        result = _technical_writer.generate_chapter(
            conn,
            project_id=project_id,
            chapter_id=chapter_id,
            rewrite_note=payload.rewrite_note if payload else None,
            target_pages=payload.target_pages if payload else None,
            created_by=user.display_name,
        )
        result.setdefault("generation_metadata", _template_instances.build_generation_inputs(conn, project_id=project_id)["metadata"])
        return result
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/projects/{project_id}/technical-bid/chapters/{chapter_id}/generate-async", status_code=202)
async def generate_technical_chapter_async(
    project_id: UUID,
    chapter_id: UUID,
    payload: TechnicalGenerateBody | None = None,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    chapter_project_id = require_resource_project_access(
        conn,
        resource_id=chapter_id,
        query=_CHAPTER_PROJECT_QUERY,
        not_found_detail="bid chapter not found",
        user=user,
    )
    if chapter_project_id != project_id:
        raise HTTPException(status_code=404, detail="bid chapter not found")
    try:
        project = _project_repo.get(conn, project_id=project_id)
        _template_instances.build_generation_inputs(
            conn,
            project_id=project_id,
            submission_deadline=project.submission_deadline if project else None,
        )
        return await run_in_threadpool(
            enqueue_technical_generation,
            project_id=project_id,
            chapter_id=chapter_id,
            created_by=user.display_name,
            rewrite_note=payload.rewrite_note if payload else None,
            target_pages=payload.target_pages if payload else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/projects/{project_id}/technical-bid/generation-runs/{run_id}")
async def get_technical_generation_status(
    project_id: UUID,
    run_id: str,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    require_project_access(conn, project_id=project_id, user=user)
    try:
        return await run_in_threadpool(
            get_technical_generation_run_status,
            project_id=project_id,
            run_id=run_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects/{project_id}/technical-bid/chapters/{chapter_id}/context")
async def get_technical_chapter_context(
    project_id: UUID,
    chapter_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    chapter_project_id = require_resource_project_access(
        conn,
        resource_id=chapter_id,
        query=_CHAPTER_PROJECT_QUERY,
        not_found_detail="bid chapter not found",
        user=user,
    )
    if chapter_project_id != project_id:
        raise HTTPException(status_code=404, detail="bid chapter not found")
    try:
        return _context_builder.build(conn, project_id=project_id, chapter_id=chapter_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
