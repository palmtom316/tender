# 招标文件 AI 解析耗时根因与 DeepSeek V4 优化方案

> 创建日期：2026-05-05  
> 状态：已批准，实施中  
> 范围：招标文件 source chunks → AI Gateway → DeepSeek V4 → project_requirement 落库  
> 目标：缩短完整招标包 AI 解析 wall-clock，同时保持需求抽取质量合格、可追踪、可回滚。

## 1. 结论摘要

当前耗时过长不是单纯“DeepSeek V4 Flash 慢”，而是 5 个复合瓶颈叠加，并且模型策略方向互相打架：

- Planner 已经把高价值文件计划为 `deepseek-v4-pro + reasoning_effort=max`，低价值文件计划为 `deepseek-v4-flash + no reasoning_effort`，但 worker 执行时没有使用 batch 表中的 `model` / `reasoning_effort`。
- 实际执行重新读取 `agent_config.extract` 或走 AI Gateway profile，因此可能出现“planner 要 pro、实际跑 flash”的情况。
- 一旦 `agent_config.extract` 配置为任意 DeepSeek V4 模型，当前 `_build_overrides()` 会给 primary 和 fallback 全部强制 `reasoning_effort=max`，包括 `deepseek-v4-flash`。
- DeepSeek 官方文档说明 V4 thinking 默认开启，普通请求默认 `high`，`max`主要用于复杂 Agent 场景；当前对所有 batch 强制 `max`会直接牺牲吞吐。
- 高价值 batch 目标 120k tokens、输出预算 65k、非流式长连接、无全局并发限流，和 DeepSeek “动态并发限制、10 分钟未开始推理会断连”的机制冲突。

对用户问题的直接回答：是，`planner 要 pro、实际跑 flash、所有 batch 被强制 reasoning_effort=max` 是核心根因之一，属于 P0 配置与执行路径错配。它解释了“既没有得到 pro 的质量收益，又丢掉 flash 的速度优势”的现象。但完整根因还包括 batch 粒度、非流式调用、并发调度、JSON/schema 与缓存使用不充分。

## 2. 官方文档依据

截至 2026-05-05 查阅 DeepSeek 官方文档：

- Chat Completion 只列出 `deepseek-v4-flash` 与 `deepseek-v4-pro` 两个 V4 模型；`reasoning_effort` 取值为 `high|max`；`thinking` 可 `enabled/disabled`，默认 enabled。  
  来源：https://api-docs.deepseek.com/api/create-chat-completion/
- Thinking Mode 文档说明普通请求默认 effort 为 `high`，复杂 agent 请求才自动使用 `max`；thinking mode 下 `temperature/top_p/presence_penalty/frequency_penalty` 不生效。  
  来源：https://api-docs.deepseek.com/guides/thinking_mode
- Models & Pricing 文档显示 V4 Flash / Pro 都支持 thinking/non-thinking、1M context、最高 384K 输出、JSON Output、Tool Calls；Flash 比 Pro 更便宜，Pro 当前有折扣但仍更慢更贵。  
  来源：https://api-docs.deepseek.com/quick_start/pricing
- JSON Output 文档要求设置 `response_format={"type":"json_object"}`，同时 prompt 必须明确要求 JSON 并给出 JSON 示例；也提示可能偶发 empty content，需要通过 prompt 缓解。  
  来源：https://api-docs.deepseek.com/guides/json_mode
