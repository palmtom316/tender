# 2026-05-17 三份计划遗留收口计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 收口 2026-05-17 三份计划的遗留工作 — 把已落地的 Followup Roadmap Track A/B/E 标记完成、推进 Chart Refactor 改造 1 收尾、启动改造 2 GPT-Vis-SSR POC、并完成 D-1/D-2/E-5 综合 e2e 与盲评。

**Architecture:** 四条独立 Track。Track 1 纯文档同步;Track 2 收口改造 1 的 indicator_table POC + 删除旧 SVG 函数;Track 3 完整执行改造 2 GPT-Vis-SSR POC(部署→契约→分发→对比);Track 4 跑综合 e2e + 评标专家盲评作为最终验收。Track 间依赖见 §依赖图。

**Tech Stack:** Python (pydantic / pytest), vl-convert-python, Vega-Lite, Node-based GPT-Vis-SSR(待选型), Docker Compose, FastAPI, deepseek-v4-flash/pro, LibreOffice + PyMuPDF.

**关联输入文档:**
- `docs/superpowers/plans/2026-05-17-chapter-8-followup-quality-roadmap.md`(Track A/B/E 大量 `- [ ]` 实际已落地,D-1/D-2/E-5 暂缓)
- `docs/plans/2026-05-17-chart-rendering-refactor-plan.md`(改造 1 上游完工,改造 2 整段未启)
- `docs/superpowers/plans/2026-05-17-chart-generation-quality-upgrade.md`(已并入 Followup Roadmap,本计划不再单列任务)

---

## 一、Track 1 — Followup Roadmap 文档同步(纯文档,无代码)

**Goal:** 把 `2026-05-17-chapter-8-followup-quality-roadmap.md` 中 Track A/B/E 已落地条目的 `- [ ]` 改为 `- [x]`,并在 § 修订记录段追加 v1.3 完成日期与 commit hash,使文档与代码一致。

**已落地证据(对应 commits):**

| 任务 | 代码证据 | 关联 commit |
|---|---|---|
| A-1A 15 chart types audit | `chart_service/specs.py:21,40` 含全部 15 类 | `e799780` |
| A-1B templates | `chart_service/templates.py` 全 15 类 | `abe8b16` |
| A-2 semantic spec | `chart_generation_service.py` "Never output coordinates" prompt + `_normalize_flow_nodes` 过滤视觉字段 | `2725577` |
| A-3 render_strategy | `chart_service/render_strategy.py` | `68bd1e6` |
| A-4 layout_flow | `chart_service/layout_flow.py` | `95a9dc9` |
| A-5 gantt summary | `renderers.py:262 _render_gantt_summary_svg` | `b85afa8` |
| A-6 adaptive table | `renderers.py` `_adaptive_cell_width` 等 | `5899eb7` |
| A-7 quality_gate | `chart_service/quality_gate.py:35,39,43,50` 含 text_overflow/aspect_extreme/density_overload/font_below_minimum | `0516e91` |
| A-8 fallback metadata | `chart_generation_service.py:422 degradation_chain` | `0516e91` |
| A-9 golden fixtures | `backend/tests/fixtures/chart_specs/` 15 个 JSON | `bbe0392` |
| A-10 prompt docs | `backend/tests/unit/test_chart_prompt_contracts.py` + 各 `docs/samples/*.md` | `4fcdfd0` |
| A-11 chart_key whitelist | `longform_quality.py:281 normalize_allowed_chart_keys` + `severity:"P1"` at line 334 | `270a8b3` |
| B-1 subsection density hint | `technical_bid_writer.py:539 subsection_density_hint` | `cf55d49` |
| B-2 v4-pro premium | `task_profiles.py:14 generate_longform_subsection_premium` + `longform_section_generation.py:154 premium_threshold_chars` | `5b17fc1` |
| B-3 max_rounds 6 | `longform_section_generation.py:154 max_rounds=6` | `e92845b` |
| B-4 estimated_pages dual | `longform_quality.py:43,55 estimated_pages_gate/_actual_like` | `d97bac4` |
| E-1 LONGFORM_CHAPTER_CONFIG | `technical_chapter_strategies/registry.py` | `59cbc64` |
| E-2 plan_chapter_sections | `longform_section_generation.py:33` | `59cbc64` |
| E-3 SECTION_WEIGHTS/DEFAULT_CHARTS/DEFAULT_TABLES per chapter | `registry.py:160,242,269` | `59cbc64` |
| E-4 三级编号 | `longform_quality.py:133 _present_section_codes` | `59cbc64` |
| E-5 multi-chapter script | `scripts/run_longform_multi_chapter_acceptance.py` | `59cbc64` |

### Task 1.1:勾选 Track A 全部条目

**Files:**
- Modify: `docs/superpowers/plans/2026-05-17-chapter-8-followup-quality-roadmap.md`

- [x] **Step 1:** 用 Edit 把 Track A 章节(A-1A 至 A-11)所有 `- [ ]` 改为 `- [x]`。每条 Acceptance 不动,仅 Steps 内 checkbox 翻 x。
- [x] **Step 2:** 检查改动数量(约 60+ 条):`grep -c "- \[x\]" docs/superpowers/plans/2026-05-17-chapter-8-followup-quality-roadmap.md`

