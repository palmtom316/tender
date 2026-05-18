# 配网技术标第 8/9/10 章质量统一路线图 (Trackable)

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development` 或 `superpowers:executing-plans`，按 checkbox 顺序推进。

**Context（背景）：** 2026-05-16/17 的 Phase A+B 修复（commit `73685f0`）已让第 8 章 `can_export=true` 并产出 78 页可投标 DOCX。但 `docs/acceptance/2026-05-15-longform-launch-closure.md` 仍有 4 项 P1/P2 遗留，且 `docs/superpowers/plans/2026-05-17-chart-generation-quality-upgrade.md` 提出了图表流水线升级方案。进一步代码审查发现：第 8 章走 `LongformSectionGenerator` 子节循环路径，而第 9 章、10.1/10.2/10.3 仍走单次 `generate_section`，质量和篇幅上限不一致。本文档承接上述问题，给出第 8/9/10 章统一质量路线图。

**输入文档：**
- 接续 RCA：`docs/reports/2026-05-16-chapter-8-live-test-rca.md` § 11.4
- 接续修订计划：`docs/superpowers/plans/2026-05-16-chapter-8-quality-fix-plan.md`
- 待合并的图表方案：`docs/superpowers/plans/2026-05-17-chart-generation-quality-upgrade.md`
- 待合并的遗留项：`docs/acceptance/2026-05-15-longform-launch-closure.md` "后续遗留"段
- 5/11 整改方案（仍有效）：`docs/reviews/2026-05-11-配网技术标第8-10.3章提示词及图表整改方案.md`

**Goal:** 把第 8 章 DOCX 从"勉强能用"(78 页 + can_export=true) 升级到"达到原 acceptance hard rule"(90+ 页实际 + 评标专家盲评通过 + 0 视觉缺陷)，并把 longform 子节生成路径泛化到第 9 章、10.1/10.2/10.3，最终形成约 200~250 页、质量口径一致的配网技术标正文生成能力。

**Architecture:** 五个 track，依赖图见 § 八。Track A 紧扣 chart pipeline；Track B 攻第 8 章 LLM 输出量；Track C 整顿质量评估口径；Track D 做回归验收；Track E 把 longform 路径泛化到第 9/10 章。

**Tech Stack:** Python (pydantic / pytest), Mermaid sidecar, deepseek-v4-flash/pro, FastAPI, psycopg, LibreOffice + PyMuPDF.

---

## 零、对 chart-generation-quality-upgrade.md 的审核意见

整体方向正确（template + strategy + quality_gate），但有 5 处必须修订才能合入：

| # | 问题 | 修订要求 |
| --- | --- | --- |
| **R1** | Task 8 "Standardize Fallback" 与 73685f0 已落地的 `_render_fallback` 重复 | Task 8 改为"在 73685f0 基础上补 `stage` / `degradation_chain` metadata 字段"，**不要重建 fallback 逻辑**；测试只新增 metadata 字段断言 |
| **R2** | 原审核意见认为 SUPPORTED_CHART_TYPES 当前只支持 9 种；复核代码后确认当前已支持 15 种 | A-1A 改为"审计 15 种现有支持并补齐 spec/render/default/test 覆盖"，**不要重复扩展 chart_type** |
| **R3** | Task 5 Gantt degradation 与 mermaid_sidecar 冲突路径不清 | 明确：mermaid_sidecar 成功时**跳过** native degradation；仅在 sidecar fail + native renderer 拒绝渲染 >20 个 task 时切到 summary table |
| **R4** | Task 7 quality gate 检查项过弱（仅查 `data-overflow='true'` / `font-size='10'`），renderer 不会主动写这些属性，gate 永远不触发 | 改为可执行检查：(a) text 单节点 length > template.text_rules.node_chars 时报 `text_overflow`；(b) SVG `viewBox` 宽高比 > 5 时报 `aspect_extreme`；(c) `<text>` 总数 > template.density_limits.max_nodes \* 2 时报 `density_overload` |
| **R5** | 缺失"prompt 收紧"任务的代码侧 enforcement | Task 10 之外新增 Task 11：先规范化 `recommended_charts + chart_assets` 为 allowed chart keys，再在 `_request_ai_gateway_subsection_completion` rewrite_parts 中追加白名单硬约束；服务侧 `build_chart_closure_report` 把 LLM 自创 chart_key（不在 allowed_chart_keys 中）降级为 P1 警告而非 P0 |

此外，原 plan **缺以下 5 项**，已纳入下方 § 一/二/三：

- 没有覆盖编号体系一致性的持续保障（73685f0 已修，但需 regression 测试）
- 没有覆盖 chart_assets 与 longform 内容的逐节关闭检查
- 没有覆盖 estimated_pages 公式校准
- 没有 e2e 验收
- format_passed 自动校验
- 没有覆盖 longform 路径从第 8 章泛化到第 9/10 章

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
Track E (Longform 泛化到 9/10 章) ← 统一生成路径
```

