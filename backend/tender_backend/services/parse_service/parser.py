"""Parse result persistence — writes MinerU output to database."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any
from uuid import UUID, uuid4

import structlog
from psycopg import Connection
from psycopg.rows import dict_row

logger = structlog.stdlib.get_logger(__name__)


def _json_default(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def persist_sections(conn: Connection, *, document_id: UUID, sections: list[dict]) -> int:
    """Insert parsed sections into document_section. Returns count."""
    count = 0
    with conn.cursor() as cur:
        for index, s in enumerate(sections):
            cur.execute(
                """
                INSERT INTO document_section
                    (id, document_id, section_code, title, level, page_start, page_end, text,
                     raw_json, text_source, sort_order)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    uuid4(),
                    document_id,
                    s.get("section_code"),
                    s.get("title", ""),
                    s.get("level", 1),
                    s.get("page_start"),
                    s.get("page_end"),
                    s.get("text"),
                    json.dumps(s.get("raw_json")) if s.get("raw_json") is not None else None,
                    s.get("text_source"),
                    s.get("sort_order", index),
                ),
            )
            count += 1
    conn.commit()
    logger.info("sections_persisted", document_id=str(document_id), count=count)
    return count


def persist_tables(conn: Connection, *, document_id: UUID, tables: list[dict]) -> int:
    """Insert parsed tables into document_table. Returns count."""
    count = 0
    with conn.cursor() as cur:
        for t in tables:
            cur.execute(
                """
                INSERT INTO document_table
                    (id, document_id, section_id, page, page_start, page_end, table_title, table_html, raw_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    uuid4(),
                    document_id,
                    t.get("section_id"),
                    t.get("page"),
                    t.get("page_start", t.get("page")),
                    t.get("page_end", t.get("page")),
                    t.get("table_title") or t.get("title"),
                    t.get("table_html") or t.get("html"),
                    json.dumps(t.get("data", t)),
                ),
            )
            count += 1
    conn.commit()
    logger.info("tables_persisted", document_id=str(document_id), count=count)
    return count


def persist_outline(conn: Connection, *, document_id: UUID, pages: list[dict]) -> int:
    """Build document_outline_node tree from parsed page headings. Returns count."""
    count = 0
    with conn.cursor() as cur:
        for idx, page in enumerate(pages):
            for heading in page.get("headings", []):
                cur.execute(
                    """
                    INSERT INTO document_outline_node
                        (id, document_id, parent_id, node_type, node_no, title, level, page_start, sort_order)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        uuid4(),
                        document_id,
                        heading.get("parent_id"),
                        heading.get("node_type", "heading"),
                        heading.get("node_no"),
                        heading.get("title", ""),
                        heading.get("level", 1),
                        page.get("page_number", idx + 1),
                        count,
                    ),
                )
                count += 1
    conn.commit()
    logger.info("outline_persisted", document_id=str(document_id), count=count)
    return count


def update_parse_job_status(
    conn: Connection, *, parse_job_id: UUID, status: str, provider_job_id: str | None = None, error: str | None = None
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE parse_job
            SET status = %s, provider_job_id = COALESCE(%s, provider_job_id),
                error = %s, updated_at = now()
            WHERE id = %s
            """,
            (status, provider_job_id, error, parse_job_id),
        )
    conn.commit()


def update_document_parse_assets(
    conn: Connection,
    *,
    document_id: UUID,
    parser_name: str,
    parser_version: str | None = None,
    raw_payload: Any = None,
) -> None:
    if is_dataclass(raw_payload):
        payload = raw_payload.raw_payload if isinstance(getattr(raw_payload, "raw_payload", None), dict) else asdict(raw_payload)
    else:
        payload = raw_payload
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE document
            SET parser_name = %s,
                parser_version = %s,
                raw_payload = %s
            WHERE id = %s
            """,
            (
                parser_name,
                parser_version,
                json.dumps(payload, default=_json_default) if payload is not None else None,
                document_id,
            ),
        )
    conn.commit()
