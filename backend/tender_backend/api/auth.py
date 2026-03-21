from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from psycopg import Connection

from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.user_repository import (
    UserRepository,
    SessionRepository,
    verify_password,
)

router = APIRouter(tags=["auth"])

_users = UserRepository()
_sessions = SessionRepository()


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    display_name: str
    role: str


class MeResponse(BaseModel):
    username: str
    display_name: str
    role: str


@router.post("/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest, conn: Connection = Depends(get_db_conn)) -> LoginResponse:
    result = _users.get_by_username(conn, payload.username)
    if result is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    user, password_hash = result
    if not verify_password(payload.password, password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if not user.enabled:
        raise HTTPException(status_code=403, detail="账号已禁用")

    token = _sessions.create_session(conn, user.id)
    return LoginResponse(
        token=token,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
    )


@router.get("/auth/me", response_model=MeResponse)
async def auth_me(request: Request, conn: Connection = Depends(get_db_conn)) -> MeResponse:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = auth_header[7:]

    # Try DB session first
    user = _sessions.get_user_by_token(conn, token)
    if user:
        return MeResponse(username=user.username, display_name=user.display_name, role=user.role)

    # Fallback to dev-token
    if token == "dev-token":
        return MeResponse(username="dev", display_name="Developer", role="admin")

    raise HTTPException(status_code=401, detail="Invalid or expired session")


@router.post("/auth/logout")
async def auth_logout(request: Request, conn: Connection = Depends(get_db_conn)) -> dict[str, str]:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        _sessions.delete_session(conn, token)
    return {"detail": "ok"}
