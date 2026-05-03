# 招标文件 AI 解析升级实施计划

> **创建日期：** 2026-05-02
> **计划类型：** 可跟踪 to-do 实施计划
> **范围：** Docker 依赖固化 + AI 关键条款抽取 + AI 招标摘要 + 原文对照 UI + 评分表 AI 结构化

## Goal

将当前**纯关键词规则**的招标解析升级为 **AI 主导 + 关键词兜底**：

- 关键条款由 deepseek-v4-pro（reasoning_effort=max）抽取，保留 source_chunk 链接，前端可一键回看原文。
- 招标摘要（项目名称/招标人/控制价/保证金/开标时间/工期/质量要求等）由 AI 单点提取，落库 `tender_summary`，作为项目首屏卡片。
- 评分表（技术评分/商务评分细则）由 AI 结构化为 dimension/max_score/scoring_method/sub_items，落库 `project_scoring_criteria`。
- 系统所有运行依赖（含 LibreOffice、openpyxl、python-docx 等）固化进 Docker 镜像，`docker compose up` 即起即用。

## Core Principles

- AI 抽取**叠加**关键词结果，不替换；通过 `extraction_method` 字段（`keyword`/`ai`/`merged`）区分，便于审计与回退。
- 模型策略：tender 解析任务首选 `deepseek-v4-pro` + `reasoning_effort=max`，fallback `deepseek-v4-flash`；其他任务保持 flash。
- 切块策略：按 `source_file` 分组，每文件 1 次 AI 调用为主；单文件超 200k 字符或 400 chunks 才切块。整包 18 个文件预计 ≤25 次调用。
- 所有 AI 输出必须带 `source_chunk_id`；幻觉的 chunk_id 直接丢弃，不写库。
- v4-pro 通过 `_V4_PRO_ALLOWED_TASKS` 白名单放行，仅限 `extract_tender_*` / `extract_scoring_criteria` 三类任务，避免成本失控。
- 失败隔离：单批 AI 调用失败不影响其他批，结果汇总返回 `failed_batches` 计数。
- 不动现有 `keyword` 抽取链路与 UI；新功能走新接口、新组件，灰度并行。

## Target Deliverables

- [x] Docker 镜像固化所有依赖（含 LibreOffice）
- [x] AI 关键条款抽取器 + API + 单测
- [ ] 端到端跑通包1，给出 AI vs keyword 对比
- [ ] AI 招标摘要表 + 抽取器 + API + 前端摘要卡片（后端已完成，前端待做）
- [ ] 原文对照 UI（点击 requirement → 侧滑 source_chunk）
- [ ] 评分表 AI 结构化表 + 抽取器 + API

## Phases

### Phase 1 — Docker 依赖固化 ✅

- [x] `backend/Dockerfile`：python:3.12-slim + libreoffice-core/writer/calc + fonts-noto-cjk + `pip install -e .[dev]`
- [x] `ai_gateway/Dockerfile`：python:3.12-slim + `pip install -e .[dev]`
- [x] `infra/docker-compose.yml`：backend / ai-gateway / worker-io 改 `build:`，APP_ENV 改 `development`，`DEEPSEEK_API_KEY` 透传
- [x] 端到端冒烟：包1 `.doc` / `.wps` / `.xlsx` 全部解析成功，2387 chunks

### Phase 2 — AI 关键条款抽取（进行中）

#### 已完成
- [x] `ai_gateway/task_profiles.py`：新增 `extract_tender_requirements` / `extract_tender_facts` / `extract_scoring_criteria` 三个 profile（primary v4-pro, fallback flash, max_tokens 65k/8k/16k）
- [x] `ai_gateway/fallback.py`：`_reject_disallowed_model` 改按 task_type 白名单；`call_with_fallback` 新增 `extra_body` 参数透传给 OpenAI SDK
- [x] `ai_gateway/api/chat.py`：`ProviderOverride` / `ChatRequest` 新增 `extra_body` 字段
- [x] alembic 0032：`project_requirement` 加 `extraction_method` 列 + 索引
- [x] `requirement_repo.create_many` 支持 `extraction_method`，冲突时升级为 `merged`
- [x] 新服务 `services/extract_service/ai_requirements_extractor.py`（按 source_file 分组、批次切分、prompt 构造、httpx 调用、JSON 解析、normalize、dedupe、batch usage 汇总）
- [x] 新接口 `POST /api/tender-documents/{id}/ai-extract-requirements`
- [x] ai_gateway 单测：`test_fallback.py` 增 v4-pro 白名单 / extra_body 用例（共 12 通过）
- [x] backend 单测：`test_ai_requirements_extractor.py` 8 个用例覆盖 normalize/dedupe/幻觉过滤/markdown 围栏/v4-pro 透传/单批失败隔离（全部通过）

