"""Pydantic → Vega-Lite spec 映射层。

把 RiskMatrixSpec / ResponsibilityMatrixSpec 转成 Vega-Lite JSON，
供 vl-convert 渲染。视觉常量统一来自 visual_template。
"""

from __future__ import annotations

from typing import Any

from tender_backend.services.chart_service.specs import (
    ResponsibilityMatrixSpec,
    RiskMatrixSpec,
    TableChartSpec,
)
from tender_backend.services.chart_service.visual_template import (
    FONT,
    PALETTE,
    RISK_LEVEL_COLORS,
)


_RISK_LEVEL_ORDER = ["low", "medium", "high", "critical"]
_RISK_LEVEL_CN = {"low": "低", "medium": "中", "high": "高", "critical": "极高"}
_CELL_SUMMARY_THRESHOLD = 3
_CELL_WRAP_CHARS = 10
_INDICATOR_TABLE_ROW_HEIGHT = 28
_INDICATOR_TABLE_TARGET_WIDTH = 720


def risk_matrix_to_vega(spec: RiskMatrixSpec) -> dict[str, Any]:
    cell_index = {(cell.row, cell.column): cell for cell in spec.cells}
    values: list[dict[str, Any]] = []
    for row in spec.rows:
        for column in spec.columns:
            cell = cell_index.get((row, column))
            level = cell.level if cell else None
            items = list(cell.items) if cell else []
            values.append(
                {
                    "row": row,
                    "column": column,
                    "level": level or "none",
                    "display": _risk_cell_display(items, level),
                }
            )

    column_count = max(len(spec.columns), 1)
    row_count = max(len(spec.rows), 1)
    cell_width, cell_height = _square_matrix_cell(column_count, row_count, base_size=130, max_size=200)
    width = cell_width * column_count
    height = cell_height * row_count

    color_domain = [level for level in _RISK_LEVEL_ORDER if any(item["level"] == level for item in values)]
    color_domain.append("none")
    color_range = [RISK_LEVEL_COLORS[level] for level in color_domain if level != "none"]
    color_range.append(PALETTE.risk_default)

    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "config": _config(),
        "title": _title(spec.title),
        "width": width,
        "height": height,
        "data": {"values": values},
        "encoding": {
            "x": {
                "field": "column",
                "type": "ordinal",
                "sort": list(spec.columns),
                "axis": _axis("概率"),
            },
            "y": {
                "field": "row",
                "type": "ordinal",
                "sort": list(spec.rows),
                "axis": _axis("影响"),
            },
        },
        "layer": [
            {
                "mark": {
                    "type": "rect",
                    "stroke": PALETTE.border,
                    "strokeWidth": 1,
                },
                "encoding": {
                    "color": {
                        "field": "level",
                        "type": "nominal",
                        "scale": {"domain": color_domain, "range": color_range},
                        "legend": None,
                    }
                },
            },
            {
                "mark": {
                    "type": "text",
                    "fontSize": FONT.cell_text_px,
                    "fontWeight": "normal",
                    "lineBreak": "\n",
                    "color": PALETTE.text,
                    "limit": cell_width - 18,
                },
                "encoding": {
                    "text": {"field": "display", "type": "nominal"},
                },
            },
        ],
    }


def responsibility_matrix_to_vega(spec: ResponsibilityMatrixSpec) -> dict[str, Any]:
    assignment_index = {(item.activity, item.role): item.level for item in spec.assignments}
    values: list[dict[str, Any]] = []
    for activity in spec.activities:
        for role in spec.roles:
            level = assignment_index.get((activity, role), "")
            values.append(
                {
                    "activity": activity,
                    "role": role,
                    "level": level,
                    "filled": bool(level),
                }
            )

    role_count = max(len(spec.roles), 1)
    activity_count = max(len(spec.activities), 1)
    cell_width, cell_height = _square_matrix_cell(role_count, activity_count, base_size=80, max_size=140, height_ratio=0.7)
    width = cell_width * role_count
    height = cell_height * activity_count

    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "config": _config(),
        "title": _title(spec.title),
        "width": width,
        "height": height,
        "data": {"values": values},
        "encoding": {
            "x": {
                "field": "role",
                "type": "ordinal",
                "sort": list(spec.roles),
                "axis": _axis("角色"),
            },
            "y": {
                "field": "activity",
                "type": "ordinal",
                "sort": list(spec.activities),
                "axis": _axis("工作事项"),
            },
        },
        "layer": [
            {
                "mark": {
                    "type": "rect",
                    "stroke": PALETTE.border,
                    "strokeWidth": 1,
                },
                "encoding": {
                    "color": {
                        "field": "filled",
                        "type": "nominal",
                        "scale": {
                            "domain": [True, False],
                            "range": [PALETTE.surface_alt, PALETTE.surface],
                        },
                        "legend": None,
                    }
                },
            },
            {
                "mark": {
                    "type": "text",
                    "fontSize": FONT.cell_text_px,
                    "fontWeight": "bold",
                    "color": PALETTE.primary,
                    "limit": cell_width - 8,
                },
                "encoding": {
                    "text": {"field": "level", "type": "nominal"},
                },
            },
        ],
    }


