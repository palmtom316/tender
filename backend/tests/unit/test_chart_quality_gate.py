from __future__ import annotations

from uuid import uuid4

from tender_backend.services.chart_generation_service import ChartGenerationService
from tender_backend.services.chart_service.quality_gate import evaluate_svg_quality
from tender_backend.services.chart_service.templates import get_chart_template


def test_evaluate_svg_quality_reports_extreme_svg_issues() -> None:
    template = get_chart_template("construction_flow")
    svg = (
        "<svg viewBox='0 0 1200 100'>"
        "<text font-size='8'>超长超长超长超长超长节点名称</text>"
        + "".join("<text font-size='11'>节点</text>" for _ in range(40))
        + "</svg>"
    )

    report = evaluate_svg_quality(svg, template)

    assert report["passed"] is False
    assert {
        issue["code"]
        for issue in report["issues"]
    } >= {"text_overflow", "aspect_extreme", "density_overload", "font_below_minimum"}


def test_create_or_update_records_quality_gate_without_changing_status(monkeypatch) -> None:
    rows = []

    class _Repo:
        def create(self, _conn, **kwargs):
            rows.append(kwargs)

            class _Row:
                id = uuid4()
                project_id = kwargs["project_id"]
                outline_node_id = kwargs.get("outline_node_id")
                chart_type = kwargs["chart_type"]
                title = kwargs["title"]
                spec_json = kwargs["spec_json"]
                rendered_svg = kwargs["rendered_svg"]
                rendered_path = None
                placeholder_key = kwargs["placeholder_key"]
                mermaid_source = kwargs["mermaid_source"]
                rendered_png_path = kwargs["rendered_png_path"]
                status = kwargs["status"]
                version = 1
                metadata_json = kwargs["metadata_json"]

                class _Time:
                    def isoformat(self):
                        return "2026-05-17T00:00:00"

                created_at = _Time()
                updated_at = _Time()

            return _Row()

    monkeypatch.setattr("tender_backend.services.chart_generation_service.svg_to_png", lambda _svg, path: path)
    monkeypatch.setattr(
        "tender_backend.services.chart_generation_service.render_chart_spec",
        lambda _spec: type(
            "_Rendered",
            (),
            {
                "svg": "<svg viewBox='0 0 1200 100'><text font-size='8'>超长超长超长超长超长节点名称</text></svg>",
                "mermaid_source": None,
                "engine": "native_svg",
            },
        )(),
    )
    service = ChartGenerationService(repo=_Repo())

    result = service.create_or_update(
        object(),
        project_id=uuid4(),
        chart_type="construction_flow",
        title="施工流程图",
        spec_json={"placeholder_key": "construction_flow", "nodes": ["准备"], "edges": []},
    )

    assert result["status"] == "draft"
    assert rows[0]["metadata_json"]["quality_gate"]["passed"] is False
    assert rows[0]["metadata_json"]["quality_gate"]["issues"]
