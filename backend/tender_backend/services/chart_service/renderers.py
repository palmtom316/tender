from __future__ import annotations

import html
import math
import re
import urllib.error
import urllib.request
import json
from datetime import date, timedelta
from dataclasses import dataclass
from typing import Any

from tender_backend.core.config import get_settings
from tender_backend.services.chart_service.render_strategy import resolve_render_strategy
from tender_backend.services.chart_service.specs import (
    ChartSpec,
    FlowChartSpec,
    GanttChartSpec,
    ResponsibilityMatrixSpec,
    RiskMatrixSpec,
    TableChartSpec,
)


@dataclass(frozen=True)
class ChartRenderResult:
    svg: str
    mermaid_source: str | None
    engine: str


def render_chart_spec(spec: ChartSpec) -> ChartRenderResult:
    strategy = resolve_render_strategy(spec.chart_type)
    if strategy.primary == "mermaid_sidecar":
        mermaid = build_mermaid_source(spec)
        sidecar_svg = _render_mermaid_sidecar(mermaid)
        if sidecar_svg:
            return ChartRenderResult(svg=sidecar_svg, mermaid_source=mermaid, engine="mermaid_sidecar")
        if strategy.fallback == "native_flow" and isinstance(spec, FlowChartSpec):
            return ChartRenderResult(svg=_render_flow_svg(spec), mermaid_source=mermaid, engine="system_mermaid_fallback")
        if strategy.fallback == "native_gantt" and isinstance(spec, GanttChartSpec):
            return ChartRenderResult(svg=_render_gantt_svg(spec), mermaid_source=mermaid, engine="system_mermaid_fallback")
    if spec.chart_type == "risk_matrix":
        return ChartRenderResult(svg=_render_risk_matrix_svg(spec), mermaid_source=None, engine="native_svg")
    if spec.chart_type == "responsibility_matrix":
        return ChartRenderResult(svg=_render_responsibility_matrix_svg(spec), mermaid_source=None, engine="native_svg")
    if strategy.primary == "native_svg" and isinstance(spec, TableChartSpec):
        return ChartRenderResult(svg=_render_table_svg(spec), mermaid_source=None, engine="native_svg")
    raise ValueError(f"unsupported chart type: {spec.chart_type}")


def build_mermaid_source(spec: ChartSpec) -> str | None:
    if isinstance(spec, FlowChartSpec):
        lines = [f"flowchart {spec.direction}"]
        for node in spec.nodes:
            lines.append(f"  {node.id}[\"{_mermaid_text(node.label)}\"]")
        edge_labels = {(edge.from_, edge.to): edge.label for edge in spec.edges}
        for from_id, to_id in _flow_layout_edges(spec):
            label = edge_labels.get((from_id, to_id))
            if label:
                lines.append(f"  {from_id} -->|{_mermaid_text(label)}| {to_id}")
            else:
                lines.append(f"  {from_id} --> {to_id}")
        return "\n".join(lines)
    if isinstance(spec, GanttChartSpec) and spec.chart_type == "schedule_gantt":
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
    box_width = 180
    box_height = 42
    x_gap = 54
    y_gap = 58
    top = 80
    left = 42
    layout = _flow_layout(spec)
    max_x = max((point[0] for point in layout.values()), default=0)
    max_y = max((point[1] for point in layout.values()), default=0)
    width = max(760, left * 2 + (max_x + 1) * box_width + max_x * x_gap)
    height = top + (max_y + 1) * box_height + max_y * y_gap + 44
    parts = [_svg_start(width, height), _title(spec.title, width)]
    node_map = {node.id: node for node in spec.nodes}
    positions: dict[str, tuple[float, float]] = {}
    for node_id, (col, row) in layout.items():
        positions[node_id] = (left + col * (box_width + x_gap), top + row * (box_height + y_gap))
    edge_labels = {(edge.from_, edge.to): edge.label for edge in spec.edges}
    for from_id, to_id in _flow_layout_edges(spec):
        if from_id not in positions or to_id not in positions:
            continue
        sx, sy = positions[from_id]
        tx, ty = positions[to_id]
        start_x = sx + box_width / 2
        start_y = sy + box_height
        end_x = tx + box_width / 2
        end_y = ty
        mid_y = start_y + max((end_y - start_y) / 2, 14)
        data = f" data-edge='{html.escape(from_id)}-{html.escape(to_id)}'"
        parts.append(
            f"<path{data} d='M{start_x:.1f},{start_y:.1f} L{start_x:.1f},{mid_y:.1f} "
            f"L{end_x:.1f},{mid_y:.1f} L{end_x:.1f},{end_y - 7:.1f}' "
            "fill='none' stroke='#6d93b8' stroke-width='1.6'/>"
        )
        parts.append(_arrow(end_x, end_y, "#6d93b8"))
        label = edge_labels.get((from_id, to_id))
        if label:
            parts.append(_text(label, (start_x + end_x) / 2, mid_y - 5, 11, anchor="middle", fill="#4c5661"))
    for node in spec.nodes:
        x, y = positions[node.id]
        parts.append(_rect(x, y, box_width, box_height, "#eef6ff", "#6d93b8", 6))
        for line_index, line in enumerate(_wrap(node_map[node.id].label, 12, 2)):
            parts.append(_text(line, x + box_width / 2, y + 25 + line_index * 15, 14, anchor="middle", weight="600"))
    parts.append("</svg>")
    return "".join(parts)


