# 招标 AI 抽取综合改造方案

> 创建日期：2026-05-05
> 状态：待批准
> 范围：`source_chunk` → planner → AI Gateway / DeepSeek → `tender_ai_extraction_batch` → `project_requirement`
> 合并来源：
> - 已实施改造现状（本仓库）
> - Claude 方案：[`2026-05-05-tender-ai-extraction-latency-part-2-design.md`](./2026-05-05-tender-ai-extraction-latency-part-2-design.md)
> - GitHub 参考项目与 DeepSeek 官方文档

## 1. 结论

Claude 的方案有明显可取之处，但不能原样照搬。

可直接吸收的核心点有 6 个：

1. 显式控制 `thinking.type=enabled|disabled`，而不是依赖 DeepSeek 默认行为。
2. 在 thinking 模式下不再发送 `temperature` / `top_p` / penalty 参数。
3. 做 prompt 稳定前缀重排，争取 DeepSeek context caching 命中。
4. 用 `quality_policy` 把批次策略写入 metadata，形成可观测、可灰度的 planner v2。
5. 加批次级时延与缓存指标，形成 v1/v2 可对比基线报告。
6. 增加调度优先级，让 review / 高风险批次不被普通 flash 批次阻塞。

需要改写后吸收的点有 4 个：

1. 不能把 `high_value_candidate = flash + thinking enabled + high` 设为默认主路径。
2. streaming 不能只因为“更快”就全量默认开启，前提是先解决 usage / metrics 丢失问题。
3. cache 命中率不能先拍脑袋设 `>= 30%` 为硬门槛，需要先测基线。
4. 并发上限应该是“我们系统自己的调度策略”，不是把 DeepSeek 官方“理论无并发限制”当成可直接放开。

不建议吸收的点有 2 个：

1. 继续把“大量 high_value 首轮批次”放在思考模式上跑。
2. 以“同包二次重跑 cache 命中”为主要优化抓手。真正更值钱的是同一轮内的稳定前缀和更短 prompt。

## 2. 对 Claude 方案的评估

### 2.1 可取之处

#### A. thinking 显式控制

这条成立，而且应优先做。

DeepSeek 官方 thinking 文档明确支持通过 `extra_body={"thinking": {"type": "enabled"}}` 开启思考模式；V4 同时支持 thinking / non-thinking 双模式。当前 `tender` 的抽取链路只显式传了 `reasoning_effort`，没有显式传 `thinking.type`，这会让行为依赖默认值，不利于稳定调优。

可落点：

- [backend/tender_backend/services/extract_service/ai_requirements_extractor.py](/Users/palmtom/Projects/tender/backend/tender_backend/services/extract_service/ai_requirements_extractor.py:194)
- [ai_gateway/tender_ai_gateway/fallback.py](/Users/palmtom/Projects/tender/ai_gateway/tender_ai_gateway/fallback.py:145)

#### B. thinking 模式下省略 temperature / top_p

这条成立。

DeepSeek 官方 thinking 文档明确写了 thinking 模式下 `temperature`、`top_p`、`presence_penalty`、`frequency_penalty` 不生效；继续传不会报错，但没有意义。当前 gateway 统一发送 `temperature`，应在 thinking 模式下剥离。

可落点：

- [ai_gateway/tender_ai_gateway/fallback.py](/Users/palmtom/Projects/tender/ai_gateway/tender_ai_gateway/fallback.py:161)

#### C. prompt 稳定前缀 / cache 友好重排

这条成立，而且和 DeepSeek 官方 context caching 文档一致。

DeepSeek 的 cache 命中依赖“重复前缀已持久化且完整匹配”。因此把稳定规则、schema、示例前置，把 `source_file`、`chunk_count`、`payload` 放到后面，是有价值的。

但要注意：这主要优化的是“相同稳定前缀”的首 token 延迟和成本，不能代替减少 payload 本身。

可落点：

- [backend/tender_backend/services/extract_service/ai_requirements_extractor.py](/Users/palmtom/Projects/tender/backend/tender_backend/services/extract_service/ai_requirements_extractor.py:54)

#### D. `quality_policy` 元数据化

这条成立。

当前 planner 已有 `model` / `reasoning_effort` / `metadata_json`，但还缺一层更稳定的“策略语义”。把 `quality_policy`、`strategy_version`、`thinking_enabled` 写入 batch metadata，可以把“当前为何这样调度”变成可追踪证据。