### Task 1.2:勾选 Track B 全部条目

**Files:**
- Modify: `docs/superpowers/plans/2026-05-17-chapter-8-followup-quality-roadmap.md`

- [x] **Step 1:** 把 Track B(B-1 至 B-4)的 `- [ ]` 改为 `- [x]`

### Task 1.3:勾选 Track E 全部条目

**Files:**
- Modify: `docs/superpowers/plans/2026-05-17-chapter-8-followup-quality-roadmap.md`

- [x] **Step 1:** 把 Track E(E-1 至 E-5 共 5 个任务,各含 Steps)的 `- [ ]` 改为 `- [x]`。**E-5 仅勾代码侧 step,evidence json 落档与 Track 4 Task 4.4 联动后再勾**

### Task 1.4:追加修订记录 v1.3

**Files:**
- Modify: `docs/superpowers/plans/2026-05-17-chapter-8-followup-quality-roadmap.md`(`## 修订记录` 表格末尾追加一行)

- [x] **Step 1:** 表格追加:`| v1.3 | 2026-05-18 | Track A/B/E 全部代码落地,文档 checkbox 同步。E-5 evidence 待 Track 4 联动产出。D-1/D-2 仍按既有"暂缓"决策待 Track 4 启动。|`

### Task 1.5:Commit

**Files:**
- 提交 Track 1 的全部文档变更

- [x] **Step 1:**

```bash
git add docs/superpowers/plans/2026-05-17-chapter-8-followup-quality-roadmap.md
git commit -m "docs(followup-roadmap): mark track A/B/E complete, sync with code"
```

---

## 二、Track 2 — Chart Refactor 改造 1 收尾

**Goal:** 完成改造 1 的最后两件事 — `indicator_table` vl-convert POC + 灰度验收并删除两个旧 native SVG 矩阵渲染函数。

**前置事实:**
- `render_strategy.py:21` 当前所有 `TABLE_CHART_TYPES`(含 `indicator_table`)走 `native_svg`,无 fallback
- `renderers.py:282 _render_risk_matrix_svg` / `renderers.py:313 _render_responsibility_matrix_svg` 仍作为 fallback 存在(策略表 `("vl_convert","native_svg")` 第二项)
- `vega_mapper.py` 仅含 `risk_matrix_to_vega` / `responsibility_matrix_to_vega`,无 indicator_table 入口

### Task 2.1:indicator_table → Vega-Lite mapper(TDD)

**Files:**
- Modify: `backend/tender_backend/services/chart_service/vega_mapper.py`
- Test: `backend/tests/unit/test_chart_vega_mapper.py`

- [ ] **Step 1:** 写失败测试 — 在 `test_chart_vega_mapper.py` 末尾追加:

```python
from tender_backend.services.chart_service.vega_mapper import indicator_table_to_vega
from tender_backend.services.chart_service.specs import TableChartSpec


def test_indicator_table_to_vega_emits_table_layer():
    spec = TableChartSpec(
        chart_type="indicator_table",
        title="关键指标表",
        columns=["指标", "目标", "单位"],
        rows=[
            {"cells": ["合格率", "≥98", "%"]},
            {"cells": ["返工率", "≤2", "%"]},
        ],
    )
    vega = indicator_table_to_vega(spec)
    assert vega["$schema"].startswith("https://vega.github.io/schema/vega-lite/")
    assert vega["title"]["text"] == "关键指标表"
    assert any(layer["mark"]["type"] == "text" for layer in vega["layer"])
    rows = vega["datasets"][next(iter(vega["datasets"]))]
    assert len(rows) == len(spec.columns) * (len(spec.rows) + 1)  # header + body
```

- [ ] **Step 2:** 运行:`pytest backend/tests/unit/test_chart_vega_mapper.py::test_indicator_table_to_vega_emits_table_layer -v`,期望 FAIL(import error)。

- [ ] **Step 3:** 在 `vega_mapper.py` 实现 `indicator_table_to_vega(spec)`:

```python
def indicator_table_to_vega(spec: TableChartSpec) -> dict[str, Any]:
    rows_payload: list[dict[str, Any]] = []
    for col_idx, col in enumerate(spec.columns):
        rows_payload.append({"row": 0, "col": col_idx, "text": col, "is_header": True})
    for row_idx, row in enumerate(spec.rows, start=1):
        for col_idx, value in enumerate(row.cells):
            rows_payload.append({"row": row_idx, "col": col_idx, "text": str(value), "is_header": False})

    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": {"text": spec.title, "fontSize": FONT.title_px},
        "datasets": {"cells": rows_payload},
        "data": {"name": "cells"},
        "width": 720,
        "height": 24 * (len(spec.rows) + 1),
        "layer": [
            {
                "mark": {"type": "rect", "stroke": PALETTE.border, "fill": PALETTE.surface},
                "encoding": {
                    "x": {"field": "col", "type": "ordinal", "axis": None},
                    "y": {"field": "row", "type": "ordinal", "axis": None},
                    "color": {
                        "condition": {"test": "datum.is_header", "value": PALETTE.header_fill},
                        "value": PALETTE.surface,
                    },
                },
            },
            {
                "mark": {"type": "text", "fontSize": FONT.body_px, "align": "center", "baseline": "middle"},
                "encoding": {
                    "x": {"field": "col", "type": "ordinal", "axis": None},
                    "y": {"field": "row", "type": "ordinal", "axis": None},
                    "text": {"field": "text"},
                    "fontWeight": {"condition": {"test": "datum.is_header", "value": "bold"}, "value": "normal"},
                },
            },
        ],
    }
```

