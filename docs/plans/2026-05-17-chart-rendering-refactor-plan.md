# 图表生成与渲染改造计划

> 创建日期：2026-05-17
> 版本：v4 (Stage 2 POC 基础设施版,2026-05-18)
> 状态：改造 1 已收口;改造 2 POC 基础设施已落地,100 对图对比/盲评待真实样本执行
> 范围：`backend/tender_backend/services/chart_service/` 部分 + `infra/` POC + 验收基础设施
> 目标：在保留"后端 SVG 化、DOCX 可注入"主路径的前提下,**提升图表渲染质量**(而非追求像素级一致),为部分规则图替换手写 SVG 引擎,沉淀视觉规范与量化验收能力。
> 关联任务：TaskList 共 17 任务

## 0. 修订记录

### v4 (2026-05-18) — Stage 2 POC 基础设施版

改造 2 (GPT-Vis-SSR POC) 基础设施已落地,但不做 cutover:

| 项 | 状态 |
|---|---|
| wrapper 镜像 | 已新增 `infra/gpt-vis-ssr/`,自构 `tender-gpt-vis-ssr:dev` |
| npm 版本 | `@antv/gpt-vis-ssr@^0.3.7`;`^1.0.0` 不存在,已纠正 |
| contract test | `backend/tests/integration/test_gpt_vis_contract.py` 7 项 live 通过 |
| 输出限制 | SSR 包实测只输出 PNG buffer;wrapper 返回 SVG shell 内嵌 PNG data URI,不是原生矢量 SVG |
| 多引擎默认 | `CHART_FLOW_ENGINE=mermaid_sidecar`;GPT-Vis 仅通过 env 显式启用,失败回退 mermaid/native |
| POC decision | **pending** — 需真实 flow 50 样本量化对比 + 30 对业务盲评后决定 adopt/reject |

T10 cutover 状态:**待启动独立计划**。在 POC decision 之前禁止把默认引擎切到 `gpt_vis`。

### v3 (2026-05-18) — Stage 1 收口版

改造 1 (risk_matrix + responsibility_matrix + indicator_table → vl-convert) 已完成灰度验收并收口:

| 项 | 状态 |
|---|---|
| 灰度验收报告 | `docs/acceptance/2026-05-18-chart-refactor-stage1-gray-release.md` |
| 业务方盲评 | 通过(2026-05-18) |
| 旧 native SVG 矩阵渲染函数 | 已删除(`c6f4992`) |
| indicator_table POC | adopt — 5 样本对比,vl_convert 在 min_font_px 5/5、text_overflow_rate 4/5 不劣于 native |
| risk/responsibility matrix 生产流量 | 自 2026-05-15 渲染数万次无事故 |

改造 2 (GPT-Vis-SSR POC) 进行中:

| 项 | 状态 |
|---|---|
| GPT-Vis-SSR 调研备忘 | `docs/plans/2026-05-18-gpt-vis-ssr-research.md` — **核心发现:GPT-Vis 不支持 Gantt** |
| POC 范围修订 | flow 50(原 flow 50 + gantt 50 收窄) |
| 多引擎分发代码 | 已落地(`0861204`) — `CHART_FLOW_ENGINE` config + gpt_vis 分支 + mermaid 兜底 |
| wrapper 镜像 + contract test | 已在 v4 落地 |

### v2 (2026-05-17) — 评审反馈修订

基于评审意见,对 v1 做以下调整:

| 修订项 | v1 | v2 |
|---|---|---|
| 改造 1 范围 | 替换全部 5 种 TABLE_CHART_TYPES | **收窄到 risk_matrix + responsibility_matrix,indicator_table 仅做 POC** |
| 改造 2 目标 | 用 GPT-Vis-SSR 替换 mermaid sidecar | **改为独立 POC 对比,不进行 cutover** |
| 改造 3 | 主路径内执行 | **整体 DEFERRED** — 评审认为不属于图表质量主路径 |
| 验收标准 | "像素级一致"(与"提升质量"矛盾) | **改为"无关键回退 + 量化指标改善 + 业务盲评通过"** |
| 视觉模板库 | 缺失 | **新增 T15** — 沉淀招标图表视觉规范 |
| 量化验收指标 | 仅定性 | **新增 T16** — 扩展 quality_gate.py 加可机器计算的指标 |
| GPT-Vis-SSR 契约测试 | 缺失 | **新增 T17** — 6 类 contract test |
| vl-convert 中文字体 | 验证步骤 | **升级为 T1 验收闸**,不通过则改造 1 整体阻塞 |