每 track 内任务带 ID（`A-1`/`B-2`/`C-3`），可独立 PR。Track 间依赖见 § 八。

---

## 三、Track A — Chart Pipeline 升级

**Goal:** 让所有图表稳定通过 mermaid_sidecar 或 native renderer 输出可读 SVG/PNG，AI 只生成语义结构，质量门兜底视觉缺陷。

### A-1A：审计 15 种 SUPPORTED_CHART_TYPES 覆盖（REM-C-5 收口）

**Files:**
- Modify: `backend/tender_backend/services/chart_service/specs.py`
- Modify: `backend/tender_backend/services/chart_service/renderers.py`
- Modify: `backend/tender_backend/services/chart_generation_service.py::default_chart_spec`
- Test: `backend/tests/unit/test_chart_spec_validation.py`、`backend/tests/unit/test_chart_rendering_and_injector.py`

**Steps:**
- [x] 复核 `SUPPORTED_CHART_TYPES` 当前 15 种：`org_chart / construction_flow / schedule_gantt / critical_path / responsibility_matrix / risk_matrix / quality_system / safety_system / emergency_org / response_matrix / indicator_table / interface_table / equipment_table / closure_flow / data_flow`
- [x] 保留现有 union 分类：`critical_path` 继续归入 `GanttChartSpec`；`closure_flow/data_flow` 继续归入 `FlowChartSpec`；`response_matrix/indicator_table/interface_table/equipment_table` 继续归入 `TableChartSpec`
- [x] 不新增独立 spec class，除非某类图确实需要不同字段模型
- [x] 表格类继续复用 `_render_table_svg` 或后续自适应 table renderer；责任矩阵继续走 `_render_responsibility_matrix_svg`
- [x] 流程类继续复用 flow renderer，允许 cycle 的行为由 renderer/layout 层处理，不放宽 schema 的 id/edge 引用校验
- [x] 每类至少 3 个单测（最小 spec / 完整 spec / 错误 spec），重点补当前覆盖缺口

**Acceptance:** 15 种已支持 chart_type 都有 spec/default/render/test 覆盖；现有行为向下兼容。

### A-1B：Chart Template Definitions（来自原 plan Task 1）

**Files:**
- Create: `backend/tender_backend/services/chart_service/templates.py`
- Test: `backend/tests/unit/test_chart_templates.py`

**Steps:**
- [x] `ChartTemplate` dataclass：`chart_type, layout_family, page_profile, density_limits, text_rules, degradation_policy`
- [x] `_TEMPLATES` 覆盖全部 15 种
- [x] `get_chart_template(chart_type)` lookup

**Acceptance:** 每个 SUPPORTED_CHART_TYPES 都能 lookup 出 template；template 字段非空。

**依赖：** A-1A 必须先完成。

### A-2：AI Chart Spec 语义化约束（修订原 Task 2）

**Files:**
- Modify: `backend/tender_backend/services/chart_generation_service.py::_normalize_flow_nodes / _prepare_payload`
- Modify: `backend/tender_backend/services/chart_service/specs.py`
- Modify: `backend/tender_backend/services/chart_generation_service.py::_chart_spec_system_prompt`
- Test: `backend/tests/unit/test_chart_spec_contracts.py`

**Steps:**
- [x] `_normalize_flow_nodes` 显式过滤 `x / y / fill / stroke / fontSize / width / height` 等视觉字段，仅保留 `id / label / parent`
- [x] `_chart_spec_system_prompt` 末尾追加："Never output coordinates, colors, dimensions, or SVG fragments. Only output semantic chart structure (ids, labels, parent/child, level, dates, columns, rows)."
- [x] 新增 contract test：spec 含视觉字段时被 strip，AI prompt 中含禁止条款

