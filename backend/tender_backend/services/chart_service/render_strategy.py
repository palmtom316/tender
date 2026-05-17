from __future__ import annotations

from dataclasses import dataclass

from tender_backend.services.chart_service.specs import FLOW_CHART_TYPES, TABLE_CHART_TYPES, SUPPORTED_CHART_TYPES


@dataclass(frozen=True)
class RenderStrategy:
    chart_type: str
    primary: str
    fallback: str | None = None


_STRATEGIES: dict[str, RenderStrategy] = {
    **{chart_type: RenderStrategy(chart_type, "mermaid_sidecar", "native_flow") for chart_type in FLOW_CHART_TYPES},
    "schedule_gantt": RenderStrategy("schedule_gantt", "mermaid_sidecar", "native_gantt"),
    "critical_path": RenderStrategy("critical_path", "mermaid_sidecar", "native_gantt"),
    "risk_matrix": RenderStrategy("risk_matrix", "vl_convert", "native_svg"),
    "responsibility_matrix": RenderStrategy("responsibility_matrix", "vl_convert", "native_svg"),
    **{chart_type: RenderStrategy(chart_type, "native_svg", None) for chart_type in TABLE_CHART_TYPES},
}

if set(_STRATEGIES) != SUPPORTED_CHART_TYPES:
    missing = sorted(SUPPORTED_CHART_TYPES - set(_STRATEGIES))
    extra = sorted(set(_STRATEGIES) - SUPPORTED_CHART_TYPES)
    raise RuntimeError(f"chart render strategy mismatch: missing={missing}, extra={extra}")


def resolve_render_strategy(chart_type: str) -> RenderStrategy:
    return _STRATEGIES[chart_type]