可落点：

- [backend/tender_backend/services/extract_service/ai_extraction_planner.py](/Users/palmtom/Projects/tender/backend/tender_backend/services/extract_service/ai_extraction_planner.py:59)
- [backend/tender_backend/db/repositories/tender_ai_extraction_repo.py](/Users/palmtom/Projects/tender/backend/tender_backend/db/repositories/tender_ai_extraction_repo.py:44)

#### E. 调度优先级与更细并发槽位

这条成立。

当前已经做了 per-model 限流，但还没有把“同样是 flash，也要区分低风险普通批次和高风险批次”的优先级体系补齐。应继续做，但实现方式应以我们自己的 worker 调度为主，而不是假设上游 provider 会替我们处理。

可落点：

- [backend/tender_backend/services/extract_service/retry_policy.py](/Users/palmtom/Projects/tender/backend/tender_backend/services/extract_service/retry_policy.py:27)
- [backend/tender_backend/workers/tasks_extract.py](/Users/palmtom/Projects/tender/backend/tender_backend/workers/tasks_extract.py:232)

#### F. 基线对比脚本和指标补齐

这条成立，且是后续验收必须项。

当前已有 `latency_ms`、`prompt_cache_hit_tokens`、`prompt_cache_miss_tokens`，但缺：

- `queue_to_start_ms`
- `persist_latency_ms`
- `prompt_cache_hit_ratio`
- `output_tokens_to_max_ratio`
- `strategy_version`

没有这些，后续任何“更快了”都不够可证。

### 2.2 需要改写后吸收

#### A. `high_value_candidate = flash + thinking enabled + high`

这条不应原样采用。

原因有三点：

1. 它和我们已经确认过的根因方向冲突。前面已经修掉了“首轮批次大量高推理导致串行和超时”的问题。
2. GitHub 上更成熟的 RFP / 结构化抽取路径，普遍是“先快筛，再少量深推理”，不是“所有 high_value 都先思考模式”。
3. DeepSeek V4 Flash 虽然支持 thinking，但思考内容也吃 `max_tokens`，会直接拉高长批次 latency。

替代方案：

- `high_value` 不等于默认启用 thinking
- `high_value` 只意味着：
  - 更小 batch
  - 更高调度优先级
  - 更严格空输出复核
  - 更高概率走专用表格 / 专用章节 prompt

#### B. streaming 默认全开

这条只可部分吸收。

当前 worker 已经显式 `stream=True` 调用，但 gateway 的流式分支只拼接内容，usage 统计会丢失或归零，见 [fallback.py](/Users/palmtom/Projects/tender/ai_gateway/tender_ai_gateway/fallback.py:173)。

因此正确顺序不是“先全开再说”，而是：

1. 先补齐流式模式下的 usage / finish_reason / reasoning_content 采集能力。
2. 再决定哪些 `quality_policy` 默认流式。

建议：

- `fast_prefilter` 和 `flash_extract` 默认流式
- `pro_review` 初期保守保留非流式或可切换

#### C. cache 命中硬阈值

这条应改成“观察项”，不宜现在就写死。

DeepSeek 官方文档说明 cache 命中依赖完整前缀单元匹配。对我们的场景，system/schema 前缀可以稳定，但 `source_chunks` 主体高度变化，真实命中率需要实测。

因此建议：

- 先记录 `prompt_cache_hit_ratio`
- 暂不把 `>= 30%` 作为硬验收门槛
- 第一次基线跑完后再确定合理阈值

#### D. 不改 requirement schema

这条只能短期接受，不能作为中期终局。

短期内不改 schema 可以降低风险；但中期如果要真正吸收 GitHub 参考项目的优点，`project_requirement` 至少要更好表达：

- requirement 是否需要投标文件回应
- 建议放在哪个投标章节
- 是否需要证明材料
- 证据类型 / 证据片段

所以本方案分两层：

- Phase A：只用 metadata 和现有表落地
- Phase B：评估是否补充 requirement schema

### 2.3 不建议采用

#### A. 让大量 high_value 首轮直接进入 thinking

不建议。

这是最容易把当前已经修复的慢路径重新带回来的设计。

#### B. 把“二次重跑同一包”当成主要 cache 收益场景

不建议。

更现实的收益场景是：

- 同一轮内多个 batch 共享稳定 system/rules/schema 前缀
- review batch 与 retry batch 共享上游固定前缀

