from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row


_STANDARD_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")
_CODE_RE = re.compile(r"^GB\s*(\d+)\s*[- ]\s*(\d{4})$")
_FILENAME_PREFIX_RE = re.compile(r"^GB\s*(\d+)\s+(\d{4})\s+")


def _normalize_standard_code(value: str) -> str:
    compact = "".join(str(value).strip().split())
    match = re.match(r"^GB(\d+)-(\d{4})$", compact, flags=re.IGNORECASE)
    if not match:
        raise ValueError(f"Unsupported standard code: {value}")
    return f"GB {match.group(1)}-{match.group(2)}"


def _extract_standard_name(bundle: dict) -> str:
    source_files = bundle.get("source_files") or {}
    pdf_path = Path(str(source_files.get("pdf") or ""))
    stem = pdf_path.stem.replace("_", " ").strip()
    match = _FILENAME_PREFIX_RE.match(stem)
    if match:
        remainder = stem[match.end() :].strip()
        if remainder:
            return remainder

    for page in ((bundle.get("document") or {}).get("raw_payload") or {}).get("pages") or []:
        markdown = str(page.get("markdown") or "").strip()
        for line in markdown.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("电气装置安装工程"):
                return line
    raise ValueError("Unable to derive standard_name from bundle")


def _build_import_record(bundle_path: Path) -> dict:
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    raw_name = str(bundle.get("name") or "").strip()
    standard_code = _normalize_standard_code(raw_name)
    code_match = _CODE_RE.match(standard_code)
    assert code_match is not None
    version_year = code_match.group(2)
    return {
        "bundle_path": bundle_path,
        "bundle": bundle,
        "standard_code": standard_code,
        "standard_name": _extract_standard_name(bundle),
        "version_year": version_year,
        "document_id": UUID(str(((bundle.get("document") or {}).get("document_id")) or ((bundle.get("document") or {}).get("id")))),
        "source_pdf": str((bundle.get("source_files") or {}).get("pdf") or ""),
        "sections": bundle.get("sections") or [],
        "tables": bundle.get("tables") or [],
        "raw_payload": ((bundle.get("document") or {}).get("raw_payload")) or {},
        "parser_name": ((bundle.get("document") or {}).get("parser_name")) or "mineru",
        "parser_version": ((bundle.get("document") or {}).get("parser_version")),
    }