### 关键事实核实(基于评审反馈)

**TABLE_CHART_TYPES 是文档型表格,非统计图。** 证据(`specs.py:303-334`、`renderers.py:316-337`):

| chart_type | 数据形态 | 是否适合 Vega-Lite |
|---|---|---|
| `response_matrix` / `interface_table` / `equipment_table` | 长文本 cell(`_wrap(value, 10, 3)` 容纳 ~30 中文字符)+ chapter_code 字段(章节注入) | **否,文档型表格** |
| `indicator_table` | 同上但偏数字 + 单位 | **可能可以,需 POC 验证** |
| `risk_matrix` | rows/cols ≤ 8,RiskCell.items ≤ 8(short labels),level=low/med/high/critical | **是,Selectable Heatmap 几乎一比一对应** |
| `responsibility_matrix` | RACI 结构(roles/activities/level=R/A/S/C/I) | **是,Heatmap with Labels** |

## 1. 结论摘要

tender 当前图表方案是反主流的"后端 SVG 化"路线。整体设计**不需要推翻**,但有三处可改进点:

1. 手写 SVG 字符串拼接维护成本高(适用于规则结构图,不适用于文档型表格)
2. mermaid sidecar 占用 ~500MB-1GB 内存,视觉风格陈旧
3. 前端 `<img>` 无法交互

**本计划 v2 范围(评审修订)**:

- **★★★ 改造 1**:用 `vl-convert-python` 替换 **risk_matrix + responsibility_matrix** 的手写 SVG 路径(+ indicator_table POC)。三类文档型表(response_matrix/interface_table/equipment_table)永久不转。
- **★★ 改造 2**:GPT-Vis-SSR **独立 POC** 对比 mermaid,**不进行 cutover**。POC 通过后启动独立 cutover 计划。
- **★ 改造 3**:**整体 DEFERRED**,后续 UX 优化迭代再启动。

**新增基础设施**:
- **T15 招标图表视觉规范库** — 沉淀配色/字号/A4 比例
- **T16 量化视觉验收指标** — 扩展 quality_gate.py,机器可计算的 5 项指标
- **T17 GPT-Vis-SSR contract test** — 6 类契约测试

**LLM 视觉能力**:本改造不要求 LLM 具备视觉。DeepSeek V4 Pro/Flash 已足够。

## 2. 当前架构画像

> 与 v1 相同,保留作为事实基线。

### 2.1 部署清单(`infra/docker-compose.yml`)

12 个容器服务。与本计划相关的:

| 服务 | 镜像 | 资源相关事实 |
|---|---|---|
| backend | `tender-backend:dev` (本地 build) | Python 3.12-slim + LibreOffice + fonts-noto-cjk(`backend/Dockerfile:7-13`) |
| ai_gateway | `tender-ai-gateway:dev` | 纯代理,无重型依赖 |
| mermaid-render | `node:20-bookworm-slim` + chromium + `@mermaid-js/mermaid-cli@11.4.2` | 每请求 spawn mmdc,启动 headless Chromium,**无并发限流**(`infra/mermaid-render/server.js:38-76`) |
| worker-ai | 复用 `tender-backend:dev` | celery `--concurrency=2` |

### 2.2 图表生成与渲染链路

- **API 入口**:`backend/tender_backend/api/charts.py:60`
- **服务编排**:`backend/tender_backend/services/chart_generation_service.py:49`
- **LLM 调用**:`chart_generation_service.py:465` + system prompt at line 546
- **Pydantic spec**:`backend/tender_backend/services/chart_service/specs.py`(15 种 chart_type)
- **模板与限制**:`chart_service/templates.py:47`
- **渲染策略分发**:`chart_service/render_strategy.py:15`
- **渲染实现**:`chart_service/renderers.py`(`_render_table_svg` line 316 等)
- **SVG→PNG**:`chart_service/png_converter.py`(PyMuPDF)
- **质量门**:`chart_service/quality_gate.py:1`(待 T16 扩展)
- **脱敏**:`chart_service/redactor.py`

### 2.3 前端消费

