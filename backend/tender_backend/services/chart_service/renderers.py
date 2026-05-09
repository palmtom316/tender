from __future__ import annotations

import html
import math
import re
import urllib.error
import urllib.request
import json
from dataclasses import dataclass
from typing import Any

from tender_backend.core.config import get_settings
from tender_backend.services.chart_service.specs import (
    FLOW_CHART_TYPES,
    ChartSpec,
    FlowChartSpec,
    GanttChartSpec,
    ResponsibilityMatrixSpec,
    RiskMatrixSpec,
)


@dataclass(frozen=True)
class ChartRenderResult:
    svg: str
    mermaid_source: str | None
    engine: str


def render_chart_spec(spec: ChartSpec) -> ChartRenderResult:
    if spec.chart_type in FLOW_CHART_TYPES:
        mermaid = build_mermaid_source(spec)
        sidecar_svg = _render_mermaid_sidecar(mermaid)
        if sidecar_svg:
            return ChartRenderResult(svg=sidecar_svg, mermaid_source=mermaid, engine="mermaid_sidecar")
        return ChartRenderResult(svg=_render_flow_svg(spec), mermaid_source=mermaid, engine="system_mermaid_fallback")
    if spec.chart_type == "schedule_gantt":
        mermaid = build_mermaid_source(spec)
        sidecar_svg = _render_mermaid_sidecar(mermaid)
        if sidecar_svg:
            return ChartRenderResult(svg=sidecar_svg, mermaid_source=mermaid, engine="mermaid_sidecar")
        return ChartRenderResult(svg=_render_gantt_svg(spec), mermaid_source=mermaid, engine="system_mermaid_fallback")
    if spec.chart_type == "risk_matrix":
        return ChartRenderResult(svg=_render_risk_matrix_svg(spec), mermaid_source=None, engine="native_svg")
    if spec.chart_type == "responsibility_matrix":
        return ChartRenderResult(svg=_render_responsibility_matrix_svg(spec), mermaid_source=None, engine="native_svg")
    raise ValueError(f"unsupported chart type: {spec.chart_type}")


def build_mermaid_source(spec: ChartSpec) -> str | None:
    if isinstance(spec, FlowChartSpec):
        lines = [f"flowchart {spec.direction}"]
        for node in spec.nodes:
            lines.append(f"  {node.id}[\"{_mermaid_text(node.label)}\"]")
        for edge in spec.edges:
            if edge.label:
                lines.append(f"  {edge.from_} -->|{_mermaid_text(edge.label)}| {edge.to}")
            else:
                lines.append(f"  {edge.from_} --> {edge.to}")
        return "\n".join(lines)
    if isinstance(spec, GanttChartSpec):
        lines = ["gantt", f"  title {_mermaid_text(spec.title)}", "  dateFormat  YYYY-MM-DD"]
        current_group: str | None = None
        for task in spec.tasks:
            if task.group and task.group != current_group:
                current_group = task.group
                lines.append(f"  section {_mermaid_text(current_group)}")
            lines.append(f"  {_mermaid_text(task.label)} :{task.id}, {task.start.isoformat()}, {task.end.isoformat()}")
        return "\n".join(lines)
    return None


