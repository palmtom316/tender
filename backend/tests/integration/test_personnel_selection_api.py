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


def _apply_personnel_schema(conn: psycopg.Connection) -> None:
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

    CREATE TABLE IF NOT EXISTS person_profile (
      id UUID PRIMARY KEY,
      library_company_id UUID REFERENCES library_company(id) ON DELETE CASCADE,
      full_name TEXT NOT NULL,
      gender TEXT,
      age INT,
      education TEXT,
      title TEXT,
      role_name TEXT,
      specialty TEXT,
      years_experience INT,
      phone TEXT,
      email TEXT,
      resume_text TEXT,
      profile_json JSONB NOT NULL DEFAULT '{}'::jsonb,
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

    CREATE TABLE IF NOT EXISTS project_personnel_selection (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      person_id UUID NOT NULL REFERENCES person_profile(id) ON DELETE RESTRICT,
      intended_role TEXT,
      snapshot_json JSONB,
      display_order INT NOT NULL DEFAULT 0,
      confirmed BOOLEAN NOT NULL DEFAULT FALSE,
      confirmed_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE UNIQUE INDEX IF NOT EXISTS ux_pps_project_person ON project_personnel_selection(project_id, person_id);
    """)
    conn.commit()


def _reset_personnel_tables(conn: psycopg.Connection) -> None:
    conn.execute("DELETE FROM project_personnel_selection;")
    conn.execute("DELETE FROM evidence_asset;")
    conn.execute("DELETE FROM person_profile;")
    conn.execute("DELETE FROM project_member;")
    conn.execute("DELETE FROM library_company;")
    conn.execute("DELETE FROM user_session;")
    conn.execute("DELETE FROM app_user;")
    conn.execute("DELETE FROM project;")
    conn.commit()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def test_personnel_selection_flow() -> None:
    db_url = _db_url()
    if not db_url:
        pytest.skip("DATABASE_URL not set; skipping integration test")

    project_id = uuid4()
    other_project_id = uuid4()
    person_id = uuid4()
    library_company_id = uuid4()

    with psycopg.connect(db_url) as conn:
        _apply_personnel_schema(conn)
        _reset_personnel_tables(conn)
        conn.execute(
            "INSERT INTO library_company (id, company_key, company_name) VALUES (%s, %s, %s)",
            (library_company_id, "cq-demo-personnel", "重庆示例电力工程有限责任公司"),
        )
        conn.execute("INSERT INTO project (id, name) VALUES (%s, %s)", (project_id, "测试项目"))
        conn.execute("INSERT INTO project (id, name) VALUES (%s, %s)", (other_project_id, "其他项目"))
        conn.execute(
            """
            INSERT INTO person_profile (
              id, library_company_id, full_name, gender, age, education, title, role_name, specialty, years_experience, phone
            ) VALUES (%s, %s, '张三', '男', 36, '本科', '高级工程师', '项目经理', '电力工程', 12, '13800000000')
            """,
            (person_id, library_company_id),
        )
        conn.execute(
            """
            INSERT INTO evidence_asset (
              id, library_company_id, owner_type, owner_id, asset_name, asset_domain, asset_category,
              asset_type, file_name, file_path, metadata_json
            ) VALUES (%s, %s, 'person_profile', %s, '一级建造师证书', 'personnel', 'practice_certificate', 'practice_certificate', 'cert.pdf', '/tmp/cert.pdf', '{"cert_no":"渝123"}'::jsonb)
            """,
            (uuid4(), library_company_id, person_id),
        )
        conn.commit()

    client = SyncASGIClient(app)
    client.headers.update(_AUTH_HEADERS)
    try:
        candidates = client.get(f"/api/projects/{project_id}/personnel/people?q=张三")
        assert candidates.status_code == 200
        assert len(candidates.json()) == 1

        created = client.post(
            f"/api/projects/{project_id}/personnel/selections",
            json={"person_id": str(person_id)},
        )
        assert created.status_code == 201
        selection_id = UUID(created.json()["id"])
        assert created.json()["confirmed"] is False

        duplicate = client.post(
            f"/api/projects/{project_id}/personnel/selections",
            json={"person_id": str(person_id)},
        )
        assert duplicate.status_code == 201
        assert duplicate.json()["id"] == str(selection_id)

        wrong_project_update = client.put(
            f"/api/projects/{other_project_id}/personnel/selections/{selection_id}",
            json={"intended_role": "不应写入"},
        )
        assert wrong_project_update.status_code == 404

        unchanged = client.get(f"/api/projects/{project_id}/personnel/selections")
        assert unchanged.status_code == 200
        assert unchanged.json()[0]["intended_role"] == "项目经理"

        updated = client.put(
            f"/api/projects/{project_id}/personnel/selections/{selection_id}",
            json={"intended_role": "项目负责人", "display_order": 2},
        )
        assert updated.status_code == 200
        assert updated.json()["intended_role"] == "项目负责人"

        confirmed = client.post(f"/api/projects/{project_id}/personnel/selections/confirm")
        assert confirmed.status_code == 200
        snapshot = confirmed.json()[0]["snapshot_json"]
        assert snapshot["full_name"] == "张三"
        assert snapshot["intended_role"] == "项目负责人"
        assert snapshot["attachments"][0]["asset_category"] == "practice_certificate"

        preview = client.get(f"/api/projects/{project_id}/personnel/preview")
        assert preview.status_code == 200
        assert preview.json()[0]["姓名"] == "张三"
        assert preview.json()[0]["拟任岗位"] == "项目负责人"
        assert "执业资格证" in preview.json()[0]["主要证件/附件"]
    finally:
        client.close()