## 3. GitHub 可借鉴路径，哪些应并入新方案

### 3.1 应采纳的外部模式

#### A. `AutoRFP` 的问题清单优先

参考项目：

- https://github.com/run-llama/auto_rfp

应借鉴点：

- 把“招标 requirement 抽取”进一步收敛为“响应所需问题 / 义务 / 证明材料清单抽取”
- 降低自由总结比例

对 `tender` 的改造含义：

- prompt 不只抽 `category/title/requirement_text`
- 增加：
  - `response_needed`
  - `deliverable_type`
  - `evidence_required`
  - `target_bid_section`

#### B. `OpenContracts` / `LangExtract` 的结构化证据定位

参考项目：

- https://github.com/Open-Source-Legal/OpenContracts
- https://github.com/google/langextract

应借鉴点：

- 结果必须强绑定证据来源，便于人工复核和后续生成引用

对 `tender` 的改造含义：

- 在 `source_metadata` 中补：
  - `section_title`
  - `evidence_kind`
  - `evidence_span_text`
  - `table_header_fingerprint`

#### C. `Docling` / `MinerU` / `Unstructured` 的结构先行

参考项目：

- https://github.com/docling-project/docling
- https://github.com/opendatalab/mineru
- https://github.com/Unstructured-IO/unstructured

应借鉴点：

- 进入 LLM 之前先做标题层级、表格类型、阅读顺序、章节角色约束

对 `tender` 的改造含义：

- planner 不再只按 `source_file + token budget` 切
- 增加：
  - 按 `document_type`
  - 按 `section_title`
  - 按 `chunk_type`
  - 按表格/正文角色

### 3.2 不直接照搬的外部模式

#### A. 端到端 agent 化生成

像 Microsoft RFP Agent 这类方案更偏后续响应编写，不是当前“抽取阶段”的核心矛盾，不应现在扩大范围。

#### B. 重新更换底层解析栈

虽然 `Docling` / `MinerU` 值得参考，但当前 `tender` 已有成熟 `source_chunk` 管线。现阶段更应该在“chunk 组织和抽取策略”上改，而不是重构整套 OCR / parser。

## 4. 新综合方案

## 4.1 目标

1. 在不降低高风险条款召回的前提下，进一步缩短完整招标包 AI 抽取总耗时。
2. 保持当前已修复成果不回退：
   - 不再持有长事务等待 AI
   - 不再让主路径大量落入 `pro/max`
   - 不再让超大 flash 批次拖垮 wall-clock
3. 让后续优化有据可比、有文档、有回滚点。

## 4.2 设计原则

1. 首轮默认快模型、非 thinking、短 prompt。
2. 高价值不等于高思考；高价值优先通过更小批次、专用 prompt、复核兜底保障质量。
3. 深推理只用于：
   - 小型评分/资格/否决/递交关键表
   - 空输出复核
   - 重试升级
4. 结构先于模型：
   - 先做好章节/表格/标题聚类
   - 再做抽取
5. 所有策略必须写入 metadata，可追踪可比较。

## 4.3 Planner v2

新增 `strategy_version = "tender_extract_v2"`。

新增 `quality_policy`，建议不是 Claude 的三段，而是四段：

| quality_policy | 作用 | 默认模型 | thinking | effort |
|---|---|---|---|---|
| `fast_prefilter` | 首轮候选筛选，过滤无要求 chunk | `deepseek-v4-flash` | disabled | 不传 |
| `flash_extract` | 候选 chunk 的主抽取路径 | `deepseek-v4-flash` | disabled | 不传 |
| `table_or_critical_extract` | 小型高风险表、资格/评分/否决关键片段 | `deepseek-v4-flash` 或小批 `pro` | 默认 disabled；仅小批可 enabled | 视批次 |
| `pro_review` | 空输出复核、失败升级、关键小批终审 | `deepseek-v4-pro` | enabled | `high`，必要时 `max` |

说明：

- 与 Claude 方案最大区别：`high_value` 不是一个独立的“全量 thinking”档位。
- `high_value` 只是影响：
  - 是否进 `fast_prefilter`
  - batch 大小
  - 调度优先级
  - 空输出是否自动复核
  - 是否走专用 extractor

### 4.3.1 批次切分

建议目标：