**Acceptance:** AI 即便返回带视觉字段的 JSON，落地 spec_json 也是纯语义。

### A-3：Renderer Strategy Layer（原 Task 3）

**Files:**
- Create: `backend/tender_backend/services/chart_service/render_strategy.py`
- Modify: `backend/tender_backend/services/chart_service/renderers.py::render_chart_spec`
- Test: `backend/tests/unit/test_chart_render_strategy.py`

**Steps:**
- [x] `RenderStrategy(chart_type, primary, fallback)` dataclass
- [x] `_STRATEGIES` 覆盖 15 种：sidecar / native_svg / hybrid
- [x] `render_chart_spec` 改为按 strategy 调度
- [x] 测试 schedule_gantt → mermaid_sidecar → native_gantt fallback；risk_matrix → native_svg

**Acceptance:** Strategy registry 与 SUPPORTED_CHART_TYPES 一一对应；render_chart_spec 不再用 if-chain。

### A-4：Flow Layout 修复（REM-C-1）

**Files:**
- Create: `backend/tender_backend/services/chart_service/layout_flow.py`
- Modify: `backend/tender_backend/services/chart_service/renderers.py::_render_flow_svg, _flow_layout`
- Test: `backend/tests/unit/test_flow_layout_quality.py`

**Steps:**
- [x] `compute_flow_layout(node_ids, edges)` 实现 BFS 分层 + 同层水平排列
- [x] 替换 `_flow_layout` 内联实现
- [x] 新增 3 类拓扑测试：线性 / 树 / 单源多汇 DAG → 断言节点位置非重叠 + edges 全可达

**Acceptance:** sidecar 关闭时第 8.3/8.5/8.6 体系图分层正确，不再竖线塌缩。

### A-5：Gantt 密度控制与降级（修订原 Task 5）

**Files:**
- Modify: `backend/tender_backend/services/chart_service/renderers.py::_render_gantt_svg`
- Test: `backend/tests/unit/test_gantt_degradation.py`

**Steps:**
- [x] 渲染前查 `len(spec.tasks) > template.density_limits.max_tasks` (默认 20)，**且** sidecar fail 时，切到 `_render_gantt_summary_svg`
- [x] `_render_gantt_summary_svg` 输出 group 汇总 table（不展开每个 task）
- [x] 单测：25 task gantt，sidecar 关闭 → engine in {native_gantt_summary, mermaid_sidecar}
- [x] 单测：sidecar 启用时正常渲染 25 task，不走 summary

**Acceptance:** 大型甘特图在 sidecar 不可用时不会渲染成不可读 SVG；sidecar 可用时保留全部 task。

### A-6：Matrix/Table 自适应布局（原 Task 6）

**Files:**
- Modify: `backend/tender_backend/services/chart_service/renderers.py::_render_table_svg, _render_responsibility_matrix_svg, _render_risk_matrix_svg`
- Test: `backend/tests/unit/test_matrix_table_adaptive_layout.py`

**Steps:**
- [x] `_adaptive_cell_width(columns, min_width, max_width)` 按列文本长度自适应
- [x] `_wrap(text, chars_per_line, max_lines)` 长文本截断 + 加 `…`
- [x] 单测：长文本 cell 渲染含 `…` 或多行 `dy=`

**Acceptance:** indicator_table 含 30 字 cell 不再溢出。

### A-7：Visual Quality Gate（修订原 Task 7，R4 强化）

**Files:**
- Create: `backend/tender_backend/services/chart_service/quality_gate.py`
- Modify: `backend/tender_backend/services/chart_generation_service.py::create_or_update`
- Test: `backend/tests/unit/test_chart_quality_gate.py`

**Steps:**
- [x] `evaluate_svg_quality(svg, template)` 检测：
  - `text_overflow`: 任意 `<text>` 节点内文本长度 > `template.text_rules.node_chars`
  - `aspect_extreme`: 解析 `viewBox`，宽高比 > 5 或 < 0.2
  - `density_overload`: `<text>` 节点总数 > `template.density_limits.max_nodes * 2`
  - `font_below_minimum`: `font-size` 属性值 < `template.text_rules.min_font_px`
