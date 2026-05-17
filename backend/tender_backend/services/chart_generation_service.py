"""Structured chart asset creation, validation, rendering, and approval."""

from __future__ import annotations

from pathlib import Path
import json
import urllib.error
import urllib.request
from datetime import date
from typing import Any
from uuid import UUID

from psycopg import Connection

from tender_backend.core.config import get_settings
from tender_backend.db.repositories.agent_config_repo import AgentConfigRepository
from tender_backend.db.repositories.chart_asset_repo import (
    ChartAssetRepository,
    chart_asset_to_dict,
)
from tender_backend.services.chart_service.png_converter import svg_to_png
from tender_backend.services.chart_service.renderers import render_chart_spec
from tender_backend.services.chart_service.redactor import redact_context_for_chart, scan_blind_bid_keywords
from tender_backend.services.chart_service.specs import (
    SUPPORTED_CHART_TYPES,
    ChartValidationError,
    parse_chart_spec,
    validate_chart_spec,
)
from tender_backend.services.ai_gateway_client import ai_gateway_headers


SOURCE_REQUIRED_CHART_TYPES = {"schedule_gantt", "critical_path"}
SOURCE_TRACE_KEYS = {
    "constraint_id",
    "constraint_ids",
    "source_chunk_id",
    "source_chunk_ids",
    "standard_clause_id",
    "standard_clause_ids",
    "user_confirmed_by",
    "manual_confirmation_id",
    "confirmed_by",
}


