# 招标 AI 解析耗时优化 Part 2 设计文档

> 创建日期：2026-05-05
> 状态：待批准
> 范围：招标文件 source chunks → AI Gateway → DeepSeek V4 → project_requirement 落库
> 关联文档：[`docs/plans/2026-05-05-tender-ai-extraction-latency-root-cause-and-optimization-plan.md`](../../plans/2026-05-05-tender-ai-extraction-latency-root-cause-and-optimization-plan.md)（v1 plan）

## 1. 目标与范围

### 1.1 与 v1 plan 的关系

v1 plan 已识别五大根因并实施 Phase 0/1 全量、Phase 3/4/5 部分修复，本文档定位为 **Part 2 续作**，专注 v1 中标 `[ ]` 未完成的 Phase 2、Phase 3 末尾、Phase 4 中段，叠加新发现：

- thinking 模式显式控制（DeepSeek 文档要求 `extra_body.thinking.type` 显式声明）
- prompt 前缀缓存友好重排（DeepSeek KV Cache 命中需稳定前缀）
- thinking 启用时 temperature/top_p/penalty 字段不发（DeepSeek 文档明确不生效）
- streaming 默认开（v1 已实现支持但未默认启用）

v1 plan 不被废弃，仅停止追加完成日记；本设计文档承接所有后续记录。

### 1.2 目标（按优先级）

1. 缩短完整招标包 requirements 初抽 wall-clock：当前不可解释的 10–50 分钟 → 目标 ≤ 8–12 分钟。
2. 不丢质量：高价值文件（招标正文、资格、技术、递交、评分）召回不退化；保留 Phase 5 的 `pro_review` 兜底。
3. 改造可观测、可灰度、可回滚：通过 `strategy_version` 与 batch metadata 标记 v1/v2，run 级可对比。

### 1.3 非目标

- 不引入新模型供应商，仍以 DeepSeek 为主。
- 不改持久化 schema 中的 requirement 表；只在 `tender_ai_extraction_batch.metadata_json` 内追加字段。
- 不实现模型 race / cache 预热（C 方案已被排除；收益不稳定且改动面大）。

## 2. 核心策略：quality_policy 三段式

每个 batch 在 planner 阶段绑定一个 `quality_policy`，决定模型 + thinking + effort + 并发槽位 + 输入预算。

| quality_policy | 适用对象 | model | thinking.type | reasoning_effort | 全局并发上限 | 单 batch 输入预算 |
|---|---|---|---|---|---:|---|
| `fast_candidate` | 普通附件、合同模板、纯说明类（非 high_value） | `deepseek-v4-flash` | `disabled` | 不传 | 6 | ≤ 25k tokens / ≤ 60 chunks |
| `high_value_candidate` | 招标正文 / 资格 / 技术 / 递交 / 评分 / 否决（high_value=true） | `deepseek-v4-flash` | `enabled` | `high` | 4 | ≤ 30k tokens / ≤ 60 chunks |
| `pro_review` | high_value 空输出复核 / 失败重试第二阶段 / 评分表小批 | `deepseek-v4-pro` | `enabled` | `high`（默认）；`max` 仅在 pro_review 仍空输出再次升级时触发 | 2（max=1） | ≤ 12k tokens / ≤ 24 chunks |

### 2.1 判定规则（planner 内）

- `_is_high_value(source_file, classification)` 命中 → `high_value_candidate`，否则 `fast_candidate`。
- `_use_direct_pro` 现有逻辑保留：≤ 24 chunks ∧ ≤ 12k tokens ∧（评分细则 / 资格要求 / 否决 / 废标 / 递交要求 关键词）→ 直接 `pro_review`（一阶段直入 pro 复核）。
- 失败重试或 high_value 空输出 → 创建 `pro_review` 子 batch（沿用 Phase 5 实现的路径，标记 `quality_policy` 即可）。

### 2.2 与 v1 默认行为的差异

