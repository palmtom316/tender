from __future__ import annotations

import pytest

from tender_backend.core import config
from tender_backend.services.chart_service.render_strategy import resolve_render_strategy
from tender_backend.services.chart_service.specs import SUPPORTED_CHART_TYPES


@pytest.fixture(autouse=True)
def reset_settings_cache():
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


@pytest.mark.parametrize("chart_type", sorted(SUPPORTED_CHART_TYPES))
def test_every_supported_chart_type_has_render_strategy(chart_type: str) -> None:
    strategy = resolve_render_strategy(chart_type)

    assert strategy.chart_type == chart_type
    assert strategy.primary in {"mermaid_sidecar", "native_svg", "vl_convert"}
    assert strategy.fallback in {None, "native_flow", "native_gantt", "native_svg"}


def test_schedule_gantt_uses_mermaid_then_native_gantt() -> None:
    strategy = resolve_render_strategy("schedule_gantt")

    assert strategy.primary == "mermaid_sidecar"
    assert strategy.fallback == "native_gantt"


def test_risk_matrix_uses_vl_convert_with_native_fallback() -> None:
    strategy = resolve_render_strategy("risk_matrix")

    assert strategy.primary == "vl_convert"
    assert strategy.fallback == "native_svg"


def test_indicator_table_uses_vl_convert_with_native_fallback() -> None:
    strategy = resolve_render_strategy("indicator_table")

    assert strategy.primary == "vl_convert"
    assert strategy.fallback == "native_svg"


def test_other_table_types_stay_native_svg_only() -> None:
    for chart_type in ("response_matrix", "interface_table", "equipment_table"):
        strategy = resolve_render_strategy(chart_type)

        assert strategy.primary == "native_svg"
        assert strategy.fallback is None


def test_unknown_render_strategy_raises_key_error() -> None:
    with pytest.raises(KeyError):
        resolve_render_strategy("unknown_chart")


def test_flow_strategy_defaults_to_mermaid_sidecar() -> None:
    strategy = resolve_render_strategy("construction_flow")

    assert strategy.primary == "mermaid_sidecar"
    assert strategy.fallback == "native_flow"


def test_flow_strategy_uses_gpt_vis_when_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("CHART_FLOW_ENGINE", "gpt_vis")
    config.get_settings.cache_clear()

    strategy = resolve_render_strategy("construction_flow")

    assert strategy.primary == "gpt_vis"
    assert strategy.fallback == "mermaid_sidecar"


def test_gantt_strategy_stays_mermaid_even_when_flow_engine_is_gpt_vis(monkeypatch) -> None:
    """GPT-Vis does not support Gantt — schedule_gantt/critical_path must stay mermaid.

    See docs/plans/2026-05-18-gpt-vis-ssr-research.md §1.5.
    """
    monkeypatch.setenv("CHART_FLOW_ENGINE", "gpt_vis")
    config.get_settings.cache_clear()

    gantt = resolve_render_strategy("schedule_gantt")
    critical = resolve_render_strategy("critical_path")

    assert gantt.primary == "mermaid_sidecar"
    assert gantt.fallback == "native_gantt"
    assert critical.primary == "mermaid_sidecar"
    assert critical.fallback == "native_gantt"


def test_matrix_strategies_unaffected_by_flow_engine_override(monkeypatch) -> None:
    monkeypatch.setenv("CHART_FLOW_ENGINE", "gpt_vis")
    config.get_settings.cache_clear()

    for chart_type in ("risk_matrix", "responsibility_matrix", "indicator_table"):
        strategy = resolve_render_strategy(chart_type)
        assert strategy.primary == "vl_convert"
        assert strategy.fallback == "native_svg"
