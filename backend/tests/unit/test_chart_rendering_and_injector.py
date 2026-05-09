from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from docx import Document

from tender_backend.db.repositories.chart_asset_repo import ChartAssetRow
from tender_backend.services.chart_service.captions import FigureNumbering
from tender_backend.services.chart_service.png_converter import svg_to_png
from tender_backend.services.chart_service.renderers import render_chart_spec
from tender_backend.services.chart_service.specs import parse_chart_spec
from tender_backend.services.export_service import chart_asset_injector
from tender_backend.services.export_service.chart_asset_injector import ChartAssetInjector


def test_native_risk_matrix_renders_svg_and_png(tmp_path: Path) -> None:
    spec = parse_chart_spec(
        {
            "chart_type": "risk_matrix",
            "title": "项目风险矩阵",
            "rows": ["低影响", "高影响"],
            "columns": ["低概率", "高概率"],
            "cells": [{"row": "高影响", "column": "高概率", "items": ["工期延误"], "level": "high"}],
        }
    )

    rendered = render_chart_spec(spec)
    png = svg_to_png(rendered.svg, tmp_path / "risk.png")

    assert "项目风险矩阵" in rendered.svg
    assert rendered.engine == "native_svg"
    assert png.is_file()
    assert png.stat().st_size > 0


def test_figure_numbering_uses_chapter_prefix() -> None:
    numbering = FigureNumbering()

    assert numbering.next_number(chapter_code="8.1") == "图8-1"
    assert numbering.next_number(chapter_code="8.2") == "图8-2"
    assert numbering.next_number(chapter_code="9") == "图9-1"
    assert numbering.next_number(chapter_code="9", explicit="图A-1") == "图A-1"


def test_chart_asset_injector_replaces_placeholder_with_image_and_caption(tmp_path: Path, monkeypatch) -> None:
    project_id = uuid4()
    png = tmp_path / "chart.png"
    svg_to_png(
        "<svg xmlns='http://www.w3.org/2000/svg' width='120' height='60'><rect width='120' height='60' fill='white'/><text x='10' y='30'>测试图</text></svg>",
        png,
    )
    asset = ChartAssetRow(
        id=uuid4(),
        project_id=project_id,
        outline_node_id=None,
        chart_type="construction_flow",
        title="施工流程图",
        spec_json={"chapter_code": "8.1"},
        rendered_svg=None,
        rendered_path=None,
        placeholder_key="construction_flow_main",
        mermaid_source="flowchart TB",
        rendered_png_path=str(png),
        status="approved",
        version=1,
        metadata_json={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    class _Repo:
        def find_for_placeholder(self, _conn, *, project_id, key):
            assert key == "construction_flow_main"
            return [asset]

    monkeypatch.setattr(chart_asset_injector, "ChartAssetRepository", lambda: _Repo())

    document = Document()
    document.add_paragraph("{{chart:construction_flow_main}}")
    output = tmp_path / "out.docx"

    count = ChartAssetInjector(document, object(), project_id=project_id).inject_all()
    document.save(str(output))
    rendered = Document(str(output))
    text = "\n".join(paragraph.text for paragraph in rendered.paragraphs)

    assert count == 1
    assert "{{chart:" not in text
    assert "图8-1 施工流程图" in text
    assert len(rendered.inline_shapes) == 1
