from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from psycopg import Connection

from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.user_repository import UserRepository

router = APIRouter(tags=["users"])

_repo = UserRepository()


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str
    role: str
    enabled: bool
    created_at: str
    updated_at: str


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=4)
    display_name: str = Field(min_length=1, max_length=100)
    role: str = Field(default="editor")


class UserUpdate(BaseModel):
    display_name: str | None = None
    role: str | None = None
    password: str | None = None
    enabled: bool | None = None


def _to_out(user) -> UserOut:
    return UserOut(
        id=str(user.id),
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        enabled=user.enabled,
        created_at=user.created_at.isoformat(),
        updated_at=user.updated_at.isoformat(),
    )


@router.get("/users", response_model=list[UserOut])
async def list_users(conn: Connection = Depends(get_db_conn)) -> list[UserOut]:
    users = _repo.list_all(conn)
    return [_to_out(u) for u in users]


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(payload: UserCreate, conn: Connection = Depends(get_db_conn)) -> UserOut:
    valid_roles = {"editor", "reviewer", "admin"}
    if payload.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {valid_roles}")

    try:
        user = _repo.create(
            conn,
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
            role=payload.role,
        )
    except Exception as exc:
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise HTTPException(status_code=409, detail="用户名已存在")
        raise
    return _to_out(user)


@router.put("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    conn: Connection = Depends(get_db_conn),
) -> UserOut:
    uid = UUID(user_id)
    existing = _repo.get_by_id(conn, uid)
    if existing is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    updated = _repo.update(conn, uid, **payload.model_dump(exclude_none=True))
    if updated is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return _to_out(updated)


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, conn: Connection = Depends(get_db_conn)) -> dict[str, str]:
    uid = UUID(user_id)
    deleted = _repo.delete(conn, uid)
    if not deleted:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"detail": "ok"}
