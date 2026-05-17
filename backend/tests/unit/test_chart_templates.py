from __future__ import annotations

import pytest

from tender_backend.services.chart_service.specs import SUPPORTED_CHART_TYPES
from tender_backend.services.chart_service.templates import get_chart_template


@pytest.mark.parametrize("chart_type", sorted(SUPPORTED_CHART_TYPES))
def test_every_supported_chart_type_has_template(chart_type: str) -> None:
    template = get_chart_template(chart_type)

    assert template.chart_type == chart_type
    assert template.layout_family in {"flow", "gantt", "matrix", "table"}
    assert template.page_profile in {"a4_portrait", "a4_landscape", "adaptive_landscape"}
    assert template.density_limits
    assert template.text_rules
    assert template.degradation_policy


def test_schedule_template_sets_task_density_limit() -> None:
    template = get_chart_template("schedule_gantt")

    assert template.layout_family == "gantt"
    assert template.density_limits["max_tasks"] == 20
    assert template.degradation_policy["overflow"] == "summary_table"


def test_unknown_chart_template_raises_key_error() -> None:
    with pytest.raises(KeyError):
        get_chart_template("unknown_chart")
