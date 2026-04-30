from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from tender_backend.core.project_access import require_project_access, require_resource_project_access
from tender_backend.core.security import CurrentUser, Role


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.executed.append((query, params))
        return self

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None


class _Conn:
    def __init__(self, rows):
        self.cursor_obj = _Cursor(rows)

    def cursor(self, *args, **kwargs):
        return self.cursor_obj


def _user(role: Role = Role.EDITOR) -> CurrentUser:
    return CurrentUser(token="token", role=role, display_name="User")


def test_require_project_access_accepts_existing_project() -> None:
    project_id = uuid4()
    conn = _Conn([{"id": project_id}])

    require_project_access(conn, project_id=project_id, user=_user())

    assert conn.cursor_obj.executed


def test_require_project_access_raises_404_for_missing_project() -> None:
    with pytest.raises(HTTPException) as exc:
        require_project_access(_Conn([]), project_id=uuid4(), user=_user())

    assert exc.value.status_code == 404


def test_require_resource_project_access_returns_resource_project_id() -> None:
    project_id = uuid4()

    result = require_resource_project_access(
        _Conn([{"project_id": project_id}, {"id": project_id}]),
        resource_id=uuid4(),
        query="SELECT project_id FROM resource WHERE id = %s",
        not_found_detail="resource not found",
        user=_user(),
    )

    assert result == project_id


def test_require_resource_project_access_raises_404_for_missing_resource() -> None:
    with pytest.raises(HTTPException) as exc:
        require_resource_project_access(
            _Conn([]),
            resource_id=uuid4(),
            query="SELECT project_id FROM resource WHERE id = %s",
            not_found_detail="resource not found",
            user=_user(),
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "resource not found"
