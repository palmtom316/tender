from __future__ import annotations

from dataclasses import dataclass

from tender_backend.core.config import get_settings
from tender_backend.services.chart_service.specs import (
    DIAGRAM_PLACEHOLDER_TYPES,
    FLOW_CHART_TYPES,
    TABLE_CHART_TYPES,
    SUPPORTED_CHART_TYPES,
)


@dataclass(frozen=True)
class RenderStrategy:
    chart_type: str
    primary: str
    fallback: str | None = None


_TABLE_TYPES_NATIVE_ONLY = TABLE_CHART_TYPES - {"indicator_table", "fmea_matrix"}

# Static strategies for non-flow chart types. Flow types are resolved
# dynamically in resolve_render_strategy() so the CHART_FLOW_ENGINE
# setting can switch them between mermaid_sidecar (default) and gpt_vis
# at request time. Gantt types stay on mermaid because GPT-Vis does not
# support Gantt (see docs/plans/2026-05-18-gpt-vis-ssr-research.md §1.5).
_STATIC_STRATEGIES: dict[str, RenderStrategy] = {
    "schedule_gantt": RenderStrategy("schedule_gantt", "mermaid_sidecar", "native_gantt"),
    "critical_path": RenderStrategy("critical_path", "mermaid_sidecar", "native_gantt"),
    "outage_timeline": RenderStrategy("outage_timeline", "mermaid_sidecar", "native_gantt"),
    "risk_matrix": RenderStrategy("risk_matrix", "vl_convert", "native_svg"),
    "responsibility_matrix": RenderStrategy("responsibility_matrix", "vl_convert", "native_svg"),
    "indicator_table": RenderStrategy("indicator_table", "vl_convert", "native_svg"),
    "fmea_matrix": RenderStrategy("fmea_matrix", "vl_convert", "native_svg"),
    **{chart_type: RenderStrategy(chart_type, "native_svg", None) for chart_type in _TABLE_TYPES_NATIVE_ONLY},
    **{chart_type: RenderStrategy(chart_type, "native_svg", None) for chart_type in DIAGRAM_PLACEHOLDER_TYPES},
}

_NON_FLOW_TYPES = set(_STATIC_STRATEGIES)

if _NON_FLOW_TYPES | FLOW_CHART_TYPES != SUPPORTED_CHART_TYPES:
    missing = sorted(SUPPORTED_CHART_TYPES - (_NON_FLOW_TYPES | FLOW_CHART_TYPES))
    extra = sorted((_NON_FLOW_TYPES | FLOW_CHART_TYPES) - SUPPORTED_CHART_TYPES)
    raise RuntimeError(f"chart render strategy mismatch: missing={missing}, extra={extra}")


def _flow_strategy(chart_type: str) -> RenderStrategy:
    engine = (get_settings().chart_flow_engine or "mermaid_sidecar").strip().lower()
    if engine == "gpt_vis":
        return RenderStrategy(chart_type, "gpt_vis", "mermaid_sidecar")
    return RenderStrategy(chart_type, "mermaid_sidecar", "native_flow")


def resolve_render_strategy(chart_type: str) -> RenderStrategy:
    if chart_type in FLOW_CHART_TYPES:
        return _flow_strategy(chart_type)
    return _STATIC_STRATEGIES[chart_type]
