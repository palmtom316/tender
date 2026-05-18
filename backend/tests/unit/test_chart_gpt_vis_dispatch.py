"""GPT-Vis multi-engine flow dispatch tests (T8).

When CHART_FLOW_ENGINE=gpt_vis and CHART_GPT_VIS_URL is unset (or the
service is unreachable), render_chart_spec must fall through to the
mermaid_sidecar fallback rather than raise. With CHART_FLOW_ENGINE
defaulting to mermaid_sidecar, the gpt_vis branch is never even
attempted — behavior identical to pre-T8.
"""

from __future__ import annotations

import pytest

from tender_backend.core import config
from tender_backend.services.chart_service import renderers
from tender_backend.services.chart_service.renderers import (
    _flow_to_gpt_vis_payload,
    render_chart_spec,
)
from tender_backend.services.chart_service.specs import parse_chart_spec


@pytest.fixture(autouse=True)
def reset_settings_cache():
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def _flow_spec():
    return parse_chart_spec(
        {
            "chart_type": "construction_flow",
            "title": "施工流程",
            "direction": "TB",
            "nodes": [
                {"id": "start", "label": "准备"},
                {"id": "build", "label": "实施"},
                {"id": "review", "label": "检查"},
            ],
            "edges": [
                {"from": "start", "to": "build"},
                {"from": "build", "to": "review"},
            ],
        }
    )


def test_flow_to_gpt_vis_payload_maps_org_chart_to_organization_chart():
    spec = parse_chart_spec(
        {
            "chart_type": "org_chart",
            "title": "项目组织",
            "direction": "TB",
            "nodes": [{"id": "pm", "label": "项目经理"}, {"id": "tech", "label": "技术员", "parent": "pm"}],
            "edges": [{"from": "pm", "to": "tech"}],
        }
    )

    payload = _flow_to_gpt_vis_payload(spec)

    assert payload["type"] == "organization-chart"
    assert payload["data"]["title"] == "项目组织"


def test_flow_to_gpt_vis_payload_maps_quality_system_to_network_graph():
    spec = parse_chart_spec(
        {
            "chart_type": "quality_system",
            "title": "质量体系",
            "direction": "TB",
            "nodes": [{"id": "a", "label": "策划"}, {"id": "b", "label": "执行"}],
            "edges": [{"from": "a", "to": "b"}],
        }
    )

    payload = _flow_to_gpt_vis_payload(spec)

    assert payload["type"] == "network-graph"


def test_flow_to_gpt_vis_payload_defaults_to_flow_diagram():
    payload = _flow_to_gpt_vis_payload(_flow_spec())

    assert payload["type"] == "flow-diagram"
    assert len(payload["data"]["nodes"]) == 3
    assert len(payload["data"]["edges"]) == 2


def test_render_chart_spec_falls_back_to_mermaid_when_gpt_vis_url_unset(monkeypatch):
    monkeypatch.setenv("CHART_FLOW_ENGINE", "gpt_vis")
    monkeypatch.delenv("CHART_GPT_VIS_URL", raising=False)
    config.get_settings.cache_clear()

    # Stub mermaid sidecar to return a known SVG so we don't depend on a live
    # mermaid-render container in the test environment.
    monkeypatch.setattr(renderers, "_render_mermaid_sidecar", lambda *_args, **_kw: "<svg id='from-mermaid'/>")

    result = render_chart_spec(_flow_spec())

    assert result.engine == "mermaid_sidecar"
    assert result.svg == "<svg id='from-mermaid'/>"


def test_render_chart_spec_uses_gpt_vis_when_client_returns_svg(monkeypatch):
    monkeypatch.setenv("CHART_FLOW_ENGINE", "gpt_vis")
    monkeypatch.setenv("CHART_GPT_VIS_URL", "http://gpt-vis-ssr:7102")
    config.get_settings.cache_clear()

    monkeypatch.setattr(renderers, "render_via_gpt_vis", lambda payload: "<svg id='from-gpt-vis'/>")

    result = render_chart_spec(_flow_spec())

    assert result.engine == "gpt_vis"
    assert result.svg == "<svg id='from-gpt-vis'/>"


def test_render_chart_spec_falls_back_to_native_when_both_gpt_vis_and_mermaid_fail(monkeypatch):
    monkeypatch.setenv("CHART_FLOW_ENGINE", "gpt_vis")
    monkeypatch.setenv("CHART_GPT_VIS_URL", "http://gpt-vis-ssr:7102")
    config.get_settings.cache_clear()

    monkeypatch.setattr(renderers, "render_via_gpt_vis", lambda payload: None)
    monkeypatch.setattr(renderers, "_render_mermaid_sidecar", lambda *_args, **_kw: None)

    result = render_chart_spec(_flow_spec())

    assert result.engine == "system_mermaid_fallback"
    assert result.svg.startswith("<svg")


def test_render_chart_spec_default_engine_unchanged(monkeypatch):
    # No env override → strategy stays mermaid; gpt_vis branch never entered.
    monkeypatch.delenv("CHART_FLOW_ENGINE", raising=False)
    config.get_settings.cache_clear()

    monkeypatch.setattr(renderers, "_render_mermaid_sidecar", lambda *_args, **_kw: "<svg id='from-mermaid'/>")
    called = {"gpt_vis": False}

    def _fail_if_called(_payload):
        called["gpt_vis"] = True
        return "<svg/>"

    monkeypatch.setattr(renderers, "render_via_gpt_vis", _fail_if_called)

    result = render_chart_spec(_flow_spec())

    assert result.engine == "mermaid_sidecar"
    assert called["gpt_vis"] is False
