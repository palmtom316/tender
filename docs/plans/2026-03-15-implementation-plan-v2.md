# AI辅助投标系统一期 Implementation Plan v2

> **修订版：** 基于 2026-03-15 专家审批意见书修订
> **修订基线：** v1 实施计划 + 专家审批 19 条问题（5 P0 / 8 P1 / 6 P2）
> **审批条件跟踪：** 见第 8 节

**Goal:** 基于 `docs/ai_tender_PRD_v1.1_master.md` 落地一期"技术标智能编制系统"，在 10 周内完成从招标文件上传、解析、要求抽取、人工核验、检索增强、章节生成、审校到导出的闭环能力。

**Architecture:** 采用前后端分离和固定工作流 Agent 架构。数据库作为事实真源，OpenSearch 负责 BM25+中文分词+同义词检索，MinerU 负责文档解析，AI Gateway 负责模型路由，核心流程按"解析 -> 抽取 -> 检索 -> 生成 -> 审校 -> 导出"串联。

**Tech Stack:** FastAPI、PostgreSQL、Redis、OpenSearch（ik_max_word 中文分词）、MinIO、Celery、Alembic、MinerU Commercial API、独立 AI Gateway、**DeepSeek（主）、Qwen（备）**、OpenAI-compatible providers、Claude-compatible providers、docxtpl、React 18、TypeScript、Vite、TanStack Router、TanStack Query。

---

## 0. 当前基线与 v1→v2 变更摘要

### 0.1 当前基线（Phase 0 已完成）

仓库已完成 3 次提交，包含：

- **代码路径：** `backend/tender_backend/`（非文档中的 `backend/app/`）
- **AI Gateway：** `ai_gateway/tender_ai_gateway/`
- **前端壳工程：** `frontend/`（React 18 + Vite + TanStack）
- **基础设施：** `infra/docker-compose.yml`（9 服务）
- **数据库迁移：** 13 张表（裸 SQL，无版本管理）
- **后端 API：** 4 个路由（health、projects、files、parse）
- **AI Gateway：** 合约桩（chat、health、credentials、task_profiles）

### 0.2 v2 主要变更（对照审批意见）

| 变更类型 | 内容 | 对应审批编号 |
|---|---|---|
| **模型策略统一** | 所有文档统一为"DeepSeek 主、Qwen 备" | A-01 |
| **代码路径统一** | 全部使用 `tender_backend/`，不再引用 `app/` | C-02 |
| **引入 Alembic** | 数据库迁移版本化管理 | C-04 |
| **引入 Celery** | 异步任务处理（解析、生成等） | C-03 |
| **引入中文分词** | OpenSearch 使用 `ik_max_word` 替代 `standard` | A-02 |
| **Workflow Engine 前移** | Week 7 → Week 2-3 | C-05 |
| **前端分散开发** | Week 10 集中 → Week 2-9 同步推进 | C-06 |
| **分阶段补表** | 13→25 张表分两阶段补齐 | C-01 |
| **新增评分标准建模** | `scoring_criteria` 表 + 评分维度结构化 | B-02 |
| **新增响应矩阵** | 招标要求 → 章节 → 响应状态追踪 | B-03 |
| **基础认证** | 固定 token + 角色标记 | C-07 |
| **结构化日志** | structlog + 全局异常中间件 | C-08 |
| **Eval 提前** | Week 10 → Week 7 | A-05 |
| **同义词扩容** | 100-200 → 300-500 条 | B-04 |
| **Prompt 版本化** | 入库 + trace 关联 + 版本回溯 | A-03 |
| **AI Gateway 增强** | fallback + token/cost + 超时重试 | A-04 |
| **项目紧急度** | tender_deadline 基础上增加优先级调度 | B-05 |
| **格式要求** | 招标文件格式要求抽取 + 模板校验 | B-06 |

---

## 1. PRD 需求追踪矩阵（v2 扩展）

| Req ID | PRD 来源 | 需求摘要 | 交付物 | 验收标准 |
|---|---|---|---|---|
| R01 | 一、系统定位 | 一期范围仅覆盖技术标 | 范围声明、菜单与接口边界 | 页面、接口、导出均不出现经济标流程 |
| R02 | 一、系统定位 | AI 辅助，人类最终确认 | 人工确认状态字段、确认页、导出门禁 | 未确认否决项时禁止导出 |
| R03 | 2.1 否决项防线 | 识别否决项并逐条人工确认 | `project_requirement` + 确认 API/UI | `human_confirmed=false` 时导出失败 |
| R04 | 2.2 资格与业绩要求 | 提取企业资质、人员、业绩、技术要求 | 要求抽取服务、待确认列表 | 缺失字段进入待确认队列 |
| R05 | 四、Agent/Workflow | 固定工作流 Agent 执行主链路 | Workflow Engine、tool schema、workflow tests | 主链路可串行跑通并留痕 |
| R06 | 五、检索系统 | OpenSearch BM25 + 中文分词 + 同义词检索 | 索引、分词器配置、同义词文件、搜索 API | 检索结果可命中同义词等价词 |
| R07 | 六、文档解析 | MinerU 解析标题树、条款、表格、页码 | 解析服务、section/table 持久化 | 上传文档后可查看解析结果 |
| R08 | 六、表格纠错 | 表格人工修正并覆盖保存 | `document_table_override`、修正页/API | 修正后查看以覆盖结果为准 |
| R09 | 七、Word 导出 | Word 模板占位符替换并导出 PDF | 模板引擎、导出服务、导出记录 | 章节成功写入模板并生成记录 |
| R10 | 八、AI 模型策略 | AI Gateway 统一路由，DeepSeek 主 Qwen 备 | `/ai/chat`、fallback、token/cost 记录 | 各任务按预设模型/参数调用，主备切换正常 |
| R11 | 九、页面设计 | 一期 7 个核心页面齐备 | `frontend/` 页面与组件 | 用户可完成端到端主链路 |
| R12 | 十三/十四章 | 核心表、对象存储、索引、服务目录 | DDL、Alembic 迁移、compose、骨架 | 本地环境可启动核心基础设施 |
| R13 | 十五/十六章 | 工程行业同义词库 300-500 条 | `synonyms.txt`、维护表、维护流程 | 可导入、查询、增补同义词 |
| R14 | 十七、最终能力总结 | 解析、抽取、生成、审校、导出闭环 | 联调方案、验收用例、试运行记录 | 真实样例项目完成闭环演示 |
| **R15** | **审批 B-02** | **评分标准结构化** | `scoring_criteria` 表、抽取逻辑 | 评分维度/分值/方式入库可查 |
| **R16** | **审批 B-03** | **响应矩阵（Compliance Matrix）** | 响应矩阵视图、覆盖状态追踪 | 每条要求可追踪对应章节和响应状态 |
| **R17** | **审批 C-07** | **基础认证授权** | token 认证、角色标记 | 三角色（编辑/复核/管理员）权限区分 |
| **R18** | **审批 A-03** | **Prompt 版本管理** | prompt 入库、版本号 + trace 关联 | 可按版本回溯生成效果 |

