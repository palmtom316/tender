from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest

from tender_backend.core.config import get_settings
from tender_backend.db.migrations import load_initial_schema_sql
from tender_backend.main import app
from tender_backend.test_support.asgi_client import SyncASGIClient


_STANDARD_PROJECT_ID = "00000000-0000-0000-0000-000000000001"
_AUTH_HEADERS = {"Authorization": "Bearer dev-token"}


def _db_url() -> str | None:
    return os.environ.get("DATABASE_URL")


def _apply_extra_schema(conn: psycopg.Connection) -> None:
    conn.execute("""
    ALTER TABLE project
      ADD COLUMN IF NOT EXISTS owner_name TEXT,
      ADD COLUMN IF NOT EXISTS tender_no TEXT,
      ADD COLUMN IF NOT EXISTS project_type VARCHAR(64),
      ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'draft',
      ADD COLUMN IF NOT EXISTS tender_deadline TIMESTAMPTZ,
      ADD COLUMN IF NOT EXISTS created_by VARCHAR(100),
      ADD COLUMN IF NOT EXISTS priority VARCHAR(16) NOT NULL DEFAULT 'normal',
      ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

    CREATE TABLE IF NOT EXISTS standard (
      id UUID PRIMARY KEY,
      standard_code VARCHAR(100) NOT NULL,
      standard_name TEXT NOT NULL,
      version_year VARCHAR(20),
      status VARCHAR(32) NOT NULL DEFAULT 'effective',
      specialty VARCHAR(64),
      document_id UUID REFERENCES document(id) ON DELETE SET NULL,
      processing_status VARCHAR(32) NOT NULL DEFAULT 'pending',
      error_message TEXT,
      processing_started_at TIMESTAMPTZ,
      processing_finished_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS standard_clause (
      id UUID PRIMARY KEY,
      standard_id UUID NOT NULL REFERENCES standard(id) ON DELETE CASCADE,
      parent_id UUID REFERENCES standard_clause(id) ON DELETE CASCADE,
      clause_no VARCHAR(100),
      clause_title TEXT,
      clause_text TEXT NOT NULL,
      summary TEXT,
      tags JSONB NOT NULL DEFAULT '[]'::jsonb,
      page_start INT,
      page_end INT,
      sort_order INT NOT NULL DEFAULT 0,
      clause_type VARCHAR(20) NOT NULL DEFAULT 'normative',
      commentary_clause_id UUID REFERENCES standard_clause(id) ON DELETE SET NULL,
      node_type VARCHAR(20) NOT NULL DEFAULT 'clause',
      node_key VARCHAR(255),
      node_label VARCHAR(100),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS standard_processing_job (
      id UUID PRIMARY KEY,
      standard_id UUID NOT NULL UNIQUE REFERENCES standard(id) ON DELETE CASCADE,
      document_id UUID NOT NULL REFERENCES document(id) ON DELETE CASCADE,
      ocr_status VARCHAR(16) NOT NULL DEFAULT 'queued',
      ocr_error TEXT,
      ocr_started_at TIMESTAMPTZ,
      ocr_finished_at TIMESTAMPTZ,
      ocr_attempts INT NOT NULL DEFAULT 0,
      ai_status VARCHAR(16) NOT NULL DEFAULT 'blocked',
      ai_error TEXT,
      ai_started_at TIMESTAMPTZ,
      ai_finished_at TIMESTAMPTZ,
      ai_attempts INT NOT NULL DEFAULT 0,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS skill_definition (
      id UUID PRIMARY KEY,
      skill_name VARCHAR(255) NOT NULL UNIQUE,
      description TEXT,
      tool_names JSONB NOT NULL DEFAULT '[]'::jsonb,
      prompt_template_id UUID,
      version INT NOT NULL DEFAULT 1,
      active BOOLEAN NOT NULL DEFAULT TRUE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    INSERT INTO project (id, name)
    VALUES ('00000000-0000-0000-0000-000000000001', '规范规程资料库')
    ON CONFLICT DO NOTHING;
    """)
    conn.execute("""
    ALTER TABLE standard_clause
      ADD COLUMN IF NOT EXISTS clause_type VARCHAR(20) NOT NULL DEFAULT 'normative',
      ADD COLUMN IF NOT EXISTS commentary_clause_id UUID REFERENCES standard_clause(id) ON DELETE SET NULL,
      ADD COLUMN IF NOT EXISTS node_type VARCHAR(20) NOT NULL DEFAULT 'clause',
      ADD COLUMN IF NOT EXISTS node_key VARCHAR(255),
      ADD COLUMN IF NOT EXISTS node_label VARCHAR(100);

    ALTER TABLE document
      ADD COLUMN IF NOT EXISTS parser_name TEXT,
      ADD COLUMN IF NOT EXISTS parser_version TEXT,
      ADD COLUMN IF NOT EXISTS raw_payload JSONB;

    ALTER TABLE document_section
      ADD COLUMN IF NOT EXISTS raw_json JSONB,
      ADD COLUMN IF NOT EXISTS text_source VARCHAR(32),
      ADD COLUMN IF NOT EXISTS sort_order INT NOT NULL DEFAULT 0;

    ALTER TABLE document_table
      ADD COLUMN IF NOT EXISTS page_start INT,
      ADD COLUMN IF NOT EXISTS page_end INT,
      ADD COLUMN IF NOT EXISTS table_title TEXT,
      ADD COLUMN IF NOT EXISTS table_html TEXT;

    ALTER TABLE standard_clause
      ADD COLUMN IF NOT EXISTS source_type VARCHAR(20) NOT NULL DEFAULT 'text',
      ADD COLUMN IF NOT EXISTS source_label TEXT;
    """)
    conn.commit()