- Context Caching 默认开启，但缓存命中依赖完全匹配的前缀单元；响应 usage 会返回 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`。  
  来源：https://api-docs.deepseek.com/guides/kv_cache
- Rate Limit 文档说明 DeepSeek 会基于服务负载动态限制并发，超限直接 429；请求未开始推理超过 10 分钟，服务端会关闭连接。  
  来源：https://api-docs.deepseek.com/quick_start/rate_limit

## 3. 本地代码证据

关键链路：

- `backend/tender_backend/api/tender_documents.py:887-904` 创建 run，并把 `build_extraction_batch_plan()` 的结果写入 `tender_ai_extraction_batch`。
- `backend/tender_backend/services/extract_service/ai_extraction_planner.py:122-129` 高价值 batch 计划为 `deepseek-v4-pro + max`，低价值 batch 计划为 `deepseek-v4-flash + None`。
- `backend/tender_backend/workers/tasks_extract.py:89-96` 执行 batch 时只传 `chunks/source_file/response_format`，没有传 `batch["model"]` 和 `batch["reasoning_effort"]`。
- `backend/tender_backend/services/extract_service/ai_requirements_extractor.py:184-211` 执行时重新读取 `agent_config.extract`，并对 primary/fallback 中所有 DeepSeek V4 模型强制 `reasoning_effort=max`。
- `ai_gateway/tender_ai_gateway/task_profiles.py:19-28` `extract_tender_requirements` profile 又定义为 `flash` primary、`pro` fallback，和 planner 的 high_value 路由并不一致。
- `ai_gateway/tender_ai_gateway/fallback.py:157-172` request-level `extra_body` 会被 provider override 的 `extra_body` 覆盖，实际执行参数以 override 为准。
- `backend/tender_backend/services/extract_service/ai_requirements_extractor.py:41-43` legacy extractor 仍保留 `200 chunks` 与 `concurrency=4`，worker 新路径虽然使用 preplanned batch，但没有全局 provider 并发控制。
- `backend/tender_backend/services/extract_service/ai_requirements_extractor.py:237-243` 使用非流式 HTTP POST，单个请求 timeout 2400 秒。
- `backend/tender_backend/services/extract_service/ai_requirements_extractor.py:47-80` prompt 要求输出 JSON 数组，但 API 请求传 `response_format={"type":"json_object"}`，schema 语义不完全一致。

## 4. 根因分级

### P0 根因：计划模型与实际模型脱钩

Planner 已经产生 batch 级模型计划，但 worker 不使用这些字段，导致可观测表中的 `model/reasoning_effort` 不能代表真实调用。这个问题会造成三类偏差：

- 性能评估偏差：看到 batch 表是 flash 或 pro，但真实请求可能不是。
- 质量策略失效：高价值文件本应进入 pro 路由，实际可能被 Gateway profile 的 flash primary 接管。
- 成本策略失效：低价值文件本应 flash/no max，实际可能被强制 max。

### P0 根因：`reasoning_effort=max` 被过度使用

DeepSeek 官方默认普通请求为 `high`，而当前代码只要模型名是 DeepSeek V4，就强制 `max`。这对招标包批量抽取很不合适：

- Flash 的主要价值是吞吐，强制 max 会抵消 flash 优势。
- Pro + max 应只用于否决项、资格、评分、失败复核、空输出复核等高价值/低频场景。
- `temperature=0.0` 在 thinking mode 下无效，当前请求仍传 temperature，说明调用参数没有按 V4 thinking 特性重新校准。

### P1 根因：大 batch + 非流式 + 高输出预算形成长连接瓶颈

高价值文件 batch 目标为 120k estimated tokens，Gateway profile 输出预算为 65,536 tokens。再叠加 pro/max 或 flash/max，单次请求很容易进入分钟级甚至十几分钟级。

当前没有 streaming，服务端开始推理前或生成中长时间无业务内容返回时，链路更容易出现 read timeout、502、Broken pipe。DeepSeek 文档也明确提到未开始推理超过 10 分钟会关闭连接。

### P1 根因：并发调度没有 provider-aware 限流

`run_tender_ai_extraction()` 会把所有 pending batch 逐个 `.delay()`，实际并发由 Celery worker 数量、队列和外部服务共同决定。代码没有按 DeepSeek 动态并发限制做全局 semaphore、429 backoff、per-model 并发池。

结果是：

- 并发过高时，部分请求排队或 429，wall-clock 反而变长。
- 多个 pro/max 大 batch 同时发出时，队列等待可能超过 DeepSeek 的 10 分钟连接阈值。
- 失败重试目前只是重新 pending，没有缩批、降 effort、切模型或指数退避。

### P1 根因：Prompt 和 schema 没有最大化 JSON/缓存能力

当前 prompt 要求“只输出 JSON 数组”，但请求设置 `json_object`。DeepSeek JSON Output 文档建议给出 JSON 示例并合理设置 max_tokens，且提示 empty content 风险。当前没有 `batch_quality`，导致高价值 batch 空输出也可能被标记为 succeeded。

缓存方面，当前可复用的 system prompt 很短；user prompt 中 `source_file/chunk_count` 早于主要规则和 schema，会降低大段稳定前缀的缓存收益。官方缓存是前缀匹配，应该把稳定规则、schema、示例放在变量 payload 前面，并记录 `prompt_cache_hit_tokens`。

### P2 根因：质量门禁不足，耗时优化缺少闭环

当前成功标准主要是请求成功和 JSON 可解析，缺少这些硬门禁：

- 高价值 batch 输出 0 条但输入包含明显关键词时，应自动复核或进入 `needs_review`。
- `dropped_invalid` 过高时，应按 schema/prompt 问题处理，而不是仅记录。
- 没有记录 `finish_reason`、`reasoning_tokens`、cache hit/miss、planned vs actual model，因此无法判断时间花在排队、输入处理、reasoning、输出生成还是重试。

## 5. 改进原则

- 以 batch 表为执行事实来源：worker 必须执行 batch 的 `model/reasoning_effort/response_format/max_retries`。
- Flash 走吞吐路线：普通 requirements 初抽默认 `deepseek-v4-flash`，优先 non-thinking 或默认 high，不允许全量 max。
- Pro 走质量路线：仅高价值、失败复核、空输出复核、摘要/评分关键任务使用 `deepseek-v4-pro`，默认 `high`，只有复核或争议 batch 使用 `max`。
- 所有长输出走 streaming：降低长连接风险，并保留 usage 汇总。
- Prompt cache 友好：稳定规则和 schema 前置，变量 payload 后置，记录 cache hit/miss。
- 质量不能靠“少抽”换速度：用两阶段抽取和复核，而不是简单降模型。

## 6. 待批准实施方案

### Phase 0：加观测，不改行为

- [x] 在 AI Gateway `CompletionResult` 增加 `finish_reason`、`prompt_cache_hit_tokens`、`prompt_cache_miss_tokens`、`reasoning_tokens`。
- [x] 在 batch metadata 记录 `planned_model`、`planned_reasoning_effort`、`actual_model`、`actual_reasoning_effort`、`used_fallback`、`finish_reason`、cache token 与 reasoning token。
- [ ] 在 worker 日志增加 batch 级 `queue_to_start_ms`、`provider_latency_ms`、`persist_latency_ms`。
- [ ] 输出一份当前基线报告：总耗时、每 batch 耗时、失败类型、0 输出 batch、dropped_invalid、cache 命中率。

验收：

- 任一 batch 能明确回答“计划跑什么、实际跑什么、为什么慢”。
- 不改变现有抽取结果。

### Phase 1：修正模型执行路径

- [x] 修改 `extract_requirements_for_batch()` 签名，接收 `model`、`reasoning_effort`、`fallback_model` 或完整 provider override。
- [x] 修改 `tasks_extract.py`，从 `tender_ai_extraction_batch` 读取 `model/reasoning_effort` 并传入 extractor。
- [x] 修改 `_build_overrides()`，只有显式传入 `reasoning_effort` 时才写入 extra_body；不再对所有 DeepSeek V4 统一强制 max。
- [x] 将 `deepseek_api.py` 默认 effort 从 `max` 改为显式策略常量：`None/high/max`，禁止 helper 静默默认 max。
- [x] 单测覆盖：preplanned batch 实际调用 pro/max；low_value/flash batch 实际调用 flash 且不带 max。

验收：

- batch 表 `model/reasoning_effort` 与 AI Gateway 实际请求一致。
- Flash batch 不再自动带 `reasoning_effort=max`。

### Phase 2：重做模型路由策略

建议默认策略从 `v4_flash_then_pro` 改成更明确的三段式：

| 场景 | 模型 | thinking / effort | 目的 |
|---|---|---|---|
| 普通附件、合同模板、非核心说明 | `deepseek-v4-flash` | `thinking disabled` 或不传 effort | 快速初抽 |
| 招标正文、资格、技术、递交、评分 | `deepseek-v4-flash` 初抽 + 关键词覆盖门禁 | 不传 max | 快速召回候选 |
| 高价值缺口复核、否决项复核、失败重试第二阶段 | `deepseek-v4-pro` | `high`，必要时 `max` | 保质量 |
| 摘要、评分表结构化 | `deepseek-v4-pro` | `high` | 小输入高准确 |

- [ ] Planner 增加 `strategy_version=tender_extract_v2`。
- [ ] 增加 batch `quality_policy`：`fast_candidate`、`high_value_candidate`、`pro_review`。
- [ ] 第一次抽取优先减少 pro/max 数量；只有命中质量门禁才触发 pro review。
- [ ] 对否决项、资格、评分关键词命中的 source chunks 建立小型 review batch，而不是整文件 pro/max。

验收：

- 完整包初抽 wall-clock 下降，但高价值文件仍有复核闭环。
- pro/max 请求数量可解释、可追踪，不超过总 batch 的约 10%-25%，具体以质量门禁触发为准。

### Phase 3：流式与并发控制

- [x] AI Gateway 对 `extract_tender_requirements` 支持 `stream=true`，并聚合 SSE 内容；当前 stream 分支保留 `finish_reason`，cache/reasoning usage 仍以非流式返回为准。
- [x] Worker 增加 per-model 并发限制：flash 并发高于 pro，pro/max 并发最低。
- [x] 对 429、ReadError、502 增加指数退避；第一次失败会按 backoff 重新入队。
- [x] 第一次失败优先缩批或降 effort，不立即重复同一大请求。
- [ ] 将超大 batch 拆为更稳定的 20k-60k 输入；高价值只在复核小 batch 使用 max。

建议初始限流：

- `deepseek-v4-flash`：全局并发 2-4。
- `deepseek-v4-pro high`：全局并发 1-2。
- `deepseek-v4-pro max`：全局并发 1。

验收：

- 不再出现批量 429 或长时间无响应导致的批量失败。
- 单 batch P95 latency 可控，失败 batch 可自动进入下一阶段策略。

### Phase 4：Prompt、JSON schema 与缓存优化

- [x] 将输出从裸 JSON 数组改为 JSON object：

```json
{
  "requirements": [],
  "batch_quality": {
    "has_requirements": false,
    "coverage_note": "",
    "suspected_missing": false
  }
}
```

- [x] prompt 中加入完整 JSON 示例，满足 DeepSeek JSON Output 文档要求。
- [ ] 稳定 system/rules/schema/example 放在 user prompt 前半段，`source_chunks` payload 放最后，提升前缀缓存命中。
- [ ] 记录并展示 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`。
- [ ] 保留 strict Tool Calls spike；如果 DeepSeek strict tool 在实测中稳定，再切到 tool schema，否则继续 JSON Output。

