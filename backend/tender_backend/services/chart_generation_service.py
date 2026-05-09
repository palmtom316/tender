"""Structured chart asset creation, validation, rendering, and approval."""

from __future__ import annotations

from pathlib import Path
import json
import urllib.error
import urllib.request
from typing import Any
from uuid import UUID

from psycopg import Connection

from tender_backend.core.config import get_settings
from tender_backend.db.repositories.chart_asset_repo import (
    ChartAssetRepository,
    chart_asset_to_dict,
)
from tender_backend.services.chart_service.png_converter import svg_to_png
from tender_backend.services.chart_service.renderers import render_chart_spec
from tender_backend.services.chart_service.specs import (
    SUPPORTED_CHART_TYPES,
    ChartValidationError,
    parse_chart_spec,
    validate_chart_spec,
)
from tender_backend.services.ai_gateway_client import ai_gateway_headers


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
    ) -> dict[str, Any]:
        if chart_type not in SUPPORTED_CHART_TYPES:
            raise ValueError(f"unsupported chart type: {chart_type}")
        payload = _prepare_payload(chart_type=chart_type, title=title, spec_json=spec_json)
        payload["chart_type"] = chart_type
        payload["title"] = title
        validation = self.validate(chart_type=chart_type, spec_json=payload)
        if not validation["valid"]:
            row = self._repo.create(
                conn,
                project_id=project_id,
                outline_node_id=outline_node_id,
                chart_type=chart_type,
                title=title,
                spec_json=payload,
                rendered_svg=None,
                rendered_png_path=None,
                placeholder_key=_placeholder_from_spec(payload),
                mermaid_source=None,
                status="needs_review",
                metadata_json={"validation": validation},
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
            status="draft",
            metadata_json={
                "validation": validation,
                "render_engine": rendered.engine,
                "source_kind": "json_spec",
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

    def generate_spec(
        self,
        *,
        chart_type: str,
        title: str,
        placeholder_key: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ai_spec = _generate_spec_with_ai(
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


def _placeholder_from_spec(spec_json: dict[str, Any]) -> str | None:
    value = spec_json.get("placeholder_key")
    return str(value) if value else None


def _prepare_payload(*, chart_type: str, title: str, spec_json: dict[str, Any]) -> dict[str, Any]:
    payload = dict(spec_json)
    payload["chart_type"] = chart_type
    if title:
        payload["title"] = title
    if chart_type in {"org_chart", "construction_flow", "quality_system", "safety_system", "emergency_org"}:
        payload["nodes"] = _normalize_flow_nodes(payload.get("nodes") or payload.get("steps") or [])
        if "edges" not in payload:
            payload["edges"] = [
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
            nodes.append({"id": node_id, "label": label})
        else:
            nodes.append({"id": f"n{index}", "label": str(item)})
    return nodes


def _safe_filename(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value).strip("_") or "chart"


def default_chart_spec(*, chart_type: str, title: str, placeholder_key: str | None = None) -> dict[str, Any]:
    base: dict[str, Any] = {"placeholder_key": placeholder_key or f"{chart_type}_main"}
    if chart_type == "schedule_gantt":
        return {
            **base,
            "tasks": [
                {"id": "prepare", "label": "施工准备", "start": "2026-06-01", "end": "2026-06-05", "group": "准备阶段"},
                {"id": "execute", "label": "组织实施", "start": "2026-06-06", "end": "2026-06-20", "group": "实施阶段"},
            ],
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
    chart_type: str,
    title: str,
    placeholder_key: str | None,
    context: dict[str, Any],
) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.ai_gateway_url:
        return None
    prompt = (
        "你是投标文件图表规划助手。只输出 JSON，不要 Markdown。"
        "字段必须符合 tender chart spec。AI 只生成结构化 spec，不生成代码。"
    )
    user_content = {
        "chart_type": chart_type,
        "title": title,
        "placeholder_key": placeholder_key or f"{chart_type}_main",
        "context": context,
    }
    payload = {
        "task_type": "generate_chart_spec",
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)},
        ],
        "temperature": 0.1,
        "max_tokens": 1600,
        "response_format": {"type": "json_object"},
    }
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


__all__ = ["ChartGenerationService", "SUPPORTED_CHART_TYPES"]
