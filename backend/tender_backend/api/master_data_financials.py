from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from psycopg import Connection

from tender_backend.core.security import get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.master_data_repo import MasterDataRepository


router = APIRouter(tags=["master-data"], dependencies=[Depends(get_current_user)])

_repo = MasterDataRepository()


def _not_found(detail: str) -> None:
    raise HTTPException(status_code=404, detail=detail)


class FinancialStatementBase(BaseModel):
    library_company_id: UUID | None = None
    fiscal_year: int
    statement_type: str = Field(min_length=1)
    statement_data: dict[str, Any] = Field(default_factory=dict)
    source_note: str | None = None


class FinancialStatementCreate(FinancialStatementBase):
    pass


class FinancialStatementUpdate(BaseModel):
    library_company_id: UUID | None = None
    fiscal_year: int | None = None
    statement_type: str | None = None
    statement_data: dict[str, Any] | None = None
    source_note: str | None = None


class FinancialStatementOut(FinancialStatementBase):
    id: UUID
    created_at: str
    updated_at: str


def _financial_out(row) -> FinancialStatementOut:
    return FinancialStatementOut(
        id=row.id,
        library_company_id=row.library_company_id,
        fiscal_year=row.fiscal_year,
        statement_type=row.statement_type,
        statement_data=row.statement_data,
        source_note=row.source_note,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


@router.get("/master-data/financial-statements", response_model=list[FinancialStatementOut])
async def list_financial_statements(
    library_company_id: UUID | None = Query(None),
    conn: Connection = Depends(get_db_conn),
) -> list[FinancialStatementOut]:
    return [_financial_out(row) for row in _repo.list_financial_statements(conn, library_company_id=library_company_id)]


@router.post("/master-data/financial-statements", response_model=FinancialStatementOut, status_code=201)
async def create_financial_statement(
    payload: FinancialStatementCreate,
    conn: Connection = Depends(get_db_conn),
) -> FinancialStatementOut:
    try:
        row = _repo.create_financial_statement(conn, **payload.model_dump())
    except Exception as exc:
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise HTTPException(status_code=409, detail="financial statement already exists for year/type") from exc
        raise
    return _financial_out(row)


@router.put("/master-data/financial-statements/{record_id}", response_model=FinancialStatementOut)
async def update_financial_statement(
    record_id: UUID,
    payload: FinancialStatementUpdate,
    conn: Connection = Depends(get_db_conn),
) -> FinancialStatementOut:
    try:
        row = _repo.update_financial_statement(conn, record_id, **payload.model_dump(exclude_unset=True))
    except Exception as exc:
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise HTTPException(status_code=409, detail="financial statement already exists for year/type") from exc
        raise
    if row is None:
        _not_found("financial statement not found")
    return _financial_out(row)


@router.delete("/master-data/financial-statements/{record_id}")
async def delete_financial_statement(record_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict[str, bool]:
    if not _repo.delete_financial_statement(conn, record_id):
        _not_found("financial statement not found")
    return {"deleted": True}
