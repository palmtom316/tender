"""indicator_table vl-convert vs native_svg POC 对比脚本.

读取 backend/tests/fixtures/chart_specs/indicator_table*.json (5 份样本),
分别用 native_svg 与 vl_convert 渲染, 落 SVG/PNG 到 outputs 目录, 并对每图
采集 T16 量化指标(文字溢出率/最小字号/A4 比例/DPI/字体). 最终产 JSON
报告 + 决策建议 (adopt | reject).

判定规则:
- 对每个样本对比 native vs vl_convert 在三项关键量化指标上的表现:
  文字溢出率, 最小字号, A4 宽高比.
- 整体决策: vl_convert 在 ≥2/3 关键指标上不劣于 native 即 adopt; 否则 reject.

用法(在 backend 目录下):
    python scripts/render_indicator_table_samples.py \
        --out /tmp/indicator_table_poc \
        --evidence ../docs/acceptance/2026-05-18-indicator-table-poc-evidence.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tender_backend.services.chart_service.png_converter import svg_to_png
from tender_backend.services.chart_service.quality_gate import evaluate_svg_quality
from tender_backend.services.chart_service.renderers import (
    _render_table_svg,
    _render_vega_svg,
)
from tender_backend.services.chart_service.specs import parse_chart_spec
from tender_backend.services.chart_service.templates import get_chart_template
from tender_backend.services.chart_service.vega_mapper import indicator_table_to_vega


FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "chart_specs"
FIXTURE_FILES = [
    "indicator_table.json",
    "indicator_table_a.json",
    "indicator_table_b.json",
    "indicator_table_c.json",
    "indicator_table_d.json",
]


def _load_specs() -> list[tuple[str, Any]]:
    items: list[tuple[str, Any]] = []
    for name in FIXTURE_FILES:
        path = FIXTURES_DIR / name
        if not path.exists():
            print(f"[warn] fixture missing: {path}")
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        spec = parse_chart_spec(payload["spec"])
        items.append((path.stem, spec))
    return items


def _native_svg(spec: Any) -> str:
    return _render_table_svg(spec)


def _vega_svg(spec: Any) -> str | None:
    return _render_vega_svg(indicator_table_to_vega(spec))


def _decide(samples: list[dict[str, Any]]) -> dict[str, Any]:
    metrics_keys = ("text_overflow_rate", "min_font_px", "aspect_ratio")
    wins = {key: 0 for key in metrics_keys}
    comparable = {key: 0 for key in metrics_keys}
    for sample in samples:
        n_metrics = sample.get("native_metrics") or {}
        v_metrics = sample.get("vl_convert_metrics") or {}
        if not v_metrics:
            continue
        for key in metrics_keys:
            native_value = n_metrics.get(key)
            vega_value = v_metrics.get(key)
            if native_value is None or vega_value is None:
                continue
            comparable[key] += 1
            if key == "text_overflow_rate":
                if vega_value <= native_value:
                    wins[key] += 1
            elif key == "min_font_px":
                if vega_value >= native_value:
                    wins[key] += 1
            elif key == "aspect_ratio":
                if 0.6 <= vega_value <= 1.5 and not (0.6 <= native_value <= 1.5):
                    wins[key] += 1
                elif 0.6 <= vega_value <= 1.5 and 0.6 <= native_value <= 1.5:
                    wins[key] += 1
    pass_keys = [key for key in metrics_keys if comparable[key] and wins[key] >= comparable[key] / 2]
    decision = "adopt" if len(pass_keys) >= 2 else "reject"
    return {
        "decision": decision,
        "pass_keys": pass_keys,
        "win_counts": wins,
        "comparable_counts": comparable,
        "rule": "vl_convert 在 ≥2/3 关键指标(文字溢出率/最小字号/A4 比例)不劣于 native_svg 即 adopt",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("/tmp/indicator_table_poc"))
    parser.add_argument("--evidence", type=Path, default=None)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "native").mkdir(exist_ok=True)
    (args.out / "vl_convert").mkdir(exist_ok=True)

    summary: list[dict[str, Any]] = []
    for name, spec in _load_specs():
        template = get_chart_template(spec.chart_type)

        native_svg = _native_svg(spec)
        vega_svg = _vega_svg(spec)

        (args.out / "native" / f"{name}.svg").write_text(native_svg, encoding="utf-8")
        if vega_svg:
            (args.out / "vl_convert" / f"{name}.svg").write_text(vega_svg, encoding="utf-8")
            try:
                svg_to_png(vega_svg, args.out / "vl_convert" / f"{name}.png")
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] PNG conversion failed for vl_convert/{name}: {exc}")
        try:
            svg_to_png(native_svg, args.out / "native" / f"{name}.png")
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] PNG conversion failed for native/{name}: {exc}")

        native_report = evaluate_svg_quality(native_svg, template)
        vega_report = evaluate_svg_quality(vega_svg, template) if vega_svg else None
        summary.append(
            {
                "name": name,
                "chart_type": spec.chart_type,
                "row_count": len(spec.rows),
                "col_count": len(spec.columns),
                "native_passed": native_report["passed"],
                "native_metrics": native_report["metrics"],
                "native_issues": native_report["issues"],
                "vl_convert_passed": vega_report["passed"] if vega_report else None,
                "vl_convert_metrics": vega_report["metrics"] if vega_report else None,
                "vl_convert_issues": vega_report["issues"] if vega_report else None,
            }
        )

    decision = _decide(summary)
    report = {
        "samples": summary,
        "decision": decision,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    (args.out / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nevidence written to: {args.evidence}")
    print(f"artifacts written to: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