- v1：所有 flash batch 实际都带 thinking enabled（V4 默认行为）+ effort high（Phase 1 后），无法关闭；本设计的 `fast_candidate` 显式 `thinking.type=disabled`，按 DeepSeek 文档可显著提速。
- v1：`high_value` 与普通 flash 共用同一参数；本设计区分两档并发槽位，避免高价值 batch 与低价值 batch 互相阻塞。
- v1：`temperature=0.0` 始终发；本设计 thinking enabled 时省略 temperature/top_p（DeepSeek 文档：thinking 模式下不生效）。

## 3. Planner v2：路由判定与 batch schema 变更

### 3.1 `ai_extraction_planner.py` 改动

- 新增常量：`STRATEGY_VERSION = "tender_extract_v2"`。
- 新增 `QualityPolicy` 字面量类型：`fast_candidate | high_value_candidate | pro_review`。
- `ExtractionBatchPlan` 新增字段：
  - `quality_policy: str`（必填，写库）
  - `thinking_enabled: bool`（默认 None；显式注入到 metadata 而非顶级，方便后续改回退）
- `_model_for(...)` 替换为 `_policy_for(direct_pro, high_value, model_policy)`，返回 `(model, thinking_enabled, reasoning_effort, quality_policy)`：
  - `direct_pro=True` → `(pro, True, "high", "pro_review")`（一阶段直接 pro 复核）
  - `high_value=True` → `(flash, True, "high", "high_value_candidate")`
  - 其他 → `(flash, False, None, "fast_candidate")`
- `target_tokens` 与 `max_chunks_per_batch` 改为按 `quality_policy` 分档：

```text
fast_candidate:        target=25_000, max_chunks=60
high_value_candidate:  target=30_000, max_chunks=60
pro_review:            target=12_000, max_chunks=24（沿用 DIRECT_PRO_MAX_*）
```

v1 的 `TARGET_TOKENS_NORMAL=50_000`、`TARGET_TOKENS_HIGH_VALUE=120_000`、`FLASH_MAX_CHUNKS_PER_BATCH=120` 替换为上表，保留旧名作为 alias 仅用于 v1 plan 路径兼容。

- `metadata_json` 新增：`strategy_version`、`quality_policy`、`thinking_enabled`、`planned_thinking`，与 `planned_model`、`planned_reasoning_effort` 同行写入。

### 3.2 DB 层变更（轻改，避免迁移风险）

- `tender_ai_extraction_batch` 表 **不加新列**；`quality_policy` / `thinking_enabled` 写入 `metadata_json` 即可。
- repository 的 `create_batches` / `mark_batch_succeeded` 把这些字段与 `planned_*` 对齐输出，便于事后查询。

### 3.3 Worker 改动（`tasks_extract.py`）

- `_resolve_batch_overrides` 在拼 `primary_override` 时，从 batch metadata 读取 `thinking_enabled` 显式写入 `extra_body.thinking.type=enabled|disabled`（不依赖 V4 默认）。
- `_build_retry_batches` 在生成 retry batch 时继承 `quality_policy`：
  - `high_value_candidate` 第一次失败 → 拆 + 降 effort（保持 `high_value_candidate`）
  - 第二次失败 → 升级为 `pro_review`

## 4. AI 调用层：显式 thinking、streaming 默认、cache 友好 prompt

### 4.1 `ai_requirements_extractor.py` 改动

1. **streaming 默认开**：`extract_requirements_for_batch(..., stream: bool = True)`；worker 不需改调用方式即可生效。Gateway 端 stream 分支已实现，stream 模式下 usage 缺失字段（cache/reasoning tokens）继续以 0 记录，metadata 标 `stream=true`。
2. **`_provider_override` 接收 `thinking_enabled: bool | None`**，注入：

```python
override["extra_body"] = {
    "thinking": {"type": "enabled" if thinking_enabled else "disabled"},
}
if reasoning_effort:
    override["extra_body"]["reasoning_effort"] = reasoning_effort
```

3. **temperature 在 thinking enabled 时不发**：

