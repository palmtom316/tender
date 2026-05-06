from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

import tender_backend.api.parse as parse_api
import tender_backend.api.projects as projects_api
import tender_backend.api.users as users_api
import tender_backend.core.security as security
from tender_backend.db.deps import get_db_conn
from tender_backend.main import app
from tender_backend.test_support.asgi_client import SyncASGIClient


@dataclass(frozen=True)
class _UserRow:
    id: UUID
    username: str
    display_name: str
    role: str
    enabled: bool = True
    created_at: datetime = datetime(2026, 1, 1, tzinfo=timezone.utc)
    updated_at: datetime = datetime(2026, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class _ProjectRow:
    id: UUID
    name: str


@dataclass(frozen=True)
class _ParseJobRow:
    id: UUID
    document_id: UUID
    provider: str = "mineru"
    provider_job_id: str | None = None
    status: str = "failed"
    error: str | None = None


class _FakeConn:
    pass


class _FakeUsers:
    def list_all(self, _conn):
        return []

    def create(self, _conn, *, username: str, password: str, display_name: str, role: str):
        return _UserRow(id=uuid4(), username=username, display_name=display_name, role=role)

    def get_by_id(self, _conn, user_id: UUID):
        return _UserRow(id=user_id, username="existing", display_name="Existing", role="editor")

    def update(self, _conn, user_id: UUID, **_fields):
        return _UserRow(id=user_id, username="existing", display_name="Existing", role="editor")

    def delete(self, _conn, _user_id: UUID):
        return True


class _FakeProjects:
    created_for_user_id: UUID | None = None

    def create(self, _conn, *, name: str):
        return _ProjectRow(id=uuid4(), name=name)

    def create_for_user(self, _conn, *, name: str, user_id: UUID | None):
        self.created_for_user_id = user_id
        return _ProjectRow(id=uuid4(), name=name)

    def list(self, _conn):
        return []

    def list_for_user(self, _conn, *, user):
        return self.list(_conn)

    def delete(self, _conn, *, project_id: UUID):
        return True


class _FakeParseJobs:
    def find_active_for_document(self, _conn, *, document_id: UUID):
        return None

    def create(self, _conn, *, document_id: UUID, provider: str, status: str):
        return _ParseJobRow(id=uuid4(), document_id=document_id, provider=provider, status=status)

    def get(self, _conn, *, parse_job_id: UUID):
        return _ParseJobRow(id=parse_job_id, document_id=uuid4())

    def latest_for_document(self, _conn, *, document_id: UUID):
        return _ParseJobRow(id=uuid4(), document_id=document_id)


class _FakeSessions:
    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id

    def get_user_by_token(self, _conn, token: str):
        if token != "session-token":
            return None
        return _UserRow(
            id=self.user_id,
            username="session-user",
            display_name="Session User",
            role="editor",
        )


@pytest.fixture(autouse=True)
def _isolated_authz(monkeypatch: pytest.MonkeyPatch):
    app.dependency_overrides[get_db_conn] = lambda: _FakeConn()
    monkeypatch.setenv(
        "AUTH_TOKENS",
        "admin-token:admin:Admin,editor-token:editor:Editor,reviewer-token:reviewer:Reviewer",
    )
    monkeypatch.setattr(security, "_token_map", None)
    monkeypatch.setattr(users_api, "_repo", _FakeUsers())
    monkeypatch.setattr(projects_api, "_repo", _FakeProjects())
    monkeypatch.setattr(parse_api, "_jobs", _FakeParseJobs())
    yield
    app.dependency_overrides.clear()
    monkeypatch.setattr(security, "_token_map", None)


def _client(token: str | None = None) -> SyncASGIClient:
    client = SyncASGIClient(app)
    if token:
        client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_user_management_requires_admin() -> None:
    anonymous = _client()
    assert anonymous.get("/api/users").status_code == 401
    assert anonymous.post(
        "/api/users",
        json={
            "username": "xuser",
            "password": "secret123",
            "display_name": "X User",
            "role": "editor",
        },
    ).status_code == 401

    editor = _client("editor-token")
    assert editor.get("/api/users").status_code == 403
    assert editor.post(
        "/api/users",
        json={
            "username": "xuser",
            "password": "secret123",
            "display_name": "X User",
            "role": "editor",
        },
    ).status_code == 403


def test_project_routes_require_authentication_and_write_roles() -> None:
    anonymous = _client()
    assert anonymous.get("/api/projects").status_code == 401
    assert anonymous.post("/api/projects", json={"name": "demo"}).status_code == 401

    reviewer = _client("reviewer-token")
    assert reviewer.post("/api/projects", json={"name": "demo"}).status_code == 403
    assert reviewer.delete(f"/api/projects/{uuid4()}").status_code == 403

    editor = _client("editor-token")
    assert editor.post("/api/projects", json={"name": "demo"}).status_code == 200

    admin = _client("admin-token")
    assert admin.post("/api/projects", json={"name": "demo"}).status_code == 200
    assert admin.delete(f"/api/projects/{uuid4()}").status_code == 200


def test_project_create_receives_session_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    repo = _FakeProjects()
    monkeypatch.setattr(security, "_sessions", _FakeSessions(user_id))
    monkeypatch.setattr(projects_api, "_repo", repo)

    response = _client("session-token").post("/api/projects", json={"name": "demo"})

    assert response.status_code == 200
    assert repo.created_for_user_id == user_id


def test_legacy_parse_routes_require_authentication() -> None:
    anonymous = _client()
    document_id = uuid4()
    parse_job_id = uuid4()

    assert anonymous.post(
        f"/api/documents/{document_id}/parse-jobs",
        json={"force_reparse": True},
    ).status_code == 401
    assert anonymous.get(f"/api/parse-jobs/{parse_job_id}").status_code == 401
    assert anonymous.get(f"/api/documents/{document_id}/parse-result").status_code == 401
    assert anonymous.post(f"/api/parse-jobs/{parse_job_id}/retry").status_code == 401