- [ ] **Step 4:** 运行同一测试:`pytest backend/tests/unit/test_chart_vega_mapper.py::test_indicator_table_to_vega_emits_table_layer -v`,期望 PASS。

- [ ] **Step 5:** 跑全量 mapper 测试:`pytest backend/tests/unit/test_chart_vega_mapper.py -v`,期望全绿。

- [ ] **Step 6:** Commit:

```bash
git add backend/tender_backend/services/chart_service/vega_mapper.py backend/tests/unit/test_chart_vega_mapper.py
git commit -m "feat(chart): add indicator_table vega mapper for vl-convert poc"
```

### Task 2.2:render_strategy 接入 indicator_table → vl_convert(POC flag)

**Files:**
- Modify: `backend/tender_backend/services/chart_service/render_strategy.py`
- Modify: `backend/tender_backend/services/chart_service/renderers.py`(`render_chart_spec` 分发分支)
- Test: `backend/tests/unit/test_chart_render_strategy.py`

- [ ] **Step 1:** 写失败测试 — 在 `test_chart_render_strategy.py` 末尾追加:

```python
def test_indicator_table_strategy_uses_vl_convert_with_native_fallback():
    strategy = resolve_render_strategy("indicator_table")
    assert strategy.primary == "vl_convert"
    assert strategy.fallback == "native_svg"
```

- [ ] **Step 2:** 运行:`pytest backend/tests/unit/test_chart_render_strategy.py::test_indicator_table_strategy_uses_vl_convert_with_native_fallback -v`,期望 FAIL。

- [ ] **Step 3:** 修改 `render_strategy.py`,把 `indicator_table` 从默认 `TABLE_CHART_TYPES` 字典推开,显式声明:

```python
_TABLE_CHART_TYPES_NATIVE = TABLE_CHART_TYPES - {"indicator_table"}

_STRATEGIES: dict[str, RenderStrategy] = {
    **{chart_type: RenderStrategy(chart_type, "mermaid_sidecar", "native_flow") for chart_type in FLOW_CHART_TYPES},
    "schedule_gantt": RenderStrategy("schedule_gantt", "mermaid_sidecar", "native_gantt"),
    "critical_path": RenderStrategy("critical_path", "mermaid_sidecar", "native_gantt"),
    "risk_matrix": RenderStrategy("risk_matrix", "vl_convert", "native_svg"),
    "responsibility_matrix": RenderStrategy("responsibility_matrix", "vl_convert", "native_svg"),
    "indicator_table": RenderStrategy("indicator_table", "vl_convert", "native_svg"),
    **{chart_type: RenderStrategy(chart_type, "native_svg", None) for chart_type in _TABLE_CHART_TYPES_NATIVE},
}
```

- [ ] **Step 4:** 在 `renderers.py:render_chart_spec` 的 `vl_convert` 分支中,为 `indicator_table` 加路由(参考 `risk_matrix` 当前实现):

```python
if isinstance(spec, TableChartSpec) and spec.chart_type == "indicator_table" and strategy.primary == "vl_convert":
    vega_spec = indicator_table_to_vega(spec)
    vega_svg = _render_vega_svg(vega_spec)
    if vega_svg:
        return ChartRenderResult(svg=vega_svg, mermaid_source=None, engine="vl_convert")
    # fall through to native_svg via _render_table_svg
```

记得在文件顶部 import:`from tender_backend.services.chart_service.vega_mapper import indicator_table_to_vega`。

- [ ] **Step 5:** 运行:`pytest backend/tests/unit/test_chart_render_strategy.py backend/tests/unit/test_chart_rendering_and_injector.py -v`,期望全绿。

- [ ] **Step 6:** Commit:

```bash
git add backend/tender_backend/services/chart_service/render_strategy.py backend/tender_backend/services/chart_service/renderers.py backend/tests/unit/test_chart_render_strategy.py
git commit -m "feat(chart): route indicator_table to vl-convert with native fallback"
```

### Task 2.3:indicator_table POC 样本对比脚本

**Files:**
- Create: `backend/scripts/render_indicator_table_samples.py`(参考已有 `render_matrix_samples.py` 风格)
- Create: `docs/acceptance/2026-MM-DD-indicator-table-poc-evidence.json`(脚本输出)

- [ ] **Step 1:** 在 `backend/tests/fixtures/chart_specs/` 下增 4 份 `indicator_table` 真实样本 JSON(来自第 8/9/10 章产出),命名 `indicator_table_a.json` ~ `indicator_table_d.json`,加上原有 `indicator_table.json` 共 5 份。