验收：

- `dropped_invalid` 明显下降。
- 空输出 batch 必须带 `batch_quality` 说明；高价值空输出不能直接 completed。
- cache hit tokens 在重复/复核请求中可见。

### Phase 5：质量门禁与复核

- [x] 高价值 batch 输出 0 条且输入包含资格、评分、否决、递交、技术响应等关键词时，自动创建 `pro_review` batch。
- [x] `pro_review` batch 若仍为空输出，进入 `needs_review`。
- [ ] `dropped_invalid / raw_items` 超过阈值时进入 `needs_review`。
- [ ] 对每个 source_file 计算覆盖率：covered chunks、requirements count、zero-output reason。
- [ ] 增加前 20 条人工抽样报告模板，要求 title/category/source_chunk_id/requirement_text 四项合格率。

建议合格线：

- 高价值文件 0 输出率：0，除非 `batch_quality.has_requirements=false` 且人工可解释。
- 幻觉 chunk_id：0 写库。
- 非法 category：0 写库，且 dropped_invalid 率低于 5%。
- 前 20 条抽样：至少 16 条 title/category/source 定位合格。
- 否决/资格/评分关键词覆盖：不得低于规则抽取候选的 95%，缺口进入复核。

## 7. 预期收益

保守预期：

- 去掉全量 `reasoning_effort=max` 后，flash batch 延迟显著下降。
- 修正 planner/executor 脱钩后，高价值质量策略真实生效。
- streaming + 限流后，ReadError/502/Broken pipe 数量下降。
- cache-friendly prompt 和 usage 观测后，可区分输入缓存、reasoning、输出生成的耗时来源。

目标指标：

| 指标 | 当前风险 | 目标 |
|---|---:|---:|
| 完整包 requirements 初抽 wall-clock | 10-50 分钟级不稳定 | ≤ 10-15 分钟 |
| 单 batch P95 latency | 不可解释 | ≤ 3-6 分钟 |
| failed/needs_review batch | 可能隐性成功 | 0 failed，needs_review 可解释 |
| 高价值空输出 | 可能 succeeded | 自动复核或 needs_review |
| planned vs actual model 一致率 | 无法保证 | 100% |
| flash batch 强制 max | 可能大量存在 | 0 |

## 8. 风险与回滚

- 如果 flash non-thinking 质量不足，回滚到 flash thinking default/high，但仍禁止全量 max。
- 如果 streaming 对 usage 统计不完整，先保留非流式作为 fallback，但大 batch 仍强制拆小。
- 如果 strict Tool Calls 不稳定，继续使用 JSON Output object schema。
- 如果并发限流过保守，优先增加 flash 并发，不增加 pro/max 并发。
- 所有改动通过 `strategy_version` 和 batch metadata 标记，可按 run 级别对比 v1/v2。

## 9. 建议实施顺序

1. 先做 Phase 0 和 Phase 1：这是修正根因的最小闭环，风险低，能立即证明“planner 和实际执行一致”。
2. 再做 Phase 3 的限流与 streaming：解决长连接和外部服务动态并发问题。
3. 同步做 Phase 4 的 JSON object schema：降低空输出和解析失败。
4. 最后做 Phase 2/5 的完整质量路由：用实测数据决定 flash/pro/high/max 的触发阈值。

