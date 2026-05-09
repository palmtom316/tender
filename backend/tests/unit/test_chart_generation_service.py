from tender_backend.services.chart_generation_service import ChartGenerationService


def test_org_chart_requires_nodes() -> None:
    result = ChartGenerationService().validate(chart_type="org_chart", spec_json={})

    assert result["valid"] is False
    assert result["issues"]


def test_render_svg_accepts_string_and_object_nodes() -> None:
    svg = ChartGenerationService().render_svg(
        title="项目组织机构图",
        spec_json={"nodes": ["项目经理", {"label": "安全负责人"}]},
    )

    assert "项目组织机构图" in svg
    assert "项目经理" in svg
    assert "安全负责人" in svg