- [ ] **Step 2:** 实现脚本:对 5 份 fixture 各分别强制 `engine="vl_convert"` 与 `engine="native_svg"` 渲染,落 SVG/PNG 到 `outputs/indicator-table-poc/{vl,native}/`,并按 T16 量化指标(文字溢出率/最小字号/A4 比例/DPI/字体)产 JSON 报告。

- [ ] **Step 3:** 运行脚本,导出 `docs/acceptance/2026-05-18-indicator-table-poc-evidence.json`(日期按实际),含每图量化指标对比。

- [ ] **Step 4:** 在 JSON 报告末尾追加 `decision` 字段:`adopt | reject`。判定规则:vl_convert 在文字溢出率、最小字号、A4 比例 三项中 ≥2 项不劣于 native_svg 即 `adopt`。

- [ ] **Step 5:** 若 `decision == reject`,回滚 Task 2.2 的 strategy 改动并在 evidence JSON 记录原因,Track 2.4 跳过 indicator_table 部分。

- [ ] **Step 6:** Commit:

```bash
git add backend/scripts/render_indicator_table_samples.py backend/tests/fixtures/chart_specs/indicator_table_*.json docs/acceptance/2026-05-18-indicator-table-poc-evidence.json
git commit -m "feat(chart): indicator_table vl-convert poc evidence"
```

### Task 2.4:改造 1 灰度验收(risk_matrix + responsibility_matrix + (indicator_table?))

**Files:**
- Create: `docs/acceptance/2026-05-18-chart-refactor-stage1-gray-release.md`

- [ ] **Step 1:** 从历史项目 chart_assets 抽 30 对(新 vs 旧)矩阵图;risk_matrix 10 对、responsibility_matrix 10 对、若 Task 2.3 adopt 则 indicator_table 10 对,否则补成 risk/responsibility 各 15 对。

- [ ] **Step 2:** 对每对图采集:
  - T16 5 项量化指标(`quality_gate.evaluate_svg_quality + compute_post_metrics`)
  - 业务方盲评(标注是 A/B 哪边胜出或持平)

- [ ] **Step 3:** 在 `2026-05-18-chart-refactor-stage1-gray-release.md` 落:
  - 30 对量化指标表
  - 盲评汇总表(胜率/持平率)
  - 通过判定:量化指标全部达 T16 阈值 + 盲评胜率 ≥60%
  - 若不通过列出阻塞项与回滚步骤

- [ ] **Step 4:** Commit:

```bash
git add docs/acceptance/2026-05-18-chart-refactor-stage1-gray-release.md
git commit -m "docs(chart-refactor): stage-1 gray release acceptance"
```

### Task 2.5:删除旧 native SVG 矩阵渲染函数

**前置:** Task 2.4 判定通过

**Files:**
- Modify: `backend/tender_backend/services/chart_service/renderers.py`(删除 `_render_risk_matrix_svg`、`_render_responsibility_matrix_svg`)
- Modify: `backend/tender_backend/services/chart_service/render_strategy.py`(把 risk/responsibility 的 fallback 从 `native_svg` 改为 `None`,或保留但移除 dispatcher 分支)

- [ ] **Step 1:** 在 `renderers.py:render_chart_spec` 中,把 risk_matrix / responsibility_matrix 的 native_svg fallback 路径删掉,只保留 vl_convert 与最终 `_render_fallback`(73685f0 的 fallback chain 兜底)。

- [ ] **Step 2:** 删除 `renderers.py:282 _render_risk_matrix_svg` 函数与 `renderers.py:313 _render_responsibility_matrix_svg` 函数(整段)。

- [ ] **Step 3:** 改 `render_strategy.py`:

```python
"risk_matrix": RenderStrategy("risk_matrix", "vl_convert", None),
"responsibility_matrix": RenderStrategy("responsibility_matrix", "vl_convert", None),
```

(若 Task 2.3 adopt,indicator_table 保持 `fallback="native_svg"`,因为 native table renderer 仍服务于其他 table 类型;不删 `_render_table_svg`。)

- [ ] **Step 4:** 跑现有矩阵相关测试:

```bash
pytest backend/tests/unit/test_chart_render_strategy.py \
       backend/tests/unit/test_chart_rendering_and_injector.py \
       backend/tests/unit/test_chart_vega_mapper.py \
       backend/tests/unit/test_chart_snapshot_contracts.py -v
```

期望全绿。若 fixture 测试期望旧 SVG 文本,顺手把 fixture 测试期望同步到 vl_convert 输出。

- [ ] **Step 5:** Commit:

```bash
git add backend/tender_backend/services/chart_service/renderers.py backend/tender_backend/services/chart_service/render_strategy.py backend/tests/
git commit -m "refactor(chart): drop native matrix svg renderers after vl-convert gray release"
```

### Task 2.6:更新 chart-rendering-refactor-plan.md

**Files:**
- Modify: `docs/plans/2026-05-17-chart-rendering-refactor-plan.md`

