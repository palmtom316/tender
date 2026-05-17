from __future__ import annotations

from tender_backend.services.chart_service.renderers import render_chart_spec
from tender_backend.services.chart_service.specs import parse_chart_spec


def test_table_renderer_truncates_long_cell_content() -> None:
    spec = parse_chart_spec(
        {
            "chart_type": "indicator_table",
            "title": "绿色施工指标表",
            "columns": ["指标事项", "来源依据", "控制措施"],
            "rows": [
                {
                    "cells": [
                        "超长超长超长超长超长超长超长指标事项需要全过程记录并持续复核闭环整改",
                        "招标文件第五章及现场踏勘纪要联合确认要求",
                        "按照批准方案执行并设置复核节点全过程留痕",
                    ]
                }
            ],
        }
    )

    rendered = render_chart_spec(spec)

    assert "…" in rendered.svg
    assert "全过程记录并持续复核" not in rendered.svg


def test_table_renderer_expands_width_for_long_column_headers() -> None:
    spec = parse_chart_spec(
        {
            "chart_type": "interface_table",
            "title": "接口管理表",
            "columns": ["非常长的接口协调事项名称", "来源", "措施"],
            "rows": [{"cells": ["停电协调", "招标文件", "按计划执行"]}],
        }
    )

    rendered = render_chart_spec(spec)

    assert "width='220.0'" in rendered.svg