- [x] `create_or_update` 在 render 成功后跑 quality_gate；issues 写入 `metadata_json.quality_gate`
- [x] v1 阶段 quality_gate **只记录不阻塞**：不改变 chart asset status，不接入 review_engine，不改变 export gate
- [x] 后续如要阻塞，另开 v2 task 接入 review_engine/export_gate，并先定义误杀豁免规则
- [x] 单测：构造极端 SVG → 报告 issues 列表非空

**Acceptance:** 视觉缺陷有 evidence trail；不改变当前 can_export 判定。

### A-8：Standardize Fallback Metadata（修订原 Task 8，R1 整改）

**Files:**
- Modify: `backend/tender_backend/services/chart_generation_service.py`
- Test: `backend/tests/unit/test_chart_fallback_pipeline.py`

**Steps:**
- [x] 在 73685f0 的 `_render_fallback` 基础上：metadata_json.fallback_render 增加字段 `stage`（`validation_failed | provenance | blind_bid`）、`degradation_chain`（数组，记录尝试过的 renderer 序列）
- [x] **不重建** fallback 逻辑（已在 73685f0 完成）
- [x] 单测：fallback 触发后 metadata 包含 stage + degradation_chain

**Acceptance:** fallback 路径可追溯，前端可基于 stage 区分展示。

### A-9：Golden Chart Fixtures（原 Task 9）

**Files:**
- Create: `backend/tests/fixtures/chart_specs/*.json`
- Create: `backend/tests/unit/test_chart_snapshot_contracts.py`

**Steps:**
- [x] 每个 chart family 1 个 fixture：construction_flow / schedule_gantt / risk_matrix / responsibility_matrix / indicator_table / critical_path / response_matrix / closure_flow / data_flow / equipment_table / interface_table / quality_system / safety_system / org_chart / emergency_org
- [x] 单测：每个 fixture 渲染后 SVG 含 title 文本 + `<svg` 开头 + 关键节点 label

**Acceptance:** 后续 chart_service 重构可用 fixtures 做 regression。

### A-10：Prompt 文档对齐（原 Task 10）

**Files:**
- Modify: `docs/samples/配网施工方案及技术措施提示词.md`
- Modify: `docs/samples/配网工作规划描述提示词.md`
- Modify: `docs/samples/配网质量保证措施提示词.md`
- Modify: `docs/samples/配网安全与绿色施工保障措施提示词.md`
- Modify: `docs/samples/配网工程进度计划及保证措施提示词.md`

**Steps:**
- [x] 在每份提示词的"图表能力"段，列出 15 种 SUPPORTED_CHART_TYPES
- [x] 明确："未列入支持类型的图表，一律用 Markdown 表格表达"
- [x] grep 验证：`rg "{{chart:" docs/samples/` 输出只含支持类型

**Acceptance:** LLM 不会被提示词诱导写不支持的 chart_key。

### A-11：服务侧 chart_key 白名单校验（R5）

**Files:**
- Modify: `backend/tender_backend/services/longform_quality.py::build_chart_closure_report`
- Modify: `backend/tender_backend/services/technical_bid_writer.py::_request_ai_gateway_subsection_completion`
- Test: `backend/tests/unit/test_longform_quality.py`

**Steps:**
- [x] 新增 `normalize_allowed_chart_keys(recommended_charts, chart_assets)`：同时收集 `placeholder_key` 和 `chart_type`，兼容 dict/object/string 三种输入
- [x] `_request_ai_gateway_subsection_completion` rewrite_parts 增加："chart_key 必须从 [allowed_chart_keys] 中选；写不在列表中的 chart_key 占位符将被视为错误"
- [x] `build_chart_closure_report`：referenced chart_key 不在传入的 `allowed_chart_keys`（新增参数）时，降级 issue severity 为 P1（不阻塞 export，但前端展示警告）
- [x] `_save_chapter_draft` 调用 build_chart_closure_report 时传 `allowed_chart_keys=normalize_allowed_chart_keys(context.get('recommended_charts'), context.get('chart_assets'))`
- [x] 单测：LLM 自创 chart_key → severity=P1 不阻塞

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
- [x] 在 LLM payload 中新增 `subsection_density_hint`：每节 expected_chars / expected_paragraphs / expected_subsections，按 `_SECTION_WEIGHTS` 派生
- [x] rewrite_parts 增"展开 N 个独立子专题"硬指令（参考 weights 高的节展开更多）
- [x] 单测：payload 含 expected_chars / expected_subsections