- [ ] **Step 1:** 在 § 0 修订记录段追加 v3(2026-05-18):"改造 1 灰度验收通过,旧 SVG 矩阵函数删除。indicator_table POC 决策 = adopt/reject(择一)。"

- [ ] **Step 2:** Commit:

```bash
git add docs/plans/2026-05-17-chart-rendering-refactor-plan.md
git commit -m "docs(chart-refactor): close stage 1, record indicator_table decision"
```

---

## 三、Track 3 — Chart Refactor 改造 2:GPT-Vis-SSR POC

**Goal:** 按计划 § 4 把 GPT-Vis-SSR 作为独立 POC 与 mermaid 并存对比,跑 100 对图量化指标 + 盲评,产 POC 报告决定后续 cutover。不在本计划范围内执行 cutover。

**关键事实(已核实):**
- 仓库零 GPT-Vis 关键词
- `infra/docker-compose.yml` 不含 gpt-vis-ssr service
- `backend/tests/integration/test_gpt_vis_contract.py` 不存在
- mermaid-render 当前 spawn mmdc + headless Chromium,无并发限流

### Task 3.1:GPT-Vis-SSR 调研备忘(T6)

**Files:**
- Create: `docs/plans/2026-05-18-gpt-vis-ssr-research.md`

- [ ] **Step 1:** 调研 GPT-Vis-SSR(GitHub `antvis/GPT-Vis`)落以下内容:
  - 官方镜像 / Dockerfile / API 形态(REST? CLI?)
  - 输入 spec 形态(JSON?Mermaid?antv g6?)
  - 中文字体支持情况
  - 离线部署可行性
  - 与 mermaid-render 同样关注的:并发限流、内存占用、启动时延
  - 失败模式(超时 / 4xx / 5xx / 非法 spec)
  - 能力边界:哪几类图表更适合 GPT-Vis、哪几类不如 mermaid

- [ ] **Step 2:** 在备忘末尾写 **POC 范围**:flow 50 + gantt 50,各章节图表来源、采样规则。

- [ ] **Step 3:** Commit:

```bash
git add docs/plans/2026-05-18-gpt-vis-ssr-research.md
git commit -m "docs(chart-refactor): gpt-vis-ssr research memo"
```

### Task 3.2:infra 加 gpt-vis-ssr service(T7)

**Files:**
- Modify: `infra/docker-compose.yml`(新增 service)
- Create: `infra/gpt-vis-ssr/`(若需自定义镜像,放 Dockerfile + entrypoint;否则只放 `README.md` 引用官方镜像)

- [ ] **Step 1:** 按 Task 3.1 调研结论选官方镜像或自构建,在 `infra/docker-compose.yml` 增 service:

```yaml
  gpt-vis-ssr:
    image: <调研选定镜像>
    container_name: gpt-vis-ssr
    restart: unless-stopped
    ports:
      - "127.0.0.1:7102:7102"
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:7102/health"]
      interval: 30s
      timeout: 5s
      retries: 5
    networks:
      - default
```

具体端口、health 端点按调研结论调整。

- [ ] **Step 2:** 启动并验证:

```bash
cd infra
docker compose up -d gpt-vis-ssr
docker compose ps gpt-vis-ssr
curl -fsS http://localhost:7102/health
```

期望 healthy。

- [ ] **Step 3:** Commit:

```bash
git add infra/docker-compose.yml infra/gpt-vis-ssr/
git commit -m "infra: add gpt-vis-ssr container for chart poc"
```

### Task 3.3:GPT-Vis-SSR 6 类 contract test(T17,TDD)

**Files:**
- Create: `backend/tests/integration/test_gpt_vis_contract.py`
- Create: `backend/tender_backend/services/chart_service/gpt_vis_client.py`(HTTP 调用封装)

- [ ] **Step 1:** 写 6 类失败测试(简化骨架,实际签名按 Task 3.2 选定 API 调整):

```python
import pytest
from tender_backend.services.chart_service.gpt_vis_client import GptVisClient


@pytest.fixture(scope="module")
def client():
    return GptVisClient(base_url="http://gpt-vis-ssr:7102")


def test_basic_render_returns_valid_svg(client):
    svg = client.render({"chart_type": "flow", "nodes": [{"id": "a", "label": "起点"}], "edges": []})
    assert svg.startswith("<svg")


def test_svg_fits_a4_aspect(client):
    svg = client.render(...)  # 略
    # 解析 viewBox,断言 0.6 ≤ width/height ≤ 1.5


def test_chinese_font_rendering(client):
    svg = client.render({"chart_type": "flow", "nodes": [{"id": "a", "label": "中文节点"}], "edges": []})
    assert "中文节点" in svg


def test_invalid_spec_returns_4xx(client):
    with pytest.raises(client.BadRequest):
        client.render({"chart_type": "unknown", "nonsense": True})


def test_timeout_handling(client, monkeypatch):
    monkeypatch.setattr(client, "_timeout_seconds", 0.001)
    with pytest.raises(client.Timeout):
        client.render({"chart_type": "flow", "nodes": [...], "edges": [...]})


def test_offline_render_no_external_egress(client):
    # 通过 iptables/网络配置或 sidecar 检查无出网
    svg = client.render(...)
    assert svg.startswith("<svg")


def test_concurrency_10_under_30s(client):
    import concurrent.futures, time
    payload = {"chart_type": "flow", "nodes": [...], "edges": [...]}
    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _: client.render(payload), range(10)))
    assert all(svg.startswith("<svg") for svg in results)
    assert time.time() - start < 30
```

