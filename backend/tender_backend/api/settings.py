from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from psycopg import Connection

from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.agent_config_repo import AgentConfigRepository, AgentConfigRow

router = APIRouter(tags=["settings"])

_repo = AgentConfigRepository()


def _mask_key(key: str) -> str:
    """Return masked API key: '****' + last 4 chars, or empty if unset."""
    if not key:
        return ""
    if len(key) <= 4:
        return "****"
    return "****" + key[-4:]


class AgentConfigOut(BaseModel):
    agent_key: str
    display_name: str
    description: str
    agent_type: str
    base_url: str
    api_key_display: str
    primary_model: str
    fallback_base_url: str
    fallback_api_key_display: str
    fallback_model: str
    enabled: bool
    updated_at: str


class AgentConfigUpdate(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    primary_model: str | None = None
    fallback_base_url: str | None = None
    fallback_api_key: str | None = None
    fallback_model: str | None = None
    enabled: bool | None = None


def _to_out(row: AgentConfigRow) -> AgentConfigOut:
    return AgentConfigOut(
        agent_key=row.agent_key,
        display_name=row.display_name,
        description=row.description,
        agent_type=row.agent_type,
        base_url=row.base_url,
        api_key_display=_mask_key(row.api_key),
        primary_model=row.primary_model,
        fallback_base_url=row.fallback_base_url,
        fallback_api_key_display=_mask_key(row.fallback_api_key),
        fallback_model=row.fallback_model,
        enabled=row.enabled,
        updated_at=row.updated_at.isoformat(),
    )


@router.get("/settings/agents", response_model=list[AgentConfigOut])
def list_agent_configs(conn: Connection = Depends(get_db_conn)) -> list[AgentConfigOut]:
    rows = _repo.list_all(conn)
    return [_to_out(r) for r in rows]


@router.put("/settings/agents/{agent_key}", response_model=AgentConfigOut)
def update_agent_config(
    agent_key: str,
    payload: AgentConfigUpdate,
    conn: Connection = Depends(get_db_conn),
) -> AgentConfigOut:
    existing = _repo.get_by_key(conn, agent_key)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Agent config not found: {agent_key}")

    row = _repo.upsert(conn, agent_key, **payload.model_dump(exclude_none=True))
    return _to_out(row)