| 路径 | target_tokens | max_chunks |
|---|---:|---:|
| `fast_prefilter` | 18k-24k | 40-60 |
| `flash_extract` | 20k-28k | 30-50 |
| `table_or_critical_extract` | 8k-16k | 8-24 |
| `pro_review` | 8k-12k | 8-24 |

说明：

- 这个预算比 Claude 方案更保守，因为当前痛点不是“模型吃不下”，而是“长批次拖慢首轮 throughput”。
- 正文和表格必须区别处理。

### 4.3.2 批次输入组织

planner / extractor 进入 prompt 时，至少应保留：

- `id`
- `chunk_type`
- `document_type`
- `section_title`
- `source_locator`
- `page_start`
- `sheet_name`
- `row_start`
- `row_end`
- `title`
- `text`
- `table_rows`

当前 `_serialize_chunk_for_prompt` 丢了 `document_type` / `section_title` / 页表定位信号，这会让模型做更多无谓判断。

## 4.4 两阶段抽取

### Stage 1: 候选筛选

目标：只找“可能包含投标约束的 chunk / table”。

方式：

- 规则 + 轻量 prompt 混合
- 过滤：
  - 目录
  - 纯说明
  - 背景介绍
  - 页眉页脚
  - 空白模板

输出：

- `candidate_chunk_ids`
- `candidate_reason`
- `candidate_kind`：`text` / `table` / `mixed`

优势：

- 这是 GitHub 外部方案里最值得借鉴的提速方式
- 比单纯在 Stage 2 继续压 token 更有效

### Stage 2: 结构化 requirement 抽取

只对候选 chunk 做结构化抽取。

通用正文 prompt 输出建议：

- `category`
- `title`
- `requirement_text`
- `response_needed`
- `deliverable_type`
- `evidence_required`
- `is_veto`
- `is_hard_constraint`
- `ignored_for_pricing`
- `confidence`

表格专用 prompt 额外输出：

- `table_axis`
- `header_mapping`
- `row_selector`

### Stage 3: review / retry

保留当前已经实现的：

- 空输出 review
- 失败拆批 retry
- effort 降级或升级

新增：

- `flash_extract` 二次失败后升级 `pro_review`
- `table_or_critical_extract` 空输出直接进入 `pro_review`

## 4.5 Prompt v2

### 4.5.1 稳定前缀

固定区：

1. system role
2. 抽取判定规则
3. category 列表
4. JSON schema
5. 一到两个短示例

变量区：

1. `source_file`
2. `document_type`
3. `section_title`
4. `chunk_count`
5. `payload`

### 4.5.2 专用 prompt

至少拆 3 套：

1. 通用正文 requirement 抽取
2. 表格 requirement 抽取
3. 评分/资格/否决关键片段抽取

原因：

- 当前通用 prompt 同时吞正文和表格，模型负担过大
- 这类文档的慢与漏，很多都出在“表格被当自然语言总结”

## 4.6 AI Gateway 与 DeepSeek 参数策略

### 4.6.1 必做

1. 显式传 `thinking.type`
2. thinking 模式下剥离 `temperature` / `top_p` / penalties
3. 非 thinking 模式继续允许 `temperature=0.0`

### 4.6.2 推荐

1. 按 `quality_policy` 传 `max_tokens` hint
2. 记录 `reasoning_tokens`
3. 为流式模式补 usage 采集能力

### 4.6.3 不建议

1. 首轮把大部分 high_value 批次放进 thinking 模式
2. 因为官方说并发理论上宽松，就去掉本地限流

## 4.7 调度与限流

建议把 provider 限流从二元组扩成三元语义：

- `model`
- `thinking_enabled`
- `reasoning_effort`

建议优先级：

1. `pro_review`
2. `table_or_critical_extract`
3. `flash_extract`
4. `fast_prefilter`

建议并发起点：

| 路径 | 建议并发 |
|---|---:|
| `fast_prefilter` | 4-6 |
| `flash_extract` | 3-4 |
| `table_or_critical_extract` | 2-3 |
| `pro_review(high)` | 1-2 |
| `pro_review(max)` | 1 |

说明：

- 这是系统调度策略，不是 provider 能力上限声明。
- 最终值以首轮基线压测为准。

## 4.8 观测与验收

新增 batch metadata：