def _reset_standard_tables(conn: psycopg.Connection) -> None:
    conn.execute("DELETE FROM standard_processing_job;")
    conn.execute("DELETE FROM standard_clause;")
    conn.execute("DELETE FROM standard;")
    conn.execute("DELETE FROM document;")
    conn.execute("DELETE FROM project_file;")
    conn.execute(
        "DELETE FROM project WHERE id <> '00000000-0000-0000-0000-000000000001'"
    )
    conn.commit()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()


@pytest.fixture()
def client(tmp_path: Path, monkeypatch) -> SyncASGIClient:
    db_url = _db_url()
    if not db_url:
        pytest.skip("DATABASE_URL not set; skipping integration test")

    with psycopg.connect(db_url) as conn:
        conn.execute(load_initial_schema_sql())
        _apply_extra_schema(conn)
        _reset_standard_tables(conn)

    import tender_backend.api.standards as standards_api
    import tender_backend.main as main_module

    monkeypatch.setattr(standards_api, "_UPLOAD_DIR", str(tmp_path))
    scheduler_stub = type("_SchedulerStub", (), {"wake": lambda self: None})()
    monkeypatch.setattr(main_module, "ensure_standard_processing_scheduler_started", lambda: scheduler_stub)
    monkeypatch.setattr(standards_api, "ensure_standard_processing_scheduler_started", lambda: scheduler_stub)

    test_client = SyncASGIClient(app)
    test_client.headers.update(_AUTH_HEADERS)
    try:
        yield test_client
    finally:
        test_client.close()
        with psycopg.connect(db_url) as conn:
            _reset_standard_tables(conn)


@pytest.fixture()
def anon_client(tmp_path: Path, monkeypatch) -> SyncASGIClient:
    db_url = _db_url()
    if not db_url:
        pytest.skip("DATABASE_URL not set; skipping integration test")

    with psycopg.connect(db_url) as conn:
        conn.execute(load_initial_schema_sql())
        _apply_extra_schema(conn)
        _reset_standard_tables(conn)

    import tender_backend.api.standards as standards_api
    import tender_backend.main as main_module

    monkeypatch.setattr(standards_api, "_UPLOAD_DIR", str(tmp_path))
    scheduler_stub = type("_SchedulerStub", (), {"wake": lambda self: None})()
    monkeypatch.setattr(main_module, "ensure_standard_processing_scheduler_started", lambda: scheduler_stub)
    monkeypatch.setattr(standards_api, "ensure_standard_processing_scheduler_started", lambda: scheduler_stub)

    test_client = SyncASGIClient(app)
    try:
        yield test_client
    finally:
        test_client.close()
        with psycopg.connect(db_url) as conn:
            _reset_standard_tables(conn)