### 1.1 已确认业务约束

- 一期角色模型：`项目编辑 / 复核人 / 管理员`
- 否决项确认：编辑先确认，导出前需复核人/管理员二次确认
- 导出模板：一期 1 套默认技术标 Word 模板，原始样板需在 Week 2 前补齐
- 占位符：同时支持章节名和章节编码占位符
- 规范库来源：业务侧手工整理首批高频规范 PDF
- **同义词库：一期整理 300-500 条高频种子词（按专业分类：土建、安装、市政、装饰）**（v2 扩容，B-04）
- 审校门禁：`P0/P1` 阻断导出，`P2/P3` 仅提示
- **主模型策略：DeepSeek 主、Qwen 备**（v2 统一，A-01）
- **数据库迁移：使用 Alembic 版本化管理**（v2 新增，C-04）
- **异步任务：Celery + Redis broker**（v2 新增，C-03）
- **验收样本：Week 1 结束前落实 2-3 份真实招标文件 + 1 套期望导出样例**（v2 新增，B-01）

---

## 2. 里程碑与周计划（v2 重排）

| Milestone | 周次 | 目标 | 完成标志 |
|---|---|---|---|
| M0 | Week 1 | 工程补强：Alembic、structlog、验收样本 | 迁移可版本化执行，日志结构化，样本文件到位 |
| M1 | Week 2 | 补表 Phase 1 + Celery + 基础认证 + Workflow 基座 + 前端项目列表/上传页 | worker 可执行异步任务，workflow_run 可落库 |
| M2 | Week 3 | MinerU 解析 + tender_ingestion workflow + 前端解析结果页 | 文档解析通过 workflow 编排，前端可查看结果 |
| M3 | Week 4 | 要求抽取 + 评分标准 + 否决项确认 + 前端确认页 | 否决项/评分标准结构化入库，人工确认闭环 |
| M4 | Week 5 | 规范库 + OpenSearch 中文分词 + 同义词(300-500) | 规范 PDF 入库，中文分词检索可用 |
| M5 | Week 6 | 补表 Phase 2 + AI Gateway 增强 + Tool/Search 层 | AI Gateway 可实际调用模型并 fallback |
| M6 | Week 7 | 章节生成 workflow + Prompt 版本化 + Eval 基础 + 前端编辑页 | 生成草稿并留痕，Eval 可评估 |
| M7 | Week 8 | 审校 workflow + 响应矩阵 + 前端审校页 | 问题清单 + 覆盖状态矩阵可用 |
| M8 | Week 9 | 导出 + 格式校验 + 前端导出页 | 基于模板完成导出，格式合规 |
| M9 | Week 10 | Eval 迭代 + 联调 + UAT + 文档 | 真实样本通过验收 |

---

## 3. 交付拆解与执行顺序

### Task 1: 工程补强（Week 1 补充）

**对应审批：** C-04、C-08、B-01、C-02
**对应需求：** R12

**目标：** 引入 Alembic 迁移工具、结构化日志、全局异常处理；落实验收样本；统一代码路径。

**Files:**
- Create: `backend/tender_backend/db/alembic/env.py`
- Create: `backend/tender_backend/db/alembic/versions/0001_initial_schema.py`
- Create: `backend/tender_backend/core/logging.py`
- Create: `backend/tender_backend/core/middleware.py`
- Create: `docs/samples/README.md`

**Step 1: 引入 Alembic 迁移管理**

将现有裸 SQL 迁移转换为 Alembic 版本化迁移。配置 `alembic.ini` 和 `env.py`，将 `0001_initial_schema.sql` 转为首个 Alembic revision。

Expected: `alembic upgrade head` 可重复执行，`alembic history` 可查看版本链

**Step 2: 配置 structlog + 全局异常中间件**

在 `tender_backend/core/logging.py` 配置 structlog JSON 格式日志。在 `tender_backend/core/middleware.py` 实现 FastAPI 全局异常处理中间件，捕获未处理异常并返回标准错误响应，确保所有请求可追踪。

