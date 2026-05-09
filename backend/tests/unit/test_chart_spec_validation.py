from __future__ import annotations

from tender_backend.services.chart_service.renderers import build_mermaid_source
from tender_backend.services.chart_service.specs import parse_chart_spec, validate_chart_spec


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
