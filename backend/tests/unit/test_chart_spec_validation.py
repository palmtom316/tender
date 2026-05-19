from __future__ import annotations

import pytest

from tender_backend.services.chart_generation_service import default_chart_spec
from tender_backend.services.chart_service.renderers import build_mermaid_source
from tender_backend.services.chart_service.renderers import render_chart_spec
from tender_backend.services.chart_service.specs import parse_chart_spec, validate_chart_spec
from tender_backend.services.chart_service.specs import SUPPORTED_CHART_TYPES


@pytest.mark.parametrize("chart_type", sorted(SUPPORTED_CHART_TYPES - {"schedule_gantt", "critical_path", "outage_timeline"}))
def test_default_chart_specs_parse_and_render_for_supported_non_schedule_types(chart_type: str) -> None:
    title = f"{chart_type} 默认图表"
    spec_json = default_chart_spec(chart_type=chart_type, title=title, placeholder_key=f"{chart_type}_main")
    payload = {"chart_type": chart_type, "title": title, **spec_json}

    validation = validate_chart_spec(payload)

    assert validation["valid"] is True, validation["issues"]
    spec = parse_chart_spec(payload)
    rendered = render_chart_spec(spec)
    assert rendered.svg.startswith("<svg")
    assert title in rendered.svg


@pytest.mark.parametrize("chart_type", ["schedule_gantt", "critical_path", "outage_timeline"])
def test_default_schedule_specs_are_source_safe_table_fallbacks(chart_type: str) -> None:
    spec_json = default_chart_spec(chart_type=chart_type, title="进度计划图", placeholder_key=f"{chart_type}_main")

    assert spec_json["_default_spec"] is True
    assert "tasks" not in spec_json
    assert "fallback_reason" in spec_json
    assert spec_json["columns"] == ["阶段/工序", "计划开始条件", "计划完成条件", "衔接关系", "来源"]


def test_flow_chart_spec_validates_and_builds_mermaid() -> None:
    spec = parse_chart_spec(
        {
            "chart_type": "construction_flow",
            "title": "施工流程图",
            "placeholder_key": "construction_flow_main",
            "nodes": [
                {"id": "prepare", "label": "施工准备"},
                {"id": "install", "label": "设备安装"},
            ],
            "edges": [{"from": "prepare", "to": "install"}],
        }
    )

    source = build_mermaid_source(spec)

    assert source is not None
    assert "flowchart TB" in source
    assert 'prepare["施工准备"]' in source
    assert "prepare --> install" in source


def test_rejects_markup_and_dangling_edges() -> None:
    result = validate_chart_spec(
        {
            "chart_type": "construction_flow",
            "title": "施工流程图",
            "nodes": [{"id": "prepare", "label": "<script>alert(1)</script>"}],
            "edges": [{"from": "prepare", "to": "missing"}],
        }
    )

    assert result["valid"] is False
    assert result["issues"]


def test_gantt_rejects_end_before_start() -> None:
    result = validate_chart_spec(
        {
            "chart_type": "schedule_gantt",
            "title": "进度计划",
            "tasks": [{"id": "a", "label": "施工", "start": "2026-06-10", "end": "2026-06-01"}],
        }
    )

    assert result["valid"] is False


def test_matrix_specs_validate_references() -> None:
    risk = validate_chart_spec(
        {
            "chart_type": "risk_matrix",
            "title": "风险矩阵",
            "rows": ["低", "高"],
            "columns": ["低", "高"],
            "cells": [{"row": "高", "column": "高", "items": ["工期延误"], "level": "high"}],
        }
    )
    responsibility = validate_chart_spec(
        {
            "chart_type": "responsibility_matrix",
            "title": "职责矩阵",
            "roles": ["项目经理"],
            "activities": ["施工准备"],
            "assignments": [{"role": "项目经理", "activity": "施工准备", "level": "负责"}],
        }
    )

    assert risk["valid"] is True
    assert responsibility["valid"] is True