#### 待完成
- [ ] 跑 alembic 升级到 0032
- [ ] 真实端到端：对包1 调 `ai-extract-requirements`，记录 token 消耗、延时、AI vs keyword 数量与质量对比（2026-05-04 按用户要求暂不跑完整招标文件抽取）
- [ ] 评估前 20 条 AI 抽取的 title/category 质量，给出问题样本（依赖真实端到端抽取结果）
- [ ] 可选：根据评估结果调整 prompt 或 chunk 策略

### Phase 3 — AI 招标摘要（待开始）

- [x] alembic 0034：新建 `tender_summary` 表（project_id PK + 项目名称/招标人/招标代理/建设地点/工期/质量要求/控制价/保证金/开标时间/截止时间 + `raw_facts_json` + `extracted_at`）。注：0033 已用于异步抽取 run/batch 表。
- [x] `services/extract_service/tender_facts_extractor.py`：调 AI Gateway `extract_tender_facts` profile，并支持规则 fallback
- [x] 新接口 `POST /api/tender-documents/{id}/extract-facts` + `GET /api/projects/{id}/tender-summary`
- [x] 单测覆盖
- [ ] 前端：项目首屏顶部加摘要卡片

### Phase 4 — 原文对照 UI（待开始）

- [x] 后端：`GET /api/source-chunks/{chunk_id}` 单条详情接口（已有 list 但缺 by-id）
- [ ] 前端 `Requirement` 类型扩展：`source_chunk_id` / `source_file` / `source_locator` / `paragraph_index` / `page_start`
- [ ] 新组件 `SourceChunkViewer`：右侧 Drawer，table 类型渲染 `<table>`，段落渲染 `text`
- [ ] `RequirementsContent` 卡片点击 → 打开 viewer
- [ ] 前端 e2e 手测

### Phase 5 — 评分表 AI 结构化（待开始）

- [ ] alembic 0034：`project_scoring_criteria` 表（id, project_id, source_chunk_id, dimension_name, max_score, scoring_method, sub_items_json, source_file, source_locator）
- [ ] `services/extract_service/ai_scoring_extractor.py`：扫描 `chunk_type='table' AND document_type='scoring_sheet'` 的 chunk，逐表 AI 提取
- [ ] 新接口 `POST /api/tender-documents/{id}/extract-scoring-criteria`
- [ ] 单测 + 端到端验证

## 验收标准

| 指标 | 目标 |
|---|---|
| 包1 端到端 AI 抽取耗时 | ≤ 10 分钟 |
| AI 抽取 requirement 总量 | 与 keyword（2082）同量级，期待 800–1500 条（去除 keyword 假阳性） |
| AI 抽取 title 质量 | 前 20 条人工抽样评估 ≥ 16 条"准确精炼" |
| `extraction_method='merged'` 占比 | ≥ 30%，证明 AI 与 keyword 有足够交集 |
| `failed_batches` | 0 |
| Token 消耗 | input 总量 ≤ 400k，output 总量 ≤ 60k |
| 招标摘要字段完整度 | 项目名称/招标人/控制价/保证金/开标时间 5 项必填全部命中 |
| 评分表结构化 | 包1 技术评分/商务评分细则的 dimension 全部抽出，max_score 合计与原表一致 |

## Out of Scope

- AI 编写（章节生成）模型策略调整 — 走另一个工单
- 前端整体重构 — 仅在 RequirementsContent / 项目首屏做局部增量
- 历史 keyword 数据迁移 — 不回填，仅新跑生效

## 相关文件

- `backend/Dockerfile`、`ai_gateway/Dockerfile`、`infra/docker-compose.yml`
- `ai_gateway/tender_ai_gateway/{task_profiles,fallback,api/chat}.py`
- `backend/tender_backend/services/extract_service/ai_requirements_extractor.py`
- `backend/tender_backend/api/tender_documents.py`
- `backend/tender_backend/db/alembic/versions/0032_requirement_extraction_method.py`
- `backend/tender_backend/db/repositories/requirement_repo.py`
- `backend/tests/unit/test_ai_requirements_extractor.py`
- `ai_gateway/tests/smoke/test_{fallback,task_profiles}.py`

## 跟踪

每阶段完成后更新本文档相应 checkbox 与"待完成"项；末尾追加"实测数据"小节记录 token、延时、对比结论。