Expected: 所有 API 请求产生结构化 JSON 日志，包含 request_id

**Step 3: 落实验收样本计划**

创建 `docs/samples/README.md`，记录验收样本需求：2-3 份真实招标文件 + 1 套期望导出样例。标注截止日期为 Week 1 结束。

Expected: 验收样本需求和截止日期明确记录

**Step 4: Commit**

```bash
git add backend/tender_backend/db/alembic backend/tender_backend/core/logging.py backend/tender_backend/core/middleware.py docs/samples
git commit -m "chore: add alembic migrations, structlog, and error middleware"
```

---

### Task 2: 数据库补表 Phase 1 + Celery + 基础认证 + Workflow 基座（Week 2）

**对应审批：** C-01、C-03、C-05、C-06、C-07
**对应需求：** R05、R12、R17

**目标：** 补齐一期核心缺失表；引入 Celery 异步任务框架；搭建 Workflow Engine 基座；实现基础 token 认证；完成前端项目列表和上传页面。

**Files:**
- Create: `backend/tender_backend/db/alembic/versions/0002_phase1_tables.py`
- Create: `backend/tender_backend/workers/celery_app.py`
- Create: `backend/tender_backend/workers/tasks_parse.py`
- Create: `backend/tender_backend/core/security.py`
- Create: `backend/tender_backend/workflows/base.py`
- Create: `backend/tender_backend/workflows/registry.py`
- Create: `backend/tender_backend/workflows/states.py`
- Create: `backend/tender_backend/db/repositories/workflow_repo.py`
- Create: `frontend/src/pages/project-list.tsx`
- Create: `frontend/src/pages/upload.tsx`
- Create: `frontend/src/lib/api.ts`

**Step 1: Alembic 迁移补表 Phase 1**

新增迁移 `0002_phase1_tables.py`，补充以下表：
- `document_outline_node` — 文档大纲节点
- `standard` — 规范库主表
- `standard_clause` — 规范条款
- `project_outline_node` — 项目提纲节点
- `human_confirmation` — 通用人工确认记录
- `section_template` — 章节模板
- `workflow_run` — 工作流执行记录
- `workflow_step_log` — 工作流步骤日志
- `scoring_criteria` — 评分标准（新增，B-02）

对 `project` 表增加列：`owner_name`、`tender_no`、`project_type`、`status`、`tender_deadline`、`created_by`、`priority`（B-05 紧急度标识）。

Expected: `alembic upgrade head` 补齐至 21 张表

**Step 2: 引入 Celery + Redis broker**

添加 `celery[redis]` 依赖。创建 `celery_app.py`（配置 broker 和队列：`io_tasks`、`workflow_tasks`）。创建 `tasks_parse.py` 作为异步解析任务入口。

更新 `infra/docker-compose.yml` 添加 `worker-io` 服务：
```yaml
worker-io:
  build: ./backend
  command: celery -A tender_backend.workers.celery_app worker -Q io_tasks -l info
  depends_on:
    - redis
    - postgres
```

Expected: Celery worker 可启动并消费 io_tasks 队列

**Step 3: 基础认证实现**

在 `tender_backend/core/security.py` 实现固定 token + 角色标记方案：
- 支持三角色：项目编辑、复核人、管理员
- 通过 HTTP Header `Authorization: Bearer <token>` 认证
- 提供 `require_role()` 依赖注入装饰器

Expected: 受保护 API 需要有效 token，角色不足返回 403

**Step 4: Workflow Engine 基座**

实现 `BaseWorkflow`、`WorkflowContext`、`WorkflowStep` 基类和状态机（pending → running → suspended → completed / failed / cancelled）。实现 `WorkflowRegistry` 注册表。实现 `workflow_repo.py` 持久化 `workflow_run` 和 `workflow_step_log`。

Expected: 可注册、启动、挂起、恢复 workflow，执行记录落库

**Step 5: 前端项目列表 + 上传页**

实现 `project-list.tsx`（项目列表、创建项目入口）和 `upload.tsx`（文件拖拽上传、上传状态）。建立 `api.ts` 前端 API 调用层。

Expected: 可在浏览器中创建项目并上传文件

**Step 6: Commit**

```bash
git add backend/tender_backend/db/alembic backend/tender_backend/workers backend/tender_backend/core/security.py backend/tender_backend/workflows backend/tender_backend/db/repositories/workflow_repo.py frontend/src/pages frontend/src/lib infra/docker-compose.yml
git commit -m "feat: add phase1 tables, celery, auth, workflow engine, and frontend pages"
```

---

### Task 3: 文档解析 + tender_ingestion Workflow（Week 3）

**对应审批：** C-05（workflow 实际应用）、C-06（前端同步）
**对应需求：** R05、R07

**目标：** 接入 MinerU 商业 API，通过 Celery 异步执行解析任务，使用 tender_ingestion workflow 编排解析流程；完成前端解析结果页。

**Files:**
- Create: `backend/tender_backend/services/parse_service/mineru_client.py`
- Create: `backend/tender_backend/services/parse_service/parser.py`
- Create: `backend/tender_backend/services/parse_service/task_poller.py`
- Create: `backend/tender_backend/workflows/tender_ingestion.py`
- Create: `frontend/src/pages/parse-results.tsx`
- Create: `backend/tests/integration/test_parse_pipeline.py`

**Step 1: 封装 MinerU 客户端**

支持申请上传链接、后端直传文件、轮询解析结果、标准化输出。

Expected: MinerU API 调用封装完整

**Step 2: 解析结果持久化**

