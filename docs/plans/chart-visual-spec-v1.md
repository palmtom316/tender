# 招标图表视觉规范 v1

> 创建日期：2026-05-17
> 适用范围：tender 后端 chart_service 全部矩阵 / 表格 / 流程图渲染
> 单一事实源：`backend/tender_backend/services/chart_service/visual_template.py`

本规范沉淀招标响应文档对图表的视觉要求，配套 `visual_template.py` 提供常量。修改本文档时必须同步修改代码，反之亦然。

## 1. 配色（PALETTE）

| 用途 | 名称 | 色值 |
|---|---|---|
| 主色（标题/坐标轴/重点边框） | primary | `#1f4e79` |
| 主色暗调 | primary_dark | `#173e60` |
| 表面背景 | surface | `#ffffff` |
| 表面变体（表头/分组底色） | surface_alt | `#f1f5f9` |
| 边框 | border | `#8b98a8` |
| 主文字 | text | `#1f2933` |
| 辅助文字（注释/坐标标签） | text_muted | `#4c5661` |
| 风险等级 — low | risk_low | `#e7f5e8` |
| 风险等级 — medium | risk_medium | `#fff4ce` |
| 风险等级 — high | risk_high | `#ffe0cc` |
| 风险等级 — critical | risk_critical | `#ffd6d6` |
| 风险等级 — 未定义 | risk_default | `#ffffff` |

**红色 `risk_critical` 仅在风险等级 critical 出现，不作为装饰色**。

## 2. 字号阶梯（FONT）

| 元素 | 字号 | 用途 |
|---|---|---|
| title | 18px | 图表主标题 |
| subtitle | 14px | 副标题、坐标轴标题 |
| axis_label | 13px | 行/列轴标签 |
| cell_text | 12px | 矩阵 cell 内容、表格 cell |
| legend | 11px | 图例、注释 |
| min | 9px | 量化指标硬下限，低于此值视为不可读 |

字体族：`Noto Sans CJK SC, Microsoft YaHei, SimSun, sans-serif`。镜像必须含 `fonts-noto-cjk`。

## 3. A4 适配（PAGE）

| 参数 | 值 | 说明 |
|---|---|---|
| a4_portrait_width_pt | 595 | A4 纵向像素宽度参考 |
| a4_landscape_width_pt | 842 | A4 横向像素宽度参考 |
| matrix_max_aspect_ratio | 1.5 | viewBox 宽:高，超过判异常 |
| matrix_min_aspect_ratio | 0.6 | viewBox 宽:高，低于判异常 |
| docx_image_width_in | 6.0 | DOCX 注入目标宽度（英寸） |

**矩阵类图表（risk_matrix / responsibility_matrix）默认 a4_landscape**，比例区间 `[0.6, 1.5]`。

## 4. 量化验收指标（T16 → quality_gate）

| 指标 | 计算 | 阈值 |
|---|---|---|
| 文字溢出率 | `<text>` 字符超过模板 `node_chars/cell_chars/task_chars` 的比例 | < 2% |
| 最小字号 | 所有 `<text>` 的 `font-size` 最小值 | ≥ 9px |
| A4 比例 | viewBox `width / height` | `[0.6, 1.5]` |
| 渲染清晰度 | SVG → PNG（PyMuPDF）后 PNG 像素宽 / docx 注入宽（英寸） | ≥ 96 DPI |
| 字体可读性 | SVG 中字体族在 backend 镜像可用 | 100% |

quality_gate 输出向后兼容：保留 `passed/issues` 顶层字段，新增 `metrics` 子字段。

## 5. 下游消费方

- `chart_service/vega_mapper.py`（T2）— 注入到 Vega-Lite spec
- `chart_service/renderers.py`（T4）— 替换 risk_matrix / responsibility_matrix 后引用 PALETTE/FONT
- `chart_service/quality_gate.py`（T16）— 阈值来源
- `tests/unit/test_chart_visual_template.py` — 防止常量被静默篡改