```python
payload = {"task_type": "extract_tender_requirements", "messages": [...]}
if not thinking_enabled:
    payload["temperature"] = 0.0
```

4. **prompt 前缀重排**：`_INSTRUCTION` 重写为 **稳定段在前 / 变量段在后**：

```text
[稳定 system + 规则 + JSON schema + 示例]   ← 缓存命中区
---
[本批元数据：source_file=…, chunk_count=…]  ← 仍是变量但很短
---
[source_chunks JSON payload]                ← 主变量段
```

- 把 `categories` 字符串、JSON schema、示例固定为模块级 const，避免 f-string 在前缀注入随机空白。
- `source_file` / `chunk_count` 行下沉到 payload 之前的最后一节，整段 hash 不再随每个 batch 完全变化。
- 验收：第二次相同 run 的 `prompt_cache_hit_tokens` 占输入的比例从近 0 → ≥ 30%（同包不同 batch 间的 system+schema 部分都应命中）。

### 4.2 `ai_gateway/fallback.py` 改动

- 既有 `extra_body` merge 逻辑保留；不再硬编码 `reasoning_effort`。
- 新增轻量校验：当 `thinking.type=disabled` 时，`reasoning_effort` 字段被剥离（DeepSeek 在 disabled 下传 effort 行为未文档化，避免歧义）。

## 5. 并发与 batch 缩粒：参数变更

### 5.1 `retry_policy.provider_limit_for(...)`

判定逻辑改为按 `(model, thinking_enabled, reasoning_effort)` 三元组而不是只看 model+effort。Worker 在 dispatch 与 requeue 时统一调用。

| 模型 / 配置 | v1 上限 | v2 上限 |
|---|---:|---:|
| `deepseek-v4-flash`（thinking disabled，fast_candidate） | 4 | 6 |
| `deepseek-v4-flash`（thinking enabled，high_value_candidate） | 4 | 4 |
| `deepseek-v4-pro` + `high` | 2 | 2 |
| `deepseek-v4-pro` + `max` | 1 | 1 |

### 5.2 Batch 输入预算 / chunk 上限

| quality_policy | target_tokens | max_chunks |
|---|---:|---:|
| fast_candidate | 25_000 | 60 |
| high_value_candidate | 30_000 | 60 |
| pro_review | 12_000 | 24 |

### 5.3 Worker 调度优先级

- `run_tender_ai_extraction` 仍逐个 dispatch；`_dispatch_batch` 在 provider_limit 已满时延迟入队 15s。
- 新逻辑增加 batch 优先级：`pro_review > high_value_candidate > fast_candidate`，避免 fast 占满 flash slot 阻塞 high_value。
- 实现：`list_batches(..., status="pending")` 后按 `metadata_json.quality_policy` 排序，再按 `batch_index` 排序。

### 5.4 `max_tokens` 输出预算

- 不动 task_profile 的 `max_tokens=65536` 全局上限。
- worker 调用时按 `quality_policy` 传 hint：

| quality_policy | output max_tokens hint |
|---|---:|
| fast_candidate | 16_384 |
| high_value_candidate | 24_576 |
| pro_review | 32_768 |

Gateway 已支持 `max_tokens` 透传，profile 上限做兜底。如基线对比中发现 `output_tokens_to_max_ratio > 0.95` 的 batch 出现，对应 quality_policy 的 hint 按 1.5× 上调，再跑一次。

## 6. 观测埋点与基线对比

### 6.1 完成 v1 plan Phase 0 剩余三段 latency

每个 batch 在 worker 中记录：

- `queue_to_start_ms`：`tender_ai_extraction_batch.created_at` → `mark_batch_running` 时间差。
- `provider_latency_ms`：AI Gateway 调用 `start` → `end`。已有 `latency_ms` 字段，本设计将其镜像写入 `metadata.provider_latency_ms` 与结构化日志同名 key，旧 `latency_ms` 列保留不动避免破坏已有读取。
- `persist_latency_ms`：`on_batch_persisted` 内部 `start` → `commit` 时间。

