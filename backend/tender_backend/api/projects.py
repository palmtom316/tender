from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi import HTTPException
from pydantic import BaseModel, Field
from psycopg import Connection
from psycopg.rows import dict_row

from tender_backend.core.project_access import require_project_access
from tender_backend.core.security import CurrentUser, Role, get_current_user, require_role
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.project_repository import ProjectRepository
from tender_backend.services.project_setup_service import ProjectSetupService


router = APIRouter(tags=["projects"])

_repo = ProjectRepository()
_setup = ProjectSetupService(_repo)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1)
    category_code: str = Field(min_length=1)
    tender_no: str | None = None
    project_type: str | None = None
    industry: str | None = "power"
    business_line: str | None = None
    sub_type: str | None = None
    employer_name: str | None = None
    employer_type: str | None = None
    evaluation_method: str | None = None
    evaluation_detail: dict[str, Any] | None = None
    qualification_review_type: str | None = None
    submission_deadline: datetime | None = None
    bid_opening_time: datetime | None = None
    bid_validity_period: int | None = None
    bid_bond_amount: str | None = None
    bid_bond_form: str | None = None
    bid_bond_deadline: datetime | None = None
    voltage_level: list[str] = Field(default_factory=list)
    project_scope: list[str] = Field(default_factory=list)
    tender_platform: str | None = None
    submission_target: str | None = "local_zip"
    procurement_type: str | None = "single"
    section_name: str | None = None
    lot_name: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    tender_no: str | None = None
    project_type: str | None = None
    industry: str | None = None
    business_line: str | None = None
    sub_type: str | None = None
    category_code: str | None = None
    employer_name: str | None = None
    employer_type: str | None = None
    evaluation_method: str | None = None
    evaluation_detail: dict[str, Any] | None = None
    qualification_review_type: str | None = None
    submission_deadline: datetime | None = None
    bid_opening_time: datetime | None = None
    bid_validity_period: int | None = None
    bid_bond_amount: str | None = None
    bid_bond_form: str | None = None
    bid_bond_deadline: datetime | None = None
    voltage_level: list[str] | None = None
    project_scope: list[str] | None = None
    tender_platform: str | None = None
    submission_target: str | None = None
    procurement_type: str | None = None
    section_name: str | None = None
    lot_name: str | None = None


class ProjectOut(BaseModel):
    id: UUID
    name: str
    created_at: datetime | None = None
    status: str | None = None
    tender_no: str | None = None
    project_type: str | None = None
    industry: str | None = None
    business_line: str | None = None
    sub_type: str | None = None
    employer_name: str | None = None
    employer_type: str | None = None
    evaluation_method: str | None = None
    evaluation_detail: dict[str, Any] | None = None
    qualification_review_type: str | None = None
    submission_deadline: datetime | None = None
    bid_opening_time: datetime | None = None
    bid_validity_period: int | None = None
    bid_bond_amount: str | None = None
    bid_bond_form: str | None = None
    bid_bond_deadline: datetime | None = None
    voltage_level: list[str] = Field(default_factory=list)
    project_scope: list[str] = Field(default_factory=list)
    tender_platform: str | None = None
    submission_target: str | None = None
    procurement_type: str | None = None
    section_name: str | None = None
    lot_name: str | None = None
    category_code: str | None = None
    selected_template_package_id: UUID | None = None
    workflow_status: str | None = None


class ProjectWorkflowTransitionBody(BaseModel):
    next_status: str
    reason: str | None = None
    metadata: dict[str, Any] | None = None


def _project_out(project) -> ProjectOut:
    return ProjectOut(**project.__dict__)


def _assert_category_enabled(conn: Connection, *, category_code: str) -> None:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            "SELECT 1 FROM template_package_category WHERE code = %s AND enabled = TRUE",
            (category_code,),
        ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=400,
            detail=f"invalid category_code: {category_code}",
        )


@router.post("/projects", response_model=ProjectOut)
async def create_project(
    payload: ProjectCreate,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(require_role(Role.EDITOR, Role.ADMIN)),
) -> ProjectOut:
    _assert_category_enabled(conn, category_code=payload.category_code)
    metadata = payload.model_dump(exclude={"name"})
    project = _setup.create_project(
        conn,
        name=payload.name.strip(),
        user_id=user.user_id,
        metadata=metadata,
        actor=user.display_name,
    )
    return _project_out(project)


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[ProjectOut]:
    projects = _repo.list_for_user(conn, user=user)
    return [_project_out(p) for p in projects]


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(require_role(Role.EDITOR, Role.ADMIN)),
) -> ProjectOut:
    fields = payload.model_dump(exclude_unset=True)
    if "name" in fields:
        fields["name"] = fields["name"].strip()
    if "category_code" in fields and fields["category_code"]:
        _assert_category_enabled(conn, category_code=fields["category_code"])
    project = _repo.update(conn, project_id=project_id, fields=fields)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return _project_out(project)


@router.post("/projects/{project_id}/workflow-transition", response_model=ProjectOut)
async def transition_project_workflow(
    project_id: UUID,
    payload: ProjectWorkflowTransitionBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(require_role(Role.EDITOR, Role.ADMIN)),
) -> ProjectOut:
    try:
        project = _setup.transition(
            conn,
            project_id=project_id,
            next_status=payload.next_status,
            actor=user.display_name,
            reason=payload.reason,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _project_out(project)


@router.get("/projects/{project_id}/workflow-events")
async def list_project_workflow_events(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    require_project_access(conn, project_id=project_id, user=user)
    return _setup.list_events(conn, project_id=project_id)


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(require_role(Role.ADMIN)),
) -> dict[str, bool]:
    deleted = _repo.delete(conn, project_id=project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="project not found")
    return {"deleted": True}