def test_table_chart_specs_validate_and_render() -> None:
    for chart_type in ["response_matrix", "indicator_table", "interface_table", "equipment_table"]:
        result = validate_chart_spec(
            {
                "chart_type": chart_type,
                "title": "表格图表",
                "columns": ["事项", "来源", "措施"],
                "rows": [
                    {"cells": ["施工准备", "招标文件", "按要求执行"]},
                    {"cells": ["资料归档", "发包人要求", "同步留痕"]},
                ],
            }
        )

        assert result["valid"] is True


def test_extended_flow_and_critical_path_specs_validate() -> None:
    closure = validate_chart_spec(
        {
            "chart_type": "closure_flow",
            "title": "问题闭环流程",
            "nodes": [{"id": "find", "label": "发现"}, {"id": "close", "label": "销项"}],
            "edges": [{"from": "find", "to": "close"}],
        }
    )
    data_flow = validate_chart_spec(
        {
            "chart_type": "data_flow",
            "title": "数据流转图",
            "nodes": [{"id": "collect", "label": "采集"}, {"id": "archive", "label": "归档"}],
            "edges": [{"from": "collect", "to": "archive"}],
        }
    )
    critical_path = validate_chart_spec(
        {
            "chart_type": "critical_path",
            "title": "关键路径图",
            "tasks": [
                {"id": "a", "label": "施工准备", "start": "2026-06-01", "end": "2026-06-02", "is_critical": True},
                {"id": "b", "label": "设备安装", "start": "2026-06-03", "end": "2026-06-10", "is_critical": True},
            ],
            "dependencies": [{"from": "a", "to": "b"}],
        }
    )

    assert closure["valid"] is True
    assert data_flow["valid"] is True
    assert critical_path["valid"] is True


@pytest.mark.parametrize(
    ("chart_type", "spec_json"),
    [
        (
            "single_line_diagram",
            {
                "elements": ["10kV进线", "环网柜", "配变", "低压出线"],
                "notes": ["结构化占位，需人工复核一次接线关系"],
            },
        ),
        (
            "site_layout",
            {
                "elements": ["施工围挡", "材料堆场", "电缆沟", "临时通道"],
                "notes": ["结构化占位，需结合现场平面图复核"],
            },
        ),
        (
            "outage_timeline",
            {
                "tasks": [
                    {"id": "permit", "label": "停电许可", "start": "2026-06-01", "end": "2026-06-01"},
                    {"id": "work", "label": "施工窗口", "start": "2026-06-02", "end": "2026-06-03"},
                ],
                "dependencies": [{"from": "permit", "to": "work"}],
            },
        ),
        (
            "wbs_tree",
            {
                "nodes": [
                    {"id": "root", "label": "配网改造"},
                    {"id": "line", "label": "线路施工", "parent": "root"},
                    {"id": "test", "label": "试验送电", "parent": "root"},
                ],
            },
        ),
        (
            "fmea_matrix",
            {
                "columns": ["工序", "失效模式", "影响", "控制措施"],
                "rows": [{"cells": ["电缆接头", "受潮", "绝缘下降", "环境封闭与耐压试验"]}],
            },
        ),
    ],
)
def test_distribution_deep_chart_types_validate_and_render_nonempty(chart_type: str, spec_json: dict) -> None:
    title = f"{chart_type} 图表"
    payload = {"chart_type": chart_type, "title": title, **spec_json}

    validation = validate_chart_spec(payload)

    assert validation["valid"] is True, validation["issues"]
    rendered = render_chart_spec(parse_chart_spec(payload))
    assert rendered.svg.lstrip().startswith("<svg")
    assert len(rendered.svg) > 120
    assert title in rendered.svg


def test_single_line_and_site_layout_render_structured_manual_review_placeholders() -> None:
    for chart_type in ("single_line_diagram", "site_layout"):
        spec = parse_chart_spec(
            {
                "chart_type": chart_type,
                "title": "结构化占位图",
                "elements": ["进线", "设备", "出线"],
                "notes": ["待人工复核"],
            }
        )

        rendered = render_chart_spec(spec)

        assert rendered.engine == "structured_placeholder"
        assert "人工复核" in rendered.svg