def _seed_standard(
    *,
    db_url: str,
    tmp_path: Path,
    processing_status: str = "completed",
    ocr_status: str = "completed",
    ai_status: str = "completed",
    storage_key: str | None = None,
    filename: str = "spec.pdf",
) -> dict[str, str]:
    pdf_bytes = b"%PDF-1.7 standard"
    pdf_path = Path(storage_key) if storage_key is not None else (tmp_path / f"{uuid4()}.pdf")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(pdf_bytes)

    project_file_id = uuid4()
    document_id = uuid4()
    standard_id = uuid4()
    root_clause_id = uuid4()
    child_clause_id = uuid4()
    job_id = uuid4()

    with psycopg.connect(db_url) as conn:
        conn.execute(
            """
            INSERT INTO project_file (id, project_id, filename, content_type, size_bytes, storage_key)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (project_file_id, _STANDARD_PROJECT_ID, filename, "application/pdf", len(pdf_bytes), str(pdf_path)),
        )
        conn.execute(
            "INSERT INTO document (id, project_file_id) VALUES (%s, %s)",
            (document_id, project_file_id),
        )
        conn.execute(
            """
            INSERT INTO standard (
              id, standard_code, standard_name, specialty, document_id, processing_status
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (standard_id, "GB 50010", "混凝土结构设计规范", "结构", document_id, processing_status),
        )
        conn.execute(
            """
            INSERT INTO standard_processing_job (
              id, standard_id, document_id, ocr_status, ai_status
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (job_id, standard_id, document_id, ocr_status, ai_status),
        )
        conn.execute(
            """
            INSERT INTO standard_clause (
              id, standard_id, parent_id, clause_no, clause_title, clause_text,
              summary, tags, page_start, page_end, sort_order, clause_type
            ) VALUES (%s, %s, NULL, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
            """,
            (
                root_clause_id,
                standard_id,
                "3",
                "总则",
                "混凝土结构应符合本规范要求。",
                "总则摘要",
                '["结构"]',
                12,
                12,
                1,
                "normative",
            ),
        )
        conn.execute(
            """
            INSERT INTO standard_clause (
              id, standard_id, parent_id, clause_no, clause_title, clause_text,
              summary, tags, page_start, page_end, sort_order, clause_type
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
            """,
            (
                child_clause_id,
                standard_id,
                root_clause_id,
                "3.2.1",
                "材料要求",
                "混凝土强度等级不应低于 C30。",
                "规定混凝土最低强度等级。",
                '["结构","混凝土"]',
                15,
                15,
                2,
                "normative",
            ),
        )
        conn.commit()

    return {
        "standard_id": str(standard_id),
        "document_id": str(document_id),
        "project_file_id": str(project_file_id),
        "root_clause_id": str(root_clause_id),
        "child_clause_id": str(child_clause_id),
        "pdf_path": str(pdf_path),
        "pdf_bytes": pdf_bytes.decode("latin1"),
    }


def test_reset_standard_tables_removes_seeded_standard(tmp_path: Path) -> None:
    db_url = _db_url()
    if not db_url:
        pytest.skip("DATABASE_URL not set; skipping integration test")

    with psycopg.connect(db_url) as conn:
        conn.execute(load_initial_schema_sql())
        _apply_extra_schema(conn)
        _seed_standard(db_url=db_url, tmp_path=tmp_path)

        _reset_standard_tables(conn)

        assert conn.execute("SELECT count(*) FROM standard;").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM standard_processing_job;").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM document;").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM project_file;").fetchone()[0] == 0


def test_list_standards_marks_pytest_temp_file_as_dev_artifact(client: TestClient, tmp_path: Path) -> None:
    db_url = _db_url()
    assert db_url is not None

    _seed_standard(
        db_url=db_url,
        tmp_path=tmp_path,
        storage_key="/tmp/pytest-of-root/pytest-99/test-case/spec.pdf",
    )

    response = client.get("/api/standards")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["is_dev_artifact"] is True


def test_list_standards_leaves_regular_uploaded_file_unmarked(client: TestClient, tmp_path: Path) -> None:
    db_url = _db_url()
    assert db_url is not None

    _seed_standard(
        db_url=db_url,
        tmp_path=tmp_path,
        storage_key="/workspace/data/standards/gb50010.pdf",
        filename="gb50010.pdf",
    )

    response = client.get("/api/standards")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["is_dev_artifact"] is False


def test_get_standard_viewer_returns_pdf_url_and_clause_tree(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_url = _db_url()
    assert db_url is not None
    seeded = _seed_standard(db_url=db_url, tmp_path=tmp_path)

    response = client.get(f"/api/standards/{seeded['standard_id']}/viewer")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == seeded["standard_id"]
    assert payload["document_id"] == seeded["document_id"]
    assert payload["pdf_url"].endswith(f"/api/standards/{seeded['standard_id']}/pdf")
    assert len(payload["clause_tree"]) == 1
    assert payload["clause_tree"][0]["children"][0]["id"] == seeded["child_clause_id"]
    assert payload["clause_tree"][0]["children"][0]["source_type"] == "text"


def test_get_standard_viewer_includes_clause_source_metadata(
    client: SyncASGIClient,
    tmp_path: Path,
) -> None:
    db_url = _db_url()
    assert db_url is not None
    seeded = _seed_standard(db_url=db_url, tmp_path=tmp_path)

    with psycopg.connect(db_url) as conn:
        conn.execute(
            """
            UPDATE standard_clause
            SET source_type = 'table',
                source_label = '表格: 主要参数'
            WHERE id = %s
            """,
            (seeded["child_clause_id"],),
        )
        conn.commit()

    response = client.get(f"/api/standards/{seeded['standard_id']}/viewer")

    assert response.status_code == 200
    child = response.json()["clause_tree"][0]["children"][0]
    assert child["source_type"] == "table"
    assert child["source_label"] == "表格: 主要参数"


def test_get_standard_parse_assets_returns_parser_sections_and_tables(
    client: SyncASGIClient,
    tmp_path: Path,
) -> None:
    db_url = _db_url()
    assert db_url is not None
    seeded = _seed_standard(db_url=db_url, tmp_path=tmp_path)
    section_id = uuid4()
    table_id = uuid4()

    with psycopg.connect(db_url) as conn:
        conn.execute(
            """
            UPDATE document
            SET parser_name = 'mineru',
                parser_version = 'v1',
                raw_payload = %s::jsonb
            WHERE id = %s
            """,
            ('{"batch_id":"batch-123"}', seeded["document_id"]),
        )
        conn.execute(
            """
            INSERT INTO document_section
              (id, document_id, section_code, title, level, page_start, page_end, text, text_source, sort_order, raw_json)
            VALUES
              (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                section_id, seeded["document_id"], "3", "总则", 1, 12, 12, "正文内容",
                "mineru_markdown", 0, '{"page_number":12,"markdown":"3 总则\\n正文内容"}',
            ),
        )
        conn.execute(
            """
            INSERT INTO document_table
              (id, document_id, section_id, page, page_start, page_end, table_title, table_html, raw_json)
            VALUES
              (%s, %s, NULL, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                table_id, seeded["document_id"], 13, 13, 13, "主要参数",
                "<table><tr><td>额定电压</td><td>10kV</td></tr></table>",
                '{"page":13,"title":"主要参数"}',
            ),
        )
        conn.commit()

    response = client.get(f"/api/standards/{seeded['standard_id']}/parse-assets")

    assert response.status_code == 200
    payload = response.json()
    assert payload["standard_id"] == seeded["standard_id"]
    assert payload["document"]["parser_name"] == "mineru"
    assert payload["document"]["raw_payload"]["batch_id"] == "batch-123"
    assert payload["document"]["raw_payload"]["pages"] == [
        {
            "page_number": 12,
            "markdown": "3 总则\n正文内容",
            "raw_page": {"page_number": 12, "markdown": "3 总则\n正文内容"},
            "source_ref": f"document_section:{section_id}",
        }
    ]
    assert payload["document"]["raw_payload"]["tables"] == [
        {
            "source_ref": f"table:{table_id}",
            "page_start": 13,
            "page_end": 13,
            "table_title": "主要参数",
            "table_html": "<table><tr><td>额定电压</td><td>10kV</td></tr></table>",
            "raw_json": {"page": 13, "title": "主要参数"},
        }
    ]
    assert payload["document"]["raw_payload"]["full_markdown"] == "3 总则\n正文内容"
    assert payload["sections"][0]["text_source"] == "mineru_markdown"
    assert payload["sections"][0]["raw_json"]["page_number"] == 12
    assert payload["tables"][0]["table_title"] == "主要参数"
    assert payload["tables"][0]["table_html"].startswith("<table>")


def test_get_standard_quality_report_returns_gates_metrics_and_skill_recommendations(
    client: SyncASGIClient,
    tmp_path: Path,
) -> None:
    db_url = _db_url()
    assert db_url is not None
    seeded = _seed_standard(db_url=db_url, tmp_path=tmp_path)
    section_id = uuid4()
    skill_id = uuid4()

    with psycopg.connect(db_url) as conn:
        conn.execute(
            """
            INSERT INTO document_section
              (id, document_id, section_code, title, level, page_start, page_end, text, text_source, sort_order)
            VALUES
              (%s, %s, %s, %s, %s, NULL, NULL, %s, %s, %s)
            """,
            (
                section_id,
                seeded["document_id"],
                "1",
                "总则",
                1,
                "正文内容",
                "mineru_markdown",
                0,
            ),
        )
        conn.execute(
            """
            INSERT INTO skill_definition
              (id, skill_name, description, tool_names, version, active)
            VALUES
              (%s, %s, %s, %s::jsonb, %s, %s)
            """,
            (
                skill_id,
                "mineru-standard-bundle",
                "OCR 质量复盘工具",
                '["run_mineru_standard_bundle"]',
                1,
                True,
            ),
        )
        conn.commit()

    response = client.get(f"/api/standards/{seeded['standard_id']}/quality-report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["standard_id"] == seeded["standard_id"]
    assert payload["report"]["overview"]["status"] == "fail"
    assert payload["report"]["metrics"]["raw_section_count"] == 1
    assert payload["report"]["metrics"]["section_anchor_coverage"] == 0.0
    assert payload["report"]["gates"][0]["code"] == "section_anchor_coverage"
    assert payload["report"]["recommended_skills"][0]["skill_name"] == "mineru-standard-bundle"
    assert payload["report"]["recommended_skills"][0]["active"] is True


def test_get_standard_viewer_nests_commentary_under_matching_clause(
    client: TestClient,
    tmp_path: Path,
) -> None:
    db_url = _db_url()
    assert db_url is not None
    seeded = _seed_standard(db_url=db_url, tmp_path=tmp_path)
    commentary_id = uuid4()

    with psycopg.connect(db_url) as conn:
        conn.execute(
            """
            INSERT INTO standard_clause (
              id, standard_id, parent_id, clause_no, clause_title, clause_text,
              summary, tags, page_start, page_end, sort_order, clause_type, commentary_clause_id
            ) VALUES (%s, %s, NULL, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
            """,
            (
                commentary_id,
                seeded["standard_id"],
                "3.2.1",
                "条文说明",
                "说明内容",
                "说明摘要",
                '["混凝土"]',
                18,
                18,
                3,
                "commentary",
                seeded["child_clause_id"],
            ),
        )
        conn.commit()

    response = client.get(f"/api/standards/{seeded['standard_id']}/viewer")

    assert response.status_code == 200
    payload = response.json()
    child = payload["clause_tree"][0]["children"][0]
    assert len(child["children"]) == 1
    assert child["children"][0]["id"] == str(commentary_id)
    assert child["children"][0]["clause_type"] == "commentary"


def test_get_standard_viewer_returns_outline_first_tree(
    client: TestClient,
    tmp_path: Path,
) -> None:
    db_url = _db_url()
    assert db_url is not None
    seeded = _seed_standard(db_url=db_url, tmp_path=tmp_path)

    with psycopg.connect(db_url) as conn:
        conn.execute(
            """
            INSERT INTO document_section
              (id, document_id, section_code, title, level, page_start, page_end, text)
            VALUES
              (%s, %s, %s, %s, %s, %s, %s, %s),
              (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                uuid4(), seeded["document_id"], "3", "总则", 1, 12, 12, None,
                uuid4(), seeded["document_id"], "3.2", "材料", 2, 15, 15, None,
            ),
        )
        conn.commit()

    response = client.get(f"/api/standards/{seeded['standard_id']}/viewer")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["clause_tree"]) == 1
    assert payload["clause_tree"][0]["clause_no"] == "3"
    assert payload["clause_tree"][0]["clause_type"] == "normative"
    assert payload["clause_tree"][0]["children"][0]["clause_no"] == "3.2"
    assert payload["clause_tree"][0]["children"][0]["clause_type"] == "outline"
    assert payload["clause_tree"][0]["children"][0]["children"][0]["id"] == seeded["child_clause_id"]


def test_standard_endpoints_require_authentication(
    anon_client: TestClient,
    tmp_path: Path,
) -> None:
    db_url = _db_url()
    assert db_url is not None
    seeded = _seed_standard(db_url=db_url, tmp_path=tmp_path)

    list_response = anon_client.get("/api/standards")
    assert list_response.status_code == 401

    search_response = anon_client.get("/api/standards/search", params={"q": "混凝土"})
    assert search_response.status_code == 401

    delete_response = anon_client.delete(f"/api/standards/{seeded['standard_id']}")
    assert delete_response.status_code == 401


def test_get_standard_pdf_streams_uploaded_pdf(client: TestClient, tmp_path: Path) -> None:
    db_url = _db_url()
    assert db_url is not None
    seeded = _seed_standard(db_url=db_url, tmp_path=tmp_path)

    response = client.get(f"/api/standards/{seeded['standard_id']}/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content == seeded["pdf_bytes"].encode("latin1")


def test_standard_search_returns_enriched_hits_with_db_fallback(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_url = _db_url()
    assert db_url is not None
    seeded = _seed_standard(db_url=db_url, tmp_path=tmp_path)

    import tender_backend.api.standards as standards_api

    async def fake_search_clauses(query: str, *, specialty: str | None = None, top_k: int = 5) -> list[dict]:
        assert query == "混凝土"
        assert specialty is None
        return [
            {
                "clause_id": seeded["child_clause_id"],
                "clause_no": "3.2.1",
                "tags": ["结构", "混凝土"],
                "summary": "规定混凝土最低强度等级。",
            }
        ]

    monkeypatch.setattr(standards_api, "search_standard_clauses", fake_search_clauses, raising=False)

    response = client.get("/api/standards/search", params={"q": "混凝土"})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["standard_id"] == seeded["standard_id"]
    assert payload[0]["standard_name"] == "混凝土结构设计规范"
    assert payload[0]["specialty"] == "结构"
    assert payload[0]["clause_id"] == seeded["child_clause_id"]
    assert payload[0]["page_start"] == 15
    assert payload[0]["page_end"] == 15


def test_standard_search_drops_hits_without_resolvable_identifiers(
    client: TestClient,
    monkeypatch,
) -> None:
    import tender_backend.api.standards as standards_api

    async def fake_search_clauses(query: str, *, specialty: str | None = None, top_k: int = 5) -> list[dict]:
        assert query == "孤立条款"
        return [
            {
                "summary": "缺少标识信息的脏索引命中",
                "tags": ["脏数据"],
            }
        ]

    monkeypatch.setattr(standards_api, "search_standard_clauses", fake_search_clauses, raising=False)

    response = client.get("/api/standards/search", params={"q": "孤立条款"})

    assert response.status_code == 200
    assert response.json() == []


def test_standard_search_batches_db_fallback_for_multiple_hits(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_url = _db_url()
    assert db_url is not None
    seeded = _seed_standard(db_url=db_url, tmp_path=tmp_path)

    import tender_backend.api.standards as standards_api

    second_clause_id = str(uuid4())
    captured: dict[str, object] = {}

    async def fake_search_clauses(query: str, *, specialty: str | None = None, top_k: int = 5) -> list[dict]:
        assert query == "结构"
        return [
            {"clause_id": seeded["child_clause_id"], "summary": "命中一"},
            {"clause_id": second_clause_id, "summary": "命中二"},
        ]

    def fake_get_clauses_by_ids(conn, clause_ids):
        captured["clause_ids"] = [str(clause_id) for clause_id in clause_ids]
        return {
            seeded["child_clause_id"]: {
                "id": seeded["child_clause_id"],
                "standard_id": seeded["standard_id"],
                "standard_name": "混凝土结构设计规范",
                "specialty": "结构",
                "clause_no": "3.2.1",
                "page_start": 15,
                "page_end": 15,
                "tags": ["结构", "混凝土"],
            },
            second_clause_id: {
                "id": second_clause_id,
                "standard_id": seeded["standard_id"],
                "standard_name": "混凝土结构设计规范",
                "specialty": "结构",
                "clause_no": "3.2.2",
                "page_start": 16,
                "page_end": 16,
                "tags": ["结构"],
            },
        }

    def fail_get_clause(*args, **kwargs):
        pytest.fail("search fallback should batch clause lookups")

    monkeypatch.setattr(standards_api, "search_standard_clauses", fake_search_clauses, raising=False)
    monkeypatch.setattr(standards_api._repo, "get_clauses_by_ids", fake_get_clauses_by_ids, raising=False)
    monkeypatch.setattr(standards_api._repo, "get_clause", fail_get_clause)

    response = client.get("/api/standards/search", params={"q": "结构"})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert captured["clause_ids"] == [seeded["child_clause_id"], second_clause_id]
    assert payload[1]["clause_no"] == "3.2.2"


def test_standard_search_drops_stale_index_hits_without_live_db_clause(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_url = _db_url()
    assert db_url is not None
    seeded = _seed_standard(db_url=db_url, tmp_path=tmp_path)

    import tender_backend.api.standards as standards_api

    stale_clause_id = str(uuid4())

    async def fake_search_clauses(query: str, *, specialty: str | None = None, top_k: int = 5) -> list[dict]:
        assert query == "变压器"
        return [
            {
                "standard_id": str(uuid4()),
                "standard_name": "已删除的旧规范",
                "clause_id": stale_clause_id,
                "clause_no": "9.9.9",
                "summary": "陈旧索引命中",
                "page_start": 99,
                "page_end": 99,
                "tags": ["脏数据"],
            },
            {
                "clause_id": seeded["child_clause_id"],
                "summary": "有效命中",
            },
        ]

    monkeypatch.setattr(standards_api, "search_standard_clauses", fake_search_clauses, raising=False)

    response = client.get("/api/standards/search", params={"q": "变压器"})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["clause_id"] == seeded["child_clause_id"]
    assert payload[0]["standard_id"] == seeded["standard_id"]


def test_delete_standard_removes_completed_standard(client: TestClient, tmp_path: Path) -> None:
    db_url = _db_url()
    assert db_url is not None
    seeded = _seed_standard(db_url=db_url, tmp_path=tmp_path)

    import tender_backend.api.standards as standards_api

    captured: dict[str, object] = {}

    async def fake_delete_from_index(*, standard_id: str) -> None:
        captured["standard_id"] = standard_id

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(standards_api, "delete_standard_clauses_from_index", fake_delete_from_index, raising=False)

    response = client.delete(f"/api/standards/{seeded['standard_id']}")

    assert response.status_code == 200
    assert response.json()["standard_id"] == seeded["standard_id"]
    assert captured == {"standard_id": seeded["standard_id"]}

    detail = client.get(f"/api/standards/{seeded['standard_id']}")
    assert detail.status_code == 404

    monkeypatch.undo()


def test_delete_standard_blocks_active_processing(client: TestClient, tmp_path: Path) -> None:
    db_url = _db_url()
    assert db_url is not None
    seeded = _seed_standard(
        db_url=db_url,
        tmp_path=tmp_path,
        processing_status="processing",
        ocr_status="completed",
        ai_status="running",
    )

    response = client.delete(f"/api/standards/{seeded['standard_id']}")

    assert response.status_code == 409
    assert "processing" in response.json()["detail"].lower()


def test_delete_standard_does_not_invoke_asyncio_run(client: TestClient, tmp_path: Path) -> None:
    db_url = _db_url()
    assert db_url is not None
    seeded = _seed_standard(db_url=db_url, tmp_path=tmp_path)

    import tender_backend.api.standards as standards_api

    captured: dict[str, object] = {}

    async def fake_delete_from_index(*, standard_id: str) -> None:
        captured["standard_id"] = standard_id

    def fail_asyncio_run(*args, **kwargs):
        raise AssertionError("delete endpoint must not call asyncio.run inside request handling")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(standards_api, "delete_standard_clauses_from_index", fake_delete_from_index, raising=False)
    monkeypatch.setattr(standards_api, "asyncio", SimpleNamespace(run=fail_asyncio_run), raising=False)

    response = client.delete(f"/api/standards/{seeded['standard_id']}")

    assert response.status_code == 200
    assert captured == {"standard_id": seeded["standard_id"]}

    monkeypatch.undo()
