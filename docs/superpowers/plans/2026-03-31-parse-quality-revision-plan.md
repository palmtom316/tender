# GB 50148-2010 解析质量修订计划

**日期：** 2026-03-31

**依据：** `docs/superpowers/specs/2026-03-31-gb-50148-parse-quality-improvement-plan.md` 中未完成项

**范围：** 仅实施剩余改进项，不涉及已完成的功能

---

## Chunk 1: Temperature → 0.0

**改动：** `norm_processor.py:1494` 一行

```python
# before
"temperature": 0.1,
# after
"temperature": 0.0,
```

**影响范围：** 所有通过 `_call_ai_gateway()` 的 LLM 调用
**风险：** 极低。DeepSeek-V3 在 temperature=0 下仍可能因 batching 有微小方差，但可测量地更稳定
**验证：** 无需单独验证，随后续重跑一并确认

---

## Chunk 2: 去重 key 加入 source_label

**改动：** `ast_builder.py:deduplicate_entries()` 第72行

当前 key 构造：
```python
key = f"{ctype}:{node_key}" if node_key else ""
```

改为：
```python
source_label = str(entry.get("source_label") or "").strip()
key = f"{ctype}:{node_key}:{source_label}" if node_key else ""
```

同样更新 `_build_nested_ast()` 中 `seen_node_keys` 的 `dedupe_key` 构造（当前约第243行），加入 `source_label`：
```python
source_label = (current_entry.get("source_label") or "").strip()
dedupe_key = f"{clause_type}:{node_key}:{source_label}" if node_key else ""
```

**影响范围：** AST 构建阶段的去重判定。附录与正文中编号相同的条款不再碰撞
**风险：** 低。可能导致少量之前被去重的条目现在保留，需确认不引入真正的重复
**验证：** 重跑后对比总条款数变化，检查是否出现新的重复条款

---

## Chunk 3: Commentary 召回排查与修复

**目标：** 实际 39 条 commentary vs 目标 49+，找到丢失的 ~10 条

**排查步骤：**

1. 检查 `block_segments.py:build_single_standard_blocks()` 中 commentary 块的分类逻辑：
   - `_is_commentary()` 是否过于严格（只匹配 title 中含"条文说明"）
   - `in_commentary_tail` 跟踪是否过早终止

2. 检查 `norm_processor.py:_should_skip_block_for_ai()` 第1057-1068行：
   - commentary_block 无 text 时被跳过 — 合理
   - 无 clause_no 且非 table 时被跳过 — **这可能丢失无编号的 commentary 段落**

3. 检查 `_deterministic_entries_from_block()` 第1010行：
   - commentary_block 直接走确定性提取，但要求有 text — 合理
   - 但 commentary 中的子项/列表是否被正确处理？

**预计修复方向：** 放宽 `_should_skip_block_for_ai()` 对 commentary_block 的 clause_no 要求。commentary 条文说明中很多段落没有独立的条款编号，而是引用正文编号

**验证：** 重跑后 commentary 数量应接近 49+

---

## Chunk 4: Confidence 驱动路由（可选优化）

**当前状态：** `block_segments.py:_block_confidence()` 已为每个 block 计算 high/medium/low，但 `norm_processor.py` 中确定性提取判定基于 `_should_extract_normative_block_deterministically()` 的文本长度/列表信号启发式，未使用 confidence 字段

**改动方向：**
- 在 `_deterministic_entries_from_block()` 中，将 `_should_extract_normative_block_deterministically()` 的判定改为以 confidence 为主：
  - `high` → 直接确定性提取（当前140字符限制可放宽到300+）
  - `medium` → 保持当前逻辑（短文本确定性，长文本走LLM）
  - `low` → 必须走LLM
- 在日志中输出 confidence 分布，便于后续调优

**风险：** 中等。放宽确定性提取范围可能降低 summary/tags 质量（确定性提取不生成这些字段）
**验证：** 重跑后对比条款质量，确认 summary/tags 缺失是否可接受

---

## 实施顺序

```
Chunk 1: Temperature → 0.0                    [立即，1分钟]
Chunk 2: 去重 key 加入 source_label           [立即，10分钟]
Chunk 3: Commentary 召回排查与修复             [排查 → 修复，30分钟-1小时]
Chunk 4: Confidence 路由                       [可选，视 Chunk 1-3 效果决定]
```

Chunk 1-2 无依赖可并行。Chunk 3 需排查后确定具体改动。Chunk 4 为可选优化。

---

## 不在本轮范围内

- 专用轻量 prompt（3.1）— 需独立 prompt 设计和效果验证，留作后续
- 实验泛化到其他标准 — 需更多标准验证，留作后续