解析结果写入 `document_section`、`document_table`、`document_outline_node`。通过 Celery `io_tasks` 队列异步执行。

Expected: 解析结果入库，异步任务可追踪状态

**Step 3: tender_ingestion workflow**

使用 Task 2 建立的 Workflow Engine，编排 tender_ingestion 流程：`upload_to_minio → request_parse → poll_result → persist_sections → persist_tables → extract_outline`。

workflow_run 和 step_log 全程落库。支持按 `project.priority` 调度任务优先级（B-05）。

Expected: 解析流程通过 workflow 编排，执行过程可追踪

**Step 4: 前端解析结果页**

实现 `parse-results.tsx`：展示文档结构树、章节内容、表格列表、解析状态。

Expected: 上传文档后可在浏览器中查看解析结果

**Step 5: 验证解析主链路**

```bash
pytest backend/tests/integration/test_parse_pipeline.py -v
```

Expected: 测试样本可通过 workflow 完成解析并持久化

**Step 6: Commit**

```bash
git add backend/tender_backend/services/parse_service backend/tender_backend/workflows/tender_ingestion.py frontend/src/pages/parse-results.tsx backend/tests/integration
git commit -m "feat: add document parsing via workflow with async celery execution"
```

---

### Task 4: 要求抽取 + 评分标准 + 否决项确认（Week 4）

**对应审批：** B-02、B-05、B-06、C-06
**对应需求：** R02、R03、R04、R15

**目标：** 实现要求抽取（含评分标准和格式要求）、否决项识别、人工确认闭环；前端确认页面。

**Files:**
- Create: `backend/tender_backend/services/extract_service/requirements_extractor.py`
- Create: `backend/tender_backend/services/extract_service/facts_extractor.py`
- Create: `backend/tender_backend/services/extract_service/scoring_extractor.py`
- Create: `backend/tender_backend/api/requirements.py`
- Create: `backend/tender_backend/api/scoring.py`
- Create: `backend/tender_backend/db/repositories/requirement_repo.py`
- Create: `backend/tender_backend/db/repositories/scoring_repo.py`
- Create: `frontend/src/pages/requirements-confirmation.tsx`
- Create: `backend/tests/integration/test_requirement_confirmation.py`

**Step 1: 要求抽取服务**

实现 `requirements_extractor.py`（抽取否决项、资质、人员、业绩、技术要求）和 `facts_extractor.py`（抽取项目事实）。

`requirement_category` 扩展新增：
- `scoring` — 评分标准类别（B-02）
- `format` — 格式要求类别（B-06）

Expected: 可从解析结果中抽取各类要求

**Step 2: 评分标准结构化**

实现 `scoring_extractor.py`，从评分表中抽取评分维度、分值、评分方式。持久化到 `scoring_criteria` 表（字段：`project_id`、`dimension`、`max_score`、`scoring_method`、`source_document_id`、`source_page`、`human_confirmed`）。

Expected: 评分标准结构化入库，可供生成和审校引用

**Step 3: 人工确认 API + 导出门禁**

暴露待确认清单查询、逐条确认、记录确认人和时间。导出前校验所有否决项已确认。

Expected: `human_confirmed=false` 的否决项阻断导出

**Step 4: 前端确认页面**

实现 `requirements-confirmation.tsx`：按类别筛选（否决项/评分标准/资质/格式等）、查看原文上下文、确认状态切换。

Expected: 可在浏览器中逐条审核和确认要求

**Step 5: 验证确认闭环**

```bash
pytest backend/tests/integration/test_requirement_confirmation.py -v
```

Expected: 确认流程和导出门禁通过测试

**Step 6: Commit**

```bash
git add backend/tender_backend/services/extract_service backend/tender_backend/api/requirements.py backend/tender_backend/api/scoring.py backend/tender_backend/db/repositories frontend/src/pages/requirements-confirmation.tsx backend/tests/integration
git commit -m "feat: add requirement extraction with scoring criteria and confirmation gate"
```

---

### Task 5: 规范库 + OpenSearch 中文分词 + 同义词（Week 5）

**对应审批：** A-02、B-04
**对应需求：** R06、R13

**目标：** 规范库入库与条款树索引；OpenSearch 配置中文分词器替代 `standard` tokenizer；同义词词典扩容至 300-500 条。

**Files:**
- Create: `backend/tender_backend/services/search_service/index_manager.py`
- Create: `backend/tender_backend/services/search_service/synonym_loader.py`
- Create: `backend/tender_backend/workflows/standard_ingestion.py`
- Create: `backend/tender_backend/db/repositories/standard_repo.py`
- Update: `infra/opensearch/opensearch.yml` — 添加 ik 分词器插件
- Update: `infra/opensearch/synonyms.txt` — 扩容至 300-500 条
- Create: `backend/tests/integration/test_search_with_synonyms.py`

**Step 1: OpenSearch 中文分词配置**

在 OpenSearch 中安装 `analysis-ik` 插件。将所有索引的 `cn_with_synonym` analyzer 中的 tokenizer 从 `standard` 替换为 `ik_max_word`：

```json
{
  "analyzer": {
    "cn_with_synonym": {
      "tokenizer": "ik_max_word",
      "filter": ["lowercase", "construction_synonym"]
    }
  }
}
```

更新 `infra/opensearch/opensearch.yml` 确保 Docker 镜像包含 ik 插件。

Expected: 中文文本可做词级分词，"混凝土浇筑施工方案"可切分为有意义的词

**Step 2: 同义词词典扩容**

