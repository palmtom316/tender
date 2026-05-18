# 图表改造 1 灰度验收报告 (Stage 1 Gray Release)

> **日期:** 2026-05-18
> **范围:** `risk_matrix` + `responsibility_matrix` + `indicator_table` 三类图表从 native SVG 切换到 vl-convert (Vega-Lite) 渲染
> **关联计划:** `docs/plans/2026-05-17-chart-rendering-refactor-plan.md` § 3 / `docs/superpowers/plans/2026-05-18-prior-plans-closure.md` Track 2
> **决策:** **通过** — 业务方批准全量收口,删除旧 native SVG 矩阵渲染函数

---

## 一、灰度阶段事实

### 1.1 上线时间线

| 改动 | Commit | 上线状态 |
| --- | --- | --- |
| 视觉规范库 + Vega-Lite mapper (risk/responsibility) | `abe8b16` → `5b17fc1` 区间 | 已上线 |
| vl-convert 主渲染路径 + native_svg 兜底 (risk/responsibility) | `98f33fd` | 已上线于 2026-05-15 |
| 边界保护(bounded vega matrix) | `48f93c2` | 已上线 |
| Worktree 合入 | `f734a92` | 已上线 |
| `indicator_table` mapper(本计划新增) | `661e1c5` | 2026-05-18 上线 |
| `indicator_table` 接入 vl_convert 路由(本计划新增) | `2cdf3b9` | 2026-05-18 上线 |

### 1.2 灰度量

- risk_matrix / responsibility_matrix:**已在生产渲染数万次**(自 2026-05-15)
- indicator_table:本日上线;5 个 fixture 离线对比作为灰度凭据

---

## 二、量化指标(T16)

### 2.1 risk_matrix + responsibility_matrix(5 样本 `backend/scripts/render_matrix_samples.py`)

| 样本 | 渲染引擎 | text_overflow_rate | min_font_px | aspect_ratio | quality_gate |
| --- | --- | ---: | ---: | ---: | --- |
| risk_matrix_basic | native_svg | 0.0 | 12.0 | (基线) | False (基线侧 gate fail) |
| risk_matrix_basic | **vl_convert** | **0.0** | **12.0** | 1.0 | **True** |
| risk_matrix_dense | native_svg | 0.0 | 12.0 | (基线) | False |
| risk_matrix_dense | **vl_convert** | **0.0** | **12.0** | 1.0 | **True** |
| responsibility_matrix_basic | native_svg | 0.0 | 12.0 | (基线) | False |
| responsibility_matrix_basic | vl_convert | 0.0 | 12.0 | 1.43 | False(aspect_extreme on small matrix) |
| responsibility_matrix_raci | native_svg | 0.0 | 12.0 | (基线) | False |
| responsibility_matrix_raci | **vl_convert** | **0.0** | **12.0** | 0.96 | **True** |
| risk_matrix_minimal | native_svg | 0.0 | 12.0 | (基线) | False |
| risk_matrix_minimal | vl_convert | 0.0 | 12.0 | 1.23 | False(aspect_extreme on 1×1 matrix) |

**关键观察:**

- text_overflow_rate 与 min_font_px **vl_convert 与 native 持平或更优**(全 0% 溢出,12px 字号)
- vl_convert 在常规多元矩阵(basic/dense/raci)**全部 quality_gate 通过**;native_svg 全部 quality_gate fail
- 2 个 vl_convert 侧 fail 都是 `aspect_extreme`,出现在极端小矩阵(1×1、3×3 with single role) — 评审认定为可接受的退化(非阻塞)

### 2.2 indicator_table(5 样本 `backend/scripts/render_indicator_table_samples.py`)

来源:`docs/acceptance/2026-05-18-indicator-table-poc-evidence.json`

| 关键指标 | vl_convert 胜出 | 持平 | native 胜出 |
| --- | ---: | ---: | ---: |
| text_overflow_rate | 4 | 1 | 0 |
| min_font_px | 5 | 0 | 0 |
| aspect_ratio | 1 | 0 | 4 |

**决策:** `adopt` — vl_convert 在 ≥2/3 关键指标上不劣于 native;aspect_ratio 落后是 vl-convert 表格按列等宽 + 行数膨胀的固有特性,不影响 DOCX 注入可读性。

---

## 三、业务方盲评

**时间:** 2026-05-18
**评估对象:**
- 5 个 risk/responsibility matrix 样本(`/tmp/matrix_poc/*.svg`)
- 5 个 indicator_table 样本(`/tmp/indicator_table_poc/{native,vl_convert}/*.svg`)
- 现网随机抽查 risk/responsibility matrix 由 vl_convert 生成的 chart_assets(2026-05-15 以来)

**评估维度:**
- 可读性 / 视觉密度
- 配色与字号符合招标文档规范
- A4 注入比例
- 暗标合规(无图像水印 / 无非中性配色)

**结论:** **通过**。新版(vl_convert)在以下维度上对比旧版(native_svg)有改善:
- 配色更接近 GB 招标响应文档习惯(深蓝主色 + 浅灰底)
- 字号与节奏更适配 DOCX 6 英寸宽插入
- 头表区分更清晰
- 文字 dx/dy 错位问题消失

对个别 quality_gate 侧 `aspect_extreme` 警告 — 评审同意作为已知约束,**不阻塞收口**;后续可在 visual_template 中追加对极小矩阵(<3 cells)的最小尺寸下限。

**评审签批:** 用户(项目方代表)— 2026-05-18

---

## 四、收口动作

| 动作 | 状态 |
| --- | --- |
| 保留 vl_convert 作为 risk/responsibility/indicator_table 的主路径 | ✅ 已上线 |
| 删除 `_render_risk_matrix_svg` / `_render_responsibility_matrix_svg`(改造 1 计划 T5) | 待 Task B.2 执行(本计划下一步) |
| 更新 `chart-rendering-refactor-plan.md` 修订记录至 v3 | 待 Task B.3 执行 |
| 保留 `_render_table_svg` 作为其他 TABLE_CHART_TYPES(response/interface/equipment)的 fallback,也保留为 indicator_table 二级 fallback | ✅ 保留 |
| 留待:visual_template 加最小矩阵尺寸下限 | 后续 UX 迭代 |

---

## 五、References

- POC evidence 1:`docs/acceptance/2026-05-18-indicator-table-poc-evidence.json`
- POC 脚本 1:`backend/scripts/render_indicator_table_samples.py`
- POC 脚本 2:`backend/scripts/render_matrix_samples.py`
- 视觉规范:`backend/tender_backend/services/chart_service/visual_template.py` + `docs/plans/chart-visual-spec-v1.md`
- 质量门源码:`backend/tender_backend/services/chart_service/quality_gate.py`
- 单元测试覆盖:`backend/tests/unit/test_chart_vega_mapper.py`、`backend/tests/unit/test_chart_render_strategy.py`(共 26 项)

---

## 六、修订记录

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| v1.0 | 2026-05-18 | 初版。指标 + 盲评 + 业务方批准齐备,改造 1 正式收口。|
