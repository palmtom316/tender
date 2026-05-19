from __future__ import annotations

from tender_backend.services.chart_service.specs import parse_chart_spec
from tender_backend.services.chart_service import vega_mapper
from tender_backend.services.chart_service.vega_mapper import indicator_table_to_vega, responsibility_matrix_to_vega, risk_matrix_to_vega


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


def test_responsibility_matrix_to_vega_bounds_tall_matrix_dimensions() -> None:
    spec = parse_chart_spec(
        {
            "chart_type": "responsibility_matrix",
            "title": "单角色长活动矩阵",
            "roles": ["项目经理"],
            "activities": [f"事项{i}" for i in range(40)],
            "assignments": [],
        }
    )

    chart = responsibility_matrix_to_vega(spec)

    assert chart["width"] <= 900
    assert chart["height"] <= 2400


def test_indicator_table_to_vega_emits_header_and_body_cells() -> None:
    spec = parse_chart_spec(
        {
            "chart_type": "indicator_table",
            "title": "关键指标表",
            "columns": ["指标", "目标", "单位"],
            "rows": [
                {"cells": ["合格率", "≥98", "%"]},
                {"cells": ["返工率", "≤2", "%"]},
            ],
        }
    )

    chart = indicator_table_to_vega(spec)

    assert chart["$schema"].startswith("https://vega.github.io/schema/vega-lite/")
    assert chart["title"]["text"] == "关键指标表"

    values = chart["data"]["values"]
    assert len(values) == 3 * 3  # 1 header row + 2 body rows × 3 columns
    header_cells = [item for item in values if item["is_header"]]
    body_cells = [item for item in values if not item["is_header"]]
    assert len(header_cells) == 3
    assert len(body_cells) == 6
    assert any(item["text"] == "指标" and item["is_header"] for item in values)
    assert any(item["text"] == "合格率" and not item["is_header"] for item in values)

    layer_marks = [layer["mark"]["type"] for layer in chart["layer"]]
    assert "rect" in layer_marks
    assert "text" in layer_marks


def test_indicator_table_to_vega_grows_height_with_row_count() -> None:
    rows = [{"cells": [f"指标{i}", f"≥{i}", "%"]} for i in range(12)]
    spec = parse_chart_spec(
        {
            "chart_type": "indicator_table",
            "title": "大表",
            "columns": ["指标", "目标", "单位"],
            "rows": rows,
        }
    )

    chart = indicator_table_to_vega(spec)

    # height must scale with body row count to keep cells readable; 12 rows + header
    assert chart["height"] >= 13 * 24


def test_fmea_matrix_to_vega_reuses_table_grid() -> None:
    spec = parse_chart_spec(
        {
            "chart_type": "fmea_matrix",
            "title": "施工FMEA矩阵",
            "columns": ["工序", "失效模式", "影响", "控制措施"],
            "rows": [{"cells": ["电缆接头", "受潮", "绝缘下降", "环境封闭与耐压试验"]}],
        }
    )

    chart = vega_mapper.fmea_matrix_to_vega(spec)

    assert chart["title"]["text"] == "施工FMEA矩阵"
    assert any(item["text"] == "失效模式" and item["is_header"] for item in chart["data"]["values"])
    assert any(item["text"] == "绝缘下降" and not item["is_header"] for item in chart["data"]["values"])
