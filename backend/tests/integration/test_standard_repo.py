from __future__ import annotations

import os
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from tender_backend.db.migrations import load_initial_schema_sql
from tender_backend.db.repositories.standard_repo import StandardRepository


_STANDARD_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")


def _db_url() -> str | None:
    return os.environ.get("DATABASE_URL")


def _ensure_schema(conn: psycopg.Connection) -> None:
    conn.execute(load_initial_schema_sql())
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

    """)
    conn.execute("""
    ALTER TABLE standard_clause
      ADD COLUMN IF NOT EXISTS clause_type VARCHAR(20) NOT NULL DEFAULT 'normative',
      ADD COLUMN IF NOT EXISTS commentary_clause_id UUID REFERENCES standard_clause(id) ON DELETE SET NULL,
      ADD COLUMN IF NOT EXISTS node_type VARCHAR(20) NOT NULL DEFAULT 'clause',
      ADD COLUMN IF NOT EXISTS node_key VARCHAR(255),
      ADD COLUMN IF NOT EXISTS node_label VARCHAR(100),
      ADD COLUMN IF NOT EXISTS source_type VARCHAR(20) NOT NULL DEFAULT 'text',
      ADD COLUMN IF NOT EXISTS source_label TEXT;

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
    """)
    conn.execute(
        """
        INSERT INTO project (id, name)
        VALUES (%s, '规范规程资料库')
        ON CONFLICT DO NOTHING;
        """,
        (_STANDARD_PROJECT_ID,),
    )
    conn.commit()


def _reset_standard_tables(conn: psycopg.Connection) -> None:
    conn.rollback()
    conn.execute("DELETE FROM standard_clause;")
    conn.execute("DELETE FROM standard;")
    conn.execute("DELETE FROM document;")
    conn.execute("DELETE FROM project_file;")
    conn.execute("DELETE FROM project WHERE id <> %s;", (_STANDARD_PROJECT_ID,))
    conn.commit()


@pytest.fixture()
def conn() -> psycopg.Connection:
    db_url = _db_url()
    if not db_url:
        pytest.skip("DATABASE_URL not set; skipping integration test")

    conn = psycopg.connect(db_url, row_factory=dict_row)
    _ensure_schema(conn)
    _reset_standard_tables(conn)
    try:
        yield conn
    finally:
        _reset_standard_tables(conn)
        conn.close()


def _create_standard(conn: psycopg.Connection, *, code: str) -> tuple[UUID, UUID]:
    project_file_id = uuid4()
    document_id = uuid4()
    standard_id = uuid4()
    conn.execute(
        """
        INSERT INTO project_file (id, project_id, filename, content_type, size_bytes, storage_key)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (project_file_id, _STANDARD_PROJECT_ID, f"{code}.pdf", "application/pdf", 7, f"standards/{code}.pdf"),
    )
    conn.execute(
        "INSERT INTO document (id, project_file_id) VALUES (%s, %s)",
        (document_id, project_file_id),
    )
    conn.execute(
        """
        INSERT INTO standard (
          id, standard_code, standard_name, document_id, processing_status
        ) VALUES (%s, %s, %s, %s, 'processing')
        """,
        (standard_id, code, f"{code} name", document_id),
    )
    conn.commit()
    return standard_id, document_id