def _flow_parent_edges(spec: FlowChartSpec) -> list[tuple[str, str]]:
    node_ids = {node.id for node in spec.nodes}
    return [(node.parent, node.id) for node in spec.nodes if node.parent and node.parent in node_ids]


def _flow_layout_edges(spec: FlowChartSpec) -> list[tuple[str, str]]:
    edges = [(edge.from_, edge.to) for edge in spec.edges]
    return edges or _flow_parent_edges(spec)


def _render_gantt_svg(spec: GanttChartSpec) -> str:
    width = 980
    chart_left = 260
    row_height = 38
    top = 110
    height = top + len(spec.tasks) * row_height + 54
    min_date = min(task.start for task in spec.tasks)
    max_date = max(task.end for task in spec.tasks)
    total_days = max((max_date - min_date).days + 1, 1)
    chart_width = width - chart_left - 44
    parts = [_svg_start(width, height), _title(spec.title, width)]
    tick_step = _gantt_tick_step(total_days)
    tick = min_date
    while tick <= max_date:
        x = chart_left + ((tick - min_date).days / total_days) * chart_width
        parts.append(f"<line data-tick='{tick.isoformat()}' x1='{x:.1f}' y1='{top - 38:.1f}' x2='{x:.1f}' y2='{height - 28:.1f}' stroke='#e1e7ef' stroke-width='1'/>")
        parts.append(_text(_gantt_tick_label(tick, tick_step), x, top - 48, 10, anchor="middle", fill="#4c5661"))
        tick = tick + timedelta(days=tick_step)
    parts.append(_line(chart_left, top - 24, chart_left + chart_width, top - 24, "#9aa4af"))
    task_positions: dict[str, tuple[float, float, float]] = {}
    group_colors = ("#f8fafc", "#eef6ff")
    current_group: str | None = None
    group_index = -1
    for index, task in enumerate(spec.tasks):
        y = top + index * row_height
        if task.group != current_group:
            current_group = task.group
            group_index += 1
        if task.group:
            fill = group_colors[group_index % len(group_colors)]
            parts.append(_rect(12, y - 2, width - 24, row_height, fill, "#edf2f7", 0))
            parts.append(_text(task.group, 24, y + 23, 11, anchor="start", fill="#53606f"))
        start_offset = (task.start - min_date).days / total_days
        duration = max((task.end - task.start).days + 1, 1) / total_days
        x = chart_left + start_offset * chart_width
        bar_w = max(duration * chart_width, 18)
        task_positions[task.id] = (x, y + 8, bar_w)
        label_x = 104 if task.group else 24
        label_weight = "700" if task.is_critical else "400"
        stroke = "#d92d20" if task.is_critical else "#78a66a"
        parts.append(_text(task.label, label_x, y + 24, 13, anchor="start", weight=label_weight))
        parts.append(_rect(x, y + 8, bar_w, 20, "#dff0d8", stroke, 4))
        parts.append(_text(f"{task.start.isoformat()} - {task.end.isoformat()}", min(x + bar_w + 8, width - 170), y + 24, 11, anchor="start", fill="#4c5661"))
    for dependency in spec.dependencies:
        if dependency.from_ not in task_positions or dependency.to not in task_positions:
            continue
        sx, sy, sw = task_positions[dependency.from_]
        tx, ty, _tw = task_positions[dependency.to]
        start_x = sx + sw
        start_y = sy + 10
        end_x = tx
        end_y = ty + 10
        mid_x = start_x + max((end_x - start_x) / 2, 12)
        parts.append(
            f"<path data-dependency='{html.escape(dependency.from_)}-{html.escape(dependency.to)}' "
            f"d='M{start_x:.1f},{start_y:.1f} L{mid_x:.1f},{start_y:.1f} L{mid_x:.1f},{end_y:.1f} L{end_x - 7:.1f},{end_y:.1f}' "
            "fill='none' stroke='#667085' stroke-width='1.4' stroke-dasharray='4 3'/>"
        )
        parts.append(_right_arrow(end_x, end_y, "#667085"))
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
                display = _risk_cell_summary(cell.items, cell.level) if len(cell.items) > 3 else "；".join(cell.items)
                lines = _wrap(display, 12, 4)
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


