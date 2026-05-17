from __future__ import annotations

import json
from pathlib import Path

import pytest

from tender_backend.services.chart_service.renderers import render_chart_spec
from tender_backend.services.chart_service.specs import SUPPORTED_CHART_TYPES, parse_chart_spec


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "chart_specs"


@pytest.mark.parametrize("chart_type", sorted(SUPPORTED_CHART_TYPES))
def test_golden_chart_fixture_renders_snapshot_contract(chart_type: str) -> None:
    fixture_path = FIXTURE_DIR / f"{chart_type}.json"
    assert fixture_path.exists()
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    spec = parse_chart_spec(fixture["spec"])
    rendered = render_chart_spec(spec)

    assert rendered.svg.startswith("<svg")
    assert fixture["spec"]["title"] in rendered.svg
    for label in fixture["expected_labels"]:
        assert label in rendered.svg