def _delete_existing_standard(conn: psycopg.Connection, *, standard_code: str) -> None:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT s.id AS standard_id, s.document_id, d.project_file_id
            FROM standard s
            LEFT JOIN document d ON d.id = s.document_id
            WHERE s.standard_code = %s
            """,
            (standard_code,),
        ).fetchall()

        for row in rows:
            standard_id = row["standard_id"]
            document_id = row["document_id"]
            project_file_id = row["project_file_id"]

            cur.execute("DELETE FROM standard_processing_job WHERE standard_id = %s", (standard_id,))
            cur.execute("DELETE FROM standard_clause WHERE standard_id = %s", (standard_id,))
            cur.execute("DELETE FROM standard WHERE id = %s", (standard_id,))
            if document_id:
                cur.execute("DELETE FROM parse_job WHERE document_id = %s", (document_id,))
                cur.execute("DELETE FROM document_table WHERE document_id = %s", (document_id,))
                cur.execute("DELETE FROM document_section WHERE document_id = %s", (document_id,))
                cur.execute("DELETE FROM document WHERE id = %s", (document_id,))
            if project_file_id:
                cur.execute("DELETE FROM project_file WHERE id = %s", (project_file_id,))
    conn.commit()


def _insert_bundle(conn: psycopg.Connection, record: dict) -> dict:
    bundle = record["bundle"]
    document_id = record["document_id"]
    standard_id = uuid4()
    project_file_id = uuid4()
    parse_job_id = uuid4()
    processing_job_id = uuid4()
    source_pdf = record["source_pdf"]
    filename = Path(source_pdf).name or f"{record['standard_code']}.pdf"
    size_bytes = Path(source_pdf).stat().st_size if source_pdf and Path(source_pdf).exists() else 0

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO project_file (id, project_id, filename, content_type, size_bytes, storage_key)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (project_file_id, _STANDARD_PROJECT_ID, filename, "application/pdf", size_bytes, source_pdf or None),
        )
        cur.execute(
            """
            INSERT INTO document (id, project_file_id, parser_name, parser_version, raw_payload)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                document_id,
                project_file_id,
                record["parser_name"],
                record["parser_version"],
                json.dumps(record["raw_payload"], ensure_ascii=False),
            ),
        )
        cur.execute(
            """
            INSERT INTO parse_job (id, document_id, status, provider, provider_job_id, error)
            VALUES (%s, %s, %s, %s, NULL, NULL)
            """,
            (parse_job_id, document_id, "completed", "mineru"),
        )
        cur.execute(
            """
            INSERT INTO standard (
              id, standard_code, standard_name, version_year, specialty, document_id, processing_status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                standard_id,
                record["standard_code"],
                record["standard_name"],
                record["version_year"],
                "electrical",
                document_id,
                "processing",
            ),
        )
        cur.execute(
            """
            INSERT INTO standard_processing_job (
              id, standard_id, document_id, ocr_status, ocr_finished_at, ocr_attempts, ai_status, ai_attempts
            )
            VALUES (%s, %s, %s, %s, now(), %s, %s, %s)
            """,
            (processing_job_id, standard_id, document_id, "completed", 1, "blocked", 0),
        )

        for index, section in enumerate(record["sections"]):
            cur.execute(
                """
                INSERT INTO document_section (
                  id, document_id, section_code, title, level, page_start, page_end, text,
                  raw_json, text_source, sort_order
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    UUID(str(section["id"])),
                    document_id,
                    section.get("section_code"),
                    section.get("title") or "",
                    int(section.get("level") or 1),
                    section.get("page_start"),
                    section.get("page_end"),
                    section.get("text"),
                    json.dumps(section.get("raw_json"), ensure_ascii=False) if section.get("raw_json") is not None else None,
                    section.get("text_source"),
                    section.get("sort_order", index),
                ),
            )

        for table in record["tables"]:
            section_id = table.get("section_id")
            cur.execute(
                """
                INSERT INTO document_table (
                  id, document_id, section_id, page, page_start, page_end, table_title, table_html, raw_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    UUID(str(table["id"])),
                    document_id,
                    UUID(str(section_id)) if section_id else None,
                    table.get("page"),
                    table.get("page_start", table.get("page")),
                    table.get("page_end", table.get("page")),
                    table.get("table_title"),
                    table.get("table_html"),
                    json.dumps(table.get("raw_json"), ensure_ascii=False) if table.get("raw_json") is not None else None,
                ),
            )

    conn.commit()
    return {
        "standard_id": str(standard_id),
        "document_id": str(document_id),
        "standard_code": record["standard_code"],
        "standard_name": record["standard_name"],
        "sections": len(record["sections"]),
        "tables": len(record["tables"]),
        "bundle_path": str(record["bundle_path"]),
    }


def _summarize(conn: psycopg.Connection, *, standard_id: UUID) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        standard = cur.execute(
            """
            SELECT s.id, s.standard_code, s.standard_name, s.processing_status, s.error_message, s.document_id,
                   j.ocr_status, j.ai_status
            FROM standard s
            LEFT JOIN standard_processing_job j ON j.standard_id = s.id
            WHERE s.id = %s
            """,
            (standard_id,),
        ).fetchone()
        assert standard is not None
        document_id = standard["document_id"]
        section_count = cur.execute(
            "SELECT count(*) AS count FROM document_section WHERE document_id = %s",
            (document_id,),
        ).fetchone()["count"]
        table_count = cur.execute(
            "SELECT count(*) AS count FROM document_table WHERE document_id = %s",
            (document_id,),
        ).fetchone()["count"]
        clause_count = cur.execute(
            "SELECT count(*) AS count FROM standard_clause WHERE standard_id = %s",
            (standard_id,),
        ).fetchone()["count"]
    return {
        "standard_id": str(standard["id"]),
        "standard_code": standard["standard_code"],
        "standard_name": standard["standard_name"],
        "processing_status": standard["processing_status"],
        "ocr_status": standard["ocr_status"],
        "ai_status": standard["ai_status"],
        "section_count": section_count,
        "table_count": table_count,
        "clause_count": clause_count,
        "error_message": standard["error_message"],
        "document_id": str(document_id),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import cleaned MinerU standard bundles into PostgreSQL.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument(
        "--bundle",
        action="append",
        required=True,
        help="Path to a cleaned-system-bundle.json file. Repeat for multiple standards.",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write the import summary JSON.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    records = [_build_import_record(Path(item)) for item in args.bundle]
    imported: list[dict] = []
    with psycopg.connect(args.database_url) as conn:
        for record in records:
            _delete_existing_standard(conn, standard_code=record["standard_code"])
            result = _insert_bundle(conn, record)
            imported.append(_summarize(conn, standard_id=UUID(result["standard_id"])))

    payload = {"imported": imported}
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
