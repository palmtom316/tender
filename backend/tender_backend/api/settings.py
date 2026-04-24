from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from psycopg import Connection
from uuid import UUID

from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.agent_config_repo import AgentConfigRepository, AgentConfigRow
from tender_backend.db.repositories.skill_definition_repo import (
    SkillDefinitionRepository,
    SkillDefinitionRow,
)
from tender_backend.services.skill_catalog import default_skill_specs

router = APIRouter(tags=["settings"])

_repo = AgentConfigRepository()
_skills = SkillDefinitionRepository()


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


class SkillDefinitionOut(BaseModel):
    skill_name: str
    description: str
    tool_names: list[str]
    prompt_template_id: str | None
    version: int
    active: bool
    created_at: str


class SkillDefinitionCreate(BaseModel):
    skill_name: str
    description: str = ""
    tool_names: list[str] = []
    prompt_template_id: str | None = None
    version: int = 1
    active: bool = True


class SkillDefinitionUpdate(BaseModel):
    description: str | None = None
    tool_names: list[str] | None = None
    prompt_template_id: str | None = None
    version: int | None = None
    active: bool | None = None


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


def _skill_to_out(row: SkillDefinitionRow) -> SkillDefinitionOut:
    return SkillDefinitionOut(
        skill_name=row.skill_name,
        description=row.description,
        tool_names=row.tool_names,
        prompt_template_id=str(row.prompt_template_id) if row.prompt_template_id else None,
        version=row.version,
        active=row.active,
        created_at=row.created_at.isoformat(),
    )


def _parse_prompt_template_id(raw: str | None) -> UUID | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="prompt_template_id must be a valid UUID") from exc


@router.get("/settings/agents", response_model=list[AgentConfigOut])
async def list_agent_configs(conn: Connection = Depends(get_db_conn)) -> list[AgentConfigOut]:
    rows = _repo.list_all(conn)
    return [_to_out(r) for r in rows]


@router.put("/settings/agents/{agent_key}", response_model=AgentConfigOut)
async def update_agent_config(
    agent_key: str,
    payload: AgentConfigUpdate,
    conn: Connection = Depends(get_db_conn),
) -> AgentConfigOut:
    existing = _repo.get_by_key(conn, agent_key)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Agent config not found: {agent_key}")

    row = _repo.upsert(conn, agent_key, **payload.model_dump(exclude_none=True))
    return _to_out(row)


@router.post("/settings/agents/{agent_key}/test")
async def test_agent_connection(
    agent_key: str,
    conn: Connection = Depends(get_db_conn),
) -> dict:
    """Test connectivity to an agent's API endpoint."""
    import httpx

    config = _repo.get_by_key(conn, agent_key)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Agent config not found: {agent_key}")

    if not config.base_url or not config.api_key:
        return {"success": False, "message": "未配置 Base URL 或 API Key"}

    if config.agent_type == "ocr":
        # For OCR (MinerU), just check the base domain is reachable
        try:
            url = config.base_url.rstrip("/")
            # Try a HEAD request to the base domain
            base_domain = "/".join(url.split("/")[:3])
            resp = httpx.get(base_domain, timeout=10.0, follow_redirects=True)
            return {"success": True, "message": f"连接成功 (HTTP {resp.status_code})"}
        except Exception as e:
            return {"success": False, "message": f"连接失败: {e}"}
    else:
        # For LLM, send a minimal chat request
        try:
            headers = {
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": config.primary_model or "deepseek-chat",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5,
            }
            url = config.base_url.rstrip("/")
            if not url.endswith("/chat/completions"):
                url += "/chat/completions"
            resp = httpx.post(url, json=payload, headers=headers, timeout=15.0)
            if resp.status_code == 200:
                return {"success": True, "message": "API 连通正常"}
            return {"success": False, "message": f"API 返回 HTTP {resp.status_code}: {resp.text[:200]}"}
        except Exception as e:
            return {"success": False, "message": f"连接失败: {e}"}


@router.get("/settings/skills", response_model=list[SkillDefinitionOut])
async def list_skill_definitions(conn: Connection = Depends(get_db_conn)) -> list[SkillDefinitionOut]:
    return [_skill_to_out(row) for row in _skills.list_all(conn)]


@router.post("/settings/skills", response_model=SkillDefinitionOut)
async def create_skill_definition(
    payload: SkillDefinitionCreate,
    conn: Connection = Depends(get_db_conn),
) -> SkillDefinitionOut:
    skill_name = payload.skill_name.strip()
    existing = _skills.get_by_name(conn, skill_name)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Skill already exists: {skill_name}")

    row = _skills.create(
        conn,
        skill_name=skill_name,
        description=payload.description.strip(),
        tool_names=[tool.strip() for tool in payload.tool_names if tool.strip()],
        prompt_template_id=_parse_prompt_template_id(payload.prompt_template_id),
        version=payload.version,
        active=payload.active,
    )
    return _skill_to_out(row)


@router.put("/settings/skills/{skill_name}", response_model=SkillDefinitionOut)
async def update_skill_definition(
    skill_name: str,
    payload: SkillDefinitionUpdate,
    conn: Connection = Depends(get_db_conn),
) -> SkillDefinitionOut:
    existing = _skills.get_by_name(conn, skill_name)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_name}")

    updates = payload.model_dump(exclude_unset=True)
    if "description" in updates and updates["description"] is not None:
        updates["description"] = updates["description"].strip()
    if "tool_names" in updates and updates["tool_names"] is not None:
        updates["tool_names"] = [tool.strip() for tool in updates["tool_names"] if tool.strip()]
    if "prompt_template_id" in updates:
        updates["prompt_template_id"] = _parse_prompt_template_id(updates["prompt_template_id"])

    row = _skills.update(conn, skill_name, **updates)
    return _skill_to_out(row)


@router.delete("/settings/skills/{skill_name}")
async def delete_skill_definition(
    skill_name: str,
    conn: Connection = Depends(get_db_conn),
) -> dict[str, object]:
    deleted = _skills.delete(conn, skill_name=skill_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_name}")
    return {"skill_name": skill_name, "deleted": True}


@router.post("/settings/skills/sync-defaults")
async def sync_default_skills(conn: Connection = Depends(get_db_conn)) -> dict[str, object]:
    inserted = 0
    updated = 0
    names: list[str] = []

    for spec in default_skill_specs():
        names.append(spec.skill_name)
        existing = _skills.get_by_name(conn, spec.skill_name)
        if existing is None:
            _skills.create(
                conn,
                skill_name=spec.skill_name,
                description=spec.description,
                tool_names=spec.tool_names,
                version=spec.version,
                active=spec.active,
            )
            inserted += 1
            continue

        _skills.update(
            conn,
            spec.skill_name,
            description=spec.description,
            tool_names=spec.tool_names,
            version=max(existing.version, spec.version),
            active=existing.active,
        )
        updated += 1

    return {
        "inserted": inserted,
        "updated": updated,
        "total": len(names),
        "skill_names": sorted(names),
    }