- [ ] **Step 2:** 运行:`pytest backend/tests/integration/test_gpt_vis_contract.py -v`,期望 FAIL(import error / connection refused)。

- [ ] **Step 3:** 实现 `gpt_vis_client.py`(requests + 异常类型 + 超时配置)。

- [ ] **Step 4:** 重跑测试,需 Task 3.2 container 运行中。期望 7 个测试全绿。若某 1 项不达标,在 Task 3.1 备忘记录 known limitation。

- [ ] **Step 5:** Commit:

```bash
git add backend/tests/integration/test_gpt_vis_contract.py backend/tender_backend/services/chart_service/gpt_vis_client.py
git commit -m "test(chart-refactor): gpt-vis-ssr contract suite"
```

### Task 3.4:多引擎分发(T8,默认仍走 mermaid)

**Files:**
- Modify: `backend/tender_backend/services/chart_service/renderers.py`(`render_chart_spec`)
- Modify: `backend/tender_backend/services/chart_service/render_strategy.py`
- Modify: `backend/tender_backend/core/config.py`(加 `CHART_FLOW_ENGINE` env,默认 `mermaid_sidecar`)
- Test: `backend/tests/unit/test_chart_render_strategy.py`、`backend/tests/unit/test_chart_rendering_and_injector.py`

- [ ] **Step 1:** 在 `core/config.py` 加配置:`chart_flow_engine: Literal["mermaid_sidecar","gpt_vis"] = "mermaid_sidecar"`。

- [ ] **Step 2:** 写失败测试,断言:

```python
def test_flow_strategy_respects_env_override(monkeypatch):
    monkeypatch.setenv("CHART_FLOW_ENGINE", "gpt_vis")
    # reload config / resolver
    strategy = resolve_render_strategy("construction_flow")
    assert strategy.primary == "gpt_vis"
    assert strategy.fallback == "mermaid_sidecar"


def test_flow_strategy_default_is_mermaid():
    strategy = resolve_render_strategy("construction_flow")
    assert strategy.primary == "mermaid_sidecar"
```

- [ ] **Step 3:** 改 `render_strategy.py`,把 FLOW_CHART_TYPES + gantt 的 primary 按配置取值。`gpt_vis` 不可用时 fallback 到 `mermaid_sidecar`。

- [ ] **Step 4:** 改 `renderers.py:render_chart_spec`,新增 `primary == "gpt_vis"` 分支调用 `GptVisClient`。

- [ ] **Step 5:** 跑全量 chart 测试:`pytest backend/tests/unit/test_chart_*.py -v`。期望全绿,默认行为不变。

- [ ] **Step 6:** Commit:

```bash
git add backend/tender_backend/core/config.py backend/tender_backend/services/chart_service/ backend/tests/unit/test_chart_*.py
git commit -m "feat(chart-refactor): multi-engine flow dispatch with mermaid default"
```

### Task 3.5:100 对图离线 POC 对比(T9)

**Files:**
- Create: `backend/scripts/run_gpt_vis_poc.py`
- Create: `docs/acceptance/2026-05-18-gpt-vis-poc-evidence.json`(脚本输出)
- Create: `docs/reports/2026-05-18-gpt-vis-poc-report.md`

- [ ] **Step 1:** 脚本采样 50 个 construction_flow / closure_flow / data_flow / quality_system / safety_system / emergency_org / org_chart 的真实 spec + 50 个 schedule_gantt / critical_path 真实 spec。各 spec 同时跑 `CHART_FLOW_ENGINE=mermaid_sidecar` 与 `=gpt_vis`,落 SVG + 量化指标。

- [ ] **Step 2:** 量化指标用 `quality_gate.evaluate_svg_quality + compute_post_metrics`,T16 5 项每项做新旧对比。

- [ ] **Step 3:** 组织业务方盲评 30 对(随机抽样,A/B 双盲)。盲评维度:可读性、版面美观、招标合规性。

- [ ] **Step 4:** 落 `docs/acceptance/2026-05-18-gpt-vis-poc-evidence.json`:每图量化指标对比表 + 盲评原始记录。

- [ ] **Step 5:** 写 `docs/reports/2026-05-18-gpt-vis-poc-report.md`:
  - 100 对图汇总(量化指标平均值/中位数)
  - 盲评胜率统计
  - **决策**:`adopt | reject`(adopt 条件:≥3 项量化指标不劣于 mermaid + 盲评胜率 ≥60%)
  - 后续 cutover 计划骨架(若 adopt)/ 关闭 gpt-vis-ssr 与回退步骤(若 reject)

