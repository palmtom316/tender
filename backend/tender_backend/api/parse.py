from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection
from psycopg.rows import dict_row

from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.parse_job_repository import ACTIVE_STATUSES, ParseJobRepository


router = APIRouter(tags=["parse"])

_jobs = ParseJobRepository()


@router.post("/documents/{document_id}/parse-jobs")
def create_parse_job(document_id: UUID, payload: dict, conn: Connection = Depends(get_db_conn)) -> dict:
    force_reparse = bool(payload.get("force_reparse", False))
    if not force_reparse:
        active = _jobs.find_active_for_document(conn, document_id=document_id)
        if active is not None:
            raise HTTPException(status_code=409, detail=f"active parse job exists: {active.status}")

    job = _jobs.create(conn, document_id=document_id, provider="mineru", status="queued")
    return {"parse_job_id": str(job.id), "document_id": str(job.document_id), "status": job.status}


@router.get("/parse-jobs/{parse_job_id}")
def get_parse_job(parse_job_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict:
    job = _jobs.get(conn, parse_job_id=parse_job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="parse job not found")
    return {
        "parse_job_id": str(job.id),
        "document_id": str(job.document_id),
        "provider": job.provider,
        "provider_job_id": job.provider_job_id,
        "status": job.status,
        "error": job.error,
    }


@router.get("/documents/{document_id}/parse-result")
def get_parse_result_summary(document_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict:
    latest = _jobs.latest_for_document(conn, document_id=document_id)
    with conn.cursor(row_factory=dict_row) as cur:
        section_count = cur.execute(
            "SELECT COUNT(*) AS c FROM document_section WHERE document_id = %s",
            (document_id,),
        ).fetchone()["c"]
        table_count = cur.execute(
            "SELECT COUNT(*) AS c FROM document_table WHERE document_id = %s",
            (document_id,),
        ).fetchone()["c"]
    parsed = bool(section_count or table_count)
    return {
        "document_id": str(document_id),
        "parsed": parsed,
        "section_count": int(section_count),
        "table_count": int(table_count),
        "latest_parse_job_id": str(latest.id) if latest else None,
    }


@router.post("/parse-jobs/{parse_job_id}/retry")
def retry_parse_job(parse_job_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict:
    job = _jobs.get(conn, parse_job_id=parse_job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="parse job not found")
    if job.status not in {"failed", "timeout"}:
        raise HTTPException(status_code=409, detail=f"cannot retry status={job.status}")

    new_job = _jobs.create(conn, document_id=job.document_id, provider=job.provider, status="queued")
    return {"parse_job_id": str(new_job.id), "document_id": str(new_job.document_id), "status": new_job.status}

