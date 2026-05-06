from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi import HTTPException
from pydantic import BaseModel, Field
from psycopg import Connection

from tender_backend.core.security import CurrentUser, get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.project_repository import ProjectRepository


router = APIRouter(tags=["projects"])

_repo = ProjectRepository()


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1)


class ProjectOut(BaseModel):
    id: UUID
    name: str


@router.post("/projects", response_model=ProjectOut)
async def create_project(payload: ProjectCreate, conn: Connection = Depends(get_db_conn)) -> ProjectOut:
    project = _repo.create(conn, name=payload.name.strip())
    return ProjectOut(id=project.id, name=project.name)


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(conn: Connection = Depends(get_db_conn)) -> list[ProjectOut]:
    projects = _repo.list(conn)
    return [ProjectOut(id=p.id, name=p.name) for p in projects]


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: UUID,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(get_current_user),
) -> dict[str, bool]:
    deleted = _repo.delete(conn, project_id=project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="project not found")
    return {"deleted": True}