写入位置：batch `metadata_json` 与 worker 结构化日志（`tender_ai_extraction_batch_done`），不入新表，避免 schema 变更。

### 6.2 新增可观测字段

batch metadata（已有的基础上扩展）：

- `strategy_version`、`quality_policy`、`thinking_enabled`、`stream`（bool）
- `prompt_cache_hit_ratio`（= hit / (hit + miss)，computed at write time）
- `output_tokens_to_max_ratio`（= output_tokens / max_tokens，> 0.95 视为可能截断）

### 6.3 v1 vs v2 基线对比报告

新增 `scripts/extract_baseline_compare.py`（一次性脚本，不进 cron）：

- 输入：两个 run_id（v1 strategy 与 v2 strategy）。
- 输出 markdown 报告，落 `docs/reports/`：总耗时、按 `quality_policy` 的 P50 / P95、cache 命中率、empty_output 数、needs_review 数、dropped_invalid 率、failed 类型分布。
- 验收：v2 报告的总 wall-clock 与 high_value_candidate P95 必须明显优于 v1（具体阈值见第 7 节）。

## 7. 测试与验收门禁

### 7.1 单测

`backend/tests/unit/`：

1. `test_ai_extraction_planner.py`：
   - `fast_candidate` 路径：低价值文件 → flash + `thinking_enabled=False` + effort=None。
   - `high_value_candidate` 路径：招标正文 → flash + `thinking_enabled=True` + `effort="high"`。
   - `pro_review` 路径：评分细则小批 → pro + `thinking_enabled=True` + `effort="high"`。
   - batch 输入预算分档：fast 25k、high_value 30k、pro 12k 的 flush 边界正确。
   - `strategy_version` / `quality_policy` 写入 metadata。
2. `test_ai_requirements_extractor.py`：
   - `thinking_enabled=False` 时 payload 含 `temperature` + `extra_body.thinking.type=disabled`、不含 `reasoning_effort`。
   - `thinking_enabled=True` 时 payload 不含 temperature、含 `extra_body.thinking={"type":"enabled"}` + `reasoning_effort`。
   - `stream=True` 默认；prompt 模板的稳定前缀（system + rules + schema + example）在两次不同 payload 之间字节相同（前缀 cache 友好性的 unit-level proxy）。
3. `test_celery_extract_routes.py`：
   - retry 升级路径：`high_value_candidate` 二次失败 → 子 batch quality_policy 升 `pro_review`。
   - 调度优先级：mixed pending 列表中 `pro_review` 先于 `high_value_candidate` 先于 `fast_candidate`。
4. `test_retry_policy.py`：
   - `provider_limit_for(flash, thinking=False)` 返回 6；`provider_limit_for(flash, thinking=True)` 返回 4。

### 7.2 集成（手动 / 半自动）

- 在 dev 环境跑同一份完整招标包两次：一次用 v1 strategy（保留 `model_policy="v4_flash_then_pro"` 旧路径），一次用 v2 strategy（新默认）。运行基线对比脚本。
- 验收门禁：
  - v2 总 wall-clock ≤ v1 × 0.7（即 -30% 起步，目标 -40% ~ -55%）。
  - v2 high_value_candidate 召回 ≥ v1 × 0.95（按 requirement count + 关键词覆盖）。
  - v2 needs_review batch 数 ≤ v1 × 1.2（容许复核略多，但不能爆炸）。
  - v2 prompt_cache_hit_ratio ≥ 30%（同包不同 batch 平均）。
  - v2 没有 batch 因 `output_tokens_to_max_ratio > 0.95` 被截断；如有，说明 max_tokens 分档过小，需调。

## 8. 风险与回滚