**Acceptance:** LLM 输出量在 v4-flash 上提升 ≥ 15%。

### B-2：v4-pro Tiered 续写（不全程，仅高权重节）

**Files:**
- Modify: `backend/tender_backend/services/longform_section_generation.py::LongformSectionGenerator`
- Modify: `ai_gateway/tender_ai_gateway/task_profiles.py`
- Test: `backend/tests/unit/test_longform_section_generation.py`

**Steps:**
- [x] 新增 task_type `generate_longform_subsection_premium`：deepseek-v4-pro + max_thinking + timeout 1800s
- [x] LongformSectionGenerator 增 `premium_threshold_chars` 参数（默认 2200）：当 round_index ≥ 2 且 weighted_chars < threshold 时切到 premium profile
- [x] 单测：mock fake_completion 返回不同 task_type，断言切换

**Acceptance:** 8.4 / 8.5 / 8.6 这种高权重节实际输出 ≥ 2800 字符；总页数 ≥ 90。

### B-3：续写轮 max_rounds 上调 + 自适应

**Files:**
- Modify: `backend/tender_backend/services/longform_section_generation.py::LongformSectionGenerator`
- Test: `backend/tests/unit/test_longform_section_generation.py`

**Steps:**
- [x] max_rounds 默认从 4 → 6
- [x] 增"前轮无新内容时提前 break"逻辑：若 `_weighted_text_units(piece) < 100` 连续 2 轮，停止该节续写
- [x] 单测：fake_completion 第 3-4 轮返回空 → 节状态 failed_min_chars 但不卡死

**Acceptance:** max_rounds 上调不导致死循环，且实际 LLM 输出量稳定提升。

### B-4：长文本评分用页数（不仅字数）

**Files:**
- Modify: `backend/tender_backend/services/longform_quality.py::estimate_markdown_pages`
- Test: `backend/tests/unit/test_longform_quality.py`

**Steps:**
- [x] 明确目标：`estimated_pages` 用于 export gate 的保守门禁，不等同于 DOCX 实际页数；实际页数以 C-1 写回的 `actual_pages` 为准
- [x] 校准公式拆为两套字段：`estimated_pages_gate`（保守）与 `estimated_pages_actual_like`（贴近实际）
- [x] `estimated_pages_actual_like` 以 5/17 实测为基线：80745 weighted units / 78 actual pages ≈ 1035 units/page，初始使用 `text_units / 1000 + structure_adjustment`
- [x] `estimated_pages_gate` 可继续偏保守，但必须在 method/evidence 中明确 `gate_estimate_not_actual`
- [x] 单测：weighted=80745 且结构项接近 5/17 样本时，`estimated_pages_actual_like` 在 70~90 区间

**Acceptance:** estimated_pages 与 actual_pages 偏差 ≤ 15%。

---

## 五、Track C — 质量评估口径整顿

### C-1：导出后 actual_pages 自动写回（接 L2 治理基础）

**Files:**
- Modify: `backend/tender_backend/api/exports.py::create_export`
- Test: `backend/tests/unit/test_export_api.py`

**Steps:**
- [x] export 成功后从 `render_evidence.page_count` 取 actual_pages，update `chapter_draft.page_estimate_json` 加 `actual_pages / actual_status='counted'`
- [x] 单测：mock count_docx_pages 返回 95 → DB 中 page_estimate_json.actual_pages == 95

**Acceptance:** 第一次 export 后下次 export gate 用真实页数评估。

### C-2：format_passed 接入自动校验（L4）

**Files:**
- Create: `backend/tender_backend/services/export_service/format_checker.py`
- Modify: `backend/tender_backend/services/export_gate_service.py::_format_gate_state`
- Test: `backend/tests/unit/test_format_checker.py`

**Steps:**
- [x] `check_docx_format(docx_path)` 检查：(a) 字体（默认仿宋/黑体）、(b) 段落对齐、(c) 章节标题样式一致性、(d) 表格边框/字号
- [x] `_format_gate_state()` 改为 `_format_gate_state(conn, *, project_id)`：从最新 export_record.metadata_json.render_evidence.format_check 读
- [x] `build_export_gate_state` 调用点同步传入 `conn/project_id`
- [x] export_record 创建时跑 format_checker 并写入 metadata
- [x] 单测：构造一个不合格 docx → format_passed=False

