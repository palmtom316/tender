from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from psycopg import Connection

from tender_backend.core.security import get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.master_data_repo import MasterDataRepository


router = APIRouter(tags=["master-data"], dependencies=[Depends(get_current_user)])

_repo = MasterDataRepository()


def _not_found(detail: str) -> None:
    raise HTTPException(status_code=404, detail=detail)


class PersonProfileBase(BaseModel):
    library_company_id: UUID | None = None
    full_name: str = Field(min_length=1)
    gender: str | None = None
    age: int | None = None
    education: str | None = None
    title: str | None = None
    role_name: str | None = None
    specialty: str | None = None
    years_experience: int | None = None
    phone: str | None = None
    email: str | None = None
    resume_text: str | None = None
    profile_json: dict[str, Any] = Field(default_factory=dict)


class PersonProfileCreate(PersonProfileBase):
    pass


class PersonProfileUpdate(BaseModel):
    library_company_id: UUID | None = None
    full_name: str | None = None
    gender: str | None = None
    age: int | None = None
    education: str | None = None
    title: str | None = None
    role_name: str | None = None
    specialty: str | None = None
    years_experience: int | None = None
    phone: str | None = None
    email: str | None = None
    resume_text: str | None = None
    profile_json: dict[str, Any] | None = None


class PersonProfileOut(PersonProfileBase):
    id: UUID
    created_at: str
    updated_at: str


def _person_out(row) -> PersonProfileOut:
    return PersonProfileOut(
        id=row.id,
        library_company_id=row.library_company_id,
        full_name=row.full_name,
        gender=row.gender,
        age=row.age,
        education=row.education,
        title=row.title,
        role_name=row.role_name,
        specialty=row.specialty,
        years_experience=row.years_experience,
        phone=row.phone,
        email=row.email,
        resume_text=row.resume_text,
        profile_json=row.profile_json,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


@router.get("/master-data/people", response_model=list[PersonProfileOut])
async def list_people(
    library_company_id: UUID | None = Query(None),
    conn: Connection = Depends(get_db_conn),
) -> list[PersonProfileOut]:
    return [_person_out(row) for row in _repo.list_people(conn, library_company_id=library_company_id)]


@router.post("/master-data/people", response_model=PersonProfileOut, status_code=201)
async def create_person(payload: PersonProfileCreate, conn: Connection = Depends(get_db_conn)) -> PersonProfileOut:
    return _person_out(_repo.create_person(conn, **payload.model_dump()))


@router.put("/master-data/people/{record_id}", response_model=PersonProfileOut)
async def update_person(record_id: UUID, payload: PersonProfileUpdate, conn: Connection = Depends(get_db_conn)) -> PersonProfileOut:
    row = _repo.update_person(conn, record_id, **payload.model_dump(exclude_unset=True))
    if row is None:
        _not_found("person profile not found")
    return _person_out(row)


@router.delete("/master-data/people/{record_id}")
async def delete_person(record_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict[str, bool]:
    if not _repo.delete_person(conn, record_id):
        _not_found("person profile not found")
    return {"deleted": True}