def test_bulk_create_clauses_orders_self_references_before_insert(conn: psycopg.Connection) -> None:
    repo = StandardRepository()
    standard_id, _ = _create_standard(conn, code="GB 1")
    parent_id = uuid4()
    child_id = uuid4()
    commentary_id = uuid4()
    clauses = [
        {
            "id": child_id,
            "standard_id": standard_id,
            "parent_id": parent_id,
            "clause_no": "1.1",
            "clause_title": "child",
            "clause_text": "child text",
            "summary": None,
            "tags": [],
            "page_start": 1,
            "page_end": 1,
            "sort_order": 1,
            "clause_type": "normative",
            "commentary_clause_id": None,
        },
        {
            "id": commentary_id,
            "standard_id": standard_id,
            "parent_id": None,
            "clause_no": "1",
            "clause_title": "commentary",
            "clause_text": "commentary text",
            "summary": None,
            "tags": [],
            "page_start": 1,
            "page_end": 1,
            "sort_order": 2,
            "clause_type": "commentary",
            "commentary_clause_id": parent_id,
        },
        {
            "id": parent_id,
            "standard_id": standard_id,
            "parent_id": None,
            "clause_no": "1",
            "clause_title": "parent",
            "clause_text": "parent text",
            "summary": None,
            "tags": [],
            "page_start": 1,
            "page_end": 1,
            "sort_order": 0,
            "clause_type": "normative",
            "commentary_clause_id": None,
        },
    ]

    inserted = repo.bulk_create_clauses(conn, clauses)

    assert inserted == 3
    rows = conn.execute(
        """
        SELECT id, parent_id, commentary_clause_id
        FROM standard_clause
        WHERE standard_id = %s
        ORDER BY sort_order
        """,
        (standard_id,),
    ).fetchall()
    assert [row["id"] for row in rows] == [parent_id, child_id, commentary_id]
    assert rows[1]["parent_id"] == parent_id
    assert rows[2]["commentary_clause_id"] == parent_id


def test_get_clause_tree_nests_commentary_under_linked_normative_clause(
    conn: psycopg.Connection,
) -> None:
    repo = StandardRepository()
    standard_id, _ = _create_standard(conn, code="GB 2")
    normative_id = uuid4()
    commentary_id = uuid4()

    repo.bulk_create_clauses(conn, [
        {
            "id": normative_id,
            "standard_id": standard_id,
            "parent_id": None,
            "clause_no": "4.5.5",
            "clause_title": "正文条款",
            "clause_text": "正文内容",
            "summary": "正文摘要",
            "tags": [],
            "page_start": 0,
            "page_end": 0,
            "sort_order": 0,
            "clause_type": "normative",
            "commentary_clause_id": None,
        },
        {
            "id": commentary_id,
            "standard_id": standard_id,
            "parent_id": None,
            "clause_no": "4.5.5",
            "clause_title": "条文说明",
            "clause_text": "说明内容",
            "summary": "说明摘要",
            "tags": [],
            "page_start": 12,
            "page_end": 12,
            "sort_order": 1,
            "clause_type": "commentary",
            "commentary_clause_id": normative_id,
        },
    ])

    tree = repo.get_clause_tree(conn, standard_id)

    assert len(tree) == 1
    assert tree[0]["id"] == str(normative_id)
    assert len(tree[0]["children"]) == 1
    assert tree[0]["children"][0]["id"] == str(commentary_id)
    assert tree[0]["children"][0]["clause_type"] == "commentary"


def test_list_document_sections_prefers_explicit_sort_order(
    conn: psycopg.Connection,
) -> None:
    repo = StandardRepository()
    _, document_id = _create_standard(conn, code="GB 3")

    first_id = uuid4()
    second_id = uuid4()

    conn.execute(
        """
        INSERT INTO document_section
          (id, document_id, section_code, title, level, page_start, page_end, text, text_source, sort_order, raw_json)
        VALUES
          (%s, %s, '2', '术语', 1, NULL, NULL, '第二章正文', 'mineru_markdown', 1, '{"page_number": 8}'::jsonb),
          (%s, %s, '1', '总则', 1, NULL, NULL, '第一章正文', 'mineru_markdown', 0, '{"page_number": 7}'::jsonb)
        """,
        (first_id, document_id, second_id, document_id),
    )
    conn.commit()

    rows = repo.list_document_sections(conn, document_id=document_id)

    assert [row["title"] for row in rows] == ["总则", "术语"]
    assert rows[0]["sort_order"] == 0
    assert rows[0]["text_source"] == "mineru_markdown"
    assert rows[0]["raw_json"] == {"page_number": 7}


