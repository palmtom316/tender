import os
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from tender_backend.core.config import get_settings
from tender_backend.db.migrations import load_initial_schema_sql
from tender_backend.main import app


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def _db_url() -> str | None:
    return os.environ.get("DATABASE_URL")


def test_project_and_file_flow() -> None:
    db_url = _db_url()
    if not db_url:
        pytest.skip("DATABASE_URL not set; skipping integration test")

    with psycopg.connect(db_url) as conn:
        conn.execute(load_initial_schema_sql())
        conn.execute("DELETE FROM project_file;")
        conn.execute("DELETE FROM project;")
        conn.commit()

    client = TestClient(app)

    res = client.post("/api/projects", json={"name": "demo"})
    assert res.status_code == 200
    project_id = UUID(res.json()["id"])

    res = client.get("/api/projects")
    assert res.status_code == 200
    assert any(UUID(p["id"]) == project_id for p in res.json())

    res = client.post(
        f"/api/projects/{project_id}/files",
        files={"file": ("hello.txt", b"hello", "text/plain")},
    )
    assert res.status_code == 200
    file_id = UUID(res.json()["file_id"])
    assert res.json()["size_bytes"] == 5

    res = client.get(f"/api/projects/{project_id}/files")
    assert res.status_code == 200
    assert any(UUID(f["id"]) == file_id for f in res.json())