- [ ] **Step 6:** 若 `reject`,执行:

```bash
docker compose stop gpt-vis-ssr
docker compose rm -f gpt-vis-ssr
```

并在 `infra/docker-compose.yml` 注释或删除 service,Commit 一次"chore(infra): drop gpt-vis-ssr after poc reject"。

- [ ] **Step 7:** Commit POC 结果:

```bash
git add backend/scripts/run_gpt_vis_poc.py docs/acceptance/2026-05-18-gpt-vis-poc-evidence.json docs/reports/2026-05-18-gpt-vis-poc-report.md
git commit -m "docs(chart-refactor): gpt-vis-ssr poc report and decision"
```

### Task 3.6:更新 chart-rendering-refactor-plan.md(T10 状态)

**Files:**
- Modify: `docs/plans/2026-05-17-chart-rendering-refactor-plan.md`

- [ ] **Step 1:** 在 § 0 修订记录段追加 v4(2026-05-18):"GPT-Vis-SSR POC 完成,decision = adopt/reject。T10 cutover 状态更新为 待启动独立计划 / 永久关闭。"

- [ ] **Step 2:** Commit:

```bash
git add docs/plans/2026-05-17-chart-rendering-refactor-plan.md
git commit -m "docs(chart-refactor): close stage 2 poc with decision"
```

---

## 四、Track 4 — 综合 e2e + 评标专家盲评(D-1 / D-2 / E-5 evidence)

**Goal:** 在 Track 2 完成后(Track 3 可与本 track 并行,不构成前置),跑全量改造完成后的统一 e2e:第 8/9/10.1/10.2/10.3 章合计 ~200~250 页 longform 生成 + 评标专家盲评。

### Task 4.1:第 8 章 followup final e2e(D-1)

**Files:**
- Modify(若需调整 CLI 参数): `scripts/run_chapter_8_acceptance.py`
- Create: `docs/acceptance/2026-05-18-chapter-8-followup-final-evidence.json`

- [ ] **Step 1:** 运行:

```bash
python scripts/run_chapter_8_acceptance.py --project-id <真实项目ID> --target-pages 100
```

期望:`actual_pages ≥ 90` + `coverage_passed` + `chart_closure_passed` + `charts_approved` + `format_passed` + `can_export`。

- [ ] **Step 2:** 把脚本最终 JSON 输出保存到 `docs/acceptance/2026-05-18-chapter-8-followup-final-evidence.json`。

- [ ] **Step 3:** 若任一门禁失败,记录失败项与 RCA 候选到 `docs/reports/2026-05-18-chapter-8-final-failure-rca.md`,**不勾选 4.1**,停在此处与用户对齐。

- [ ] **Step 4:** Commit:

```bash
git add docs/acceptance/2026-05-18-chapter-8-followup-final-evidence.json
git commit -m "docs(acceptance): chapter 8 followup final e2e evidence"
```

### Task 4.2:第 9/10.1/10.2/10.3 章 longform e2e(E-5)

**Files:**
- Modify(若需): `scripts/run_longform_multi_chapter_acceptance.py`
- Create: `docs/acceptance/2026-05-18-longform-8-9-10-evidence.json`

- [ ] **Step 1:** 运行:

```bash
python scripts/run_longform_multi_chapter_acceptance.py --project-id <真实项目ID> --chapters 8,9,10.1,10.2,10.3
```

- [ ] **Step 2:** 验证:
  - 第 8 章 ≥ 90 页
  - 第 9 章 30~40 页
  - 第 10.1/10.2/10.3 各 35~50 页
  - 各章 `coverage_passed + chart_closure_passed`

- [ ] **Step 3:** 落 evidence:`docs/acceptance/2026-05-18-longform-8-9-10-evidence.json`,字段含每章 `section_count / generation_rounds / actual_pages / coverage_issues / chart_closure_issues / model_usage`。

- [ ] **Step 4:** Commit:

```bash
git add docs/acceptance/2026-05-18-longform-8-9-10-evidence.json
git commit -m "docs(acceptance): longform 8/9/10 multi-chapter e2e evidence"
```

### Task 4.3:评标专家盲评(D-2)

**Files:**
- Create: `docs/reviews/2026-05-18-followup-blind-review.md`

- [ ] **Step 1:** 从 Task 4.1 + 4.2 产出中选 3 个真实项目(含 1 个暗标项目)的完整 DOCX。

- [ ] **Step 2:** 提交评标专家盲评,采集:篇幅完整度、专业表现力、图表可读性、暗标合规性,4 项各 1~5 分。

- [ ] **Step 3:** 在 `docs/reviews/2026-05-18-followup-blind-review.md` 落:每项目每维度评分 + 文字反馈 + 通过判定(均分 ≥3.5 视为通过)。

- [ ] **Step 4:** Commit:

```bash
git add docs/reviews/2026-05-18-followup-blind-review.md
git commit -m "docs(reviews): followup blind review by tender experts"
```

### Task 4.4:Followup Roadmap 收口 — 勾选 D-1/D-2/E-5 + 写 Phase 2 Final Decision

