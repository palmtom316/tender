# Chapter 8 Followup Quality Roadmap (Trackable)

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development` 或 `superpowers:executing-plans`，按 checkbox 顺序推进。

**Context（背景）：** 2026-05-16/17 的 Phase A+B 修复（commit `73685f0`）已让第 8 章 `can_export=true` 并产出 78 页可投标 DOCX。但 `docs/acceptance/2026-05-15-longform-launch-closure.md` 仍有 4 项 P1/P2 遗留，且 `docs/superpowers/plans/2026-05-17-chart-generation-quality-upgrade.md` 提出了图表流水线升级方案。本文档承接两者，给出统一的可执行路线图。

**输入文档：**
- 接续 RCA：`docs/reports/2026-05-16-chapter-8-live-test-rca.md` § 11.4
- 接续修订计划：`docs/superpowers/plans/2026-05-16-chapter-8-quality-fix-plan.md`
- 待合并的图表方案：`docs/superpowers/plans/2026-05-17-chart-generation-quality-upgrade.md`
- 待合并的遗留项：`docs/acceptance/2026-05-15-longform-launch-closure.md` "后续遗留"段
- 5/11 整改方案（仍有效）：`docs/reviews/2026-05-11-配网技术标第8-10.3章提示词及图表整改方案.md`

**Goal:** 把第 8 章 DOCX 从"勉强能用"(78 页 + can_export=true) 升级到"达到原 acceptance hard rule"(90+ 页实际 + 评标专家盲评通过 + 0 视觉缺陷)，同时整合 chart pipeline 治理。

**Architecture:** 三个并行 track，依赖图见 § 五。Track A 紧扣 chart pipeline；Track B 攻 LLM 输出量；Track C 整顿质量评估口径。

**Tech Stack:** Python (pydantic / pytest), Mermaid sidecar, deepseek-v4-flash/pro, FastAPI, psycopg, LibreOffice + PyMuPDF.

---

## 零、对 chart-generation-quality-upgrade.md 的审核意见

整体方向正确（template + strategy + quality_gate），但有 5 处必须修订才能合入：

| # | 问题 | 修订要求 |
| --- | --- | --- |
| **R1** | Task 8 "Standardize Fallback" 与 73685f0 已落地的 `_render_fallback` 重复 | Task 8 改为"在 73685f0 基础上补 `stage` / `degradation_chain` metadata 字段"，**不要重建 fallback 逻辑**；测试只新增 metadata 字段断言 |
| **R2** | Task 1 `_TEMPLATES` 列了 15 种 chart_type，但 SUPPORTED_CHART_TYPES 当前只支持 9 种 | 拆为 Task 1A（先用 5/11 整改方案 REM-C-5 把 SUPPORTED_CHART_TYPES 扩展到 15）+ Task 1B（再定义 templates）。两者不能并行 |
| **R3** | Task 5 Gantt degradation 与 mermaid_sidecar 冲突路径不清 | 明确：mermaid_sidecar 成功时**跳过** native degradation；仅在 sidecar fail + native renderer 拒绝渲染 >20 个 task 时切到 summary table |
| **R4** | Task 7 quality gate 检查项过弱（仅查 `data-overflow='true'` / `font-size='10'`），renderer 不会主动写这些属性，gate 永远不触发 | 改为可执行检查：(a) text 单节点 length > template.text_rules.node_chars 时报 `text_overflow`；(b) SVG `viewBox` 宽高比 > 5 时报 `aspect_extreme`；(c) `<text>` 总数 > template.density_limits.max_nodes \* 2 时报 `density_overload` |
| **R5** | 缺失"prompt 收紧"任务的代码侧 enforcement | Task 10 之外新增 Task 11：在 `_request_ai_gateway_subsection_completion` rewrite_parts 中追加"chart_key 必须命中 recommended_charts 白名单"硬约束；服务侧 `build_chart_closure_report` 把 LLM 自创 chart_key（不在 recommended_charts 中）降级为 P1 警告而非 P0 |

此外，原 plan **缺以下 5 项**，已纳入下方 § 一/二/三：

- 没有覆盖编号体系一致性的持续保障（73685f0 已修，但需 regression 测试）
- 没有覆盖 chart_assets 与 longform 内容的逐节关闭检查
- 没有覆盖 estimated_pages 公式校准
- 没有 e2e 验收
- format_passed 自动校验

---

## 一、合并清单（来自 longform-launch-closure.md 后续遗留）

| 遗留项 | 优先级 | 归入 Track |
| --- | --- | --- |
| L1：续提升 LLM 输出量至 90+ 页 | P1 | Track B |
| L2：校准 estimated_pages 公式与实际 DOCX 排版偏离 | P2 | Track C |
| L3：沿用 REM-C-1/C-2 修复 fallback renderer 的 flow/gantt 拓扑 | P1 | Track A (覆盖 chart plan Task 4/5) |
| L4：format_passed 接入自动格式校验 | P2 | Track C |

---

## 二、整体路线图（按 Track 划分）

```
Track A (Chart Pipeline 升级)     ← 修订后的 chart-generation-quality-upgrade.md
Track B (LLM 输出量提升)          ← 接 L1
Track C (质量评估口径整顿)         ← 接 L2 / L4 + 编号回归 + 视觉抽检
Track D (回归 e2e)                ← 最终验收
```

每 track 内任务带 ID（`A-1`/`B-2`/`C-3`），可独立 PR。Track 间依赖见 § 五。

---

## 三、Track A — Chart Pipeline 升级

**Goal:** 让所有图表稳定通过 mermaid_sidecar 或 native renderer 输出可读 SVG/PNG，AI 只生成语义结构，质量门兜底视觉缺陷。

### A-1A：扩展 SUPPORTED_CHART_TYPES 到 15 种（REM-C-5）

**Files:**
- Modify: `backend/tender_backend/services/chart_service/specs.py`
- Modify: `backend/tender_backend/services/chart_service/renderers.py`
- Modify: `backend/tender_backend/services/chart_generation_service.py::default_chart_spec`
- Test: `backend/tests/unit/test_chart_spec_validation.py`、`backend/tests/unit/test_chart_rendering_and_injector.py`

**Steps:**
- [ ] 新增 spec class：`ResponseMatrixSpec`、`IndicatorTableSpec`、`InterfaceTableSpec`、`EquipmentTableSpec`、`ClosureFlowSpec`、`DataFlowSpec`、`CriticalPathSpec`（5/11 REM-C-5 批次 1+2+3）
- [ ] 表格类（response_matrix/indicator_table/interface_table/equipment_table）复用 `_render_responsibility_matrix_svg` 网格布局
- [ ] 流程类（closure_flow/data_flow）复用 flow renderer，允许 cycle
- [ ] critical_path 初版可复用 schedule_gantt + `is_critical` 高亮
- [ ] 每类至少 3 个单测（最小 spec / 完整 spec / 错误 spec）

**Acceptance:** SUPPORTED_CHART_TYPES 扩到 15；现有 9 种向下兼容。

### A-1B：Chart Template Definitions（来自原 plan Task 1）

**Files:**
- Create: `backend/tender_backend/services/chart_service/templates.py`
- Test: `backend/tests/unit/test_chart_templates.py`

**Steps:**
- [ ] `ChartTemplate` dataclass：`chart_type, layout_family, page_profile, density_limits, text_rules, degradation_policy`
- [ ] `_TEMPLATES` 覆盖全部 15 种
- [ ] `get_chart_template(chart_type)` lookup

**Acceptance:** 每个 SUPPORTED_CHART_TYPES 都能 lookup 出 template；template 字段非空。

**依赖：** A-1A 必须先完成。

### A-2：AI Chart Spec 语义化约束（修订原 Task 2）

**Files:**
- Modify: `backend/tender_backend/services/chart_generation_service.py::_normalize_flow_nodes / _prepare_payload`
- Modify: `backend/tender_backend/services/chart_service/specs.py`
- Modify: `backend/tender_backend/services/chart_generation_service.py::_chart_spec_system_prompt`
- Test: `backend/tests/unit/test_chart_spec_contracts.py`

**Steps:**
- [ ] `_normalize_flow_nodes` 显式过滤 `x / y / fill / stroke / fontSize / width / height` 等视觉字段，仅保留 `id / label / parent`
- [ ] `_chart_spec_system_prompt` 末尾追加："Never output coordinates, colors, dimensions, or SVG fragments. Only output semantic chart structure (ids, labels, parent/child, level, dates, columns, rows)."
- [ ] 新增 contract test：spec 含视觉字段时被 strip，AI prompt 中含禁止条款

**Acceptance:** AI 即便返回带视觉字段的 JSON，落地 spec_json 也是纯语义。

### A-3：Renderer Strategy Layer（原 Task 3）

**Files:**
- Create: `backend/tender_backend/services/chart_service/render_strategy.py`
- Modify: `backend/tender_backend/services/chart_service/renderers.py::render_chart_spec`
- Test: `backend/tests/unit/test_chart_render_strategy.py`

**Steps:**
- [ ] `RenderStrategy(chart_type, primary, fallback)` dataclass
- [ ] `_STRATEGIES` 覆盖 15 种：sidecar / native_svg / hybrid
- [ ] `render_chart_spec` 改为按 strategy 调度
- [ ] 测试 schedule_gantt → mermaid_sidecar → native_gantt fallback；risk_matrix → native_svg

**Acceptance:** Strategy registry 与 SUPPORTED_CHART_TYPES 一一对应；render_chart_spec 不再用 if-chain。

### A-4：Flow Layout 修复（REM-C-1）

**Files:**
- Create: `backend/tender_backend/services/chart_service/layout_flow.py`
- Modify: `backend/tender_backend/services/chart_service/renderers.py::_render_flow_svg, _flow_layout`
- Test: `backend/tests/unit/test_flow_layout_quality.py`

**Steps:**
- [ ] `compute_flow_layout(node_ids, edges)` 实现 BFS 分层 + 同层水平排列
- [ ] 替换 `_flow_layout` 内联实现
- [ ] 新增 3 类拓扑测试：线性 / 树 / 单源多汇 DAG → 断言节点位置非重叠 + edges 全可达

**Acceptance:** sidecar 关闭时第 8.3/8.5/8.6 体系图分层正确，不再竖线塌缩。

### A-5：Gantt 密度控制与降级（修订原 Task 5）

**Files:**
- Modify: `backend/tender_backend/services/chart_service/renderers.py::_render_gantt_svg`
- Test: `backend/tests/unit/test_gantt_degradation.py`

**Steps:**
- [ ] 渲染前查 `len(spec.tasks) > template.density_limits.max_tasks` (默认 20)，**且** sidecar fail 时，切到 `_render_gantt_summary_svg`
- [ ] `_render_gantt_summary_svg` 输出 group 汇总 table（不展开每个 task）
- [ ] 单测：25 task gantt，sidecar 关闭 → engine in {native_gantt_summary, mermaid_sidecar}
- [ ] 单测：sidecar 启用时正常渲染 25 task，不走 summary

**Acceptance:** 大型甘特图在 sidecar 不可用时不会渲染成不可读 SVG；sidecar 可用时保留全部 task。

### A-6：Matrix/Table 自适应布局（原 Task 6）

**Files:**
- Modify: `backend/tender_backend/services/chart_service/renderers.py::_render_table_svg, _render_responsibility_matrix_svg, _render_risk_matrix_svg`
- Test: `backend/tests/unit/test_matrix_table_adaptive_layout.py`

**Steps:**
- [ ] `_adaptive_cell_width(columns, min_width, max_width)` 按列文本长度自适应
- [ ] `_wrap(text, chars_per_line, max_lines)` 长文本截断 + 加 `…`
- [ ] 单测：长文本 cell 渲染含 `…` 或多行 `dy=`

**Acceptance:** indicator_table 含 30 字 cell 不再溢出。

### A-7：Visual Quality Gate（修订原 Task 7，R4 强化）

**Files:**
- Create: `backend/tender_backend/services/chart_service/quality_gate.py`
- Modify: `backend/tender_backend/services/chart_generation_service.py::create_or_update`
- Test: `backend/tests/unit/test_chart_quality_gate.py`

**Steps:**
- [ ] `evaluate_svg_quality(svg, template)` 检测：
  - `text_overflow`: 任意 `<text>` 节点内文本长度 > `template.text_rules.node_chars`
  - `aspect_extreme`: 解析 `viewBox`，宽高比 > 5 或 < 0.2
  - `density_overload`: `<text>` 节点总数 > `template.density_limits.max_nodes * 2`
  - `font_below_minimum`: `font-size` 属性值 < `template.text_rules.min_font_px`
- [ ] `create_or_update` 在 render 成功后跑 quality_gate；issues 写入 `metadata_json.quality_gate`；**不阻塞**写库（status 仍由其他分支决定），但作为 review_engine 阻塞条件之一
- [ ] 单测：构造极端 SVG → 报告 issues 列表非空

**Acceptance:** 视觉缺陷有 evidence trail；导出前可由 review_engine 拦截。

### A-8：Standardize Fallback Metadata（修订原 Task 8，R1 整改）

**Files:**
- Modify: `backend/tender_backend/services/chart_generation_service.py`
- Test: `backend/tests/unit/test_chart_fallback_pipeline.py`

**Steps:**
- [ ] 在 73685f0 的 `_render_fallback` 基础上：metadata_json.fallback_render 增加字段 `stage`（`validation_failed | provenance | blind_bid`）、`degradation_chain`（数组，记录尝试过的 renderer 序列）
- [ ] **不重建** fallback 逻辑（已在 73685f0 完成）
- [ ] 单测：fallback 触发后 metadata 包含 stage + degradation_chain

**Acceptance:** fallback 路径可追溯，前端可基于 stage 区分展示。

### A-9：Golden Chart Fixtures（原 Task 9）

**Files:**
- Create: `backend/tests/fixtures/chart_specs/*.json`
- Create: `backend/tests/unit/test_chart_snapshot_contracts.py`

**Steps:**
- [ ] 每个 chart family 1 个 fixture：construction_flow / schedule_gantt / risk_matrix / responsibility_matrix / indicator_table / critical_path / response_matrix / closure_flow / data_flow / equipment_table / interface_table / quality_system / safety_system / org_chart / emergency_org
- [ ] 单测：每个 fixture 渲染后 SVG 含 title 文本 + `<svg` 开头 + 关键节点 label

**Acceptance:** 后续 chart_service 重构可用 fixtures 做 regression。

### A-10：Prompt 文档对齐（原 Task 10）

**Files:**
- Modify: `docs/samples/配网施工方案及技术措施提示词.md`
- Modify: `docs/samples/配网工作规划描述提示词.md`
- Modify: `docs/samples/配网质量保证措施提示词.md`
- Modify: `docs/samples/配网安全与绿色施工保障措施提示词.md`
- Modify: `docs/samples/配网工程进度计划及保证措施提示词.md`

**Steps:**
- [ ] 在每份提示词的"图表能力"段，列出 15 种 SUPPORTED_CHART_TYPES
- [ ] 明确："未列入支持类型的图表，一律用 Markdown 表格表达"
- [ ] grep 验证：`rg "{{chart:" docs/samples/` 输出只含支持类型

**Acceptance:** LLM 不会被提示词诱导写不支持的 chart_key。

### A-11：服务侧 chart_key 白名单校验（R5）

**Files:**
- Modify: `backend/tender_backend/services/longform_quality.py::build_chart_closure_report`
- Modify: `backend/tender_backend/services/technical_bid_writer.py::_request_ai_gateway_subsection_completion`
- Test: `backend/tests/unit/test_longform_quality.py`

**Steps:**
- [ ] `_request_ai_gateway_subsection_completion` rewrite_parts 增加："chart_key 必须从 [list of recommended_charts] 中选；写不在列表中的 chart_key 占位符将被视为错误"
- [ ] `build_chart_closure_report`：referenced chart_key 不在传入的 `allowed_chart_keys`（新增参数）时，降级 issue severity 为 P1（不阻塞 export，但前端展示警告）
- [ ] `_save_chapter_draft` 调用 build_chart_closure_report 时传 `allowed_chart_keys=context['recommended_charts']`
- [ ] 单测：LLM 自创 chart_key → severity=P1 不阻塞

**Acceptance:** 73685f0 修复后类似 `framework_risk_matrix` 这种 LLM 幻想占位符不再阻塞 export。

---

## 四、Track B — LLM 输出量提升（攻 90+ 页目标）

**Goal:** 让 5 月 17 日的 78 页 DOCX 升到 ≥ 90 页实际，并保持质量评分稳定。

### B-1：长文本子节专用 prompt overlay

**Files:**
- Modify: `backend/tender_backend/services/technical_bid_writer.py::_request_ai_gateway_subsection_completion`
- Modify: `backend/tender_backend/services/technical_chapter_context.py::with_target_pages_override`
- Test: `backend/tests/unit/test_technical_bid_writer.py`

**Steps:**
- [ ] 在 LLM payload 中新增 `subsection_density_hint`：每节 expected_chars / expected_paragraphs / expected_subsections，按 `_SECTION_WEIGHTS` 派生
- [ ] rewrite_parts 增"展开 N 个独立子专题"硬指令（参考 weights 高的节展开更多）
- [ ] 单测：payload 含 expected_chars / expected_subsections

**Acceptance:** LLM 输出量在 v4-flash 上提升 ≥ 15%。

### B-2：v4-pro Tiered 续写（不全程，仅高权重节）

**Files:**
- Modify: `backend/tender_backend/services/longform_section_generation.py::LongformSectionGenerator`
- Modify: `ai_gateway/tender_ai_gateway/task_profiles.py`
- Test: `backend/tests/unit/test_longform_section_generation.py`

**Steps:**
- [ ] 新增 task_type `generate_longform_subsection_premium`：deepseek-v4-pro + max_thinking + timeout 1800s
- [ ] LongformSectionGenerator 增 `premium_threshold_chars` 参数（默认 2200）：当 round_index ≥ 2 且 weighted_chars < threshold 时切到 premium profile
- [ ] 单测：mock fake_completion 返回不同 task_type，断言切换

**Acceptance:** 8.4 / 8.5 / 8.6 这种高权重节实际输出 ≥ 2800 字符；总页数 ≥ 90。

### B-3：续写轮 max_rounds 上调 + 自适应

**Files:**
- Modify: `backend/tender_backend/services/longform_section_generation.py::LongformSectionGenerator`
- Test: `backend/tests/unit/test_longform_section_generation.py`

**Steps:**
- [ ] max_rounds 默认从 4 → 6
- [ ] 增"前轮无新内容时提前 break"逻辑：若 `_weighted_text_units(piece) < 100` 连续 2 轮，停止该节续写
- [ ] 单测：fake_completion 第 3-4 轮返回空 → 节状态 failed_min_chars 但不卡死

**Acceptance:** max_rounds 上调不导致死循环，且实际 LLM 输出量稳定提升。

### B-4：长文本评分用页数（不仅字数）

**Files:**
- Modify: `backend/tender_backend/services/longform_quality.py::estimate_markdown_pages`
- Test: `backend/tests/unit/test_longform_quality.py`

**Steps:**
- [ ] 校准公式系数：text_units/340 → text_units/420 (基于 5/17 实测：80745 units → 78 实际页 ≈ 1035 units/page；保守 420 留余量)
- [ ] heading 系数 0.08 → 0.05；chart 0.55 → 0.3；table_row 0.06 → 0.04
- [ ] 单测：weighted=42000 + 90 heading + 9 chart + 100 table_row → estimated ≈ 105 页

**Acceptance:** estimated_pages 与 actual_pages 偏差 ≤ 15%。

---

## 五、Track C — 质量评估口径整顿

### C-1：导出后 actual_pages 自动写回（接 L2 治理基础）

**Files:**
- Modify: `backend/tender_backend/api/exports.py::create_export`
- Test: `backend/tests/unit/test_export_api.py`

**Steps:**
- [ ] export 成功后从 `render_evidence.page_count` 取 actual_pages，update `chapter_draft.page_estimate_json` 加 `actual_pages / actual_status='counted'`
- [ ] 单测：mock count_docx_pages 返回 95 → DB 中 page_estimate_json.actual_pages == 95

**Acceptance:** 第一次 export 后下次 export gate 用真实页数评估。

### C-2：format_passed 接入自动校验（L4）

**Files:**
- Create: `backend/tender_backend/services/export_service/format_checker.py`
- Modify: `backend/tender_backend/services/export_gate_service.py::_format_gate_state`
- Test: `backend/tests/unit/test_format_checker.py`

**Steps:**
- [ ] `check_docx_format(docx_path)` 检查：(a) 字体（默认仿宋/黑体）、(b) 段落对齐、(c) 章节标题样式一致性、(d) 表格边框/字号
- [ ] `_format_gate_state` 不再硬编码 false：从最新 export_record.metadata_json.render_evidence.format_check 读
- [ ] export_record 创建时跑 format_checker 并写入 metadata
- [ ] 单测：构造一个不合格 docx → format_passed=False

**Acceptance:** format_passed 反映真实排版状态。

### C-3：编号体系一致性回归测试

**Files:**
- Test: `backend/tests/unit/test_longform_section_generation.py`

**Steps:**
- [ ] 新增 test：`plan_chapter_8_sections(target_pages=100)` 返回的 `(section_code, title)` 必须严格等于 `registry.CHAPTER_8_SECTIONS` 解析后的 `(code, title)`
- [ ] 如出现编号 drift 立刻 fail

**Acceptance:** 73685f0 修复的编号对齐被持久化保护。

### C-4：视觉抽检脚本

**Files:**
- Create: `scripts/visual_inspect_chapter_8.py`

**Steps:**
- [ ] 输入 chapter_draft.id，输出：
  - 每节字数 + min_chars 表
  - 每个 chart_asset 的 png 路径
  - residual chart placeholder list
  - DOCX 实际页数 + 章节级页数分布（用 LibreOffice 生成的 PDF 截各节首页 thumbnail）
- [ ] 落到 `outputs/visual-inspect/<draft_id>/`

**Acceptance:** 评标专家盲评前可一键 dump 评审材料。

---

## 六、Track D — 回归与最终验收

### D-1：综合 e2e（Track A/B/C 全部合入后）

**Files:**
- Modify: `scripts/run_chapter_8_acceptance.py`

**Steps:**
- [ ] 重跑 `d3ed99c0` 第 8 章 generate-async + export
- [ ] 验证：实际 ≥ 90 页 + coverage_passed + chart_closure_passed + charts_approved + format_passed + can_export
- [ ] 落 `docs/acceptance/2026-MM-DD-chapter-8-followup-final-evidence.json`

### D-2：评标专家盲评

- [ ] 3 个真实项目（含 1 个暗标）盲评
- [ ] 评分维度：篇幅完整度、专业表现力、图表可读性、暗标合规性
- [ ] 落 `docs/reviews/2026-MM-DD-followup-blind-review.md`

### D-3：5/11 整改方案 REM-* 状态回写

- [ ] 在 `docs/reviews/2026-05-11-...整改方案.md` 中把 REM-C-1/-2/-5 标记 "已整改于 2026-MM-DD"
- [ ] 移除已完成 task 的 P0/P1 编号

---

## 七、依赖图

```
A-1A (15 chart types) ─→ A-1B (templates)
A-1B ──┬─→ A-3 (strategy)
       ├─→ A-4 (flow layout)
       ├─→ A-5 (gantt degradation)
       ├─→ A-6 (matrix adaptive)
       └─→ A-7 (quality gate)

A-2 (semantic spec)  ── 独立 ──→ A-3 (strategy receives clean specs)
A-3 ──→ A-4/A-5 (各 renderer 由 strategy 调度)

A-8 (fallback metadata) ── 独立，建议最后做（在 A-1~A-7 之后）

A-11 (chart_key whitelist) ── 独立，可与 A-2 并行
A-10 (prompt docs) ──→ A-11 (服务侧白名单与 prompt 一致)

B-1 → B-2 → B-3 → B-4

C-1 → C-2 → C-3 → C-4

D-1 ←─ Track A 完成 + Track B 完成 + Track C 完成
D-2 ←─ D-1
D-3 ←─ D-2
```

---

## 八、Success Criteria（hard stop）

- [ ] Track A：15 种 chart_type 全部可渲染（mermaid_sidecar 或 native）；fallback metadata 完整；quality_gate 不产生新阻塞但报 issue
- [ ] Track B：第 8 章实际 DOCX 页数 ≥ 90；高权重节字数 ≥ 2500
- [ ] Track C：format_passed 反映真实排版；编号体系 regression test 全绿；视觉抽检脚本可用
- [ ] Track D：3 个项目盲评全过；acceptance evidence 归档

---

## 九、Risk Controls

- [ ] 任一 Task 引入 e2e regression（已有第 8 章 can_export 由 true 变 false）→ 立即回滚该 PR
- [ ] B-2 / B-3 启用 v4-pro 前确认 API quota；超限切回 flash + flag warning
- [ ] A-1A 扩展 chart_type 时，向下兼容：所有现有 9 种 chart 行为不变
- [ ] A-7 quality_gate 设计为"报告不阻塞"，避免误杀

---

## 十、Reporting Cadence

- [ ] 每完成 1 个 Track 内 task：勾选 + commit message 带 `[FOLLOWUP-X-N]`
- [ ] 每完成 1 个 Track：在本文件 `## 修订记录` 段追加完成日期与 commit hash
- [ ] Track D 完成：在 `docs/acceptance/2026-05-15-longform-launch-closure.md` 追加 "Phase 2 Final Decision" 段

---

## 修订记录

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| v1.0 | 2026-05-17 | 初版落盘。合并 chart-generation-quality-upgrade.md（含修订意见 R1~R5）+ longform-launch-closure.md 遗留项 L1~L4。|
