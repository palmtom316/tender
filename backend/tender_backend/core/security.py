"""Basic token authentication with role-based access control.

Supports three roles: editor (项目编辑), reviewer (复核人), admin (管理员).
Tokens are configured via environment variables for Phase 1 simplicity.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, HTTPException, Request


class Role(StrEnum):
    EDITOR = "editor"
    REVIEWER = "reviewer"
    ADMIN = "admin"


@dataclass(frozen=True)
class CurrentUser:
    token: str
    role: Role
    display_name: str


# Phase 1: fixed tokens from env. Format: "token:role:name,token:role:name,..."
def _load_token_map() -> dict[str, CurrentUser]:
    raw = os.environ.get("AUTH_TOKENS", "")
    if not raw:
        # Development fallback — single admin token
        return {
            "dev-token": CurrentUser(
                token="dev-token", role=Role.ADMIN, display_name="Developer"
            )
        }
    token_map: dict[str, CurrentUser] = {}
    for entry in raw.split(","):
        parts = entry.strip().split(":")
        if len(parts) >= 3:
            tok, role_str, name = parts[0], parts[1], parts[2]
            try:
                role = Role(role_str)
            except ValueError:
                continue
            token_map[tok] = CurrentUser(token=tok, role=role, display_name=name)
    return token_map


_token_map: dict[str, CurrentUser] | None = None


def _get_token_map() -> dict[str, CurrentUser]:
    global _token_map
    if _token_map is None:
        _token_map = _load_token_map()
    return _token_map


def get_current_user(request: Request) -> CurrentUser:
    """Extract and validate Bearer token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth[7:]
    user = _get_token_map().get(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


def require_role(*allowed_roles: Role):
    """Dependency factory: require the current user to have one of the allowed roles."""
    def _check(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{user.role}' not authorized. Required: {[r.value for r in allowed_roles]}",
            )
        return user
    return _check