**Files:**
- Modify: `docs/superpowers/plans/2026-05-17-chapter-8-followup-quality-roadmap.md`(勾选 D-1/D-2/E-5 + § 修订记录追加 v1.4)
- Modify: `docs/acceptance/2026-05-15-longform-launch-closure.md`(追加 "Phase 2 Final Decision" 段)

- [ ] **Step 1:** 把 Followup Roadmap 中 D-1、D-2、E-5(evidence 部分)的 `- [ ]` 改为 `- [x]`。把 D-1/D-2 顶部的 "Status: 暂缓" 改为 "Status: 已完成于 2026-05-18"。

- [ ] **Step 2:** 在 § 修订记录追加:`| v1.4 | 2026-05-18 | D-1 / D-2 / E-5 完成,Phase 2 收口。|`

- [ ] **Step 3:** 在 `2026-05-15-longform-launch-closure.md` 末尾追加 "Phase 2 Final Decision" 段,引用 Task 4.1/4.2/4.3 三份 evidence 文档,声明 longform launch 整体 closure。

- [ ] **Step 4:** Commit:

```bash
git add docs/superpowers/plans/2026-05-17-chapter-8-followup-quality-roadmap.md docs/acceptance/2026-05-15-longform-launch-closure.md
git commit -m "docs(closure): roadmap phase 2 final decision + longform launch closure"
```

---

## 五、依赖图

```
Track 1 (文档同步)            ── 独立 ★ 可立即开工
                              │
Track 2 (改造 1 收尾)         ── 独立 ★ 可立即开工
  2.1 mapper ─→ 2.2 strategy ─→ 2.3 POC ─→ 2.4 灰度验收 ─→ 2.5 删旧函数 ─→ 2.6 文档
                                                                                  │
Track 3 (改造 2 POC,可与 Track 2 并行)                                            │
  3.1 调研 ─→ 3.2 部署 ─→ 3.3 contract ─→ 3.4 多引擎 ─→ 3.5 POC 对比 ─→ 3.6 文档    │
                                                                                  │
Track 4 (综合 e2e + 盲评)                                                          │
  ←── blockedBy Track 2 完成 ────────────────────────────────────────────────────┘
  4.1 第 8 章 final ─→ 4.2 9/10.x e2e ─→ 4.3 盲评 ─→ 4.4 Phase 2 收口
```

**4 个起点可立即开工(可并行):**
- Track 1(纯文档,1 名工程师 0.5 天)
- Track 2.1 mapper(0.5 天)
- Track 3.1 调研(0.5~1 天)
- (注:Track 4 不能立即开工 — 必须等 Track 2 完成)

---

## 六、Success Criteria(hard stop)

- [ ] Track 1:Followup Roadmap 文档 checkbox 与代码状态一致,修订记录追加 v1.3
- [ ] Track 2:`_render_risk_matrix_svg` / `_render_responsibility_matrix_svg` 已从 renderers.py 删除;indicator_table POC 落 evidence 与决策;灰度验收报告归档
- [ ] Track 3:6 类 contract test 全绿;100 对图 POC report 落地;POC decision = adopt/reject 任一明确;若 reject,gpt-vis-ssr 容器已下线
- [ ] Track 4:三份 evidence(`chapter-8-followup-final` / `longform-8-9-10` / `followup-blind-review`)归档;Followup Roadmap v1.4 收口;`2026-05-15-longform-launch-closure.md` 追加 Phase 2 Final Decision

---

## 七、Risk Controls

- [ ] Task 2.3 indicator_table POC 若 reject,**必须**回滚 Task 2.1/2.2 的 strategy 改动,避免线上路由到失败 mapper
- [ ] Task 2.5 删除旧函数前必须确认 Task 2.4 通过;若灰度验收任一项不达标,立即回滚 strategy 改动,**不删函数**
- [ ] Task 3.2 部署 gpt-vis-ssr 时 PVE 资源压力 +300~500MB,先确认有冗余;若达成 reject 决策,Task 3.5 Step 6 必须执行容器下线
- [ ] Task 3.4 多引擎分发上线后,默认 `CHART_FLOW_ENGINE=mermaid_sidecar`,POC 期间禁止改默认值
- [ ] Task 4.1 / 4.2 e2e 若失败,**不勾选**,停在 RCA 阶段,与用户对齐再决定继续
- [ ] Track 4 启动前 Track 2 必须完成 — 否则盲评对象不稳定

---

## 八、Reporting Cadence

- [ ] 每完成 1 个 Track 内 Task:勾选 + commit message 带 `[CLOSURE-N-M]`
- [ ] 每完成 1 个 Track:在本文件 `## 修订记录` 段追加完成日期与 commit hash
- [ ] Track 4 完成:在本文件末尾 + `2026-05-15-longform-launch-closure.md` 双向归档

---

## 九、修订记录

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| v1.0 | 2026-05-18 | 初版落盘。整理 2026-05-17 三份计划遗留(Followup Roadmap Track A/B/E 文档同步、D-1/D-2/E-5 综合 e2e + 盲评;Chart Refactor 改造 1 收尾、改造 2 POC)。|