- `strategy_version`
- `quality_policy`
- `thinking_enabled`
- `stream`
- `queue_to_start_ms`
- `provider_latency_ms`
- `persist_latency_ms`
- `prompt_cache_hit_tokens`
- `prompt_cache_miss_tokens`
- `prompt_cache_hit_ratio`
- `output_tokens_to_max_ratio`
- `candidate_chunk_count`
- `review_reason`

新增报告脚本：

- `scripts/extract_baseline_compare.py`

输出：

- 总 wall-clock
- 各 policy P50/P95
- empty-output 数
- review 数
- failure 分布
- cache 命中分布
- 每 1000 chunk requirement 产出率

## 5. 分阶段实施清单

### Phase 0 已完成，不回退

- 主路径不再大面积使用 `pro/max`
- flash 批次切小
- 长事务问题修复
- review / retry / provider backoff 已接入基础能力

### Phase 1 观测补齐

- [ ] 记录 `queue_to_start_ms`
- [ ] 记录 `persist_latency_ms`
- [ ] 记录 `prompt_cache_hit_ratio`
- [ ] 记录 `output_tokens_to_max_ratio`
- [ ] 新增 `strategy_version` / `quality_policy` 元数据

### Phase 2 DeepSeek 参数治理

- [ ] 显式 `thinking.type`
- [ ] thinking 模式下剥离 `temperature` / `top_p` / penalties
- [ ] 为不同 `quality_policy` 传 `max_tokens` hint
- [ ] 补齐流式 usage 采集，确认是否默认开启

### Phase 3 Prompt 和 chunk 结构治理

- [ ] prompt 稳定前缀重排
- [ ] `_serialize_chunk_for_prompt` 补 `document_type` / `section_title` / 页表定位字段
- [ ] 通用正文 / 表格 / 关键条款 prompt 拆分

### Phase 4 Planner v2

- [ ] 引入 `strategy_version=tender_extract_v2`
- [ ] 引入四段 `quality_policy`
- [ ] 正文与表格分流切批
- [ ] pending 批次优先级排序

### Phase 5 两阶段抽取

- [ ] 新增 `fast_prefilter`
- [ ] Stage 2 只处理 candidate chunks
- [ ] `high_value` 批次默认小批且可复核，不默认 thinking

### Phase 6 验收

- [ ] 跑同一份完整招标包 v1 / v2 对比
- [ ] 输出 markdown 验收报告
- [ ] 根据数据决定是否把 v2 设为默认

## 6. 验收标准

第一轮建议门槛：

1. v2 总 wall-clock 明显优于当前线上策略，目标先看 `-25% ~ -45%`。
2. 高风险 requirement 数量和关键词覆盖不出现明显退化。
3. `pro_review` 占比不异常膨胀。
4. `fast_prefilter` 不得把明显资格/评分/否决 chunk 大量漏掉。
5. 无 `idle in transaction` 回归。
6. 无大规模 429/backoff 雪崩。

说明：

- cache 命中率先作为观测指标，不先写硬门槛。
- 若质量与时延冲突，以“首轮快筛 + 小批复核”优先，不回到“全量高思考”。

## 7. 风险

### 风险 1：prefilter 误杀关键 chunk

缓解：

- 先对高价值分类保守放宽
- 允许 `high_value` 走“弱过滤”
- 引入 review 关键词兜底

### 风险 2：表格专用 prompt 带来额外复杂度

缓解：

- 先只覆盖 `qualification / scoring / pricing_reference`
- 不一次性覆盖所有表格

### 风险 3：流式 usage 采集不到，影响验收

缓解：

- 未补齐 usage 前，不把 streaming 作为所有 policy 的默认

### 风险 4：策略过多导致排障困难

缓解：

- 所有 batch 强制写入 `strategy_version` 和 `quality_policy`
- 报告脚本按 policy 聚合

## 8. 参考来源

- DeepSeek Thinking Mode: https://api-docs.deepseek.com/guides/thinking_mode
- DeepSeek Context Caching: https://api-docs.deepseek.com/guides/kv_cache/
- DeepSeek V4 Release Notes: https://api-docs.deepseek.com/news/news260424
- AutoRFP: https://github.com/run-llama/auto_rfp
- OpenContracts: https://github.com/Open-Source-Legal/OpenContracts
- Docling: https://github.com/docling-project/docling
- MinerU: https://github.com/opendatalab/mineru
- Unstructured: https://github.com/Unstructured-IO/unstructured
- LangExtract: https://github.com/google/langextract