def test_get_viewer_tree_prefers_outline_and_mounts_ai_nodes(
    conn: psycopg.Connection,
) -> None:
    repo = StandardRepository()
    standard_id, document_id = _create_standard(conn, code="GB 3")
    chapter_id = uuid4()
    clause_id = uuid4()
    item_id = uuid4()
    subitem_id = uuid4()
    commentary_id = uuid4()

    conn.execute(
        """
        INSERT INTO document_section
          (id, document_id, section_code, title, level, page_start, page_end, text)
        VALUES
          (%s, %s, %s, %s, %s, %s, %s, %s),
          (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            uuid4(), document_id, "4", "电力变压器、油浸电抗器", 1, 40, 42, None,
            uuid4(), document_id, "4.3", "绝缘油处理", 2, 43, 44, None,
        ),
    )
    conn.commit()

    repo.bulk_create_clauses(conn, [
        {
            "id": chapter_id,
            "standard_id": standard_id,
            "parent_id": None,
            "clause_no": "4.3",
            "clause_title": "AI 绝缘油处理",
            "clause_text": "绝缘油处理总要求。",
            "summary": "4.3 摘要",
            "tags": ["油处理"],
            "page_start": 43,
            "page_end": 44,
            "sort_order": 0,
            "clause_type": "normative",
            "commentary_clause_id": None,
            "node_type": "clause",
            "node_key": "4.3",
            "node_label": None,
        },
        {
            "id": clause_id,
            "standard_id": standard_id,
            "parent_id": chapter_id,
            "clause_no": "4.3.2",
            "clause_title": "过滤与处理",
            "clause_text": "绝缘油处理应符合下列规定。",
            "summary": "4.3.2 摘要",
            "tags": ["绝缘油"],
            "page_start": 44,
            "page_end": 44,
            "sort_order": 1,
            "clause_type": "normative",
            "commentary_clause_id": None,
            "node_type": "clause",
            "node_key": "4.3.2",
            "node_label": None,
        },
        {
            "id": item_id,
            "standard_id": standard_id,
            "parent_id": clause_id,
            "clause_no": "4.3.2",
            "clause_title": None,
            "clause_text": "油样应经预处理。",
            "summary": None,
            "tags": [],
            "page_start": 44,
            "page_end": 44,
            "sort_order": 2,
            "clause_type": "normative",
            "commentary_clause_id": None,
            "node_type": "item",
            "node_key": "4.3.2#1",
            "node_label": "1、",
        },
        {
            "id": subitem_id,
            "standard_id": standard_id,
            "parent_id": item_id,
            "clause_no": "4.3.2",
            "clause_title": None,
            "clause_text": "含水率应满足要求。",
            "summary": None,
            "tags": [],
            "page_start": 44,
            "page_end": 44,
            "sort_order": 3,
            "clause_type": "normative",
            "commentary_clause_id": None,
            "node_type": "subitem",
            "node_key": "4.3.2#1#1",
            "node_label": "1)",
        },
        {
            "id": commentary_id,
            "standard_id": standard_id,
            "parent_id": None,
            "clause_no": "4.3.2",
            "clause_title": "条文说明",
            "clause_text": "本条说明绝缘油处理原因。",
            "summary": None,
            "tags": [],
            "page_start": 45,
            "page_end": 45,
            "sort_order": 4,
            "clause_type": "commentary",
            "commentary_clause_id": clause_id,
            "node_type": "commentary",
            "node_key": "4.3.2#commentary",
            "node_label": None,
        },
    ])

    tree = repo.get_viewer_tree(conn, standard_id)

    assert len(tree) == 1
    assert tree[0]["clause_no"] == "4"
    assert tree[0]["clause_type"] == "outline"

    merged_section = tree[0]["children"][0]
    assert merged_section["id"] == str(chapter_id)
    assert merged_section["clause_no"] == "4.3"
    assert merged_section["clause_title"] == "绝缘油处理"
    assert merged_section["clause_type"] == "normative"
    assert merged_section["summary"] == "4.3 摘要"

    mounted_clause = merged_section["children"][0]
    assert mounted_clause["id"] == str(clause_id)
    assert mounted_clause["clause_no"] == "4.3.2"
    assert mounted_clause["children"][0]["id"] == str(item_id)
    assert mounted_clause["children"][0]["children"][0]["id"] == str(subitem_id)
    assert mounted_clause["children"][1]["id"] == str(commentary_id)
    assert mounted_clause["children"][1]["clause_type"] == "commentary"


def test_get_viewer_tree_falls_back_to_ai_tree_without_outline(
    conn: psycopg.Connection,
) -> None:
    repo = StandardRepository()
    standard_id, _ = _create_standard(conn, code="GB 4")
    clause_id = uuid4()

    repo.bulk_create_clauses(conn, [
        {
            "id": clause_id,
            "standard_id": standard_id,
            "parent_id": None,
            "clause_no": "4.5.5",
            "clause_title": "防护要求",
            "clause_text": "应设置防护措施。",
            "summary": None,
            "tags": [],
            "page_start": 12,
            "page_end": 12,
            "sort_order": 0,
            "clause_type": "normative",
            "commentary_clause_id": None,
            "node_type": "clause",
            "node_key": "4.5.5",
            "node_label": None,
        },
    ])

    tree = repo.get_viewer_tree(conn, standard_id)

    assert len(tree) == 1
    assert tree[0]["id"] == str(clause_id)
    assert tree[0]["clause_no"] == "4.5.5"


def test_get_viewer_tree_skips_toc_and_front_matter_outline_noise(
    conn: psycopg.Connection,
) -> None:
    repo = StandardRepository()
    standard_id, document_id = _create_standard(conn, code="GB 5")
    chapter_id = uuid4()
    clause_id = uuid4()

    conn.execute(
        """
        INSERT INTO document_section
          (id, document_id, section_code, title, level, page_start, page_end, text, sort_order)
        VALUES
          (%s, %s, %s, %s, %s, %s, %s, %s, %s),
          (%s, %s, %s, %s, %s, %s, %s, %s, %s),
          (%s, %s, %s, %s, %s, %s, %s, %s, %s),
          (%s, %s, %s, %s, %s, %s, %s, %s, %s),
          (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            uuid4(), document_id, "2010", "北京", 1, 2, 2, "封面信息", 0,
            uuid4(), document_id, None, "前言", 1, 5, 5, "前言内容", 1,
            uuid4(), document_id, "5.4", "工程交接验收 (28)", 2, 7, 7, "附录A ...(29)\n本规范用词说明 (30)", 2,
            uuid4(), document_id, "5", "互感器", 1, 35, 35, None, 3,
            uuid4(), document_id, "5.4", "工程交接验收", 2, 37, 37, None, 4,
        ),
    )
    conn.commit()

    repo.bulk_create_clauses(conn, [
        {
            "id": chapter_id,
            "standard_id": standard_id,
            "parent_id": None,
            "clause_no": "5.4",
            "clause_title": "AI 工程交接验收",
            "clause_text": "应按要求完成交接验收。",
            "summary": "5.4 摘要",
            "tags": [],
            "page_start": 37,
            "page_end": 37,
            "sort_order": 0,
            "clause_type": "normative",
            "commentary_clause_id": None,
            "node_type": "clause",
            "node_key": "5.4",
            "node_label": None,
        },
        {
            "id": clause_id,
            "standard_id": standard_id,
            "parent_id": chapter_id,
            "clause_no": "5.4.1",
            "clause_title": "检查项目",
            "clause_text": "验收时应检查外观。",
            "summary": None,
            "tags": [],
            "page_start": 37,
            "page_end": 37,
            "sort_order": 1,
            "clause_type": "normative",
            "commentary_clause_id": None,
            "node_type": "clause",
            "node_key": "5.4.1",
            "node_label": None,
        },
    ])

    tree = repo.get_viewer_tree(conn, standard_id)

    assert [node["clause_no"] for node in tree] == ["5"]
    assert tree[0]["children"][0]["id"] == str(chapter_id)
    assert tree[0]["children"][0]["clause_no"] == "5.4"
    assert tree[0]["children"][0]["clause_title"] == "工程交接验收"
    assert tree[0]["children"][0]["children"][0]["id"] == str(clause_id)