| 风险 | 触发条件 | 缓解 / 回滚 |
|---|---|---|
| `thinking.type=disabled` 在 fast_candidate 上漏抽关键条款 | 普通附件被错分类为低价值 | `_is_high_value` 关键词清单加宽（保守优先）；保留 Phase 5 `pro_review` 兜底；运行时 metric `fast_candidate_with_review_keywords_count > 0` 自动升级为 `high_value_candidate`。 |
| streaming 中断导致结果丢失 | 网络抖动 / DeepSeek 服务端关闭 | 已有失败拆批机制；新增 `stream=true` 失败计数指标，单 run 超 20% 自动回退非流式（worker 级 flag）。 |
| Prompt 前缀重排后 DeepSeek 解析变差 | 模型对新 prompt 顺序不适应 | 第一次部署只在一个 dev run 验证；保留 `_INSTRUCTION_LEGACY` 常量与 `prompt_template_version=v2` 标记，1 行切换回 v1。 |
| 并发 6 触发 DeepSeek 动态 429 | 服务端瞬时高峰 | 既有 backoff + 指数退避；新增 `dynamic_concurrency_floor=4`（连续 3 次 429 自动降并发到 4，5 分钟后恢复）。 |
| pro_review 滥用导致成本爆涨 | 关键词命中过广 | metric `pro_review_share_of_total > 25%` 触发告警；`pro_review` 仍受 `provider_limit=2` 限流。 |
| v1 / v2 共存期 batch metadata 字段缺失 | 老 run 没有 `quality_policy` | 所有读取代码用 `.get(...)` + 默认值；compare 脚本对 missing 字段标 `legacy`。 |

### 8.1 整体回滚

- 一行配置：`ExtractionPlannerSettings.strategy_version="v1"`（新增 settings 项）→ planner 走旧路径，worker 兼容。
- 已有 v2 metadata 不删，仅停止生成。

## 9. 实施顺序

按依赖与风险逐步落，每步可独立验证、独立回滚。

1. **Step 1（观测先行，无行为改动）**：补 `queue_to_start_ms` / `provider_latency_ms` / `persist_latency_ms` 三段埋点 + `cache_hit_ratio` + `output_to_max_ratio` 字段。单测 + 真实 dev run 一次，得到 v1 基线数。
2. **Step 2（调用层）**：`extract_requirements_for_batch` 默认 `stream=True`、`_provider_override` 显式写 thinking + reasoning_effort、thinking 模式下省略 temperature。单测覆盖。
3. **Step 3（prompt 重排）**：`_INSTRUCTION` 拆为 stable + variable，加单测断言稳定段字节恒定；dev run 验证 `cache_hit_ratio`。
4. **Step 4（planner v2 + quality_policy）**：新增 `strategy_version`、policy 字段、batch 预算分档；单测 + 一次 dev run 出 v2 报告。
5. **Step 5（并发参数 + 调度优先级）**：`provider_limit_for` 三元组化、worker 优先级排序。
6. **Step 6（retry 升级）**：`high_value_candidate` 二次失败升级 `pro_review`，pro_review 仍空 → `needs_review`。
7. **Step 7（基线对比）**：跑 v1 vs v2 同包对比，写入 `docs/reports/2026-05-XX-tender-extract-v1-v2-compare.md`，按验收门禁判定是否进入默认。
8. **Step 8（默认切换 + cleanup）**：`strategy_version` 默认 v2；保留 v1 路径 4 周供回滚，4 周后清理。

每步在 commit message 标 `[part2-stepN]`，便于事后 cherry-pick / revert。

## 10. 待批准事项

- [ ] 是否批准本 Part 2 设计的 quality_policy 三段式与默认参数表（第 2 / 5 节）。
- [ ] 是否允许 `fast_candidate` 显式关闭 thinking（第 4 节关键改动）。
- [ ] 是否允许将 streaming 设为 `extract_tender_requirements` 默认调用方式（第 4 节）。
- [ ] 是否同意按第 9 节 8 步顺序逐步实施，每步独立 commit 与验收。
- [ ] 是否同意 v1 路径保留 4 周后清理（第 8 / 9 节）。

## 11. 实施记录

待 Step 1 启动后追加。每完成一步追加一条小节记录：日期、step、改动摘要、单测结果、dev run 链接（如有）。
