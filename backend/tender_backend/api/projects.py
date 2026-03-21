from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from psycopg import Connection

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
