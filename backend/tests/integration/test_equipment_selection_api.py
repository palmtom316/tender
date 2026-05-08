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


def _apply_equipment_schema(conn: psycopg.Connection) -> None:
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

    CREATE TABLE IF NOT EXISTS project_member (
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      user_id UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
      role TEXT NOT NULL DEFAULT 'editor',
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      PRIMARY KEY (project_id, user_id)
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
    CREATE UNIQUE INDEX IF NOT EXISTS ux_pes_project_asset ON project_equipment_selection(project_id, asset_id);
    """)
    conn.commit()


def _reset_equipment_tables(conn: psycopg.Connection) -> None:
    conn.execute("DELETE FROM project_equipment_selection;")
    conn.execute("DELETE FROM company_asset;")
    conn.execute("DELETE FROM evidence_asset;")
    conn.execute("DELETE FROM project_member;")
    conn.execute("DELETE FROM library_company;")
    conn.execute("DELETE FROM user_session;")
    conn.execute("DELETE FROM app_user;")
    conn.execute("DELETE FROM project;")
    conn.commit()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def test_equipment_selection_flow() -> None:
    db_url = _db_url()
    if not db_url:
      pytest.skip("DATABASE_URL not set; skipping integration test")

    project_id = uuid4()
    other_project_id = uuid4()
    asset_id = uuid4()

    with psycopg.connect(db_url) as conn:
        _apply_equipment_schema(conn)
        _reset_equipment_tables(conn)
        library_company_id = uuid4()
        conn.execute(
            "INSERT INTO library_company (id, company_key, company_name) VALUES (%s, %s, %s)",
            (library_company_id, "REDACTED", "REDACTED"),
        )
        conn.execute("INSERT INTO project (id, name) VALUES (%s, %s)", (project_id, "测试项目"))
        conn.execute("INSERT INTO project (id, name) VALUES (%s, %s)", (other_project_id, "其他项目"))
        conn.execute(
            """
            INSERT INTO company_asset (
              id, library_company_id, asset_type, name, spec_model, serial_no, manufacturer,
              quantity, unit, ownership, technical_condition, extras
            ) VALUES (%s, %s, 'vehicle', '斗臂车', 'DFL5160', '渝A12345', '东风', 1, '辆', 'self', '良好', '{"vehicle_type":"aerial_bucket"}'::jsonb)
            """,
            (asset_id, library_company_id),
        )
        conn.commit()

    client = SyncASGIClient(app)
    client.headers.update(_AUTH_HEADERS)
    try:
        candidates = client.get(f"/api/projects/{project_id}/equipment/assets?asset_type=vehicle&q=DFL")
        assert candidates.status_code == 200
        assert len(candidates.json()) == 1

        created = client.post(
            f"/api/projects/{project_id}/equipment/selections",
            json={"asset_id": str(asset_id)},
        )
        assert created.status_code == 201
        selection_id = UUID(created.json()["id"])
        assert created.json()["confirmed"] is False

        duplicate = client.post(
            f"/api/projects/{project_id}/equipment/selections",
            json={"asset_id": str(asset_id)},
        )
        assert duplicate.status_code == 201
        assert duplicate.json()["id"] == str(selection_id)

        wrong_project_update = client.put(
            f"/api/projects/{other_project_id}/equipment/selections/{selection_id}",
            json={"intended_role": "不应写入"},
        )
        assert wrong_project_update.status_code == 404

        unchanged = client.get(f"/api/projects/{project_id}/equipment/selections")
        assert unchanged.status_code == 200
        assert unchanged.json()[0]["intended_role"] is None

        updated = client.put(
            f"/api/projects/{project_id}/equipment/selections/{selection_id}",
            json={"intended_role": "配电主线", "display_order": 3},
        )
        assert updated.status_code == 200
        assert updated.json()["intended_role"] == "配电主线"
        assert updated.json()["display_order"] == 3

        confirmed = client.post(f"/api/projects/{project_id}/equipment/selections/confirm")
        assert confirmed.status_code == 200
        assert len(confirmed.json()) == 1
        snapshot = confirmed.json()[0]["snapshot_json"]
        assert snapshot["name"] == "斗臂车"
        assert snapshot["spec_model"] == "DFL5160"
        assert snapshot["extras"]["vehicle_type"] == "aerial_bucket"
        assert confirmed.json()[0]["confirmed"] is True

        listed = client.get(f"/api/projects/{project_id}/equipment/selections")
        assert listed.status_code == 200
        assert len(listed.json()) == 1
        assert listed.json()[0]["snapshot_json"]["serial_no"] == "渝A12345"
    finally:
        client.close()