def indicator_table_to_vega(spec: TableChartSpec) -> dict[str, Any]:
    """Map TableChartSpec(indicator_table) to a Vega-Lite table layout.

    Documentary table: 1 header row + N body rows, each cell = rect + text.
    Width is fixed to A4-friendly target; height grows with row count.
    """
    column_count = max(len(spec.columns), 1)
    values: list[dict[str, Any]] = []
    for col_index, column in enumerate(spec.columns):
        values.append({"row": 0, "col": col_index, "text": column, "is_header": True})
    for row_index, row in enumerate(spec.rows, start=1):
        for col_index, cell in enumerate(row.cells):
            values.append({"row": row_index, "col": col_index, "text": str(cell), "is_header": False})

    total_rows = len(spec.rows) + 1
    width = _INDICATOR_TABLE_TARGET_WIDTH
    height = _INDICATOR_TABLE_ROW_HEIGHT * total_rows

    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "config": _config(),
        "title": _title(spec.title),
        "width": width,
        "height": height,
        "data": {"values": values},
        "encoding": {
            "x": {
                "field": "col",
                "type": "ordinal",
                "sort": list(range(column_count)),
                "axis": None,
            },
            "y": {
                "field": "row",
                "type": "ordinal",
                "sort": list(range(total_rows)),
                "axis": None,
            },
        },
        "layer": [
            {
                "mark": {
                    "type": "rect",
                    "stroke": PALETTE.border,
                    "strokeWidth": 1,
                },
                "encoding": {
                    "color": {
                        "field": "is_header",
                        "type": "nominal",
                        "scale": {
                            "domain": [True, False],
                            "range": [PALETTE.surface_alt, PALETTE.surface],
                        },
                        "legend": None,
                    }
                },
            },
            {
                "mark": {
                    "type": "text",
                    "fontSize": FONT.cell_text_px,
                    "color": PALETTE.text,
                    "limit": width // column_count - 12,
                    "align": "center",
                    "baseline": "middle",
                    "lineBreak": "\n",
                },
                "encoding": {
                    "text": {"field": "text", "type": "nominal"},
                    "fontWeight": {
                        "condition": {"test": "datum.is_header", "value": "bold"},
                        "value": "normal",
                    },
                },
            },
        ],
    }


def _title(text: str) -> dict[str, Any]:
    return {
        "text": text,
        "anchor": "middle",
        "fontSize": FONT.title_px,
        "fontWeight": "bold",
        "color": PALETTE.text,
        "offset": 16,
    }


def _axis(title: str) -> dict[str, Any]:
    return {
        "title": title,
        "labelFontSize": FONT.axis_label_px,
        "titleFontSize": FONT.subtitle_px,
        "labelColor": PALETTE.text,
        "titleColor": PALETTE.text_muted,
        "labelAngle": 0,
        "labelLimit": 200,
        "domainColor": PALETTE.border,
        "tickColor": PALETTE.border,
    }


def _config() -> dict[str, Any]:
    return {
        "background": PALETTE.surface,
        "font": FONT.family,
        "view": {"stroke": "transparent"},
        "axis": {
            "labelFont": FONT.family,
            "titleFont": FONT.family,
        },
        "title": {"font": FONT.family},
    }


def fmea_matrix_to_vega(spec: TableChartSpec) -> dict[str, Any]:
    return indicator_table_to_vega(spec)


def _risk_cell_display(items: list[str], level: str | None) -> str:
    if not items:
        return ""
    if len(items) > _CELL_SUMMARY_THRESHOLD:
        level_name = _RISK_LEVEL_CN.get(level or "", "风险")
        return f"{len(items)}项·{level_name}"
    return "\n".join(_wrap_cn(item, _CELL_WRAP_CHARS) for item in items)


def _wrap_cn(value: str, chars: int) -> str:
    cleaned = "".join(value.split())
    if len(cleaned) <= chars:
        return cleaned
    return "\n".join(cleaned[index : index + chars] for index in range(0, len(cleaned), chars))


def _square_matrix_cell(
    cols: int,
    rows: int,
    *,
    base_size: int,
    max_size: int,
    height_ratio: float = 1.0,
    min_total_width: int = 360,
) -> tuple[int, int]:
    """Pick bounded cell dimensions for matrix charts.

    `base_size` / `max_size` 是单元格宽度的常规下限 / 上限，`min_total_width` 保证小矩阵
    输出仍能撑到 96 DPI（A4 6 英寸 ≈ 576px @ 96 DPI，PNG 2x 缩放 = 内部 SVG ≥288）。
    这里不能按 rows / cols 无界拉伸，否则 1×40 这类合法矩阵会生成超大 SVG。
    `height_ratio` 让文字密度高的矩阵单元更扁，并用 56px 作为可读下限。
    """
    larger_axis = max(cols, rows)
    cell_width = max(base_size, min(max_size, int(base_size * 3 / larger_axis * 1.5)))
    cell_width = max(cell_width, min(max_size, _ceil_div(min_total_width, cols)))
    cell_height = max(int(base_size * height_ratio), 56)
    return cell_width, cell_height


def _ceil_div(numerator: int, denominator: int) -> int:
    return -(-numerator // denominator)