class ChartGenerationService:
    def __init__(self, repo: ChartAssetRepository | None = None):
        self._repo = repo or ChartAssetRepository()

    def create_or_update(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        chart_type: str,
        title: str,
        spec_json: dict[str, Any],
        outline_node_id: UUID | None = None,
        chapter_code: str | None = None,
        template_instance_id: UUID | None = None,
        template_revision_no: int | None = None,
    ) -> dict[str, Any]:
        if chart_type not in SUPPORTED_CHART_TYPES:
            raise ValueError(f"unsupported chart type: {chart_type}")
        payload = _prepare_payload(chart_type=chart_type, title=title, spec_json=spec_json)
        payload["chart_type"] = chart_type
        payload["title"] = title
        if chapter_code and not payload.get("chapter_code"):
            payload["chapter_code"] = chapter_code
        if not payload.get("caption_title"):
            payload["caption_title"] = title
        persisted_payload = _strip_blind_bid_blacklist(payload)
        is_default_spec = bool(payload.pop("_default_spec", False))
        is_blind_bid = bool(
            (payload.get("metadata_json") or {}).get("is_blind_bid")
            or payload.get("is_blind_bid")
        )
        validation = self.validate(chart_type=chart_type, spec_json=payload)
        if not validation["valid"]:
            fallback = self._render_fallback(
                project_id=project_id,
                chart_type=chart_type,
                title=title,
                placeholder_key=_placeholder_from_spec(payload),
                allow_render=True,
            )
            row = self._repo.create(
                conn,
                project_id=project_id,
                outline_node_id=outline_node_id,
                chart_type=chart_type,
                title=title,
                spec_json=fallback["spec"] if fallback else persisted_payload,
                rendered_svg=fallback["svg"] if fallback else None,
                rendered_png_path=fallback["png_path"] if fallback else None,
                placeholder_key=_placeholder_from_spec(payload),
                mermaid_source=None,
                status="needs_review",
                template_instance_id=template_instance_id,
                template_revision_no=template_revision_no,
                is_stale_by_template=False,
                metadata_json={
                    "validation": validation,
                    "source_kind": "default_spec" if is_default_spec else "json_spec",
                    "source_context": _source_context(payload),
                    "fallback_render": {"reason": "validation_failed", "rendered": bool(fallback)},
                },
            )
            return chart_asset_to_dict(row)

        blind_bid_issues = _blind_bid_issues(payload)
        if blind_bid_issues:
            persisted_payload = _strip_blind_bid_blacklist(payload)
            # Blind-bid hits: never auto-render — must be manually corrected and approved.
            row = self._repo.create(
                conn,
                project_id=project_id,
                outline_node_id=outline_node_id,
                chart_type=chart_type,
                title=title,
                spec_json=persisted_payload,
                rendered_svg=None,
                rendered_png_path=None,
                placeholder_key=_placeholder_from_spec(payload),
                mermaid_source=None,
                status="needs_review",
                template_instance_id=template_instance_id,
                template_revision_no=template_revision_no,
                is_stale_by_template=False,
                metadata_json={
                    "validation": validation,
                    "blind_bid_scan": {"issues": blind_bid_issues},
                    "source_kind": "json_spec",
                    "fallback_render": {"reason": "blind_bid", "rendered": False},
                },
            )
            return chart_asset_to_dict(row)

        provenance_issues = _provenance_issues(payload)
        if provenance_issues:
            # Provenance failure: render a default-spec fallback (non-blind only) so export
            # gate can proceed, but mark needs_review to require human verification.
            fallback = self._render_fallback(
                project_id=project_id,
                chart_type=chart_type,
                title=title,
                placeholder_key=_placeholder_from_spec(payload),
                allow_render=not is_blind_bid,
            )
            row = self._repo.create(
                conn,
                project_id=project_id,
                outline_node_id=outline_node_id,
                chart_type=chart_type,
                title=title,
                spec_json=fallback["spec"] if fallback else persisted_payload,
                rendered_svg=fallback["svg"] if fallback else None,
                rendered_png_path=fallback["png_path"] if fallback else None,
                placeholder_key=_placeholder_from_spec(payload),
                mermaid_source=None,
                status="needs_review",
                template_instance_id=template_instance_id,
                template_revision_no=template_revision_no,
                is_stale_by_template=False,
                metadata_json={
                    "validation": validation,
                    "provenance": {"issues": provenance_issues},
                    "source_kind": "json_spec",
                    "source_context": _source_context(payload),
                    "fallback_render": {"reason": "provenance", "rendered": bool(fallback)},
                },
            )
            return chart_asset_to_dict(row)

        spec = parse_chart_spec(payload)
        normalized = spec.model_dump(by_alias=True, mode="json")
        rendered = render_chart_spec(spec)
        png_path = self._write_png(
            project_id=project_id,
            placeholder_key=_placeholder_from_spec(normalized) or chart_type,
            svg=rendered.svg,
        )
        status = "needs_review" if is_default_spec else "draft"
        source_context = _source_context(payload)
        row = self._repo.create(
            conn,
            project_id=project_id,
            outline_node_id=outline_node_id,
            chart_type=chart_type,
            title=title,
            spec_json=normalized,
            rendered_svg=rendered.svg,
            rendered_png_path=str(png_path),
            placeholder_key=_placeholder_from_spec(normalized),
            mermaid_source=rendered.mermaid_source,
            status=status,
            template_instance_id=template_instance_id,
            template_revision_no=template_revision_no,
            is_stale_by_template=False,
            metadata_json={
                "validation": validation,
                "render_engine": rendered.engine,
                "source_kind": "default_spec" if is_default_spec else "json_spec",
                "source_context": source_context,
            },
        )
        return chart_asset_to_dict(row)

    def list_by_project(self, conn: Connection, *, project_id: UUID) -> list[dict[str, Any]]:
        return [chart_asset_to_dict(row) for row in self._repo.list_by_project(conn, project_id=project_id)]

    def approve(self, conn: Connection, *, asset_id: UUID, approved_by: str | None = None) -> dict[str, Any]:
        row = self._repo.approve(conn, asset_id=asset_id, approved_by=approved_by)
        if row is None:
            raise LookupError("chart asset not found")
        return chart_asset_to_dict(row)

    def bulk_approve(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        mode: str = "auto",
        approved_by: str = "system",
        is_blind_bid: bool = False,
    ) -> dict[str, Any]:
        """Approve all eligible chart assets for a project in one call.

        - mode='auto': only approve assets whose metadata.validation.valid is True
          AND fallback_render.reason is not in {'blind_bid'}. Skips assets that
          require human review for safety reasons.
        - mode='manual': approve all non-approved assets. Required for blind-bid
          projects (blind-bid projects MUST use mode='manual' with a real user).
        - is_blind_bid=True + mode='auto' raises ValueError; caller must catch.
        """
        if mode not in {"auto", "manual"}:
            raise ValueError(f"unsupported bulk_approve mode: {mode}")
        if is_blind_bid and mode == "auto":
            raise ValueError("blind-bid projects must use mode='manual' with explicit approver")

        approved: list[str] = []
        skipped: list[dict[str, Any]] = []
        rows = self._repo.list_by_project(conn, project_id=project_id)
        for row in rows:
            if row.status == "approved":
                continue
            metadata = dict(row.metadata_json or {})
            validation = metadata.get("validation") or {}
            fallback = metadata.get("fallback_render") or {}
            if mode == "auto":
                if not validation.get("valid"):
                    skipped.append({"asset_id": str(row.id), "reason": "validation_invalid"})
                    continue
                if str(fallback.get("reason") or "") == "blind_bid":
                    skipped.append({"asset_id": str(row.id), "reason": "blind_bid_blocked"})
                    continue
            updated = self._repo.approve(conn, asset_id=row.id, approved_by=approved_by)
            if updated is not None:
                approved.append(str(updated.id))
        return {
            "project_id": str(project_id),
            "mode": mode,
            "approved_by": approved_by,
            "approved_count": len(approved),
            "approved_ids": approved,
            "skipped": skipped,
        }

    def generate_spec(
        self,
        *,
        conn: Connection | None = None,
        chart_type: str,
        title: str,
        placeholder_key: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ai_spec = _generate_spec_with_ai(
            conn=conn,
            chart_type=chart_type,
            title=title,
            placeholder_key=placeholder_key,
            context=context or {},
        )
        if ai_spec is not None and validate_chart_spec(_prepare_payload(chart_type=chart_type, title=title, spec_json=ai_spec))["valid"]:
            return ai_spec
        return default_chart_spec(chart_type=chart_type, title=title, placeholder_key=placeholder_key)

    def validate(self, *, chart_type: str, spec_json: dict[str, Any]) -> dict[str, Any]:
        payload = _prepare_payload(chart_type=chart_type, title=str(spec_json.get("title") or ""), spec_json=spec_json)
        return validate_chart_spec(payload)

    def render_svg(self, *, title: str, spec_json: dict[str, Any]) -> str:
        payload = _prepare_payload(
            chart_type=str(spec_json.get("chart_type") or "construction_flow"),
            title=title,
            spec_json=spec_json,
        )
        try:
            spec = parse_chart_spec(payload)
        except ChartValidationError:
            fallback = {
                "chart_type": "construction_flow",
                "title": title,
                "nodes": [{"id": "pending", "label": "待补充"}],
                "edges": [],
            }
            spec = parse_chart_spec(fallback)
        return render_chart_spec(spec).svg

    def _write_png(self, *, project_id: UUID, placeholder_key: str, svg: str) -> Path:
        root = get_settings().template_render_root / "chart_assets" / str(project_id)
        filename = f"{_safe_filename(placeholder_key)}.png"
        return svg_to_png(svg, root / filename)

    def _render_fallback(
        self,
        *,
        project_id: UUID,
        chart_type: str,
        title: str,
        placeholder_key: str | None,
        allow_render: bool = True,
    ) -> dict[str, Any] | None:
        """Render a default-spec fallback chart for failure branches.

        Returns dict with svg/png_path/spec, or None if blocked (e.g., blind-bid)
        or rendering itself fails.
        """
        if not allow_render:
            return None
        try:
            fallback_spec_json = default_chart_spec(
                chart_type=chart_type,
                title=title,
                placeholder_key=placeholder_key,
            )
            payload = _prepare_payload(
                chart_type=chart_type,
                title=title,
                spec_json=fallback_spec_json,
            )
            payload.pop("_default_spec", None)
            spec = parse_chart_spec(payload)
            rendered = render_chart_spec(spec)
            normalized = spec.model_dump(by_alias=True, mode="json")
            png_path = self._write_png(
                project_id=project_id,
                placeholder_key=_placeholder_from_spec(normalized) or chart_type,
                svg=rendered.svg,
            )
            return {
                "spec": normalized,
                "svg": rendered.svg,
                "png_path": str(png_path),
            }
        except Exception:
            return None


def _placeholder_from_spec(spec_json: dict[str, Any]) -> str | None:
    value = spec_json.get("placeholder_key")
    return str(value) if value else None


def _prepare_payload(*, chart_type: str, title: str, spec_json: dict[str, Any]) -> dict[str, Any]:
    payload = dict(spec_json)
    payload["chart_type"] = chart_type
    if title:
        payload["title"] = title
    if chart_type in {"org_chart", "construction_flow", "quality_system", "safety_system", "emergency_org", "closure_flow", "data_flow"}:
        payload["nodes"] = _normalize_flow_nodes(payload.get("nodes") or payload.get("steps") or [])
        if "edges" not in payload:
            parent_edges = _flow_parent_edges(payload["nodes"])
            payload["edges"] = parent_edges or [
                {"from": payload["nodes"][index]["id"], "to": payload["nodes"][index + 1]["id"]}
                for index in range(max(len(payload["nodes"]) - 1, 0))
            ]
    return payload


def _normalize_flow_nodes(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    nodes: list[dict[str, str]] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, dict):
            label = str(item.get("label") or item.get("name") or item.get("id") or f"节点{index}")
            node_id = str(item.get("id") or f"n{index}")
            node = {"id": node_id, "label": label}
            if item.get("parent"):
                node["parent"] = str(item["parent"])
            nodes.append(node)
        else:
            nodes.append({"id": f"n{index}", "label": str(item)})
    return nodes


def _flow_parent_edges(nodes: list[dict[str, str]]) -> list[dict[str, str]]:
    node_ids = {node["id"] for node in nodes}
    edges: list[dict[str, str]] = []
    for node in nodes:
        parent = node.get("parent")
        if parent and parent in node_ids:
            edges.append({"from": parent, "to": node["id"]})
    return edges


def _safe_filename(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value).strip("_") or "chart"


def default_chart_spec(*, chart_type: str, title: str, placeholder_key: str | None = None) -> dict[str, Any]:
    base: dict[str, Any] = {"placeholder_key": placeholder_key or f"{chart_type}_main", "_default_spec": True}
    if chart_type in {"schedule_gantt", "critical_path"}:
        return {
            **base,
            "columns": ["阶段/工序", "计划开始条件", "计划完成条件", "衔接关系", "来源"],
            "rows": [
                {"cells": ["施工准备", "待补充确认", "待补充确认", "按发包人确认计划衔接", "待补充来源"]},
                {"cells": ["组织实施", "待补充确认", "待补充确认", "按发包人确认计划衔接", "待补充来源"]},
            ],
            "fallback_reason": "缺少已确认日期、工期或里程碑，暂不生成甘特图。",
        }
    if chart_type == "risk_matrix":
        return {
            **base,
            "rows": ["低影响", "中影响", "高影响"],
            "columns": ["低概率", "中概率", "高概率"],
            "cells": [{"row": "高影响", "column": "中概率", "items": ["关键节点延误"], "level": "high"}],
        }
    if chart_type == "responsibility_matrix":
        return {
            **base,
            "roles": ["项目经理", "技术负责人", "安全负责人"],
            "activities": ["施工准备", "技术交底", "安全检查"],
            "assignments": [
                {"role": "项目经理", "activity": "施工准备", "level": "负责"},
                {"role": "技术负责人", "activity": "技术交底", "level": "负责"},
                {"role": "安全负责人", "activity": "安全检查", "level": "负责"},
            ],
        }
    if chart_type in {"response_matrix", "indicator_table", "interface_table", "equipment_table"}:
        return {
            **base,
            "columns": ["事项", "来源", "措施"],
            "rows": [{"cells": [title, "待补充来源", "按确认要求执行"]}],
        }
    return {
        **base,
        "nodes": [
            {"id": "start", "label": "准备"},
            {"id": "execute", "label": title},
            {"id": "review", "label": "检查确认"},
        ],
        "edges": [{"from": "start", "to": "execute"}, {"from": "execute", "to": "review"}],
    }


def _generate_spec_with_ai(
    *,
    conn: Connection | None,
    chart_type: str,
    title: str,
    placeholder_key: str | None,
    context: dict[str, Any],
) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.ai_gateway_url:
        return None
    is_blind_bid = bool(context.get("is_blind_bid") or context.get("blind_bid") or context.get("tender_summary", {}).get("is_blind_bid"))
    prompt = _chart_spec_system_prompt(chart_type)
    user_content = {
        "chart_type": chart_type,
        "title": title,
        "placeholder_key": placeholder_key or f"{chart_type}_main",
        "context": redact_context_for_chart(context, is_blind_bid=is_blind_bid),
    }
    payload = {
        "task_type": "generate_chart_spec",
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(user_content, ensure_ascii=False, default=str)},
        ],
        "max_tokens": 1600,
        "response_format": {"type": "json_object"},
    }
    primary_override, fallback_override = _generate_section_overrides(conn)
    if primary_override:
        payload["primary_override"] = primary_override
    if fallback_override:
        payload["fallback_override"] = fallback_override
    request = urllib.request.Request(
        settings.ai_gateway_url.rstrip("/") + "/api/ai/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **ai_gateway_headers()},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.chart_ai_gateway_timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    try:
        gateway_response = json.loads(body)
        content = gateway_response.get("content")
        if not isinstance(content, str):
            return None
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _generate_section_overrides(conn: Connection | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if conn is None:
        return None, None
    config = AgentConfigRepository().get_by_key(conn, "generate_section")
    if not config or not config.enabled:
        return None, None

    primary = None
    if config.base_url and config.api_key:
        primary = {
            "base_url": config.base_url,
            "api_key": config.api_key,
            "model": config.primary_model or "deepseek-v4-flash",
        }

    fallback = None
    if config.fallback_base_url and config.fallback_api_key:
        fallback = {
            "base_url": config.fallback_base_url,
            "api_key": config.fallback_api_key,
            "model": config.fallback_model or "qwen-plus",
        }

    return primary, fallback


def _chart_spec_system_prompt(chart_type: str) -> str:
    schemas = {
        "schedule_gantt": {
            "chart_type": "schedule_gantt",
            "placeholder_key": "schedule_gantt",
            "tasks": [
                {
                    "id": "prepare",
                    "label": "施工准备",
                    "start": "YYYY-MM-DD",
                    "end": "YYYY-MM-DD",
                    "group": "准备阶段",
                    "is_critical": True,
                    "source_refs": [{"constraint_id": "..."}],
                }
            ],
            "dependencies": [{"from": "prepare", "to": "next_task"}],
        },
        "risk_matrix": {
            "chart_type": "risk_matrix",
            "placeholder_key": "risk_matrix",
            "rows": ["低影响", "中影响", "高影响"],
            "columns": ["低概率", "中概率", "高概率"],
            "cells": [{"row": "高影响", "column": "高概率", "items": ["风险场景"], "level": "high"}],
        },
        "responsibility_matrix": {
            "chart_type": "responsibility_matrix",
            "placeholder_key": "responsibility_matrix",
            "roles": ["项目经理", "技术负责人"],
            "activities": ["施工准备"],
            "assignments": [{"role": "项目经理", "activity": "施工准备", "level": "负责"}],
        },
    }
    example = schemas.get(
        chart_type,
        {
            "chart_type": chart_type,
            "placeholder_key": f"{chart_type}_main",
            "nodes": [{"id": "prepare", "label": "施工准备"}, {"id": "review", "label": "检查确认"}],
            "edges": [{"from": "prepare", "to": "review"}],
        },
    )
    return (
        "你是投标文件图表规划助手。只输出 JSON，不要 Markdown。"
        "输出必须是合法 json object，并符合 tender chart spec。"
        "AI 只生成结构化 spec，不生成代码。"
        "不得编造日期、天数、人员姓名、证书编号、设备型号、风险等级、量化指标或许可结果。"
        "schedule_gantt/critical_path 的每个任务日期必须来自 context 中已确认的工期、里程碑或约束，"
        "并在任务 source_refs 中写入 constraint_id/source_chunk_id/user_confirmed_by 等来源；缺少来源时不要输出甘特图任务。"
        "risk_matrix 的 cells[].level 只能使用 low/medium/high/critical。"
        "示例 JSON："
        + json.dumps(example, ensure_ascii=False)
    )


def _source_context(spec_json: dict[str, Any]) -> dict[str, Any]:
    source: dict[str, Any] = {}
    if spec_json.get("chapter_code"):
        source["chapter_code"] = spec_json.get("chapter_code")
    metadata = spec_json.get("metadata_json")
    if isinstance(metadata, dict):
        refs = metadata.get("source_refs") or metadata.get("source_trace")
        if refs:
            source["source_refs"] = refs
    refs = spec_json.get("source_refs") or spec_json.get("source_trace")
    if refs:
        source["source_refs"] = refs
    nested_refs = _nested_source_refs(spec_json)
    if nested_refs:
        source["nested_source_refs"] = nested_refs
    return source


def _nested_source_refs(spec_json: dict[str, Any]) -> list[Any]:
    refs: list[Any] = []
    for key in ("tasks", "nodes", "cells", "rows", "assignments"):
        values = spec_json.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            item_refs = item.get("source_refs") or item.get("source_trace")
            if item_refs:
                refs.append(item_refs)
    return refs


def _provenance_issues(spec_json: dict[str, Any]) -> list[dict[str, str]]:
    chart_type = str(spec_json.get("chart_type") or "")
    if chart_type not in SOURCE_REQUIRED_CHART_TYPES:
        return []
    issues: list[dict[str, str]] = []
    tasks = spec_json.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return []
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            continue
        has_dates = _is_iso_date(task.get("start")) and _is_iso_date(task.get("end"))
        if has_dates and not _has_source_trace(task, spec_json):
            label = str(task.get("label") or task.get("id") or index + 1)
            issues.append(
                {
                    "code": "missing_source_trace",
                    "message": f"{chart_type} task {label} has dates without source trace",
                }
            )
    return issues


def _is_iso_date(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _has_source_trace(*items: dict[str, Any]) -> bool:
    for item in items:
        if any(item.get(key) for key in SOURCE_TRACE_KEYS):
            return True
        refs = item.get("source_refs") or item.get("source_trace")
        if _refs_have_source_trace(refs):
            return True
        metadata = item.get("metadata_json")
        if isinstance(metadata, dict) and _has_source_trace(metadata):
            return True
    return False


def _refs_have_source_trace(refs: object) -> bool:
    if isinstance(refs, dict):
        return any(refs.get(key) for key in SOURCE_TRACE_KEYS)
    if isinstance(refs, list):
        return any(isinstance(ref, dict) and any(ref.get(key) for key in SOURCE_TRACE_KEYS) for ref in refs)
    return False


def _blind_bid_issues(spec_json: dict[str, Any]) -> list[dict[str, str]]:
    metadata = spec_json.get("metadata_json")
    if not isinstance(metadata, dict):
        metadata = {}
    is_blind_bid = bool(metadata.get("is_blind_bid") or spec_json.get("is_blind_bid"))
    if not is_blind_bid:
        return []
    blacklist = metadata.get("blind_bid_blacklist") or spec_json.get("blind_bid_blacklist") or []
    return scan_blind_bid_keywords(_strip_blind_bid_blacklist(spec_json), [str(value) for value in blacklist])


def _strip_blind_bid_blacklist(spec_json: dict[str, Any]) -> dict[str, Any]:
    payload = dict(spec_json)
    payload.pop("blind_bid_blacklist", None)
    metadata = payload.get("metadata_json")
    if isinstance(metadata, dict) and "blind_bid_blacklist" in metadata:
        safe_metadata = dict(metadata)
        safe_metadata.pop("blind_bid_blacklist", None)
        payload["metadata_json"] = safe_metadata
    return payload


__all__ = ["ChartGenerationService", "SUPPORTED_CHART_TYPES"]
