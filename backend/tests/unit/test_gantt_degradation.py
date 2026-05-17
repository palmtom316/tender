from __future__ import annotations

from datetime import date, timedelta

import tender_backend.services.chart_service.renderers as renderers
from tender_backend.services.chart_service.renderers import render_chart_spec
from tender_backend.services.chart_service.specs import parse_chart_spec


def _large_gantt_spec():
    start = date(2026, 6, 1)
    tasks = []
    for index in range(25):
        task_start = start + timedelta(days=index)
        tasks.append(
            {
                "id": f"t{index}",
                "label": f"工序{index}",
                "start": task_start.isoformat(),
                "end": (task_start + timedelta(days=1)).isoformat(),
                "group": f"阶段{index // 5 + 1}",
            }
        )
    return parse_chart_spec({"chart_type": "schedule_gantt", "title": "施工进度计划图", "tasks": tasks, "dependencies": []})


def test_large_gantt_uses_summary_when_sidecar_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(renderers, "_render_mermaid_sidecar", lambda _source: None)

    rendered = render_chart_spec(_large_gantt_spec())

    assert rendered.engine == "native_gantt_summary"
    assert "阶段1" in rendered.svg
    assert "阶段汇总" in rendered.svg
    assert "工序24" not in rendered.svg


def test_large_gantt_keeps_mermaid_when_sidecar_available(monkeypatch) -> None:
    monkeypatch.setattr(renderers, "_render_mermaid_sidecar", lambda _source: "<svg>sidecar</svg>")

    rendered = render_chart_spec(_large_gantt_spec())

    assert rendered.engine == "mermaid_sidecar"
    assert rendered.svg == "<svg>sidecar</svg>"
