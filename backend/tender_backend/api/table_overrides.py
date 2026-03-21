"""API routes for table overrides (human correction of parsed tables)."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection
from psycopg.rows import dict_row
from pydantic import BaseModel

from tender_backend.core.security import CurrentUser, get_current_user
from tender_backend.db.deps import get_db_conn

router = APIRouter(tags=["table-overrides"])


class TableOverrideBody(BaseModel):
    override_json: dict


@router.get("/tables/{table_id}")
async def get_table(
    table_id: UUID,
    conn: Connection = Depends(get_db_conn),
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute("SELECT * FROM document_table WHERE id = %s", (table_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="table not found")
    # Check for override
    with conn.cursor(row_factory=dict_row) as cur:
        override = cur.execute(
            "SELECT * FROM document_table_override WHERE document_table_id = %s ORDER BY created_at DESC LIMIT 1",
            (table_id,),
        ).fetchone()
    return {
        "table": row,
        "override": override,
        "effective_json": override["override_json"] if override else row["raw_json"],
    }


@router.post("/tables/{table_id}/override")
async def create_override(
    table_id: UUID,
    body: TableOverrideBody,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    import json
    with conn.cursor(row_factory=dict_row) as cur:
        # Verify table exists
        exists = cur.execute("SELECT id FROM document_table WHERE id = %s", (table_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="table not found")
        row = cur.execute(
            """
            INSERT INTO document_table_override (id, document_table_id, override_json, created_by)
            VALUES (%s, %s, %s, %s) RETURNING *
            """,
            (uuid4(), table_id, json.dumps(body.override_json), user.display_name),
        ).fetchone()
    conn.commit()
    return row  # type: ignore[return-value]