**Acceptance:** format_passed 反映真实排版状态。

### C-3：编号体系一致性回归测试

**Files:**
- Test: `backend/tests/unit/test_longform_section_generation.py`

**Steps:**
- [x] 新增 test：`plan_chapter_8_sections(target_pages=100)` 返回的 `(section_code, title)` 必须严格等于 `registry.CHAPTER_8_SECTIONS` 解析后的 `(code, title)`
- [x] 如出现编号 drift 立刻 fail

**Acceptance:** 73685f0 修复的编号对齐被持久化保护。

### C-4：视觉抽检脚本

**Files:**
- Create: `scripts/visual_inspect_chapter_8.py`

**Steps:**
- [x] 输入 chapter_draft.id，输出：
  - 每节字数 + min_chars 表
  - 每个 chart_asset 的 png 路径
  - residual chart placeholder list
  - DOCX 实际页数 + 章节级页数分布（缩略图生成暂缓到最终 e2e 阶段）
- [x] 落到 `outputs/visual-inspect/<draft_id>/`

**Acceptance:** 评标专家盲评前可一键 dump 评审材料。

---

## 六、Track D — 回归与最终验收

### D-1：综合 e2e（Track A/B/C 全部合入后）

> **Status:** 暂缓。按 2026-05-17 执行决策，真实项目生成、导出、页数统计类 e2e 在全部改造完成后统一执行，避免反复消耗长耗时测试。

**Files:**
- Modify: `scripts/run_chapter_8_acceptance.py`

**Steps:**
- [ ] 重跑 `d3ed99c0` 第 8 章 generate-async + export
- [ ] 验证：实际 ≥ 90 页 + coverage_passed + chart_closure_passed + charts_approved + format_passed + can_export
- [ ] 落 `docs/acceptance/2026-MM-DD-chapter-8-followup-final-evidence.json`

### D-2：评标专家盲评

> **Status:** 暂缓。待最终 e2e 样本统一产出后再组织人工盲评。

- [ ] 3 个真实项目（含 1 个暗标）盲评
- [ ] 评分维度：篇幅完整度、专业表现力、图表可读性、暗标合规性
- [ ] 落 `docs/reviews/2026-MM-DD-followup-blind-review.md`

### D-3：5/11 整改方案 REM-* 状态回写

- [x] 在 `docs/reviews/2026-05-11-...整改方案.md` 中把 REM-C-1/-2/-5 标记 "已整改于 2026-MM-DD"
- [x] 移除已完成 task 的 P0/P1 编号

---

## 七、Track E — Longform 路径泛化到第 9/10 章

**Goal:** 消除第 8 章与第 9/10 章生成路径不一致的问题，把 `LongformSectionGenerator` 子节循环、min_chars 续写、coverage/chart_closure gate 泛化到第 9 章和 10.1/10.2/10.3。

**代码事实：**
- 第 8 章当前路径：`LongformSectionGenerator` 子节循环 + min_chars 续写 + coverage/chart_closure gate；实测 v4-flash x 4 轮约 78 页。
- 第 9 章当前路径：单次 `_request_ai_gateway_completion(generate_section)`，`max_tokens=16384`，通常约 20~30 页。
- 第 10.1/10.2/10.3 当前路径：同第 9 章，通常约 20~30 页。
- 入口条件硬编码：`_should_use_longform_generation(chapter, target_pages)` 仅允许 `chapter_code == "8"` 且 `target_pages >= 80`。
- `plan_chapter_8_sections` 内部 `_CHAPTER_8_TITLES / _SECTION_WEIGHTS / _DEFAULT_CHARTS / _DEFAULT_TABLES` 都是 8.x 硬编码；registry 虽有第 9/10 章 sections 定义，但没有通用 `plan_chapter_sections`。

### E-1：Longform 入口从硬编码改为 registry 配置

**Files:**
- Modify: `backend/tender_backend/services/technical_bid_writer.py::_should_use_longform_generation`
- Modify: 章节 registry 所在文件（以现有 `CHAPTER_8_SECTIONS` 定义位置为准）
- Test: `backend/tests/unit/test_technical_bid_writer.py`