def _render_table_svg(spec: TableChartSpec) -> str:
    first_left = 24
    top = 88
    cell_h = 48
    cell_w = 150
    width = first_left * 2 + len(spec.columns) * cell_w
    height = top + (len(spec.rows) + 1) * cell_h + 36
    parts = [_svg_start(width, height), _title(spec.title, width)]
    for col_index, column in enumerate(spec.columns):
        x = first_left + col_index * cell_w
        parts.append(_rect(x, top, cell_w, cell_h, "#e8eef7", "#8b98a8", 0))
        for line_index, line in enumerate(_wrap(column, 10, 2)):
            parts.append(_text(line, x + cell_w / 2, top + 21 + line_index * 15, 12, anchor="middle", weight="600"))
    for row_index, row in enumerate(spec.rows):
        y = top + (row_index + 1) * cell_h
        for col_index, value in enumerate(row.cells):
            x = first_left + col_index * cell_w
            parts.append(_rect(x, y, cell_w, cell_h, "#ffffff", "#8b98a8", 0))
            for line_index, line in enumerate(_wrap(value, 12, 2)):
                parts.append(_text(line, x + 10, y + 20 + line_index * 15, 11, anchor="start"))
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


def _right_arrow(x: int | float, y: int | float, fill: str) -> str:
    return f"<path d='M{x - 6:.1f},{y - 5:.1f} L{x:.1f},{y:.1f} L{x - 6:.1f},{y + 5:.1f} Z' fill='{fill}'/>"


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


def _risk_cell_summary(items: list[str], level: str | None) -> str:
    level_name = {
        "low": "低",
        "medium": "中",
        "high": "高",
        "critical": "极高",
    }.get(level or "", "风险")
    return f"{len(items)}项·{level_name}"


def _mermaid_text(value: str) -> str:
    return value.replace('"', "'")


def _flow_layout(spec: FlowChartSpec) -> dict[str, tuple[int, int]]:
    node_ids = [node.id for node in spec.nodes]
    incoming = {node_id: 0 for node_id in node_ids}
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for from_id, to_id in _flow_layout_edges(spec):
        outgoing.setdefault(from_id, []).append(to_id)
        incoming[to_id] = incoming.get(to_id, 0) + 1
    roots = [node_id for node_id in node_ids if incoming.get(node_id, 0) == 0] or node_ids[:1]
    row_by_id: dict[str, int] = {node_id: 0 for node_id in roots}
    queue = list(roots)
    max_relaxations = max(len(node_ids) - 1, 0)
    relaxations = {node_id: 0 for node_id in node_ids}
    while queue:
        current = queue.pop(0)
        for child in outgoing.get(current, []):
            next_row = row_by_id[current] + 1
            if child not in row_by_id or next_row > row_by_id[child]:
                if relaxations.get(child, 0) >= max_relaxations:
                    continue
                row_by_id[child] = next_row
                relaxations[child] = relaxations.get(child, 0) + 1
                queue.append(child)
    for node_id in node_ids:
        row_by_id.setdefault(node_id, max(row_by_id.values(), default=0) + 1)
    rows: dict[int, list[str]] = {}
    for node_id in node_ids:
        rows.setdefault(row_by_id[node_id], []).append(node_id)
    layout: dict[str, tuple[int, int]] = {}
    max_cols = max((len(values) for values in rows.values()), default=1)
    for row, ids in rows.items():
        pad = max((max_cols - len(ids)) // 2, 0)
        for col, node_id in enumerate(ids, start=pad):
            layout[node_id] = (col, row)
    return layout


def _gantt_tick_step(total_days: int) -> int:
    if total_days <= 14:
        return 1
    if total_days <= 90:
        return 7
    return 30


def _gantt_tick_label(value: date, step_days: int) -> str:
    if step_days == 1:
        return value.strftime("%m-%d")
    if step_days == 7:
        return f"{value.month}/{value.day}"
    return value.strftime("%Y-%m")
