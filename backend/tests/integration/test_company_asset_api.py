from __future__ import annotations

import os
from uuid import UUID, uuid4

import psycopg
import pytest

from tender_backend.core.config import get_settings
from tender_backend.db.migrations import load_initial_schema_sql
from tender_backend.main import app
from tender_backend.test_support.asgi_client import SyncASGIClient


_AUTH_HEADERS = {"Authorization": "Bearer dev-token"}


def _db_url() -> str | None:
    return os.environ.get("DATABASE_URL")


def _apply_asset_schema(conn: psycopg.Connection) -> None:
    conn.execute(load_initial_schema_sql())
    conn.execute("""
    CREATE TABLE IF NOT EXISTS app_user (
      id UUID PRIMARY KEY,
      username VARCHAR(50) NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      display_name VARCHAR(100) NOT NULL,
      role VARCHAR(20) NOT NULL DEFAULT 'editor',
      enabled BOOLEAN NOT NULL DEFAULT TRUE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS user_session (
      token VARCHAR(64) PRIMARY KEY,
      user_id UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + interval '7 days'
    );

    CREATE TABLE IF NOT EXISTS library_company (
      id UUID PRIMARY KEY,
      company_key TEXT NOT NULL UNIQUE,
      company_name TEXT NOT NULL,
      company_type TEXT,
      enabled BOOLEAN NOT NULL DEFAULT TRUE,
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS evidence_asset (
      id UUID PRIMARY KEY,
      library_company_id UUID REFERENCES library_company(id) ON DELETE CASCADE,
      owner_type TEXT NOT NULL,
      owner_id UUID,
      asset_name TEXT NOT NULL,
      asset_domain VARCHAR(64) NOT NULL DEFAULT 'generic',
      asset_category VARCHAR(64) NOT NULL DEFAULT 'supporting_document',
      asset_type TEXT NOT NULL DEFAULT 'supporting_document',
      file_name TEXT NOT NULL,
      file_path TEXT NOT NULL,
      media_type TEXT,
      issuer_name TEXT,
      issued_on DATE,
      expires_on DATE,
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      sort_order INT NOT NULL DEFAULT 0,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS company_asset (
      id UUID PRIMARY KEY,
      library_company_id UUID NOT NULL REFERENCES library_company(id) ON DELETE CASCADE,
      asset_type TEXT NOT NULL CHECK (asset_type IN ('vehicle','machine','tool','safety')),
      name TEXT NOT NULL,
      spec_model TEXT,
      serial_no TEXT,
      manufacturer TEXT,
      quantity NUMERIC(12,2) NOT NULL DEFAULT 1,
      unit TEXT NOT NULL,
      ownership TEXT NOT NULL CHECK (ownership IN ('self','leased','third_party')),
      acquired_at DATE,
      expires_at DATE,
      technical_condition TEXT,
      status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','maintenance','retired')),
      location TEXT,
      extras JSONB NOT NULL DEFAULT '{}'::jsonb,
      notes TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS project_equipment_selection (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      asset_id UUID NOT NULL REFERENCES company_asset(id) ON DELETE RESTRICT,
      asset_type TEXT NOT NULL,
      intended_role TEXT,
      snapshot_json JSONB,
      display_order INT NOT NULL DEFAULT 0,
      confirmed BOOLEAN NOT NULL DEFAULT FALSE,
      confirmed_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    conn.commit()


def _reset_asset_tables(conn: psycopg.Connection) -> None:
    conn.execute("DELETE FROM project_equipment_selection;")
    conn.execute("DELETE FROM company_asset;")
    conn.execute("DELETE FROM evidence_asset;")
    conn.execute("DELETE FROM library_company;")
    conn.execute("DELETE FROM user_session;")
    conn.execute("DELETE FROM app_user;")
    conn.execute("DELETE FROM project;")
    conn.commit()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def test_company_asset_crud_flow() -> None:
    db_url = _db_url()
    if not db_url:
        pytest.skip("DATABASE_URL not set; skipping integration test")

    with psycopg.connect(db_url) as conn:
        _apply_asset_schema(conn)
        _reset_asset_tables(conn)

    client = SyncASGIClient(app)
    client.headers.update(_AUTH_HEADERS)
    try:
        library_company = client.post(
            "/api/master-data/library-companies",
            json={"company_name": "REDACTED"},
        )
        assert library_company.status_code == 201
        library_company_id = UUID(library_company.json()["id"])

        created = client.post(
            f"/api/master-data/library-companies/{library_company_id}/assets",
            json={
                "asset_type": "vehicle",
                "name": "斗臂车",
                "spec_model": "DFL5160",
                "serial_no": "渝A12345",
                "manufacturer": "东风",
                "quantity": "1",
                "unit": "辆",
                "ownership": "self",
                "technical_condition": "良好",
                "extras": {"vehicle_type": "aerial_bucket"},
            },
        )
        assert created.status_code == 201
        asset_id = UUID(created.json()["id"])
        assert created.json()["status"] == "active"

        listed = client.get(f"/api/master-data/library-companies/{library_company_id}/assets?asset_type=vehicle&q=DFL")
        assert listed.status_code == 200
        assert len(listed.json()) == 1
        assert UUID(listed.json()[0]["id"]) == asset_id

        updated = client.put(
            f"/api/master-data/assets/{asset_id}",
            json={"location": "江北仓库", "status": "maintenance"},
        )
        assert updated.status_code == 200
        assert updated.json()["location"] == "江北仓库"
        assert updated.json()["status"] == "maintenance"

        retired = client.post(f"/api/master-data/assets/{asset_id}/retire")
        assert retired.status_code == 200
        assert retired.json()["status"] == "retired"

        deleted = client.delete(f"/api/master-data/assets/{asset_id}")
        assert deleted.status_code == 200
        assert deleted.json() == {"deleted": True}
    finally:
        client.close()


def test_company_asset_delete_conflict_returns_409() -> None:
    db_url = _db_url()
    if not db_url:
        pytest.skip("DATABASE_URL not set; skipping integration test")

    with psycopg.connect(db_url) as conn:
        _apply_asset_schema(conn)
        _reset_asset_tables(conn)
        library_company_id = uuid4()
        asset_id = uuid4()
        project_id = uuid4()
        conn.execute(
            "INSERT INTO library_company (id, company_key, company_name) VALUES (%s, %s, %s)",
            (library_company_id, "REDACTED", "REDACTED"),
        )
        conn.execute(
            """
            INSERT INTO company_asset (
              id, library_company_id, asset_type, name, quantity, unit, ownership, extras
            ) VALUES (%s, %s, 'vehicle', '斗臂车', 1, '辆', 'self', '{}'::jsonb)
            """,
            (asset_id, library_company_id),
        )
        conn.execute("INSERT INTO project (id, name) VALUES (%s, %s)", (project_id, "测试项目"))
        conn.execute(
            """
            INSERT INTO project_equipment_selection (
              id, project_id, asset_id, asset_type
            ) VALUES (%s, %s, %s, 'vehicle')
            """,
            (uuid4(), project_id, asset_id),
        )
        conn.commit()

    client = SyncASGIClient(app)
    client.headers.update(_AUTH_HEADERS)
    try:
        deleted = client.delete(f"/api/master-data/assets/{asset_id}")
        assert deleted.status_code == 409
        assert "retire it instead" in deleted.json()["detail"]
    finally:
        client.close()