将 `infra/opensearch/synonyms.txt` 从示例级扩容至 300-500 条种子词，按专业分类组织：
- 土建（基坑开挖/土方开挖、脚手架/外架、...）
- 安装（管道安装/管道敷设、电缆桥架/线槽、...）
- 市政（路基施工/道路基层、排水管道/下水管、...）
- 装饰（涂料施工/刷漆、吊顶安装/天花施工、...）

标注 Week 5 前需业务侧完成初版交付。

Expected: 同义词文件按专业分类，覆盖主要术语

**Step 3: 规范库入库 + standard_ingestion workflow**

实现 `standard_ingestion` workflow：`parse_standard_pdf → build_clause_tree → tag_clauses → index_to_opensearch`。规范条款入 `standard` + `standard_clause` 表，并同步索引到 `clause_index`。

Expected: 规范 PDF 可入库并索引

**Step 4: 建立索引结构**

在 `index_manager.py` 中创建 `section_index`、`clause_index`、`requirement_index`，全部使用 `ik_max_word` 分词器。

Expected: 三个索引创建成功

**Step 5: 验证同义词检索**

```bash
pytest backend/tests/integration/test_search_with_synonyms.py -v
```

Expected: 查询"土方开挖"可命中"基坑开挖"，验证中文分词效果

**Step 6: Commit**

```bash
git add infra/opensearch backend/tender_backend/services/search_service backend/tender_backend/workflows/standard_ingestion.py backend/tender_backend/db/repositories/standard_repo.py backend/tests/integration
git commit -m "feat: add standards indexing with ik chinese tokenizer and expanded synonyms"
```

---

### Task 6: 数据库补表 Phase 2 + AI Gateway 增强 + Tool/Search 层（Week 6）

**对应审批：** C-01、A-04
**对应需求：** R05、R10

**目标：** 补齐剩余配置表；AI Gateway 达到最小可用能力；建立 Tool 基类、Registry 和 Search Service。

**Files:**
- Create: `backend/tender_backend/db/alembic/versions/0003_phase2_tables.py`
- Update: `ai_gateway/tender_ai_gateway/main.py` — 增强
- Create: `ai_gateway/tender_ai_gateway/fallback.py`
- Create: `ai_gateway/tender_ai_gateway/token_tracker.py`
- Create: `backend/tender_backend/tools/base.py`
- Create: `backend/tender_backend/tools/registry.py`
- Create: `backend/tender_backend/tools/search_clauses.py`
- Create: `backend/tender_backend/tools/search_sections.py`
- Create: `backend/tender_backend/services/search_service/query_service.py`
- Create: `backend/tender_backend/api/search.py`

**Step 1: Alembic 迁移补表 Phase 2**

新增迁移 `0003_phase2_tables.py`，补充：
- `task_trace` — AI 调用追踪
- `prompt_template` — Prompt 版本化
- `model_profile` — 模型配置
- `tool_definition` — 工具定义
- `skill_definition` — 技能定义

Expected: `alembic upgrade head` 达到完整 25+ 张表

**Step 2: AI Gateway 增强到最小可用能力**

在现有合约桩基础上实现：
1. **实际调用至少一个 provider**（DeepSeek 主，通过 OpenAI-compatible 接口）
2. **Fallback 切换**（DeepSeek 失败 → Qwen 备用）
3. **Token/Cost 记录**（每次调用记录 input_tokens、output_tokens、estimated_cost）
4. **超时重试**（可配置超时和重试次数）

Streaming 支持可推迟到 Week 7 与生成能力同步。

Expected: AI Gateway 可实际调用模型，主备切换正常

**Step 3: Tool 基类与 Registry**

实现 `Tool` 基类（pydantic 输入校验、统一 `ToolResult` 输出）和 `ToolRegistry`（注册、查找、schema 导出）。

实现 `search_clauses` 和 `search_sections` 两个检索工具。

Expected: Tool 可注册并通过 schema 暴露

**Step 4: Search Service API**

实现 `query_service.py`（BM25 + 同义词查询封装）和 `search.py` API 路由，覆盖 `search_sections`、`search_clauses`、`search_company_docs`。

Expected: 检索 API 可用

**Step 5: Commit**

```bash
git add backend/tender_backend/db/alembic ai_gateway backend/tender_backend/tools backend/tender_backend/services/search_service backend/tender_backend/api/search.py
git commit -m "feat: enhance ai gateway, add tool registry and search service"
```

---

### Task 7: 章节生成 + Prompt 版本化 + Eval 基础（Week 7）

**对应审批：** A-03、A-05、C-06
**对应需求：** R05、R18

**目标：** 实现 generate_section workflow；Prompt 版本化管理与 trace 关联；建立 Eval 基础框架；前端章节编辑页。

**Files:**
- Create: `backend/tender_backend/workflows/generate_section.py`
- Create: `backend/tender_backend/tools/assemble_evidence_pack.py`
- Create: `backend/tender_backend/services/prompt_service.py`
- Create: `backend/tender_backend/db/repositories/prompt_repo.py`
- Create: `backend/tender_backend/db/repositories/trace_repo.py`
- Create: `backend/tender_backend/api/drafts.py`
- Create: `backend/tests/evals/eval_runner.py`
- Create: `backend/tests/evals/test_sets/`
- Create: `frontend/src/pages/chapter-editor.tsx`
- Create: `backend/tests/integration/test_generate_section_flow.py`

**Step 1: generate_section workflow**

编排章节生成流程：`load_project_facts → load_section_requirements → search_clauses → search_sections → assemble_evidence_pack → llm_generate_outline → human_confirm_outline（挂起点） → llm_generate_section → save_draft`。

