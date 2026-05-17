from __future__ import annotations

from tender_backend.services.chart_service.specs import parse_chart_spec
from tender_backend.services.chart_service.vega_mapper import (
    responsibility_matrix_to_vega,
    risk_matrix_to_vega,
)


def test_risk_matrix_to_vega_emits_full_grid_and_color_scale() -> None:
    spec = parse_chart_spec(
        {
            "chart_type": "risk_matrix",
            "title": "施工风险分级矩阵",
            "rows": ["低影响", "中影响", "高影响"],
            "columns": ["低概率", "中概率", "高概率"],
            "cells": [
                {"row": "高影响", "column": "中概率", "items": ["停电窗口延误"], "level": "high"},
                {"row": "中影响", "column": "高概率", "items": ["物资到货滞后"], "level": "medium"},
            ],
        }
    )

    chart = risk_matrix_to_vega(spec)

    values = chart["data"]["values"]
    assert len(values) == 9
    high_med = next(item for item in values if item["row"] == "高影响" and item["column"] == "中概率")
    assert high_med["level"] == "high"
    assert "停电窗口延误" in high_med["display"]
    empty_cell = next(item for item in values if item["row"] == "低影响" and item["column"] == "低概率")
    assert empty_cell["level"] == "none"
    assert empty_cell["display"] == ""

    color_scale = chart["layer"][0]["encoding"]["color"]["scale"]
    assert color_scale["domain"][-1] == "none"
    assert chart["title"]["text"] == "施工风险分级矩阵"


def test_risk_matrix_to_vega_summarizes_dense_cells() -> None:
    spec = parse_chart_spec(
        {
            "chart_type": "risk_matrix",
            "title": "风险矩阵",
            "rows": ["高影响"],
            "columns": ["高概率"],
            "cells": [
                {
                    "row": "高影响",
                    "column": "高概率",
                    "items": ["风险1", "风险2", "风险3", "风险4"],
                    "level": "critical",
                }
            ],
        }
    )

    chart = risk_matrix_to_vega(spec)
    cell = chart["data"]["values"][0]

    assert cell["display"] == "4项·极高"


def test_responsibility_matrix_to_vega_marks_filled_assignments() -> None:
    spec = parse_chart_spec(
        {
            "chart_type": "responsibility_matrix",
            "title": "岗位责任矩阵图",
            "roles": ["项目经理", "技术负责人"],
            "activities": ["施工准备", "技术交底"],
            "assignments": [
                {"role": "项目经理", "activity": "施工准备", "level": "负责"},
            ],
        }
    )

    chart = responsibility_matrix_to_vega(spec)

    values = chart["data"]["values"]
    assert len(values) == 4
    filled = next(item for item in values if item["activity"] == "施工准备" and item["role"] == "项目经理")
    assert filled == {"activity": "施工准备", "role": "项目经理", "level": "负责", "filled": True}
    empty = next(item for item in values if item["activity"] == "技术交底" and item["role"] == "项目经理")
    assert empty["filled"] is False
    assert empty["level"] == ""
