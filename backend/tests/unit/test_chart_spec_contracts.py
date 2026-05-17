from __future__ import annotations

from tender_backend.services.chart_generation_service import _chart_spec_system_prompt, _prepare_payload


def test_flow_payload_strips_visual_fields_from_nodes() -> None:
    payload = _prepare_payload(
        chart_type="construction_flow",
        title="施工流程图",
        spec_json={
            "nodes": [
                {
                    "id": "prepare",
                    "label": "施工准备",
                    "x": 120,
                    "y": 80,
                    "fill": "#ff0000",
                    "stroke": "#000000",
                    "fontSize": 18,
                    "width": 240,
                    "height": 60,
                }
            ],
            "edges": [],
        },
    )

    assert payload["nodes"] == [{"id": "prepare", "label": "施工准备"}]


def test_chart_spec_prompt_forbids_visual_output() -> None:
    prompt = _chart_spec_system_prompt("construction_flow")

    assert "Never output coordinates" in prompt
    assert "colors" in prompt
    assert "SVG fragments" in prompt
    assert "Only output semantic chart structure" in prompt