Evidence pack 包含：项目事实、招标要求、评分标准、匹配条款、参考章节。

Expected: 生成草稿并落库到 `chapter_draft`

**Step 2: Prompt 版本化管理**

实现 `prompt_service.py`：
- Prompt 模板入 `prompt_template` 表，含 `prompt_name` + `version`
- 每次 AI 调用时 `task_trace` 记录 `prompt_version`
- 支持按版本查询历史生成效果

Expected: Prompt 版本可追溯，与 trace 关联

**Step 3: Eval 基础框架**

建立 `eval_runner.py`：
- 测试集管理（抽取/检索/生成测试集目录结构）
- 评分脚本（事实一致性、合规覆盖率、检索命中率基础指标）
- 可命令行执行评估并输出报告

与章节生成同步迭代，边开发边评测。

Expected: Eval 框架可运行基础评估

**Step 4: 前端章节编辑页**

实现 `chapter-editor.tsx`：展示提纲树、章节草稿、支持人工编辑和确认。

Expected: 可在浏览器中查看和编辑生成的章节

**Step 5: 验证生成闭环**

```bash
pytest backend/tests/integration/test_generate_section_flow.py -v
```

Expected: 生成提纲和章节正文并持久化

**Step 6: Commit**

```bash
git add backend/tender_backend/workflows/generate_section.py backend/tender_backend/tools backend/tender_backend/services/prompt_service.py backend/tender_backend/db/repositories backend/tender_backend/api/drafts.py backend/tests/evals frontend/src/pages/chapter-editor.tsx backend/tests/integration
git commit -m "feat: add chapter generation workflow with prompt versioning and eval framework"
```

---

### Task 8: 审校 + 响应矩阵 + 表格纠错增强（Week 8）

**对应审批：** B-03、B-06、C-06
**对应需求：** R02、R05、R08、R16

**目标：** 实现审校 workflow 和问题清单输出；建立响应矩阵视图；完善表格纠错；前端审校页。

**Files:**
- Create: `backend/tender_backend/services/review_service/review_engine.py`
- Create: `backend/tender_backend/workflows/review_section.py`
- Create: `backend/tender_backend/services/review_service/compliance_matrix.py`
- Create: `backend/tender_backend/api/review.py`
- Create: `backend/tender_backend/api/compliance.py`
- Create: `backend/tender_backend/api/table_overrides.py`
- Create: `frontend/src/pages/review-results.tsx`
- Create: `frontend/src/components/table-override-editor.tsx`
- Create: `frontend/src/components/compliance-matrix.tsx`
- Create: `backend/tests/integration/test_review_flow.py`

**Step 1: 审校引擎**

实现 `review_engine.py`：
- 规则审校：事实一致性检查、招标要求覆盖检查、规范引用检查
- 模型审校：调用 AI Gateway 进行内容质量审核
- 输出 `review_issue`（severity: P0/P1/P2/P3）

**Step 2: 响应矩阵（Compliance Matrix）**

实现 `compliance_matrix.py`：
- 逐条对照招标要求，映射到对应章节
- 生成响应状态：已覆盖 / 部分覆盖 / 未覆盖
- 作为审校的核心输入，辅助识别遗漏

Expected: 每条招标要求可追踪对应章节和覆盖状态

**Step 3: 格式要求校验**

在审校流程中增加格式要求检查：对照 B-06 要求，从招标文件中抽取的格式要求（字体、字号、行距、页边距）与导出模板进行比对。

Expected: 格式不合规时生成 review_issue

**Step 4: 表格纠错 API + 前端编辑器**

暴露表格纠错接口（读取原表、提交修正、查询生效版本）。实现 `table-override-editor.tsx` 组件。

**Step 5: 前端审校结果页 + 响应矩阵组件**

实现 `review-results.tsx`（问题级别、章节、修复状态）和 `compliance-matrix.tsx`（要求→章节→状态矩阵视图）。

Expected: 可在浏览器中查看审校结果和响应矩阵

**Step 6: 验证审校流程**

```bash
pytest backend/tests/integration/test_review_flow.py -v
```

**Step 7: Commit**

```bash
git add backend/tender_backend/services/review_service backend/tender_backend/workflows/review_section.py backend/tender_backend/api frontend/src/pages frontend/src/components backend/tests/integration
git commit -m "feat: add review workflow with compliance matrix and table override"
```

---

### Task 9: 导出 + 格式校验 + 前端导出页（Week 9）

**对应审批：** B-06
**对应需求：** R02、R09、R14

**目标：** Word 模板导出、PDF 转换、导出门禁（否决项+审校+格式）、前端导出页。

**Files:**
- Create: `backend/tender_backend/services/export_service/docx_exporter.py`
- Create: `backend/tender_backend/services/export_service/pdf_exporter.py`
- Create: `backend/tender_backend/services/export_service/format_validator.py`
- Create: `backend/tender_backend/workflows/export_bid.py`
- Create: `backend/tender_backend/api/exports.py`
- Create: `frontend/src/pages/export.tsx`
- Create: `backend/tests/integration/test_export_gate_and_render.py`

**Step 1: Word 模板导出**

基于 docxtpl 实现占位符 `{{SECTION_xxx}}` 渲染 DOCX。

**Step 2: 格式校验**

实现 `format_validator.py`：根据从招标文件抽取的格式要求（字体、字号、行距、页边距），校验导出模板是否合规。不合规时警告或阻断。

**Step 3: 导出门禁**

export_bid workflow 在导出前执行三道校验：
1. 否决项全部 `human_confirmed=true`
2. P0/P1 审校问题全部已处理
3. 格式要求校验通过