**Steps:**
- [x] 在 registry 增加 longform 配置表：`LONGFORM_CHAPTER_CONFIG[chapter_code] = {enabled, min_target_pages, section_set_key}`
- [x] 覆盖 `"8" / "9" / "10.1" / "10.2" / "10.3"`
- [x] `_should_use_longform_generation` 改为按 chapter_code 查询配置，不再硬编码 `"8"`
- [x] 单测：8 target_pages=80 返回 true；9 target_pages=30 返回 true；10.1 target_pages=35 返回 true；未配置章节返回 false

**Acceptance:** 第 9/10 章在达到配置 target_pages 时进入 longform 路径。

**Effort:** 0.3 人日

### E-2：`plan_chapter_8_sections` 泛化为 `plan_chapter_sections`

**Files:**
- Modify: `backend/tender_backend/services/longform_section_generation.py`
- Test: `backend/tests/unit/test_longform_section_generation.py`

**Steps:**
- [x] 新增 `plan_chapter_sections(chapter_code, target_pages)`，从 registry 动态读取对应 sections 元组
- [x] 保留 `plan_chapter_8_sections(target_pages)` 作为兼容 wrapper，内部调用 `plan_chapter_sections("8", target_pages)`
- [x] 将 `_CHAPTER_8_TITLES` 等 8.x 私有常量迁移到 registry 配置，或改为从 registry 派生
- [x] 单测：第 8 章输出与旧函数保持一致；第 9 章输出 8 个 section；10.1/10.2/10.3 输出对应三级编号 section

**Acceptance:** section 规划函数不再绑定第 8 章，且不破坏现有第 8 章行为。

**Effort:** 1.5 人日

### E-3：按章配置权重、默认图表、默认表格

**Files:**
- Modify: registry 所在文件
- Modify: `backend/tender_backend/services/longform_section_generation.py`
- Test: `backend/tests/unit/test_longform_section_generation.py`

**Steps:**
- [x] 新增 `SECTION_WEIGHTS[chapter_code]`
- [x] 新增 `DEFAULT_CHARTS[chapter_code]`
- [x] 新增 `DEFAULT_TABLES[chapter_code]`
- [x] 覆盖五套：`8 / 9 / 10.1 / 10.2 / 10.3`
- [x] 第 9 章推荐 target_pages: 30~40；10.1/10.2/10.3 推荐 target_pages: 35~50
- [x] 单测：每章 section weights 总和可归一化；default charts 都命中 SUPPORTED_CHART_TYPES；default tables 不为空

**Acceptance:** 各章可按自己的权重、图表、表格要求生成 longform subsection payload。

**Effort:** 1.5 人日

### E-4：三级编号体系回归

**Files:**
- Modify/Test: `backend/tests/unit/test_longform_section_generation.py`
- Modify: 如存在 `_present_section_codes` 正则定义的文件

**Steps:**
- [x] 扩展 `_present_section_codes` 正则，确认支持 `10.1.1`、`10.2.16`、`10.3.15` 这类三级编号
- [x] 新增编号对齐测试：`8 / 9 / 10.1 / 10.2 / 10.3` 五套 planned sections 必须严格等于 registry 定义
- [x] 新增 markdown 提取测试：正文含三级标题时能正确识别 present section codes

**Acceptance:** 第 10.x 节不会因为三级编号识别失败而误判 coverage 缺失。

**Effort:** 1.0 人日

### E-5：四章 longform e2e 与 evidence 归档

**Files:**
- Modify/Create: `scripts/run_longform_multi_chapter_acceptance.py`
- Create: `docs/acceptance/2026-MM-DD-longform-8-9-10-evidence.json`

**Steps:**
- [ ] 对同一项目依次生成第 8、9、10.1、10.2、10.3 章
- [ ] 验证各章 target_pages、actual_pages、coverage_passed、chart_closure_passed
- [ ] 验证第 9 章实际页数 30~40，第 10.1/10.2/10.3 实际页数 35~50，第 8 章实际页数 ≥ 90
- [ ] evidence 归档每章：section_count、generation_rounds、actual_pages、coverage issues、chart closure issues、model usage

