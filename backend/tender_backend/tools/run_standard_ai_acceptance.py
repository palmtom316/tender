from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from tender_backend.db.repositories.standard_repo import StandardRepository
from tender_backend.services.norm_service.norm_processor import process_standard_ai


_STD_REPO = StandardRepository()


def _fetch_standards(conn: psycopg.Connection, codes: list[str]) -> list[dict]:
    placeholders = ", ".join(["%s"] * len(codes))
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            f"""
            SELECT s.id, s.standard_code, s.standard_name, s.document_id
            FROM standard s
            WHERE s.standard_code IN ({placeholders})
            ORDER BY s.standard_code
            """,
            codes,
        ).fetchall()


def _get_tag_clause_config(conn: psycopg.Connection) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """
            SELECT agent_key, enabled, base_url, api_key, primary_model,
                   fallback_base_url, fallback_api_key, fallback_model
            FROM agent_config
            WHERE agent_key = 'tag_clauses'
            """
        ).fetchone()


def _assert_real_ai_ready(conn: psycopg.Connection) -> None:
    config = _get_tag_clause_config(conn)
    if not config or not config["enabled"]:
        raise SystemExit("tag_clauses agent_config is missing or disabled")

    primary_ready = bool(str(config.get("base_url") or "").strip() and str(config.get("api_key") or "").strip())
    fallback_ready = bool(
        str(config.get("fallback_base_url") or "").strip()
        and str(config.get("fallback_api_key") or "").strip()
    )
    if not primary_ready and not fallback_ready:
        raise SystemExit(
            "tag_clauses agent_config has no real primary/fallback API key; real AI acceptance cannot run"
        )


def _mark_running(conn: psycopg.Connection, *, standard_id: UUID) -> None:
    _STD_REPO.update_processing_status(conn, standard_id, "processing")
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE standard_processing_job
            SET ai_status = 'running',
                ai_error = NULL,
                ai_started_at = now(),
                ai_finished_at = NULL,
                ai_attempts = ai_attempts + 1,
                updated_at = now()
            WHERE standard_id = %s
            """,
            (standard_id,),
        )
    conn.commit()


def _mark_completed(conn: psycopg.Connection, *, standard_id: UUID) -> None:
    _STD_REPO.update_processing_status(conn, standard_id, "completed")
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE standard_processing_job
            SET ai_status = 'completed',
                ai_error = NULL,
                ai_finished_at = now(),
                updated_at = now()
            WHERE standard_id = %s
            """,
            (standard_id,),
        )
    conn.commit()


def _mark_failed(conn: psycopg.Connection, *, standard_id: UUID, error: str) -> None:
    _STD_REPO.update_processing_status(conn, standard_id, "failed", error_message=error)
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE standard_processing_job
            SET ai_status = 'failed',
                ai_error = %s,
                ai_finished_at = now(),
                updated_at = now()
            WHERE standard_id = %s
            """,
            (error, standard_id),
        )
    conn.commit()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run real AI clause extraction acceptance for imported standards.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument(
        "--standard-code",
        action="append",
        required=True,
        help="Standard code, e.g. 'GB 50148-2010'. Repeat for multiple standards.",
    )
    parser.add_argument("--output", help="Optional path to write the JSON summary.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    with psycopg.connect(args.database_url) as conn:
        _assert_real_ai_ready(conn)
        standards = _fetch_standards(conn, args.standard_code)
        missing = sorted(set(args.standard_code) - {row["standard_code"] for row in standards})
        if missing:
            raise SystemExit(f"Missing standards in DB: {', '.join(missing)}")

        results: list[dict] = []
        for standard in standards:
            standard_id = UUID(str(standard["id"]))
            document_id = str(standard["document_id"])
            try:
                _mark_running(conn, standard_id=standard_id)
                summary = process_standard_ai(conn, standard_id=standard_id, document_id=document_id)
                conn.commit()
                _mark_completed(conn, standard_id=standard_id)
                results.append({
                    "standard_id": str(standard_id),
                    "standard_code": standard["standard_code"],
                    "standard_name": standard["standard_name"],
                    **summary,
                })
            except Exception as exc:
                conn.rollback()
                _mark_failed(conn, standard_id=standard_id, error=str(exc))
                results.append({
                    "standard_id": str(standard_id),
                    "standard_code": standard["standard_code"],
                    "standard_name": standard["standard_name"],
                    "status": "failed",
                    "error": str(exc),
                })

    rendered = json.dumps({"results": results}, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