**Step 4: PDF 导出 + 导出记录**

DOCX → PDF 转换，成功后写入 `export_record`。

**Step 5: 前端导出页**

实现 `export.tsx`：选择模板、预览门禁状态、触发导出、下载文件、查看历史。

**Step 6: 验证导出流程**

```bash
pytest backend/tests/integration/test_export_gate_and_render.py -v
```

**Step 7: Commit**

```bash
git add backend/tender_backend/services/export_service backend/tender_backend/workflows/export_bid.py backend/tender_backend/api/exports.py frontend/src/pages/export.tsx backend/tests/integration
git commit -m "feat: add gated export with format validation"
```

---

### Task 10: Eval 迭代 + 联调 + UAT + 文档（Week 10）

**对应需求：** R14

**目标：** Eval 体系完善、端到端联调、真实样本 UAT、文档收尾。

**Files:**
- Update: `backend/tests/evals/` — 完善测试集和评分脚本
- Create: `frontend/tests/e2e/tender-flow.spec.ts`
- Create: `docs/tracking/uat-checklist.md`
- Update: `docs/tracking/requirements-traceability.csv`

**Step 1: Eval 迭代**

完善 Week 7 建立的 Eval 框架：
- 补充抽取测试集（事实/否决项/资格/评分标准）
- 补充检索测试集（条款命中/章节命中/同义词命中）
- 补充生成测试集（固定 evidence pack 生成）
- 补充审校测试集（人工构造错误草稿）
- Trace 回放能力：可按 trace_id 重放完整 workflow 过程

Expected: Eval 覆盖核心能力，可量化评估质量

**Step 2: 端到端联调**

E2E 测试覆盖主链路："建项目 → 上传 → 解析 → 确认 → 生成 → 审校 → 导出"。

```bash
pytest backend/tests/integration -v && npm --prefix frontend test
```

**Step 3: UAT 验收**

使用 2-3 份真实招标文件执行完整流程，验证验收基线。

**Step 4: 文档完善**

更新需求追踪矩阵，编写 UAT checklist，确保所有 Req ID 有证据链。

**Step 5: Commit**

```bash
git add backend/tests frontend/tests docs/tracking
git commit -m "feat: complete eval iteration, e2e tests, and uat checklist"
```

---

## 4. 数据库表补齐计划（对照 C-01）

### Phase 1（Week 2 迁移 0002）

| 表名 | 来源 | 说明 |
|---|---|---|
| `document_outline_node` | 架构 v2.1 §6.2 | 文档大纲节点 |
| `standard` | 架构 v2.1 §6.3 | 规范库 |
| `standard_clause` | 架构 v2.1 §6.3 | 规范条款 |
| `project_outline_node` | 架构 v2.1 §6.5 | 项目提纲节点 |
| `human_confirmation` | 架构 v2.1 §6.4 | 通用确认记录 |
| `section_template` | 架构 v2.1 §6.5 | 章节模板 |
| `workflow_run` | 架构 v2.1 §6.6 | 工作流执行 |
| `workflow_step_log` | 架构 v2.1 §6.6 | 工作流步骤 |
| `scoring_criteria` | **新增** B-02 | 评分标准 |

### Phase 2（Week 6 迁移 0003）

| 表名 | 来源 | 说明 |
|---|---|---|
| `task_trace` | 架构 v2.1 §6.6 | AI 调用追踪 |
| `prompt_template` | 架构 v2.1 §6.7 | Prompt 版本 |
| `model_profile` | 架构 v2.1 §6.7 | 模型配置 |
| `tool_definition` | 架构 v2.1 §6.7 | 工具定义 |
| `skill_definition` | 架构 v2.1 §6.7 | 技能定义 |

### project 表增列（Phase 1 同步）

`owner_name`、`tender_no`、`project_type`、`status`、`tender_deadline`、`created_by`、`priority`

---

## 5. 前端页面分散排期（对照 C-06）

| 页面 | 排期 | 对应 Task |
|---|---|---|
| 项目列表 `project-list.tsx` | Week 2 | Task 2 |
| 文件上传 `upload.tsx` | Week 2 | Task 2 |
| 解析结果 `parse-results.tsx` | Week 3 | Task 3 |
| 要求确认 `requirements-confirmation.tsx` | Week 4 | Task 4 |
| 章节编辑 `chapter-editor.tsx` | Week 7 | Task 7 |
| 审校结果 `review-results.tsx` | Week 8 | Task 8 |
| 导出页面 `export.tsx` | Week 9 | Task 9 |

---

## 6. 审批问题追踪矩阵

