# GB 50148-2010 解析质量提升方案

**日期：** 2026-03-31（初版） · 2026-03-31（更新：对齐最新代码状态）

**目标文档：** `GB 50148-2010`

---

## 当前状态总结

经过多轮迭代，GB 50148-2010 的解析质量已从"不可用"提升到"验收通过"：

| 指标 | 2026-03-24 基线 | 最新重跑（验收清单 Section 9） |
|------|-----------------|-------------------------------|
| 总条款 | 140 | **400** |
| normative | 12 | **361** |
| commentary | 128 | **39** |
| 缺失页锚点 | 63 | **0** |
| validation warnings | 78 | 大幅减少 |
| 关键条款号 | 部分缺失 | **全部存在** |

**残留问题：** commentary 数量（39）低于目标形态（49+），部分 commentary 条款可能被遗漏。

---

## 已完成项

### ~~1.1 修复 commentary 边界检测~~ ✓

`structural_nodes.py` 已改为行级匹配 + 三种变体（`附：条文说明`、`附:条文说明`、`条文说明`）+ back-matter 过滤（`本规范用词说明`、`引用标准名录`）。不再被目录残留或交叉引用中的"条文说明"误触发。

### ~~1.2 Clause type 分类~~ ✓

`block_segments.py` 实现完整分类状态机：normative → commentary → appendix → table → heading_only → non_clause。`norm_processor.py` 中基于 `block.segment_type` 正确设置 `clause_type`。

### ~~1.3 页码精确传递~~ ✓

`_apply_scope_defaults()` 递归回填 page_start/page_end，block 级别 carry 页码信息。实际重跑 `incomplete_page_anchor = 0`。

### ~~2.1 确定性条款边界预检测~~ ✓

`block_segments.py`（272行）完整实现 `build_single_standard_blocks()`，正则识别条款编号、列表项折叠、置信度评分。已集成到 `norm_processor.py`，对简短 normative 块和所有 table 块做确定性提取，绕过 LLM。当前通过实验标志仅对 GB50148 启用。

### ~~2.3 页码推断补全~~ ✓

block 级别 carry page_start/page_end + scope defaults 递归回填。实际重跑 0 缺失。

### ~~2.4 验收测试套件~~ ✓

`test_gb50148_acceptance.py` + `test_gb50148_persisted_acceptance.py` 覆盖 scaffold 和 persisted 场景，断言条款数 ≥ 370、关键编号存在、normative/commentary 均存在、table 来源存在。

---

## 未完成项

### 1.4 LLM temperature 降至 0.0

- **状态：** 未做
- **位置：** `norm_processor.py:1494` 仍为 `"temperature": 0.1`
- **方案：** 改为 `0.0`，减少运行间方差
- **复杂度：** 一行改动

### 2.2 去重身份强化（部分完成）

- **已完成：** `ast_builder.py` 的 node_key 已用 `node_type` + `node_label` + commentary 后缀强化；`_build_nested_ast()` 用 shared `seen_node_keys` 跨递归去重
- **未完成：** `source_label` 未纳入去重 key（修订计划 Phase 3 要求 `{clause_type}:{node_key}:{source_label}`）。附录与正文编号相同的条款仍可能碰撞
- **方案：** 在 `deduplicate_entries()` 和 `_build_nested_ast()` 的 dedup key 中加入 `source_label`

### 3.1 三通道独立提取（部分完成）

- **已完成：** block path 按 `segment_type` 路由到不同 `scope_type`（normative/commentary/table），确定性提取处理 table 和简短 normative 块
- **未完成：** 无专用轻量 prompt（如 `CLAUSE_NORMALIZE_PROMPT`）用于确定性提取后的 LLM 补全场景。目前 LLM 路由的 block 仍用通用 `CLAUSE_EXTRACTION_PROMPT`
- **方案：** 为 `normative_determined` scope 设计更短、更精确的 normalize prompt，减少 token 消耗和幻觉

### 3.2 置信度路由（部分完成）

- **已完成：** `block_segments.py:_block_confidence()` 为每个 block 计算 high/medium/low 置信度，字段已传到 scope context
- **未完成：** confidence 字段未用于路由决策。当前确定性提取判定基于 `_should_extract_normative_block_deterministically()` 的文本长度/列表信号启发式，与 confidence 字段无关
- **方案：** 将路由逻辑改为 confidence 驱动：high → 确定性提取，medium → 轻量 LLM prompt，low → 完整 LLM + repair 候选

### Commentary 召回补齐

- **状态：** 残留 gap
- **现象：** 实际 39 条 commentary vs 目标形态 49+
- **可能原因：** commentary 边界检测过于保守，或 commentary 块在 block_segments 中被归类为 non_clause 而跳过
- **方案：** 需排查 `block_segments.py` 中 commentary 块的分类逻辑和 `_should_skip_block_for_ai()` 的跳过条件

### 实验泛化

- **状态：** 未开始
- **现象：** block path 仅对 GB50148 启用（`_SINGLE_STANDARD_BLOCK_EXPERIMENT_IDS` / `_SINGLE_STANDARD_BLOCK_EXPERIMENT_CODES`）
- **方案：** 在更多标准上验证后，逐步移除实验标志，作为默认路径

---

## 实施优先级（剩余项）

```
立即可做:
  1.4 Temperature → 0.0                          [一行改动]

短期优化（1-2天）:
  Commentary 召回排查                              [诊断 + 修复]
  2.2 去重 key 加入 source_label                  [小改动]

中期演进（3-5天）:
  3.2 Confidence 驱动路由                          [利用已有 confidence 字段]
  3.1 轻量 normalize prompt                       [需 prompt 设计 + 效果验证]

长期:
  实验泛化到其他标准                                [需更多标准验证]
```

## 关键文件索引

| 文件 | 内容 |
|---|---|
| `services/norm_service/block_segments.py` | 确定性分块、分类状态机、置信度评分 |
| `services/norm_service/norm_processor.py` | pipeline编排、确定性提取、LLM调用、scope defaults |
| `services/norm_service/structural_nodes.py` | commentary边界、页码传递、outline scope构建 |
| `services/norm_service/ast_builder.py` | AST构建、去重逻辑 |
| `services/norm_service/scope_splitter.py` | scope拆分与rebalance |
| `services/norm_service/prompt_builder.py` | LLM prompt模板 |
| `services/norm_service/validation.py` | 结构化校验 |
| `tests/integration/test_gb50148_acceptance.py` | 验收测试scaffold |
| `tests/integration/test_gb50148_persisted_acceptance.py` | 持久化验收测试 |
