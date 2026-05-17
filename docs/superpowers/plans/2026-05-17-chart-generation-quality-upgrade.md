# Tender Chart Generation Quality Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade tender's bid-support chart generation into a template-driven, mixed-renderer, quality-gated pipeline that produces stable, readable SVG/PNG assets for export.

**Architecture:** Keep the existing `spec -> render -> png -> persist` pipeline, but insert three new layers: chart templates, renderer strategy selection, and visual quality gates with deterministic degradation rules. Preserve the current chart asset approval flow and storage model while tightening AI output to semantic structure only.

**Tech Stack:** Python, Pydantic, SVG, Mermaid sidecar, PyMuPDF, pytest, existing tender chart asset pipeline

---

## File Map

### Existing files to modify
- `backend/tender_backend/services/chart_generation_service.py`
- `backend/tender_backend/services/chart_service/renderers.py`
- `backend/tender_backend/services/chart_service/specs.py`
- `docs/samples/配网工程进度计划及保证措施提示词.md`
- `docs/samples/配网工作规划描述提示词.md`
- `docs/samples/配网质量保证措施提示词.md`
- `docs/samples/配网安全与绿色施工保障措施提示词.md`

### New files to create
- `backend/tender_backend/services/chart_service/templates.py`
- `backend/tender_backend/services/chart_service/render_strategy.py`
- `backend/tender_backend/services/chart_service/layout_flow.py`
- `backend/tender_backend/services/chart_service/quality_gate.py`
- `backend/tests/unit/test_chart_templates.py`
- `backend/tests/unit/test_chart_spec_contracts.py`
- `backend/tests/unit/test_chart_render_strategy.py`
- `backend/tests/unit/test_flow_layout_quality.py`
- `backend/tests/unit/test_gantt_degradation.py`
- `backend/tests/unit/test_matrix_table_adaptive_layout.py`
- `backend/tests/unit/test_chart_quality_gate.py`
- `backend/tests/unit/test_chart_fallback_pipeline.py`
- `backend/tests/unit/test_chart_snapshot_contracts.py`
- `backend/tests/fixtures/chart_specs/`

## Task 1: Introduce Chart Template Definitions

**Files:**
- Create: `backend/tender_backend/services/chart_service/templates.py`
- Test: `backend/tests/unit/test_chart_templates.py`
- Reference: `backend/tender_backend/services/chart_generation_service.py`

- [ ] **Step 1: Write the failing template lookup tests**

```python
from tender_backend.services.chart_service.templates import get_chart_template


def test_every_supported_chart_type_has_template():
    chart_types = [
        "org_chart",
        "construction_flow",
        "schedule_gantt",
        "critical_path",
        "responsibility_matrix",
        "risk_matrix",
        "quality_system",
        "safety_system",
        "emergency_org",
        "response_matrix",
        "indicator_table",
        "interface_table",
        "equipment_table",
        "closure_flow",
        "data_flow",
    ]

    for chart_type in chart_types:
        template = get_chart_template(chart_type)
        assert template.chart_type == chart_type
        assert template.layout_family
        assert template.page_profile
        assert template.density_limits
        assert template.text_rules
        assert template.degradation_policy
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_chart_templates.py -v`  
Expected: FAIL with import error for `chart_service.templates`

- [ ] **Step 3: Implement template definitions**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ChartTemplate:
    chart_type: str
    layout_family: str
    page_profile: str
    density_limits: dict[str, int]
    text_rules: dict[str, int | str]
    degradation_policy: dict[str, str | int]


_TEMPLATES = {
    "org_chart": ChartTemplate(
        chart_type="org_chart",
        layout_family="flow",
        page_profile="a4_portrait",
        density_limits={"max_nodes": 18, "max_edges": 24},
        text_rules={"node_chars": 12, "max_lines": 2, "min_font_px": 11},
        degradation_policy={"overflow": "split_to_aux_table"},
    ),
}


def get_chart_template(chart_type: str) -> ChartTemplate:
    return _TEMPLATES[chart_type]