def _render_mermaid_sidecar(source: str | None) -> str | None:
    if not source:
        return None
    settings = get_settings()
    if not settings.mermaid_render_url:
        return None
    payload = json.dumps({"source": source, "format": "svg"}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        settings.mermaid_render_url.rstrip("/") + "/render",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.mermaid_render_timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return body if body.lstrip().startswith("<svg") else None
    svg = data.get("svg")
    return str(svg) if svg else None


def _render_flow_svg(spec: FlowChartSpec) -> str:
    width = 760
    row_height = 62
    top = 72
    left = 80
    box_width = 600
    box_height = 38
    height = top + len(spec.nodes) * row_height + 34
    parts = [_svg_start(width, height), _title(spec.title, width)]
    for index, node in enumerate(spec.nodes):
        y = top + index * row_height
        parts.append(_rect(left, y, box_width, box_height, "#eef6ff", "#6d93b8", 6))
        parts.append(_text(node.label, left + box_width / 2, y + 25, 15, anchor="middle", weight="600"))
        if index < len(spec.nodes) - 1:
            x = left + box_width / 2
            parts.append(_line(x, y + box_height, x, y + row_height - 8, "#6d93b8"))
            parts.append(_arrow(x, y + row_height - 8, "#6d93b8"))
    parts.append("</svg>")
    return "".join(parts)


def _render_gantt_svg(spec: GanttChartSpec) -> str:
    width = 900
    label_width = 220
    chart_left = 250
    row_height = 34
    top = 76
    height = top + len(spec.tasks) * row_height + 44
    min_date = min(task.start for task in spec.tasks)
    max_date = max(task.end for task in spec.tasks)
    total_days = max((max_date - min_date).days + 1, 1)
    chart_width = width - chart_left - 44
    parts = [_svg_start(width, height), _title(spec.title, width)]
    parts.append(_line(chart_left, top - 20, chart_left + chart_width, top - 20, "#9aa4af"))
    for index, task in enumerate(spec.tasks):
        y = top + index * row_height
        start_offset = (task.start - min_date).days / total_days
        duration = max((task.end - task.start).days + 1, 1) / total_days
        x = chart_left + start_offset * chart_width
        bar_w = max(duration * chart_width, 18)
        parts.append(_text(task.label, 24, y + 20, 13, anchor="start"))
        parts.append(_rect(x, y + 5, bar_w, 18, "#dff0d8", "#78a66a", 4))
        parts.append(_text(f"{task.start.isoformat()} - {task.end.isoformat()}", x + bar_w + 8, y + 19, 11, anchor="start", fill="#4c5661"))
    parts.append("</svg>")
    return "".join(parts)


def _render_risk_matrix_svg(spec: RiskMatrixSpec) -> str:
    cell_w = 170
    cell_h = 92
    left = 150
    top = 88
    width = left + len(spec.columns) * cell_w + 36
    height = top + len(spec.rows) * cell_h + 44
    cell_map = {(cell.row, cell.column): cell for cell in spec.cells}
    parts = [_svg_start(width, height), _title(spec.title, width)]
    for col_index, column in enumerate(spec.columns):
        x = left + col_index * cell_w
        parts.append(_rect(x, top - 36, cell_w, 36, "#f1f5f9", "#9aa4af", 0))
        parts.append(_text(column, x + cell_w / 2, top - 13, 13, anchor="middle", weight="600"))
    for row_index, row in enumerate(spec.rows):
        y = top + row_index * cell_h
        parts.append(_rect(24, y, left - 24, cell_h, "#f1f5f9", "#9aa4af", 0))
        parts.append(_text(row, 36, y + cell_h / 2 + 5, 13, anchor="start", weight="600"))
        for col_index, column in enumerate(spec.columns):
            x = left + col_index * cell_w
            cell = cell_map.get((row, column))
            fill = _risk_fill(cell.level if cell else None)
            parts.append(_rect(x, y, cell_w, cell_h, fill, "#9aa4af", 0))
            if cell and cell.items:
                lines = _wrap("；".join(cell.items), 12, 4)
                for line_index, line in enumerate(lines):
                    parts.append(_text(line, x + 10, y + 24 + line_index * 18, 12, anchor="start"))
    parts.append("</svg>")
    return "".join(parts)


def _render_responsibility_matrix_svg(spec: ResponsibilityMatrixSpec) -> str:
    first_w = 190
    cell_w = 108
    cell_h = 46
    top = 88
    left = 24
    width = left + first_w + len(spec.roles) * cell_w + 30
    height = top + (len(spec.activities) + 1) * cell_h + 36
    assignments = {(item.activity, item.role): item.level for item in spec.assignments}
    parts = [_svg_start(width, height), _title(spec.title, width)]
    parts.append(_rect(left, top, first_w, cell_h, "#e8eef7", "#8b98a8", 0))
    parts.append(_text("工作事项", left + 14, top + 29, 13, anchor="start", weight="600"))
    for role_index, role in enumerate(spec.roles):
        x = left + first_w + role_index * cell_w
        parts.append(_rect(x, top, cell_w, cell_h, "#e8eef7", "#8b98a8", 0))
        parts.append(_text(role, x + cell_w / 2, top + 29, 12, anchor="middle", weight="600"))
    for activity_index, activity in enumerate(spec.activities):
        y = top + (activity_index + 1) * cell_h
        parts.append(_rect(left, y, first_w, cell_h, "#f8fafc", "#8b98a8", 0))
        for line_index, line in enumerate(_wrap(activity, 12, 2)):
            parts.append(_text(line, left + 12, y + 19 + line_index * 16, 12, anchor="start"))
        for role_index, role in enumerate(spec.roles):
            x = left + first_w + role_index * cell_w
            parts.append(_rect(x, y, cell_w, cell_h, "#ffffff", "#8b98a8", 0))
            value = assignments.get((activity, role), "")
            if value:
                parts.append(_text(value, x + cell_w / 2, y + 28, 12, anchor="middle", weight="600"))
    parts.append("</svg>")
    return "".join(parts)


def _svg_start(width: int | float, height: int | float) -> str:
    return (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{math.ceil(width)}' height='{math.ceil(height)}' "
        f"viewBox='0 0 {math.ceil(width)} {math.ceil(height)}'>"
        "<rect width='100%' height='100%' fill='#ffffff'/>"
    )


def _title(value: str, width: int | float) -> str:
    return _text(value, width / 2, 38, 18, anchor="middle", weight="700")


def _rect(x: int | float, y: int | float, width: int | float, height: int | float, fill: str, stroke: str, rx: int) -> str:
    return f"<rect x='{x:.1f}' y='{y:.1f}' width='{width:.1f}' height='{height:.1f}' rx='{rx}' fill='{fill}' stroke='{stroke}'/>"


def _line(x1: int | float, y1: int | float, x2: int | float, y2: int | float, stroke: str) -> str:
    return f"<line x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}' stroke='{stroke}' stroke-width='1.6'/>"


def _arrow(x: int | float, y: int | float, fill: str) -> str:
    return f"<path d='M{x - 5:.1f},{y - 5:.1f} L{x:.1f},{y:.1f} L{x + 5:.1f},{y - 5:.1f} Z' fill='{fill}'/>"


def _text(
    value: str,
    x: int | float,
    y: int | float,
    size: int,
    *,
    anchor: str = "start",
    weight: str = "400",
    fill: str = "#1f2933",
) -> str:
    return (
        f"<text x='{x:.1f}' y='{y:.1f}' font-family='Noto Sans CJK SC, Microsoft YaHei, SimSun, sans-serif' "
        f"font-size='{size}' font-weight='{weight}' text-anchor='{anchor}' fill='{fill}'>{html.escape(value)}</text>"
    )


def _wrap(value: str, chars: int, max_lines: int) -> list[str]:
    text = re.sub(r"\s+", "", value)
    if not text:
        return []
    lines = [text[index : index + chars] for index in range(0, len(text), chars)]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: max(chars - 1, 1)] + "…"
    return lines


def _risk_fill(level: str | None) -> str:
    return {
        "low": "#e7f5e8",
        "medium": "#fff4ce",
        "high": "#ffe0cc",
        "critical": "#ffd6d6",
    }.get(level or "", "#ffffff")


def _mermaid_text(value: str) -> str:
    return value.replace('"', "'")
