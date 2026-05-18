from __future__ import annotations

import pytest

from tender_backend.services.chart_service.render_strategy import resolve_render_strategy
from tender_backend.services.chart_service.specs import SUPPORTED_CHART_TYPES


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