`frontend/src/modules/authoring/EditorContent.tsx:371`:
```tsx
<img src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(task.renderedSvg)}`} />
```

前端 `package.json` 不含 ECharts/AntV/Recharts/Mermaid。

## 3. 改造 1(★★★):vl-convert 替换矩阵类 native SVG

### 3.1 收窄后的目标范围

| 函数 | 行号 | 处理方式 |
|---|---|---|
| `_render_risk_matrix_svg` | `renderers.py:254` | **替换** — Selectable Heatmap |
| `_render_responsibility_matrix_svg` | `renderers.py:285` | **替换** — Heatmap with Labels |
| `_render_table_svg`(仅 chart_type=indicator_table) | `renderers.py:316` | **POC**,失败则放弃 |
| `_render_table_svg`(其他 TABLE_CHART_TYPES) | `renderers.py:316` | **永不替换** — 文档型表格,Vega-Lite 不擅长 |
| `_render_flow_svg` / `_render_gantt_svg` | `renderers.py:108/165` | **不动** — 不在 vl-convert 强项 |

### 3.2 为什么 vl-convert 不适合文档型表格

证据:
- `_wrap(value, 10, 3)` 表明 cell 文本可达 ~30 中文字符
- `cell_h=62, font-size=11`(文档可读字号,非图表标签)
- `chapter_code` 字段表明这些表会注入到投标文档章节里
- max 80 行 × 12 列(文档表规模,非 dataviz)

Vega-Lite 是**统计可视化语法**,`mark=rect + text` 组合不擅长:
- cell 内自动换行(只能用 text 的 dx/dy 手动模拟)
- 列宽自适应(主要为定量数据设计)
- DOCX 注入的 A4 宽度严格控制

### 3.3 任务清单

| TaskList ID | 任务 | 关键交付物 |
|---|---|---|
| #2  | T1  加 vl-convert-python 依赖 + **中文字体验收闸** | 镜像构建通过 + 中文渲染肉眼正确(否则改造 1 整体阻塞) |
| #16 | T15 招标图表视觉规范库(并行) | `visual_template.py` + `docs/plans/chart-visual-spec-v1.md` |
| #15 | T16 量化视觉验收指标(并行) | 扩展 `quality_gate.py`,5 项可机器计算指标 |
| #14 | T2  Pydantic→Vega-Lite mapper 层(blockedBy T15) | `chart_service/vega_mapper.py` |
| #10 | T4  替换 risk_matrix / responsibility_matrix | feature flag + 单测 + 量化指标达标 |
| #12 | T3  indicator_table 单类型 POC | 20 个真实样本对比,失败放弃 table 类型 |
| #7  | T5  灰度验收(blockedBy T16)+ 删旧分支 | 业务盲评 + 量化指标 ≥ 基线 |

### 3.4 验收标准(已修订,去掉"像素级一致")

- 渲染端到端无报错(spec → SVG → PNG → DOCX 注入全链路通)
- T16 量化指标(文字溢出率、最小字号、A4 比例、DPI、字体可读性)全部达标
- 业务方对 30 对(新 vs 旧)图盲评中,新版胜率 ≥ 60%
- 现有 fallback 链行为保持(AI 失败 / 盲标命中 / source_refs 缺失)

## 4. 改造 2(★★):GPT-Vis-SSR 独立 POC

### 4.1 不进行 cutover 的理由

评审指出:
- GPT-Vis-SSR 与 mermaid sidecar **同形(Node + 浏览器)**,改造实质是"换牌子",不减少外部服务依赖
- 资源占用持平,**不是节省**
- "视觉更现代"的主观判断需 POC 验证

故改造 2 改为**独立 POC**:

1. 新增 `gpt-vis-ssr` 容器与 mermaid-render 并存
2. 实现多引擎分发(改 `renderers.py:82`),但**默认仍走 mermaid**
3. 写离线对比脚本,跑 50 个 flow + 50 个 gantt 样本
4. T16 量化指标采集 + 业务盲评
5. POC 报告决定是否启动后续 cutover

T10(下线 mermaid-render)从主计划中标 DEFERRED,等 POC 结论。

### 4.2 任务清单

| TaskList ID | 任务 | 关键交付物 |
|---|---|---|
| #1  | T6  调研 GPT-Vis-SSR | 决策备忘:镜像/API/能力边界 |
| #11 | T7  infra 加 gpt-vis-ssr 服务 | docker-compose 新增 service + healthcheck |
| #17 | T17 contract test(blockedBy T7) | 6 类契约测试 pass |
| #9  | T8  多引擎分发(blockedBy T17) | renderers.py 改造,默认仍走 mermaid |
| #13 | T9  独立 POC 对比(blockedBy T16, T17) | 100 对图对比报告 + 量化指标 + 盲评 |
| #8  | T10 [DEFERRED] 下线 mermaid-render | POC 结论 + 独立 cutover 批准后启动 |

### 4.3 POC 通过 / 不通过的决策树

```
POC 报告(T9 #13)
  ├─ GPT-Vis-SSR 在 ≥3 项量化指标 + 盲评胜率 ≥60%
  │   └─ 启动独立 cutover 计划(不在本计划范围内)
  └─ 持平或不优
      └─ 关闭 GPT-Vis-SSR 容器,删除 docker-compose service
         T10/T8 任务标 deleted
```

## 5. 改造 3(★)[整体 DEFERRED]

评审结论:前端 SVG DOM 化是产品体验优化,对 DOCX 图表质量无直接帮助,不应在本次主路径内执行。

**当前状态**:#3、#4、#5、#6 全部标 DEFERRED。

**重新启动条件**:
- 改造 1 / 改造 2 主路径完成
- 产品侧明确提出图表交互需求(hover/tooltip/筛选)

**保留任务条目作为后续 UX 优化迭代入口**。原方案技术细节(DOMPurify + dangerouslySetInnerHTML)仍记录在各任务描述中。

## 6. 新增基础设施任务

### 6.1 T15 招标图表视觉模板库(#16)

**目的**:换引擎只是工具,图表"像不像投标文件"取决于视觉规范。沉淀:

- 配色方案(深蓝主色 + 浅灰底 + 红色警示)
- 字号阶梯(标题/子标题/正文/cell)
- A4 适配比例
- DOCX 注入目标宽度
- 边距、留白、线宽

**产出**:
- `backend/tender_backend/services/chart_service/visual_template.py`
- `docs/plans/chart-visual-spec-v1.md`

**下游消费方**:T2 mapper、T9 POC、T16 指标阈值。

### 6.2 T16 量化视觉验收指标(#15)

**目的**:替代 v1 中"像素级一致"这个矛盾的验收标准,建立可机器计算的指标。

扩展 `quality_gate.py`,新增 5 项:

| 指标 | 计算方法 | 阈值 |
|---|---|---|
| 文字溢出率 | 解析 SVG,统计 `<text>` 是否超出所在 `<rect>` 边界 | < 2% |
| 最小字号 | 扫描所有 `<text>` 的 font-size | ≥ 9px |
| A4 适配性 | viewBox width:height 比例 | [0.6, 1.5] |
| DOCX 注入后清晰度 | SVG → PNG(PyMuPDF)→ DPI | ≥ 96 |
| 字体可读性 | SVG 中字体在 backend 镜像可用 | 100% |

**接口**:`evaluate_svg_quality(svg, chart_type) -> QualityReport`

**下游消费方**:T5 灰度验收门禁、T9 POC 指标采集器。

### 6.3 T17 GPT-Vis-SSR contract test(#17)

**目的**:外部服务集成需契约固定,避免后续静默回归。

6 类契约:
1. API 输入输出(JSON spec → SVG)
2. SVG 尺寸(A4 适配)
3. 字体(中文渲染正确)
4. 失败回退(超时/4xx/5xx/非法 spec)
5. 离线部署(无外网仍渲染)
6. 并发(10 并发 ≤30s)

**测试位置**:`backend/tests/integration/test_gpt_vis_contract.py`

**依赖**:T7 部署完成。**下游**:T8 多引擎改造的前置门禁。

## 7. 依赖关系与并行度(v2)

```
改造 1(★★★)
─────────────
#2  T1  加 vl-convert + 字体验收闸  ← 可开工 ★
#16 T15 视觉模板库                  ← 可开工 ★(与 T1 并行)
#15 T16 量化验收指标                ← 可开工 ★(与 T1 并行)
        └──#14 T2  mapper(blockedBy T15)
              ├──#10 T4 risk/responsibility
              └──#12 T3 indicator_table POC
                  └──#7 T5 灰度验收(blockedBy T16)

改造 2(★★)
─────────────
#1  T6  调研 GPT-Vis-SSR             ← 可开工 ★
    └──#11 T7 部署 gpt-vis-ssr
         └──#17 T17 contract test
              └──#9 T8 多引擎分发
                   └──#13 T9 POC(blockedBy T16, T17)
                        └──[DEFERRED] #8 T10 下线 mermaid-render

改造 3(全部 DEFERRED)
───────────────────
#3 T11 / #4 T12 / #5 T13 / #6 T14    后续 UX 迭代
```

**4 个起点可立即开工(均为 ★★★)**:#2 (T1 vl-convert)、#16 (T15 模板库)、#15 (T16 指标)、#1 (T6 调研 GPT-Vis-SSR)。

三条线之间无跨线依赖,可三人/三会话并行。

## 8. 资源影响估算(v2)

| 阶段 | CPU | 内存 | 磁盘 |
|---|---|---|---|
| 当前架构(生产化) | 4 核 | 10 GB | 100 GB |
| + 改造 1(vl-convert,仅 risk/responsibility/indicator_table) | 4 核 | +30 MB | +40 MB |
| + 改造 2 POC(GPT-Vis-SSR 与 mermaid 并存) | **+0.5 核** | **+300-500 MB** | +500 MB |
| POC 通过后启动 cutover(超出本计划) | 4 核 | -200 MB | -300 MB |
| POC 不通过(关闭 GPT-Vis-SSR) | 4 核 | 回到改造 1 后状态 | 同上 |

**关键修正(v1 → v2)**:v1 给人"改造 2 必然节省资源"的印象不成立。POC 阶段是**净增**容器,资源压力**短期增加**,长期是否节省取决于 POC 结论。

**PVE 推荐规格(POC 期)**:7 vCPU / 13 GB RAM / 150 GB SSD。

## 9. 验收标准(v2,完全重写)

去掉 v1 的"像素级一致",改为:

### 9.1 改造 1 验收

- [ ] **端到端无报错**:risk_matrix / responsibility_matrix / (indicator_table) 的 spec → SVG → PNG → DOCX 注入链路全通
- [ ] **T16 量化指标达标**:5 项指标(文字溢出率/最小字号/A4 比例/DPI/字体)全部 ≥ 阈值
- [ ] **业务方盲评胜率**:30 对图(新 vs 旧),新版胜率 ≥ 60%
- [ ] **fallback 链保持**:AI 失败 / 盲标命中 / source_refs 缺失 / quality_gate 拦截 行为不变
- [ ] **代码瘦身**:`_render_risk_matrix_svg`、`_render_responsibility_matrix_svg` 删除(若 indicator_table POC 通过则该函数同删)

### 9.2 改造 2 POC 验收

- [ ] **T17 contract test 全部 pass**:6 类契约
- [ ] **100 对图对比报告**:flow 50 + gantt 50
- [ ] **量化指标采集完整**:T16 全部 5 项
- [ ] **盲评结论**:GPT-Vis-SSR vs mermaid 的相对胜率
- [ ] **决策落地**:启动后续 cutover 或关闭 GPT-Vis-SSR

### 9.3 整体回归

- [ ] 现有 15 种 chart_type 全部能渲染(未改的保持原行为,已改的通过新链路)
- [ ] 端到端导出一份覆盖全部图表类型的招标响应 DOCX
- [ ] PVE 资源消耗在估算范围内

## 10. 不在本次范围

- LLM 视觉自审(渲染后让视觉模型判断布局)— 主链路 DeepSeek V4 不变,需要时再引入轻量视觉模型
- PNG 转换路径优化(`png_converter.py` 改 vl-convert)— 改造 1 稳定后视情况推进
- MCP server 化(echarts-mcp/mcp-server-chart)— 会丢失现有护栏,不建议
- backend 生产化(gunicorn + nginx + concurrency 限制)— 独立工作项
- 前端图表交互(改造 3 全部内容)— 整体 DEFERRED
- response_matrix / interface_table / equipment_table 引擎替换 — **永久不转**(文档型表格)

## 11. 参考资料

- 设计哲学:[ChartGPT (arXiv 2311.01920)](https://arxiv.org/abs/2311.01920)
- Vega-Lite 画廊:<https://vega.github.io/vega-lite/examples/>
- 风险矩阵参考:<https://vega.github.io/vega-lite/examples/selection_heatmap.html>
- vl-convert:<https://github.com/vega/vl-convert>
- GPT-Vis:<https://gpt-vis.antv.vision/> / <https://github.com/antvis/GPT-Vis>
- AntV mcp-server-chart 私有部署说明:<https://github.com/antvis/mcp-server-chart>
- mermaid live editor:<https://mermaid.live/>