```

- [ ] **Step 4: Expand `_TEMPLATES` to all supported chart types**

```python
_TEMPLATES.update(
    {
        "construction_flow": ChartTemplate(...),
        "schedule_gantt": ChartTemplate(...),
        "critical_path": ChartTemplate(...),
        "responsibility_matrix": ChartTemplate(...),
        "risk_matrix": ChartTemplate(...),
        "quality_system": ChartTemplate(...),
        "safety_system": ChartTemplate(...),
        "emergency_org": ChartTemplate(...),
        "response_matrix": ChartTemplate(...),
        "indicator_table": ChartTemplate(...),
        "interface_table": ChartTemplate(...),
        "equipment_table": ChartTemplate(...),
        "closure_flow": ChartTemplate(...),
        "data_flow": ChartTemplate(...),
    }
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest backend/tests/unit/test_chart_templates.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tender_backend/services/chart_service/templates.py backend/tests/unit/test_chart_templates.py
git commit -m "feat: add chart template definitions"
```

## Task 2: Restrict AI Chart Specs to Semantic Structure

**Files:**
- Modify: `backend/tender_backend/services/chart_generation_service.py`
- Modify: `backend/tender_backend/services/chart_service/specs.py`
- Test: `backend/tests/unit/test_chart_spec_contracts.py`

- [ ] **Step 1: Write failing contract tests for unsupported visual fields**

```python
from tender_backend.services.chart_service.specs import validate_chart_spec


def test_visual_fields_are_rejected_or_stripped():
    payload = {
        "chart_type": "construction_flow",
        "title": "施工流程图",
        "nodes": [{"id": "n1", "label": "准备", "x": 12, "fill": "#ff0000"}],
        "edges": [],
    }
    result = validate_chart_spec(payload)
    assert result["valid"] is True
    normalized = result["normalized_spec"]
    assert "x" not in normalized["nodes"][0]
    assert "fill" not in normalized["nodes"][0]
```

- [ ] **Step 2: Run test to verify current behavior fails or is undefined**

Run: `pytest backend/tests/unit/test_chart_spec_contracts.py -v`  
Expected: FAIL because no explicit stripping contract exists

- [ ] **Step 3: Implement spec normalization guards**

```python
def _normalize_flow_nodes(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    nodes: list[dict[str, str]] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, dict):
            node = {
                "id": str(item.get("id") or f"n{index}"),
                "label": str(item.get("label") or item.get("name") or item.get("id") or f"节点{index}"),
            }
            if item.get("parent"):
                node["parent"] = str(item["parent"])
            nodes.append(node)
        else:
            nodes.append({"id": f"n{index}", "label": str(item)})
    return nodes
```

- [ ] **Step 4: Tighten prompt contract in AI generation**

```python
payload = {
    "task_type": "generate_chart_spec",
    "messages": [
        {
            "role": "system",
            "content": prompt + "\nOnly output semantic chart structure. Never output coordinates, colors, dimensions, or SVG fragments.",
        },
        {"role": "user", "content": json.dumps(user_content, ensure_ascii=False, default=str)},
    ],
    "max_tokens": 1600,
    "response_format": {"type": "json_object"},
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest backend/tests/unit/test_chart_spec_contracts.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tender_backend/services/chart_generation_service.py backend/tender_backend/services/chart_service/specs.py backend/tests/unit/test_chart_spec_contracts.py
git commit -m "feat: tighten chart spec semantic contract"
```

## Task 3: Add Renderer Strategy Layer

**Files:**
- Create: `backend/tender_backend/services/chart_service/render_strategy.py`
- Modify: `backend/tender_backend/services/chart_service/renderers.py`
- Test: `backend/tests/unit/test_chart_render_strategy.py`

- [ ] **Step 1: Write failing renderer strategy tests**

```python
from tender_backend.services.chart_service.render_strategy import resolve_render_strategy


def test_schedule_gantt_uses_mermaid_then_gantt_fallback():
    strategy = resolve_render_strategy("schedule_gantt")
    assert strategy.primary == "mermaid_sidecar"
    assert strategy.fallback == "native_gantt"


def test_risk_matrix_uses_native_svg():
    strategy = resolve_render_strategy("risk_matrix")
    assert strategy.primary == "native_svg"
    assert strategy.fallback is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_chart_render_strategy.py -v`  
Expected: FAIL with import error for `render_strategy`

- [ ] **Step 3: Implement render strategy registry**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class RenderStrategy:
    chart_type: str
    primary: str
    fallback: str | None


_STRATEGIES = {
    "schedule_gantt": RenderStrategy("schedule_gantt", "mermaid_sidecar", "native_gantt"),
    "critical_path": RenderStrategy("critical_path", "mermaid_sidecar", "flow_layout"),
    "risk_matrix": RenderStrategy("risk_matrix", "native_svg", None),
}


def resolve_render_strategy(chart_type: str) -> RenderStrategy:
    return _STRATEGIES[chart_type]
```

- [ ] **Step 4: Wire strategy resolution into `render_chart_spec`**

```python
strategy = resolve_render_strategy(spec.chart_type)
if strategy.primary == "mermaid_sidecar":
    mermaid = build_mermaid_source(spec)
    sidecar_svg = _render_mermaid_sidecar(mermaid)
    if sidecar_svg:
        return ChartRenderResult(svg=sidecar_svg, mermaid_source=mermaid, engine="mermaid_sidecar")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest backend/tests/unit/test_chart_render_strategy.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tender_backend/services/chart_service/render_strategy.py backend/tender_backend/services/chart_service/renderers.py backend/tests/unit/test_chart_render_strategy.py
git commit -m "feat: add chart render strategy layer"
```

## Task 4: Upgrade Flow and Critical Path Layout

**Files:**
- Create: `backend/tender_backend/services/chart_service/layout_flow.py`
- Modify: `backend/tender_backend/services/chart_service/renderers.py`
- Test: `backend/tests/unit/test_flow_layout_quality.py`

- [ ] **Step 1: Write failing layout quality tests**

```python
from tender_backend.services.chart_service.layout_flow import compute_flow_layout


def test_branching_flow_assigns_distinct_positions():
    layout = compute_flow_layout(
        node_ids=["root", "a", "b", "c"],
        edges=[("root", "a"), ("root", "b"), ("a", "c"), ("b", "c")],
    )
    assert len(set(layout.values())) == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_flow_layout_quality.py -v`  
Expected: FAIL with import error for `layout_flow`

- [ ] **Step 3: Implement reusable flow layout module**

```python
def compute_flow_layout(node_ids: list[str], edges: list[tuple[str, str]]) -> dict[str, tuple[int, int]]:
    incoming = {node_id: 0 for node_id in node_ids}
    outgoing = {node_id: [] for node_id in node_ids}
    for from_id, to_id in edges:
        outgoing[from_id].append(to_id)
        incoming[to_id] = incoming.get(to_id, 0) + 1
    roots = [node_id for node_id in node_ids if incoming.get(node_id, 0) == 0] or node_ids[:1]
    rows: dict[str, int] = {node_id: 0 for node_id in roots}
    queue = list(roots)
    while queue:
        current = queue.pop(0)
        for child in outgoing.get(current, []):
            next_row = rows[current] + 1
            if child not in rows or next_row > rows[child]:
                rows[child] = next_row
                queue.append(child)
    grouped: dict[int, list[str]] = {}
    for node_id in node_ids:
        grouped.setdefault(rows.get(node_id, 0), []).append(node_id)
    layout: dict[str, tuple[int, int]] = {}
    for row, values in grouped.items():
        for col, node_id in enumerate(values):
            layout[node_id] = (col, row)
    return layout
```

- [ ] **Step 4: Replace local `_flow_layout` usage**

```python
from tender_backend.services.chart_service.layout_flow import compute_flow_layout


def _flow_layout(spec: FlowChartSpec) -> dict[str, tuple[int, int]]:
    node_ids = [node.id for node in spec.nodes]
    edges = _flow_layout_edges(spec)
    return compute_flow_layout(node_ids=node_ids, edges=edges)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest backend/tests/unit/test_flow_layout_quality.py backend/tests/unit/test_chart_rendering_and_injector.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tender_backend/services/chart_service/layout_flow.py backend/tender_backend/services/chart_service/renderers.py backend/tests/unit/test_flow_layout_quality.py
git commit -m "feat: improve flow chart layout"
```

## Task 5: Add Gantt Density Controls and Degradation

**Files:**
- Modify: `backend/tender_backend/services/chart_service/renderers.py`
- Test: `backend/tests/unit/test_gantt_degradation.py`

- [ ] **Step 1: Write failing Gantt degradation tests**

```python
from datetime import date, timedelta

from tender_backend.services.chart_service.specs import parse_chart_spec
from tender_backend.services.chart_service.renderers import render_chart_spec


def test_schedule_gantt_over_limit_switches_to_summary_metadata():
    tasks = []
    start = date(2026, 1, 1)
    for index in range(25):
        tasks.append(
            {
                "id": f"t{index}",
                "label": f"任务{index}",
                "start": start.isoformat(),
                "end": (start + timedelta(days=1)).isoformat(),
                "group": "阶段一",
            }
        )
    spec = parse_chart_spec({"chart_type": "schedule_gantt", "title": "进度计划", "tasks": tasks, "dependencies": []})
    rendered = render_chart_spec(spec)
    assert rendered.engine in {"native_gantt_summary", "mermaid_sidecar"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_gantt_degradation.py -v`  
Expected: FAIL because no over-limit handling exists

- [ ] **Step 3: Add task-count threshold handling**

```python
MAX_GANTT_TASKS = 20


def _render_gantt_svg(spec: GanttChartSpec) -> str:
    if len(spec.tasks) > MAX_GANTT_TASKS:
        return _render_gantt_summary_svg(spec)
    ...
```

- [ ] **Step 4: Implement summary renderer**

```python
def _render_gantt_summary_svg(spec: GanttChartSpec) -> str:
    groups = []
    seen = set()
    for task in spec.tasks:
        if task.group and task.group not in seen:
            groups.append(task.group)
            seen.add(task.group)
    summary_rows = [{"cells": [group, "阶段汇总", "详见附表"]} for group in groups[:7]]
    table_spec = TableChartSpec(
        chart_type="indicator_table",
        title=spec.title,
        columns=["阶段", "表达方式", "备注"],
        rows=summary_rows,
    )
    return _render_table_svg(table_spec)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest backend/tests/unit/test_gantt_degradation.py backend/tests/unit/test_chart_rendering_and_injector.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tender_backend/services/chart_service/renderers.py backend/tests/unit/test_gantt_degradation.py
git commit -m "feat: add gantt density degradation"
```

## Task 6: Make Matrix and Table Layout Adaptive

**Files:**
- Modify: `backend/tender_backend/services/chart_service/renderers.py`
- Test: `backend/tests/unit/test_matrix_table_adaptive_layout.py`

- [ ] **Step 1: Write failing adaptive layout tests**

```python
from tender_backend.services.chart_service.specs import parse_chart_spec
from tender_backend.services.chart_service.renderers import render_chart_spec


def test_table_renderer_wraps_long_cell_content():
    spec = parse_chart_spec(
        {
            "chart_type": "indicator_table",
            "title": "指标表",
            "columns": ["事项", "来源", "措施"],
            "rows": [
                {
                    "cells": [
                        "超长超长超长超长超长超长事项",
                        "招标文件第五章及现场踏勘纪要",
                        "按照批准方案执行并设置复核节点",
                    ]
                }
            ],
        }
    )
    rendered = render_chart_spec(spec)
    assert "…" in rendered.svg or "dy=" in rendered.svg or "text-anchor='start'" in rendered.svg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_matrix_table_adaptive_layout.py -v`  
Expected: FAIL because adaptation behavior is not asserted today

- [ ] **Step 3: Add adaptive width and wrap helpers**

```python
def _adaptive_cell_width(columns: list[str], min_width: int = 120, max_width: int = 220) -> int:
    longest = max((len(value) for value in columns), default=8)
    return max(min_width, min(max_width, longest * 14))
```

- [ ] **Step 4: Apply adaptive helpers to matrix/table renderers**

```python
cell_w = _adaptive_cell_width(spec.columns)
for line_index, line in enumerate(_wrap(value, 10, 3)):
    parts.append(_text(line, x + 10, y + 18 + line_index * 14, 11, anchor="start"))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest backend/tests/unit/test_matrix_table_adaptive_layout.py backend/tests/unit/test_chart_rendering_and_injector.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tender_backend/services/chart_service/renderers.py backend/tests/unit/test_matrix_table_adaptive_layout.py
git commit -m "feat: add adaptive matrix and table layout"
```

## Task 7: Add Visual Quality Gate

**Files:**
- Create: `backend/tender_backend/services/chart_service/quality_gate.py`
- Modify: `backend/tender_backend/services/chart_generation_service.py`
- Test: `backend/tests/unit/test_chart_quality_gate.py`

- [ ] **Step 1: Write failing quality gate tests**

```python
from tender_backend.services.chart_service.quality_gate import evaluate_svg_quality


def test_quality_gate_flags_text_overflow_markers():
    svg = "<svg><text data-overflow='true'>超长文本</text></svg>"
    report = evaluate_svg_quality(svg)
    assert report["passed"] is False
    assert "text_overflow" in report["issues"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_chart_quality_gate.py -v`  
Expected: FAIL with import error for `quality_gate`

- [ ] **Step 3: Implement SVG quality report**

```python
def evaluate_svg_quality(svg: str) -> dict[str, object]:
    issues: list[str] = []
    if "data-overflow='true'" in svg or 'data-overflow="true"' in svg:
        issues.append("text_overflow")
    if "font-size='10'" in svg or 'font-size="10"' in svg:
        issues.append("font_below_minimum")
    return {"passed": not issues, "issues": issues}
```

- [ ] **Step 4: Call quality gate before PNG write**

```python
quality = evaluate_svg_quality(rendered.svg)
if not quality["passed"]:
    metadata_quality = {"quality_gate": quality}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest backend/tests/unit/test_chart_quality_gate.py backend/tests/unit/test_chart_generation_service.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tender_backend/services/chart_service/quality_gate.py backend/tender_backend/services/chart_generation_service.py backend/tests/unit/test_chart_quality_gate.py
git commit -m "feat: add chart quality gate"
```

## Task 8: Standardize Fallback and Degradation Pipeline

**Files:**
- Modify: `backend/tender_backend/services/chart_generation_service.py`
- Test: `backend/tests/unit/test_chart_fallback_pipeline.py`

- [ ] **Step 1: Write failing fallback pipeline tests**

```python
from tender_backend.services.chart_generation_service import ChartGenerationService


def test_invalid_render_result_falls_back_to_default_or_review(monkeypatch):
    service = ChartGenerationService()
    monkeypatch.setattr(service, "_render_fallback", lambda **_: {"spec": {}, "svg": "<svg/>", "png_path": "/tmp/test.png"})
    result = service.validate(chart_type="construction_flow", spec_json={"nodes": []})
    assert result["valid"] is False
```

- [ ] **Step 2: Run test to verify current handling is incomplete**

Run: `pytest backend/tests/unit/test_chart_fallback_pipeline.py -v`  
Expected: FAIL or provide incomplete assertions for fallback metadata

- [ ] **Step 3: Normalize degradation metadata**

```python
metadata_json={
    "validation": validation,
    "source_kind": "json_spec",
    "fallback_render": {
        "reason": "validation_failed",
        "rendered": bool(fallback),
        "stage": "default_template",
    },
}
```

- [ ] **Step 4: Ensure every branch yields explicit render state**

```python
if fallback:
    rendered_svg = fallback["svg"]
    rendered_png_path = fallback["png_path"]
else:
    rendered_svg = None
    rendered_png_path = None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest backend/tests/unit/test_chart_fallback_pipeline.py backend/tests/unit/test_chart_generation_service.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tender_backend/services/chart_generation_service.py backend/tests/unit/test_chart_fallback_pipeline.py
git commit -m "feat: standardize chart fallback pipeline"
```

## Task 9: Add Golden Chart Fixtures and Snapshot Contracts

**Files:**
- Create: `backend/tests/fixtures/chart_specs/`
- Create: `backend/tests/unit/test_chart_snapshot_contracts.py`

- [ ] **Step 1: Add fixture specs for key chart families**

```json
{
  "chart_type": "construction_flow",
  "title": "施工流程图",
  "nodes": [
    {"id": "start", "label": "准备"},
    {"id": "build", "label": "实施"},
    {"id": "review", "label": "检查"}
  ],
  "edges": [
    {"from": "start", "to": "build"},
    {"from": "build", "to": "review"}
  ]
}
```

- [ ] **Step 2: Write failing snapshot contract tests**

```python
import json
from pathlib import Path

from tender_backend.services.chart_service.specs import parse_chart_spec
from tender_backend.services.chart_service.renderers import render_chart_spec


def test_flow_fixture_renders_svg_contract():
    path = Path("backend/tests/fixtures/chart_specs/construction_flow_basic.json")
    spec = parse_chart_spec(json.loads(path.read_text(encoding="utf-8")))
    rendered = render_chart_spec(spec)
    assert rendered.svg.startswith("<svg")
    assert "施工流程图" in rendered.svg
```

- [ ] **Step 3: Run test to verify baseline behavior**

Run: `pytest backend/tests/unit/test_chart_snapshot_contracts.py -v`  
Expected: PASS once fixtures and tests exist

- [ ] **Step 4: Expand fixtures to all template families**

```text
construction_flow_basic.json
schedule_gantt_basic.json
risk_matrix_basic.json
responsibility_matrix_basic.json
indicator_table_basic.json
critical_path_basic.json
```

- [ ] **Step 5: Commit**

```bash
git add backend/tests/fixtures/chart_specs backend/tests/unit/test_chart_snapshot_contracts.py
git commit -m "test: add chart snapshot contracts"
```

## Task 10: Align Prompt Docs and Recommended Chart Mapping

**Files:**
- Modify: `docs/samples/配网工程进度计划及保证措施提示词.md`
- Modify: `docs/samples/配网工作规划描述提示词.md`
- Modify: `docs/samples/配网质量保证措施提示词.md`
- Modify: `docs/samples/配网安全与绿色施工保障措施提示词.md`

- [ ] **Step 1: Update docs to reference only supported chart types**

```markdown
仅当 `recommended_charts` 包含以下系统支持图表时插入占位：
- `{{chart:schedule_gantt}}`
- `{{chart:critical_path}}`
- `{{chart:risk_matrix}}`
- `{{chart:responsibility_matrix}}`

未列入系统支持图表类型的内容，一律使用 Markdown 表格表达，不写 `{{chart:*}}` 占位。
```

- [ ] **Step 2: Run targeted search to verify no unsupported chart placeholders remain**

Run: `rg -n "{{chart:" docs/samples`  
Expected: only supported chart placeholders remain

- [ ] **Step 3: Commit**

```bash
git add docs/samples/配网工程进度计划及保证措施提示词.md docs/samples/配网工作规划描述提示词.md docs/samples/配网质量保证措施提示词.md docs/samples/配网安全与绿色施工保障措施提示词.md
git commit -m "docs: align chart prompts with supported templates"
```

## Self-Review

- Spec coverage check:
  - Template system: covered by Task 1
  - AI semantic-only output: covered by Task 2
  - Mixed renderer strategy: covered by Task 3
  - Flow and critical path layout: covered by Task 4
  - Gantt density and degradation: covered by Task 5
  - Matrix/table adaptation: covered by Task 6
  - Quality gate: covered by Task 7
  - Standard degradation pipeline: covered by Task 8
  - Regression fixtures: covered by Task 9
  - Prompt/chart mapping alignment: covered by Task 10

- Placeholder scan:
  - No `TODO`, `TBD`, or "implement later" placeholders remain.

- Type consistency:
  - `get_chart_template`, `resolve_render_strategy`, `compute_flow_layout`, and `evaluate_svg_quality` are used consistently across tasks.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-17-chart-generation-quality-upgrade.md`.

Two execution options:

**1. Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks

**2. Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints
