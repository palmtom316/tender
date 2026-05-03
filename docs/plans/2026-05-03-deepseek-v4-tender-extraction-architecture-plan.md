# DeepSeek V4 招标文件完整抽取与异步架构修订计划

> **创建日期：** 2026-05-03  
> **计划类型：** 批准前可跟踪修订计划  
> **执行状态：** 已批准，实施中  
> **范围：** 招标文件 source chunks → AI 抽取 → project_requirement 落库的完整性、可恢复性、耗时架构改造

## 1. 背景与问题

当前 `POST /api/tender-documents/{id}/ai-extract-requirements` 以同步 HTTP 请求运行完整招标包 AI 抽取。真实包 1 已暴露以下问题：

- 大包抽取耗时约 52 分钟，超出同步接口应承载的范围。
- AI Gateway / 外部模型调用出现 `ReadError`、`502 Bad Gateway`、`Broken pipe`。
- 单批失败被汇总为 0 结果，接口仍可能返回 200，导致用户只看到“覆盖不足”，但系统没有可重试对象。
- `采购文件（服务）.docx` 已完整解析为 682 chunks，但某次抽取仅成功 82 chunks 批次，产生 18 条 requirements，造成“像是只解析前半部分”的误判。
- 目前缺少批次级状态、断点续跑、失败重试、覆盖率门禁和完成判定。

## 2. DeepSeek V4 官方能力要点

本计划依据 DeepSeek 官方 API 文档截至 2026-05-03 的公开说明：

- `deepseek-v4-flash` 和 `deepseek-v4-pro` 是当前推荐的 V4 模型。
- V4 支持 1M tokens 上下文、最高 384K 输出能力，适合减少“按 200 chunks 机械切批”的批次数。
- V4 支持 thinking 开关与 `reasoning_effort=high|max`；高推理应只用于高价值、低频、需要完整召回的阶段。
- DeepSeek API 支持 JSON Output，可要求模型输出合法 JSON 对象。
- DeepSeek API 支持 Tool Calls，并支持 strict mode/schema，以减少字段缺失、类型漂移和非法 category。
- DeepSeek API 支持 Streaming，长输出任务应优先流式接收，避免长时间无响应导致连接中断。
- DeepSeek 默认支持 Context Caching，重复前缀可命中缓存；稳定 system/schema/header prompt 有利于降低延迟与成本。
- DeepSeek 文档提示：若请求 10 分钟仍未开始推理，连接可能被服务器主动断开；本系统必须避免依赖单个超长同步连接。

官方文档入口：

- https://api-docs.deepseek.com/
- https://api-docs.deepseek.com/quick_start/pricing
- https://api-docs.deepseek.com/guides/kv_cache
- https://api-docs.deepseek.com/guides/thinking_mode

## 3. 修订目标

### 3.1 完整性目标

- 每个可抽取 source chunk 必须归属到一个可跟踪 batch。
- 每个 batch 必须有独立状态：`pending/running/succeeded/failed/skipped`。
- 任一 batch 失败时，整体 run 不得标记为 completed。
- 支持只重试失败 batch，不重跑整个文档。
- 支持按文件、batch、chunk 三层查看覆盖状态。
- 明确区分“业务上可跳过文件”和“抽取失败文件”。

### 3.2 耗时目标

- HTTP API 只创建任务并返回 `run_id`，不等待完整 AI 抽取结束。
- worker 后台处理，前端/调用方轮询进度。
- 单个 AI 调用目标耗时控制在 3-8 分钟内；超过阈值自动降级、拆批或重试。
- 包 1 完整 AI 抽取 wall-clock 目标：初版 ≤ 20 分钟，优化后 ≤ 10 分钟。
- 支持并发但有全局限流，避免多个超大 batch 同时打爆模型连接。

### 3.3 DeepSeek V4 利用目标

- 用 `deepseek-v4-flash` 做高速候选召回、低风险分类和普通附件抽取。
- 用 `deepseek-v4-pro + reasoning_effort=max` 做高价值文件/失败批次/争议批次的复核与补抽。
- 使用 JSON Output 或 strict Tool Calls 固化 schema。
- 使用 Streaming 接收长输出，降低 ReadError/Broken pipe 风险。
- 稳定 prompt 前缀和 schema，利用 Context Caching。
- 利用 1M context 做“文件级或大段级抽取”，但仍保留 batch checkpoint，不能回到单请求不可恢复模式。

## 4. 目标架构

### 4.1 流程

1. 用户调用 `POST /api/tender-documents/{id}/ai-extraction-runs`。
2. 后端创建 `tender_ai_extraction_run`，生成文件级/批次级 `tender_ai_extraction_batch`。
3. API 立即返回 `run_id`、批次数、初始状态。
4. Celery worker 从 `ai_tasks` 队列消费 batch。
5. 每个 batch 调 AI Gateway，结果即时落库 `project_requirement`。
6. batch 成功则记录 token、模型、耗时、命中 chunks、输出条数。
7. batch 失败则记录 error_type/error_message/retry_count，下次只重试该 batch。
8. run 聚合 batch 状态；全部 terminal 且无 failed 才进入 `completed`。
9. 前端/调用方通过 `GET /api/tender-ai-extraction-runs/{run_id}` 查看进度、失败文件和覆盖率。

### 4.2 模型路由

| 阶段 | 模型 | reasoning | 目的 |
|---|---|---:|---|
| 候选召回 | `deepseek-v4-flash` | off 或默认 | 快速抽取普通条款，降低总耗时 |
| 高价值文件抽取 | `deepseek-v4-pro` | `max` | 招标文件正文、否决项、资格、评分、递交要求 |
| 失败批次重试 | 先 flash 后 pro | high/max | 首次失败降并发/缩批；重复失败切 pro |
| 质量复核 | `deepseek-v4-pro` | max | 对零覆盖但疑似有要求的文件做二次检查 |
| 摘要/评分表 | pro 或 flash+pro | high/max | 独立结构化任务，不阻塞 requirements 主抽取 |

### 4.3 批次策略

从固定 `200 chunks` 改为动态 token-aware batch：

- 按 `source_file` 分组，保留文件边界。
- 估算每个 chunk token/字符量。
- 普通 batch 目标输入 20k-60k tokens。
- 高价值正文文件可合并到 80k-150k tokens，利用 V4 1M context 减少批次数。
- 表格大文件按 sheet/table 分 batch，不把整张超大表无差别塞入 prompt。
- 空白合同、签名文件、纯价格公式附件可通过分类策略标记 `skipped`，但必须有 skip reason。
- 每个 batch 存 `chunk_id[]`，输出只能引用该数组内 chunk。

### 4.4 输出 schema

优先采用 strict Tool Calls；如果兼容性不足，则采用 JSON Output。

目标 schema：

```json
{
  "requirements": [
    {
      "source_chunk_id": "uuid",
      "category": "qualification|technical|business|scoring|contract|submission|veto|special|schedule|pricing|quality|safety",
      "title": "string",
      "requirement_text": "string",
      "is_veto": true,
      "is_hard_constraint": true,
      "ignored_for_pricing": false,
      "confidence": 0.9
    }
  ],
  "batch_quality": {
    "has_requirements": true,
    "coverage_note": "string",
    "suspected_missing": false
  }
}
```

验收规则：

- `source_chunk_id` 不在 batch 输入内的输出直接丢弃。
- 非法 category 直接丢弃并计入 `dropped_invalid`。
- 空 requirements 只有在 `batch_quality.has_requirements=false` 且说明合理时才视为成功。
- 高价值文件出现空输出时进入 `needs_review` 或自动二次模型复核。

## 5. 数据库修订

### 5.1 新增 migration 0033：AI 抽取任务表

`backend/tender_backend/db/alembic/versions/0033_tender_ai_extraction_runs.py`

新增 `tender_ai_extraction_run`：

- `id UUID PK`
- `tender_document_id UUID FK`
- `project_id UUID FK`
- `status TEXT`：`pending/running/completed/failed/partial/cancelled`
- `mode TEXT`：`requirements|facts|scoring|full`
- `model_policy TEXT`：如 `v4_flash_then_pro`
- `total_batches INT`
- `succeeded_batches INT`
- `failed_batches INT`
- `skipped_batches INT`
- `total_chunks INT`
- `covered_chunks INT`
- `extracted_requirements INT`
- `total_input_tokens INT`
- `total_output_tokens INT`
- `error TEXT NULL`
- `metadata_json JSONB`
- `created_at/updated_at/started_at/finished_at`

新增 `tender_ai_extraction_batch`：

- `id UUID PK`
- `run_id UUID FK`
- `tender_document_id UUID FK`
- `tender_document_file_id UUID NULL FK`
- `source_file TEXT`
- `batch_index INT`
- `status TEXT`：`pending/running/succeeded/failed/skipped/needs_review`
- `chunk_ids UUID[]` 或 `chunk_ids_json JSONB`
- `chunk_count INT`
- `input_char_count INT`
- `estimated_input_tokens INT`
- `model TEXT`
- `reasoning_effort TEXT NULL`
- `response_format TEXT`：`json_object|tool_strict|text`
- `retry_count INT`
- `max_retries INT`
- `input_tokens INT`
- `output_tokens INT`
- `latency_ms INT`
- `extracted_requirements INT`
- `dropped_invalid INT`
- `error_type TEXT NULL`
- `error_message TEXT NULL`
- `skip_reason TEXT NULL`
- `metadata_json JSONB`
- `created_at/updated_at/started_at/finished_at`

索引：

- `(tender_document_id, status)`
- `(run_id, status)`
- `(run_id, source_file, batch_index)` unique
- `(tender_document_file_id, status)`

## 6. 后端服务修订

### 6.1 Repository

新增：

- `backend/tender_backend/db/repositories/tender_ai_extraction_repo.py`

职责：

- 创建 run。
- 批量创建 batch。
- 领取 pending batch，标记 running。
- 写入 succeeded/failed/skipped。
- 聚合 run 进度。
- 查询失败 batch 与零覆盖文件。

### 6.2 Planner

新增：

- `backend/tender_backend/services/extract_service/ai_extraction_planner.py`

职责：

- 读取 source chunks。
- 按文件分类、chunk 类型、token 估算生成 batch plan。
- 识别可跳过文件并写 skip reason。
- 标记高价值文件：招标正文、采购文件、评分、资格、递交要求、技术规范、合同补充条款。

### 6.3 Worker

新增：

- `backend/tender_backend/workers/tasks_extract.py`

Celery task：

- `run_tender_ai_extraction(run_id)`：调度批次。
- `run_tender_ai_extraction_batch(batch_id)`：执行单 batch。
- `retry_failed_tender_ai_extraction_batches(run_id)`：只重试失败 batch。

队列：

- 新增 `ai_tasks`，不要复用 `io_tasks`，避免 OCR/Office 解析和 AI 长任务互相阻塞。

### 6.4 Extractor

改造：

- `extract_requirements_with_ai()` 保留为底层 batch 执行器。
- 新增 `extract_requirements_for_batch(batch, chunks, model_policy)`。
- 支持 strict Tool Calls / JSON Output。
- 支持 streaming 接收长结果。
- 失败时返回结构化错误，不吞为 0 结果。
- 每批落库后更新 batch 状态，确保进程崩溃可恢复。

### 6.5 AI Gateway

修订：

- `ChatRequest` 增加 `stream: bool` 和 `response_format` 支持。
- `call_with_fallback()` 支持 DeepSeek JSON Output / Tool Calls strict schema。
- 对 `extract_tender_requirements` 增加更细 profile：
  - `extract_tender_requirements_fast`
  - `extract_tender_requirements_strict`
  - `extract_tender_requirements_repair`
- 明确 V4 参数：
  - flash 默认不启用 max reasoning。
  - pro 仅在高价值/重试/复核启用 `reasoning_effort=max`。
- 记录 provider latency、first token latency、cache hit 信息（如 API 返回）。

## 7. API 修订

新增：

- `POST /api/tender-documents/{id}/ai-extraction-runs`
  - 创建异步 run。
  - 参数：`mode`、`model_policy`、`force_replan`、`only_failed`。
  - 返回：`run_id`、`status`、`total_batches`。

- `GET /api/tender-ai-extraction-runs/{run_id}`
  - 返回 run 进度、token、耗时、失败统计、覆盖率。

- `GET /api/tender-ai-extraction-runs/{run_id}/batches`
  - 返回 batch 明细，支持 `status` 过滤。

- `POST /api/tender-ai-extraction-runs/{run_id}/retry-failed`
  - 只重试 failed/needs_review batch。

- `POST /api/tender-ai-extraction-runs/{run_id}/cancel`
  - 取消 pending batch，running batch 完成后不继续调度。

保留但降级：

- `POST /api/tender-documents/{id}/ai-extract-requirements`
  - 改为兼容 wrapper：创建 run 并返回 `202 Accepted` 风格响应。
  - 不再同步等待完整抽取。

## 8. 前端与可观测性

前端新增“AI 抽取进度”面板：

- 总体状态：pending/running/completed/partial/failed。
- 文件覆盖表：文件名、chunks、batches、requirements、失败批次、skip reason。
- 失败批次列表：error_type/error_message/retry_count。
- 操作：重试失败、取消、查看 source chunks。

后端日志和指标：

- `ai_extraction_run_started/finished`
- `ai_extraction_batch_started/succeeded/failed/skipped`
- `ai_extraction_batch_retry_scheduled`
- 每批记录：model、reasoning_effort、tokens、latency、requirements、dropped_invalid。

## 9. 阶段计划

### Phase 0 — 计划批准

- [x] 用户批准本计划。
- [x] 明确允许新增 migration 0033。
- [x] 明确保留旧同步接口为 wrapper。

### Phase 1 — 任务表与 Planner

- [x] 新增 `0033_tender_ai_extraction_runs.py`。
- [x] 新增 `TenderAiExtractionRepository`。
- [x] 新增 `ai_extraction_planner.py`。
- [x] 单测覆盖：文件分组、token-aware batch、高价值文件识别、skip reason。

验收：

- [ ] 对包 1 可生成完整 batch plan。（本轮按用户要求不跑完整招标文件抽取/端到端）
- [x] 每个有内容 source chunk 都归属到 batch 或有 skip reason。（单测覆盖）

### Phase 2 — 异步 Worker 与 API

- [x] 新增 `ai_tasks` 队列配置。
- [x] 新增 `tasks_extract.py`。
- [x] 新增 run 创建/查询/retry/cancel API。
- [x] 旧同步接口改为创建 run，不再长时间阻塞。
- [x] 单测覆盖 planner/repo/Celery 路由与失败批次重试基础行为。

验收：

- [ ] API 创建 run 后 1 秒内返回。（待集成/端到端验证）
- [x] worker 可后台处理 batch。（代码路径已接入，待集成验证）
- [x] 失败 batch 可单独重试。

### Phase 3 — DeepSeek V4 Schema 与 Streaming

- [x] AI Gateway 支持 `response_format` / JSON Output。
- [ ] AI Gateway 支持 strict tool schema（若兼容测试通过）。
- [x] AI Gateway 支持 streaming 聚合结果。
- [x] Extractor 改用 JSON Output 参数。
- [ ] 非法输出进入 `dropped_invalid`，不影响 batch 状态判断。

验收：

- [ ] JSON 解析失败率 < 1%。
- [ ] 不再出现长时间无响应导致的整批不可见失败。

### Phase 4 — 模型路由与重试策略

- [ ] 实现 `v4_flash_then_pro` 策略。
- [ ] 高价值文件默认 pro/max，普通文件 flash。
- [ ] 首次失败：降低并发或缩批重试。
- [ ] 二次失败：切 pro/max 或进入 `needs_review`。
- [ ] 空输出高价值 batch 自动复核。

验收：

- [ ] 包 1 `failed_batches=0` 或全部失败批次可重试恢复。
- [ ] 高价值文件不得因为一次空输出被标记完成。

### Phase 5 — 前端进度与运维闭环

- [ ] 前端显示 run/batch/file 覆盖状态。
- [ ] 支持一键重试失败批次。
- [ ] 显示 zero requirement 文件与 skip reason。
- [ ] 输出端到端验收报告。

验收：

- [ ] 用户能直接看到“哪些文件未覆盖、原因是什么、如何重试”。
- [ ] 不再需要 `rerun_missing_files.py` 这类人工脚本。

## 10. 验收指标

| 指标 | 目标 |
|---|---:|
| 创建 AI 抽取任务 API 响应时间 | ≤ 1 秒 |
| 包 1 完整抽取 wall-clock 初版 | ≤ 20 分钟 |
| 包 1 完整抽取优化后 | ≤ 10 分钟 |
| run 完成时 failed batch | 0 |
| 无解释 zero requirement 高价值文件 | 0 |
| 每个有内容 chunk 的 batch 归属率 | 100% |
| 每个 failed batch 可重试率 | 100% |
| JSON/schema 解析失败率 | < 1% |
| 人工脚本补跑需求 | 0 |

## 11. 风险与决策点

- DeepSeek strict Tool Calls 与当前 OpenAI SDK 兼容性需要小样本验证；若不稳定，先用 JSON Output。
- 1M context 不等于应把整包塞入一次请求；仍需 batch checkpoint，否则恢复性差。
- pro/max 会提升质量但增加耗时和成本，必须按文件价值路由。
- Streaming 能降低长连接风险，但 worker 仍需任务级超时与重试。
- 需要新增 `ai_tasks` worker，部署时必须启动对应 Celery worker。

## 12. 批准后首批实施文件

预计修改/新增：

- `backend/tender_backend/db/alembic/versions/0033_tender_ai_extraction_runs.py`
- `backend/tender_backend/db/repositories/tender_ai_extraction_repo.py`
- `backend/tender_backend/services/extract_service/ai_extraction_planner.py`
- `backend/tender_backend/services/extract_service/ai_requirements_extractor.py`
- `backend/tender_backend/workers/celery_app.py`
- `backend/tender_backend/workers/tasks_extract.py`
- `backend/tender_backend/api/tender_documents.py`
- `ai_gateway/tender_ai_gateway/api/chat.py`
- `ai_gateway/tender_ai_gateway/fallback.py`
- `ai_gateway/tender_ai_gateway/task_profiles.py`
- `infra/docker-compose.yml`
- 对应 backend / ai_gateway 单测与必要集成测试

## 13. 批准口径

批准本计划即表示同意：

- 将 AI requirements 抽取从同步 HTTP 改为异步 run/batch 架构。
- 新增 migration 0033。
- 新增 `ai_tasks` Celery 队列和 worker 配置。
- 旧同步接口改为兼容入口，不再执行 50 分钟级同步抽取。
- DeepSeek V4 使用策略从“所有任务 pro/max”改为“flash 快速抽取 + pro/max 高价值/重试/复核”。
