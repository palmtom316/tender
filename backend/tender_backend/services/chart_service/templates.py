from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChartTemplate:
    chart_type: str
    layout_family: str
    page_profile: str
    density_limits: dict[str, int]
    text_rules: dict[str, int]
    degradation_policy: dict[str, str]


_FLOW_DENSITY = {"max_nodes": 18, "max_edges": 28}
_FLOW_TEXT = {"node_chars": 12, "max_lines": 2, "min_font_px": 11}
_FLOW_DEGRADATION = {"overflow": "split_to_summary_table"}

_TABLE_DENSITY = {"max_rows": 80, "max_columns": 12, "max_nodes": 80}
_TABLE_TEXT = {"cell_chars": 14, "max_lines": 3, "min_font_px": 11}
_TABLE_DEGRADATION = {"overflow": "split_table"}


def _flow(chart_type: str, *, max_nodes: int = 18, page_profile: str = "a4_portrait") -> ChartTemplate:
    return ChartTemplate(
        chart_type=chart_type,
        layout_family="flow",
        page_profile=page_profile,
        density_limits={**_FLOW_DENSITY, "max_nodes": max_nodes},
        text_rules=_FLOW_TEXT,
        degradation_policy=_FLOW_DEGRADATION,
    )


def _table(chart_type: str, *, max_rows: int = 80, max_columns: int = 12) -> ChartTemplate:
    return ChartTemplate(
        chart_type=chart_type,
        layout_family="table",
        page_profile="adaptive_landscape",
        density_limits={**_TABLE_DENSITY, "max_rows": max_rows, "max_columns": max_columns},
        text_rules=_TABLE_TEXT,
        degradation_policy=_TABLE_DEGRADATION,
    )


_TEMPLATES: dict[str, ChartTemplate] = {
    "org_chart": _flow("org_chart", max_nodes=18),
    "construction_flow": _flow("construction_flow", max_nodes=16, page_profile="a4_landscape"),
    "quality_system": _flow("quality_system", max_nodes=16),
    "safety_system": _flow("safety_system", max_nodes=16),
    "emergency_org": _flow("emergency_org", max_nodes=16),
    "closure_flow": _flow("closure_flow", max_nodes=16, page_profile="a4_landscape"),
    "data_flow": _flow("data_flow", max_nodes=16, page_profile="a4_landscape"),
    "wbs_tree": _flow("wbs_tree", max_nodes=24, page_profile="a4_landscape"),
    "schedule_gantt": ChartTemplate(
        chart_type="schedule_gantt",
        layout_family="gantt",
        page_profile="a4_landscape",
        density_limits={"max_tasks": 20, "max_groups": 7, "max_nodes": 20},
        text_rules={"task_chars": 16, "max_lines": 2, "min_font_px": 11},
        degradation_policy={"overflow": "summary_table"},
    ),
    "critical_path": ChartTemplate(
        chart_type="critical_path",
        layout_family="gantt",
        page_profile="a4_landscape",
        density_limits={"max_tasks": 14, "max_dependencies": 20, "max_nodes": 14},
        text_rules={"task_chars": 16, "max_lines": 2, "min_font_px": 11},
        degradation_policy={"overflow": "critical_summary_table"},
    ),
    "outage_timeline": ChartTemplate(
        chart_type="outage_timeline",
        layout_family="gantt",
        page_profile="a4_landscape",
        density_limits={"max_tasks": 16, "max_groups": 6, "max_nodes": 16},
        text_rules={"task_chars": 16, "max_lines": 2, "min_font_px": 11},
        degradation_policy={"overflow": "summary_table"},
    ),
    "risk_matrix": ChartTemplate(
        chart_type="risk_matrix",
        layout_family="matrix",
        page_profile="a4_landscape",
        density_limits={"max_rows": 4, "max_columns": 4, "max_items_per_cell": 3, "max_nodes": 16},
        text_rules={"cell_chars": 12, "max_lines": 4, "min_font_px": 11},
        degradation_policy={"overflow": "cell_summary"},
    ),
    "responsibility_matrix": ChartTemplate(
        chart_type="responsibility_matrix",
        layout_family="matrix",
        page_profile="a4_landscape",
        density_limits={"max_roles": 8, "max_activities": 18, "max_nodes": 144},
        text_rules={"activity_chars": 12, "role_chars": 8, "max_lines": 2, "min_font_px": 11},
        degradation_policy={"overflow": "split_by_phase"},
    ),
    "response_matrix": _table("response_matrix", max_rows=80, max_columns=8),
    "indicator_table": _table("indicator_table", max_rows=80, max_columns=6),
    "interface_table": _table("interface_table", max_rows=80, max_columns=8),
    "equipment_table": _table("equipment_table", max_rows=80, max_columns=8),
    "fmea_matrix": _table("fmea_matrix", max_rows=40, max_columns=10),
    "single_line_diagram": _table("single_line_diagram", max_rows=40, max_columns=4),
    "site_layout": _table("site_layout", max_rows=40, max_columns=4),
}


def get_chart_template(chart_type: str) -> ChartTemplate:
    return _TEMPLATES[chart_type]