## 10. 待批准事项

- [x] 是否批准按本方案 Phase 0-1 先实施最小修复。
- [ ] 是否允许跑一次真实包基线，用于对比优化前后耗时与质量。
- [ ] 是否将默认策略从 `v4_flash_then_pro` 调整为 `flash_candidate_then_targeted_pro_review`。
- [ ] 是否允许启用 streaming 作为 `extract_tender_requirements` 默认调用方式。

## 11. 实施记录

### 2026-05-05 Phase 0/1 最小修复

- `extract_requirements_for_batch()` 开始接收 batch 级 `model/reasoning_effort`，worker 执行时从 `tender_ai_extraction_batch` 读取并传入。
- `_build_overrides()` 不再对 preplanned batch 隐式添加 `reasoning_effort=max`；legacy `extract_requirements_with_ai()` 暂时保留旧 max 行为以降低兼容风险。
- `deepseek_api.py` 的 helper 不再默认 max，调用方必须显式传 `high` 或 `max`。
- AI Gateway response 增加 `finish_reason`、`prompt_cache_hit_tokens`、`prompt_cache_miss_tokens`、`reasoning_tokens`。
- 已运行测试：`backend` 35 passed；`ai_gateway` 11 passed。

### 2026-05-05 Phase 3/4/5 最小增量

- requirements prompt 输出从 JSON 数组改为 JSON object，包含 `requirements[]` 与 `batch_quality`，同时保留旧数组解析兼容。
- extractor 支持 `stream` 参数透传到 AI Gateway；Gateway stream 分支聚合内容并记录 `finish_reason`。
- 高价值 batch 若 0 输出且包含资格、评分、否决、递交、技术响应等关键词，worker 标记 `needs_review`，避免隐性成功。
- 已运行测试：`backend` 41 passed；`ai_gateway` 11 passed。

### 2026-05-05 Phase 3/5 复核与限流增量

- 新增 `retry_policy.py`，集中管理 per-model 并发阈值、429/ReadError/502/timeout backoff、`pro_review` batch index 规则。
- Worker 调度和执行入口增加 provider-aware 限流：`deepseek-v4-flash` 默认 4 并发，`deepseek-v4-pro` 默认 2 并发，`deepseek-v4-pro + max` 默认 1 并发。
- 429、ReadError、ReadTimeout、ConnectError、502、Broken pipe 等错误会按指数 backoff 重新入队。
- 高价值空输出不再只停在 `needs_review`：首次命中会创建 `deepseek-v4-pro + reasoning_effort=max` 的 `pro_review` batch；复核 batch 若仍为空才进入 `needs_review`。
- 已运行测试：`backend` 50 passed；`ai_gateway` 11 passed。

### 2026-05-05 Phase 3 剩余风险关闭

- 首次 429、ReadError、ReadTimeout、ConnectError、502、Broken pipe 等传输/限流失败不再原样重跑父 batch。
- Worker 会创建拆分后的 retry batches：最多 4 份，继承原 chunk ids 子集，父 batch 标记为 superseded 且 `chunk_count=0`，避免覆盖率重复计算。
- retry batch 会降 effort：`max -> high -> none`，减少重复进入慢路径的概率。
- retry batch metadata 记录 `retry_of_batch_id`、`retry_part_index`、`retry_part_count`、`retry_strategy`、原模型与原 reasoning。
- 已运行测试：`backend` 56 passed；`ai_gateway` 11 passed。
