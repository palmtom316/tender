"""图表渲染样本对比脚本（T5 极简验收）。

生成 5 个矩阵样本，分别用 native_svg 与 vl_convert 渲染，
把 SVG/PNG 落地到 `samples/` 目录并打印量化指标，便于肉眼对比。

用法（在 backend 目录下）：
    python scripts/render_matrix_samples.py --out /tmp/chart_samples
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tender_backend.services.chart_service.png_converter import svg_to_png
from tender_backend.services.chart_service.quality_gate import evaluate_svg_quality
from tender_backend.services.chart_service.renderers import (
    _render_responsibility_matrix_svg,
    _render_risk_matrix_svg,
    _render_vega_svg,
)
from tender_backend.services.chart_service.specs import parse_chart_spec
from tender_backend.services.chart_service.templates import get_chart_template
from tender_backend.services.chart_service.vega_mapper import (
    responsibility_matrix_to_vega,
    risk_matrix_to_vega,
)


SAMPLES: list[dict[str, Any]] = [
    {
        "name": "risk_matrix_basic",
        "spec": {
            "chart_type": "risk_matrix",
            "title": "施工风险分级矩阵",
            "rows": ["低影响", "中影响", "高影响"],
            "columns": ["低概率", "中概率", "高概率"],
            "cells": [
                {"row": "高影响", "column": "中概率", "items": ["停电窗口延误"], "level": "high"},
                {"row": "中影响", "column": "高概率", "items": ["物资到货滞后"], "level": "medium"},
                {"row": "低影响", "column": "低概率", "items": ["文档格式偏差"], "level": "low"},
            ],
        },
    },
    {
        "name": "risk_matrix_dense",
        "spec": {
            "chart_type": "risk_matrix",
            "title": "总承包风险全景",
            "rows": ["低", "中", "高", "极高"],
            "columns": ["罕见", "偶发", "可能", "频繁"],
            "cells": [
                {
                    "row": "高",
                    "column": "可能",
                    "items": ["机电安装延期", "海运延误", "图纸晚出", "设计变更", "审批拖期"],
                    "level": "high",
                },
                {"row": "极高", "column": "频繁", "items": ["关键设备到货延误"], "level": "critical"},
                {"row": "中", "column": "偶发", "items": ["验收返工"], "level": "medium"},
            ],
        },
    },
    {
        "name": "responsibility_matrix_basic",
        "spec": {
            "chart_type": "responsibility_matrix",
            "title": "岗位责任矩阵图",
            "roles": ["项目经理", "技术负责人", "安全负责人"],
            "activities": ["施工准备", "技术交底", "安全检查"],
            "assignments": [
                {"role": "项目经理", "activity": "施工准备", "level": "负责"},
                {"role": "技术负责人", "activity": "技术交底", "level": "负责"},
                {"role": "安全负责人", "activity": "安全检查", "level": "负责"},
            ],
        },
    },
    {
        "name": "responsibility_matrix_raci",
        "spec": {
            "chart_type": "responsibility_matrix",
            "title": "RACI 矩阵 — 关键阶段",
            "roles": ["项目经理", "技术负责人", "安全负责人", "质量员", "资料员"],
            "activities": ["施工准备", "图纸会审", "技术交底", "材料验收", "安全检查", "质量验收", "资料整理"],
            "assignments": [
                {"role": "项目经理", "activity": "施工准备", "level": "A"},
                {"role": "技术负责人", "activity": "图纸会审", "level": "R"},
                {"role": "项目经理", "activity": "图纸会审", "level": "A"},
                {"role": "技术负责人", "activity": "技术交底", "level": "R"},
                {"role": "质量员", "activity": "材料验收", "level": "R"},
                {"role": "安全负责人", "activity": "安全检查", "level": "R"},
                {"role": "质量员", "activity": "质量验收", "level": "R"},
                {"role": "资料员", "activity": "资料整理", "level": "R"},
                {"role": "项目经理", "activity": "资料整理", "level": "A"},
            ],
        },
    },
    {
        "name": "risk_matrix_minimal",
        "spec": {
            "chart_type": "risk_matrix",
            "title": "局部风险预警",
            "rows": ["影响"],
            "columns": ["概率"],
            "cells": [{"row": "影响", "column": "概率", "items": ["材料紧缺"], "level": "high"}],
        },
    },
]


def _native_svg(spec: Any) -> str:
    if spec.chart_type == "risk_matrix":
        return _render_risk_matrix_svg(spec)
    return _render_responsibility_matrix_svg(spec)


def _vega_svg(spec: Any) -> str | None:
    if spec.chart_type == "risk_matrix":
        return _render_vega_svg(risk_matrix_to_vega(spec))
    return _render_vega_svg(responsibility_matrix_to_vega(spec))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("/tmp/chart_samples"))
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    summary: list[dict[str, Any]] = []
    for sample in SAMPLES:
        name = sample["name"]
        spec = parse_chart_spec(sample["spec"])
        template = get_chart_template(spec.chart_type)

        native_svg = _native_svg(spec)
        vega_svg = _vega_svg(spec)

        (args.out / f"{name}.native.svg").write_text(native_svg, encoding="utf-8")
        if vega_svg:
            (args.out / f"{name}.vl_convert.svg").write_text(vega_svg, encoding="utf-8")
            try:
                svg_to_png(vega_svg, args.out / f"{name}.vl_convert.png")
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] PNG conversion failed for {name}: {exc}")

        native_report = evaluate_svg_quality(native_svg, template)
        vega_report = evaluate_svg_quality(vega_svg, template) if vega_svg else None
        summary.append(
            {
                "name": name,
                "chart_type": spec.chart_type,
                "native_passed": native_report["passed"],
                "native_metrics": native_report["metrics"],
                "vl_convert_passed": vega_report["passed"] if vega_report else None,
                "vl_convert_metrics": vega_report["metrics"] if vega_report else None,
            }
        )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    (args.out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nartifacts written to: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