**Acceptance:** 四章统一进入 longform 质量路径，合计约 200~250 页技术标正文。

**Effort:** 1.0 人日

**Track E Effort:** 约 5.3 人日

**质量预期：**

| 章 | 节数 | 推荐 target_pages | 预期单节字数 | 质量预期 |
| --- | ---: | ---: | ---: | --- |
| 第 8 章 | 15 | 100 | 1500~2300 | 基准，目标 ≥90 实际页 |
| 第 9 章 | 8 | 30~40 | 1800~2500 | 大概率优于第 8 章，节数少、业务边界清晰 |
| 10.1 | 15 | 35~50 | 1500~2300 | 大概率持平，需控制三级编号 |
| 10.2 | 16 | 35~50 | 1500~2300 | 持平或略低，暗标脱敏和安全体系复杂度更高 |
| 10.3 | 15 | 35~50 | 1500~2300 | 持平，甘特图质量依赖 Track A |

---

## 八、依赖图

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

E-1 → E-2 → E-3 → E-4 → E-5
E-3 ──→ A-10/A-11（各章 recommended charts 与 chart_key 白名单一致）
Track A ──→ E-5（多章 e2e 依赖图表稳定）
Track C ──→ E-5（多章 e2e 依赖真实页数与格式口径）

D-1 ←─ Track A 完成 + Track B 完成 + Track C 完成
D-1 可与 E-5 合并为最终多章 acceptance
D-2 ←─ D-1/E-5
D-3 ←─ D-2
```

---

## 九、Success Criteria（hard stop）

- [ ] Track A：15 种 chart_type 全部可渲染（mermaid_sidecar 或 native）；fallback metadata 完整；quality_gate 不产生新阻塞但报 issue
- [ ] Track B：第 8 章实际 DOCX 页数 ≥ 90；高权重节字数 ≥ 2500
- [ ] Track C：format_passed 反映真实排版；编号体系 regression test 全绿；视觉抽检脚本可用
- [ ] Track D：3 个项目盲评全过；acceptance evidence 归档
- [ ] Track E：第 9 章、10.1、10.2、10.3 统一进入 longform 路径；四章合计约 200~250 页；各章 coverage/chart_closure gate 通过

---

## 十、Risk Controls

- [ ] 任一 Task 引入 e2e regression（已有第 8 章 can_export 由 true 变 false）→ 立即回滚该 PR
- [ ] B-2 / B-3 启用 v4-pro 前确认 API quota；超限切回 flash + flag warning
- [ ] A-1A 审计 15 种 chart_type 时，向下兼容：所有现有 chart 行为不变
- [ ] A-7 quality_gate 设计为"报告不阻塞"，避免误杀
- [ ] Track E 泛化入口时默认只对已配置章节启用，避免普通章节误入 longform 导致成本失控
- [ ] 第 10.x 三级编号必须先通过 E-4 regression，再进入 E-5 e2e

---

## 十一、Reporting Cadence

- [ ] 每完成 1 个 Track 内 task：勾选 + commit message 带 `[FOLLOWUP-X-N]`
- [ ] 每完成 1 个 Track：在本文件 `## 修订记录` 段追加完成日期与 commit hash
- [ ] Track D 完成：在 `docs/acceptance/2026-05-15-longform-launch-closure.md` 追加 "Phase 2 Final Decision" 段

---

## 修订记录

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| v1.0 | 2026-05-17 | 初版落盘。合并 chart-generation-quality-upgrade.md（含修订意见 R1~R5）+ longform-launch-closure.md 遗留项 L1~L4。|
| v1.1 | 2026-05-17 | 修订 R2/A-1A、A-7、A-11、B-4、C-2；追加 Track E，将 longform 路径泛化到第 9 章和 10.1/10.2/10.3；标题与目标升级为第 8/9/10 章统一质量路线图。 |
| v1.2 | 2026-05-17 | 完成 Track C 快速改造与 D-3 文档回写；D-1/D-2 按执行决策暂缓到全量改造完成后统一 e2e/盲评。 |
| v1.3 | 2026-05-18 | Track A/B/E1-E4 全部代码落地，文档 checkbox 同步。E-5 evidence 与 D-1/D-2 仍按"暂缓"决策，待 `2026-05-18-prior-plans-closure.md` Track 4 联动产出。 |