| 编号 | 严重度 | 问题摘要 | 解决方案 | 落地位置 | 状态 |
|---|---|---|---|---|---|
| B-01 | P0 | 验收样本 pending | Week 1 落实 2-3 份真实招标文件 | Task 1 Step 3 | **待落实** |
| A-01 | P0 | 主模型策略文档冲突 | 统一为 DeepSeek 主 Qwen 备 | 本计划 §0.2 + 架构文档修订 | **已处理** |
| A-02 | P0 | OpenSearch 中文分词缺失 | 引入 ik_max_word 替代 standard | Task 5 Step 1 | **已排期** |
| C-01 | P0 | Schema 严重不一致 | 分两阶段补齐，见 §4 | Task 2 + Task 6 | **已排期** |
| C-02 | P0 | 代码包路径不一致 | 统一为 `tender_backend/` | 本计划全文 | **已处理** |
| B-02 | P1 | 缺少评分标准结构化 | 新增 scoring_criteria 表 + 抽取逻辑 | Task 4 Step 2 | **已排期** |
| B-03 | P1 | 缺少响应矩阵 | 新增 Compliance Matrix 视图 | Task 8 Step 2 | **已排期** |
| A-03 | P1 | Prompt 版本管理不完整 | 入库 + trace 关联 + 版本回溯 | Task 7 Step 2 | **已排期** |
| A-04 | P1 | AI Gateway 过于单薄 | 增强 fallback + token/cost + 超时重试 | Task 6 Step 2 | **已排期** |
| C-03 | P1 | Celery Worker 未落地 | 引入 Celery + worker-io 服务 | Task 2 Step 2 | **已排期** |
| C-04 | P1 | 缺少数据库迁移工具 | 引入 Alembic | Task 1 Step 1 | **已排期** |
| C-05 | P1 | Workflow Engine 排期过晚 | 前移到 Week 2-3 | Task 2 Step 4 | **已排期** |
| C-06 | P1 | 前端页面集中 Week 10 | 分散到 Week 2-9 同步推进 | §5 排期表 | **已排期** |
| B-04 | P2 | 同义词种子词不足 | 扩容至 300-500 条按专业分类 | Task 5 Step 2 | **已排期** |
| B-05 | P2 | 未考虑投标截止紧迫性 | project 增加 priority 字段 + 调度优先级 | Task 2 Step 1 + Task 3 | **已排期** |
| B-06 | P2 | 缺少格式要求处理 | 新增格式要求类别 + 导出校验 | Task 4 + Task 9 | **已排期** |
| A-05 | P2 | Eval 体系过晚 | 前移到 Week 7 | Task 7 Step 3 | **已排期** |
| C-07 | P2 | 认证授权未规划 | 基础 token + 角色标记 | Task 2 Step 3 | **已排期** |
| C-08 | P2 | 缺少结构化日志 | structlog + 全局异常中间件 | Task 1 Step 2 | **已排期** |

---

## 7. 验收基线（v2 更新）

### 功能验收

- 招标文件上传后 30 分钟内可查看解析结构化结果
- 否决项必须人工确认后才能导出
- **评分标准结构化入库并可在审校中引用**（v2 新增）
- **响应矩阵可展示每条要求的覆盖状态**（v2 新增）
- 至少 1 个真实样本项目完成"解析 → 生成 → 审校 → 导出"闭环
- 检索支持 BM25 + **ik 中文分词** + 同义词，验证样例命中符合预期（v2 更新）
- 章节草稿、审校问题、导出记录均可回溯到项目维度
- **AI Gateway 主备切换正常（DeepSeek → Qwen）**（v2 新增）
- **导出前通过格式要求校验**（v2 新增）

### 技术验收

- 本地或测试环境可通过 `docker compose` 启动核心依赖
- 核心 API 具备健康检查、**结构化日志**、超时和失败重试（v2 更新）
- **数据库迁移通过 Alembic 可重复执行**（v2 更新）
- **Celery worker 可处理异步任务**（v2 新增）
- **Workflow 执行记录和步骤日志可查询**（v2 新增）
- **Prompt 版本与 trace 关联，可按版本回溯**（v2 新增）
- 集成测试覆盖主链路关键门禁
- **Eval 框架可运行基础评估并输出报告**（v2 新增）

---

## 8. 审批条件清单（开工前检查）

| 条件 | 状态 | 说明 |
|---|---|---|
| D08 验收样本落实 | **待落实** | Week 1 结束前必须到位，否则不进入 Week 3 |
| 主模型策略统一 | **已在本计划处理** | 全文统一为 DeepSeek 主 Qwen 备 |
| OpenSearch 中文分词 | **已排期 Week 5** | Task 5 Step 1 |
| Schema 与迁移对齐 | **已排期 Week 2 + Week 6** | Task 2 + Task 6 分两阶段 |
| 代码包路径统一 | **已在本计划处理** | 全文使用 `tender_backend/` |

---

## 9. 主要风险与应对（v2 更新）

| 风险 | 影响 | 应对措施 |
|---|---|---|
| **验收样本未按时到位** | 解析调优、Eval 验证无法闭环 | Week 1 就明确样本需求，设置硬性截止日期 |
| MinerU 解析质量不稳定 | 影响抽取和生成质量 | 先建立解析结果回显与表格纠错，再做下游自动化 |
| **ik 分词器与 OpenSearch 版本兼容** | 影响检索质量 | 提前在 Week 1 验证插件兼容性 |
| 同义词库初期覆盖不足 | 影响检索命中率 | 扩容至 300-500 条，Week 5 前业务侧交付初版 |
| AI 生成不稳定 | 影响章节可用性 | 强制检索证据输入、降温、审校门禁、**Eval 同步迭代** |
| **Celery 引入增加运维复杂度** | 开发环境配置变重 | 提供单进程模式用于本地开发调试 |
| 导出模板与章节命名不一致 | 影响导出成功率 | 建立占位符命名规范和导出前校验 |
| **前端分散开发增加联调成本** | 接口频繁变更 | API 合约先行，前后端共同维护 OpenAPI spec |

---

## 10. 完成判定

- 所有 `Req ID`（R01-R18）均在 `docs/tracking/requirements-traceability.csv` 中标记为 `done` 或有明确延期说明
- M0-M9 里程碑均有证据
- 19 条审批问题全部标记为 `resolved`
- 至少完成一轮真实样本 UAT
- 无阻断导出的 P0/P1 缺陷遗留
- 交付包含运行说明、测试结果、模板样例和演示记录
