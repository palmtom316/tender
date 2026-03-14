# AI辅助投标系统一期 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 基于 `docs/ai_tender_PRD_v1.1_master.md` 落地一期“技术标智能编制系统”，在 10 周内完成从招标文件上传、解析、要求抽取、人工核验、检索增强、章节生成、审校到导出的闭环能力。

**Architecture:** 采用前后端分离和固定工作流 Agent 架构。数据库作为事实真源，OpenSearch 负责 BM25+同义词检索，MinerU 负责文档解析，AI Gateway 负责模型路由，核心流程按“解析 -> 抽取 -> 检索 -> 生成 -> 审校 -> 导出”串联。

**Tech Stack:** FastAPI、PostgreSQL、Redis、OpenSearch、MinIO、MinerU Commercial API、独立 AI Gateway、DeepSeek、Qwen、ccswitch、OpenAI-compatible providers、Claude-compatible providers、docxtpl、React 18、TypeScript、Vite、TanStack Router、TanStack Query。

---

## 0. 当前基线与计划假设

- 当前仓库仅包含 PRD 文档，尚无可执行代码、CI、数据库迁移或前端工程。
- 本计划中的目录与文件路径，基于 PRD 第十三章推荐结构补齐为一期建议落盘方案。
- 技术选型已确认，详见 `docs/plans/2026-03-14-technical-stack-design.md`。
- 计划默认采用单仓 monorepo 组织：
  - `backend/`：API、workflow、services、db、tests
  - `frontend/`：页面、组件、接口调用、E2E 用例
  - `infra/`：`docker-compose.yml`、OpenSearch 同义词、初始化脚本
  - `docs/`：需求追踪、接口约定、验收记录

## 1. PRD 需求追踪矩阵

| Req ID | PRD 来源 | 需求摘要 | 交付物 | 验收标准 |
|---|---|---|---|---|
| R01 | 一、系统定位 | 一期范围仅覆盖技术标，不含经济标和复杂审计 | 范围声明、菜单与接口边界 | 页面、接口、导出均不出现经济标流程 |
| R02 | 一、系统定位 | AI 辅助，人类最终确认 | 人工确认状态字段、确认页、导出门禁 | 未确认否决项时禁止导出 |
| R03 | 2.1 否决项防线 | 识别否决项并要求逐条人工确认 | `project_requirement` 扩展、确认 API/UI | `human_confirmed=false` 时导出失败 |
| R04 | 2.2 资格与业绩要求 | 提取企业资质、项目经理、业绩、人员、技术方案要求 | 要求抽取服务、待确认列表 | 缺失字段进入待确认队列 |
| R05 | 四、Agent/Workflow | 固定工作流 Agent 执行主链路 | orchestrator、tool schema、workflow tests | 主链路可串行跑通并留痕 |
| R06 | 五、检索系统 | OpenSearch BM25 + 行业同义词检索 | 索引、同义词文件、搜索 API | 检索结果可命中同义词等价词 |
| R07 | 六、文档解析 | 使用 MinerU 解析标题树、条款、表格、页码 | 解析服务、section/table 持久化 | 上传文档后可查看解析结果 |
| R08 | 六、表格纠错机制 | 提供表格人工修正并覆盖保存 | `document_table_override`、修正页/API | 修正后再次查看以覆盖结果为准 |
| R09 | 七、Word 导出策略 | Word 模板占位符替换并导出 PDF | 模板引擎、导出服务、导出记录 | 指定章节成功写入模板并生成记录 |
| R10 | 八、AI 模型策略 | AI Gateway 统一路由模型和参数 | `/ai/chat`、任务路由配置、重试超时 | 各任务按预设模型/参数调用 |
| R11 | 九、页面设计 | 一期 7 个核心页面齐备 | `frontend/` 页面与组件 | 用户可完成端到端主链路 |
| R12 | 十三/十四章 | 完成核心表、对象存储、索引、服务目录 | DDL、迁移、compose、工程骨架 | 本地环境可启动核心基础设施 |
| R13 | 十五/十六章 | 建设并维护工程行业同义词库 | `synonyms.txt`、维护表、维护流程 | 可导入、查询、增补同义词 |
| R14 | 十七、最终能力总结 | 系统形成解析、抽取、生成、审校、导出闭环 | 联调方案、验收用例、试运行记录 | 真实样例项目完成闭环演示 |

## 1.1 已确认业务约束

- 一期角色模型：`项目编辑 / 复核人 / 管理员`
- 否决项确认：项目编辑可先确认，导出前需复核人或管理员二次确认
- 导出模板：一期先使用 1 套默认技术标 Word 模板，原始样板需在 Week 2 前补齐
- 占位符：同时支持章节名占位符和章节编码占位符，内部以编码主键维护
- 规范库来源：业务侧手工整理首批高频规范 PDF
- 同义词库：一期先整理 `100-200` 条高频种子词
- 审校门禁：`P0/P1` 阻断导出，`P2/P3` 仅提示
- 文件保留：一期默认长期保留，不做自动清理
- 环境策略：开发与测试先统一使用单机 Compose；测试环境先用 `IP + 端口`
- OpenSearch 安全：本地开发关闭安全插件，共享测试环境前切换 TLS/Auth
- 表格纠错：一期只支持整张表 JSON 覆盖
- 章节生成：一期目标为尽量全量生成所有技术标章节正文
- 企业知识库：一期接入少量精选历史标书作为参考知识库

## 2. 里程碑与周计划

| Milestone | 周次 | 目标 | 完成标志 |
|---|---|---|---|
| M0 | Week 1 | 工程骨架、基础设施、CI、DDL 初版 | 本地 `docker compose up` 成功，基础健康检查可用 |
| M1 | Week 2 | 文件上传、MinIO 存储、项目/文件元数据入库 | 可创建项目并上传招标文件 |
| M2 | Week 3 | MinerU 文档解析主链路 | 可生成 section/table/page 结构化结果 |
| M3 | Week 4 | 解析规则增强与表格纠错 | 表格覆盖保存并回显 |
| M4 | Week 5 | 规范库入库与条款树索引 | 规范 PDF 入库并可检索 |
| M5 | Week 6 | BM25 + 同义词检索能力可用 | 同义词检索命中率通过验证样例 |
| M6 | Week 7 | 章节提纲与正文生成 | 生成草稿并持久化到 `chapter_draft` |
| M7 | Week 8 | 审校能力上线 | 输出一致性/覆盖/引用问题清单 |
| M8 | Week 9 | Word/PDF 导出上线 | 基于模板完成导出 |
| M9 | Week 10 | 系统联调、试运行、验收 | 真实项目样本通过一期验收 |

## 3. 交付拆解与执行顺序

### Task 1: 仓库初始化与基础设施落位

**PRD 对应：**
- R01
- R05
- R12

**Files:**
- Create: `infra/docker-compose.yml`
- Create: `infra/opensearch/opensearch.yml`
- Create: `infra/opensearch/synonyms.txt`
- Create: `backend/app/main.py`
- Create: `backend/app/api/health.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/db/models/`
- Create: `backend/tests/smoke/test_health.py`
- Create: `frontend/package.json`
- Create: `frontend/src/main.tsx`
- Create: `docs/tracking/requirements-traceability.csv`

**Step 1: 初始化目录结构**

Run: `mkdir -p infra/opensearch backend/app/{api,core,db/models,services,agents,tools,schemas} backend/tests/smoke frontend/src docs/tracking`
Expected: 所有一期基础目录建立完成

**Step 2: 编写基础设施编排**

Run: `touch infra/docker-compose.yml infra/opensearch/synonyms.txt`
Expected: Docker Compose 至少包含 `postgres`、`redis`、`opensearch`、`minio`、`backend`、`ai-gateway`、`frontend`，其中 `opensearch` 为单节点部署

**Step 3: 建立后端健康检查**

Run: `touch backend/app/main.py backend/app/api/health.py backend/tests/smoke/test_health.py`
Expected: 具备 `/health` 接口和基础 smoke test

**Step 4: 建立前端壳工程**

Run: `touch frontend/package.json frontend/src/main.tsx`
Expected: 前端工程基于 `React 18 + TypeScript + Vite + TanStack Router + TanStack Query`

**Step 5: 创建需求追踪底表**

Run: `touch docs/tracking/requirements-traceability.csv`
Expected: 可按 `Req ID -> Work Package -> Status -> Evidence` 更新状态

**Step 6: 验证基础设施可启动**

Run: `docker compose -f infra/docker-compose.yml up -d`
Expected: 核心依赖容器全部启动

**Step 7: Commit**

```bash
git add infra backend frontend docs/tracking
git commit -m "chore: bootstrap ai tender monorepo"
```

### Task 2: 数据模型、迁移与项目文件管理

**PRD 对应：**
- R02
- R03
- R04
- R07
- R08
- R12

**Files:**
- Create: `backend/app/db/migrations/0001_initial_schema.sql`
- Create: `backend/app/db/repositories/project_repository.py`
- Create: `backend/app/db/repositories/file_repository.py`
- Create: `backend/app/api/projects.py`
- Create: `backend/app/api/files.py`
- Create: `backend/tests/integration/test_project_file_flow.py`

**Step 1: 编写一期核心表迁移**

Run: `touch backend/app/db/migrations/0001_initial_schema.sql`
Expected: 覆盖 `project`、`project_file`、`document`、`parse_job`、`document_section`、`document_table`、`document_table_override`、`project_requirement`、`project_fact`、`chapter_draft`、`review_issue`、`export_record`、`synonym_dictionary`

**Step 2: 落库 Repository**

Run: `touch backend/app/db/repositories/project_repository.py backend/app/db/repositories/file_repository.py`
Expected: 项目、文件、文档、要求、草稿、导出记录具备持久化入口

**Step 3: 暴露项目和上传接口**

Run: `touch backend/app/api/projects.py backend/app/api/files.py`
Expected: 支持创建项目、上传文件、查询文件列表

**Step 4: 验证迁移与最小业务流**

Run: `pytest backend/tests/integration/test_project_file_flow.py -v`
Expected: 项目创建和文件入库通过

**Step 5: Commit**

```bash
git add backend/app/db backend/app/api backend/tests/integration
git commit -m "feat: add project and file persistence"
```

### Task 3: 招标文件解析与结构化结果持久化

**PRD 对应：**
- R05
- R07

**Files:**
- Create: `backend/app/services/parse_service/mineru_client.py`
- Create: `backend/app/services/parse_service/parser.py`
- Create: `backend/app/services/parse_service/task_poller.py`
- Create: `backend/app/api/parse.py`
- Create: `backend/app/agents/parse_project_agent.py`
- Create: `backend/tests/integration/test_parse_pipeline.py`
- Create: `docs/plans/2026-03-14-mineru-async-parse-design.md`

**Step 1: 封装 MinerU 客户端**

Run: `touch backend/app/services/parse_service/mineru_client.py`
Expected: 支持申请 MinerU 上传链接、后端直传文件、轮询结果、标准化解析输出

**Step 2: 持久化标题树、条款、表格、页码**

Run: `touch backend/app/services/parse_service/parser.py`
Expected: 解析结果写入 `document_section` 和 `document_table`

**Step 3: 暴露解析任务接口**

Run: `touch backend/app/api/parse.py`
Expected: 上传后的文件先进入 MinIO 留档，再触发异步解析任务并可查询状态

**Step 4: 建立项目解析 Agent**

Run: `touch backend/app/agents/parse_project_agent.py`
Expected: 串联 `upload_to_minio`、`request_mineru_upload_url`、`upload_file_to_mineru`、`parse_document`、`extract_project_facts`、`extract_outline`、`save_project_constraints`

**Step 5: 验证解析主链路**

Run: `pytest backend/tests/integration/test_parse_pipeline.py -v`
Expected: 测试样本可生成结构化 section/table 数据

**Step 6: Commit**

```bash
git add backend/app/services/parse_service backend/app/api/parse.py backend/app/agents backend/tests/integration
git commit -m "feat: add tender document parsing pipeline"
```

### Task 4: 要求抽取、否决项识别与人工确认闭环

**PRD 对应：**
- R02
- R03
- R04
- R05

**Files:**
- Create: `backend/app/services/extract_service/requirements_extractor.py`
- Create: `backend/app/services/extract_service/facts_extractor.py`
- Create: `backend/app/api/requirements.py`
- Create: `frontend/src/pages/requirements-confirmation.tsx`
- Create: `backend/tests/integration/test_requirement_confirmation.py`

**Step 1: 编写要求抽取服务**

Run: `touch backend/app/services/extract_service/requirements_extractor.py backend/app/services/extract_service/facts_extractor.py`
Expected: 能抽取否决项、资质、人员、业绩、技术要求，并区分 `requirement_category`

**Step 2: 写入待确认与已确认状态**

Run: `touch backend/app/api/requirements.py`
Expected: 支持查询待确认清单、逐条确认、记录确认人和时间

**Step 3: 建立人工确认页面**

Run: `touch frontend/src/pages/requirements-confirmation.tsx`
Expected: 支持筛选否决项、查看原文、确认状态切换

**Step 4: 增加导出前门禁校验**

Run: `touch backend/tests/integration/test_requirement_confirmation.py`
Expected: 任何 `human_confirmed=false` 的否决项都会阻断导出

**Step 5: Commit**

```bash
git add backend/app/services/extract_service backend/app/api/requirements.py frontend/src/pages/requirements-confirmation.tsx backend/tests/integration
git commit -m "feat: add requirement extraction and human confirmation gate"
```

### Task 5: 规范库入库、同义词词典与检索能力

**PRD 对应：**
- R05
- R06
- R13

**Files:**
- Create: `backend/app/services/search_service/index_manager.py`
- Create: `backend/app/services/search_service/query_service.py`
- Create: `backend/app/services/search_service/synonym_loader.py`
- Create: `backend/app/api/search.py`
- Create: `backend/app/agents/index_standard_agent.py`
- Create: `backend/tests/integration/test_search_with_synonyms.py`

**Step 1: 定义索引结构**

Run: `touch backend/app/services/search_service/index_manager.py`
Expected: 建立 `section_index` 与 `clause_index`

**Step 2: 导入同义词库**

Run: `touch backend/app/services/search_service/synonym_loader.py infra/opensearch/synonyms.txt`
Expected: 支持初始导入、增量维护、与 `synonym_dictionary` 对齐

**Step 3: 建立规范入库 Agent**

Run: `touch backend/app/agents/index_standard_agent.py`
Expected: 串联 `parse_document`、`build_clause_tree`、`tag_clauses`、`index_standard`

**Step 4: 提供检索 API**

Run: `touch backend/app/services/search_service/query_service.py backend/app/api/search.py`
Expected: 覆盖 `search_tender_requirements`、`search_sections`、`search_clauses`、`search_company_docs`

**Step 5: 验证同义词检索**

Run: `pytest backend/tests/integration/test_search_with_synonyms.py -v`
Expected: 例如查询“土方开挖”时可命中“基坑开挖”相关内容

**Step 6: Commit**

```bash
git add backend/app/services/search_service backend/app/api/search.py backend/app/agents/index_standard_agent.py infra/opensearch/synonyms.txt backend/tests/integration
git commit -m "feat: add standards indexing and synonym-aware search"
```

### Task 6: AI Gateway、Tool Schema 与章节生成

**PRD 对应：**
- R05
- R09
- R10

**Files:**
- Create: `ai_gateway/app/main.py`
- Create: `ai_gateway/app/router.py`
- Create: `ai_gateway/app/task_profiles.py`
- Create: `ai_gateway/app/providers/openai_compatible.py`
- Create: `ai_gateway/app/providers/claude_compatible.py`
- Create: `ai_gateway/app/api/credentials.py`
- Create: `backend/app/tools/search_clauses.py`
- Create: `backend/app/tools/search_sections.py`
- Create: `backend/app/agents/generate_section_agent.py`
- Create: `backend/app/api/drafts.py`
- Create: `backend/tests/integration/test_generate_section_flow.py`

**Step 1: 搭建 AI Gateway**

Run: `touch ai_gateway/app/main.py ai_gateway/app/router.py`
Expected: 暴露 `/ai/chat` 与凭据管理接口，支持 DeepSeek 主、Qwen 备、ccswitch OpenAI/Claude 兼容接入，以及模型路由、重试、超时、限流、任务参数映射；不承载业务 workflow

**Step 2: 实现工具层**

Run: `touch backend/app/tools/search_clauses.py backend/app/tools/search_sections.py`
Expected: tool schema 与后端检索服务一致

**Step 3: 建立章节生成 Agent**

Run: `touch backend/app/agents/generate_section_agent.py backend/app/api/drafts.py`
Expected: 按 `get_project_facts -> search_clauses -> search_sections -> call_llm -> save_draft` 生成草稿

**Step 4: 验证生成闭环**

Run: `pytest backend/tests/integration/test_generate_section_flow.py -v`
Expected: 生成提纲和章节正文，并持久化到 `chapter_draft`

**Step 5: Commit**

```bash
git add ai_gateway backend/app/tools backend/app/agents/generate_section_agent.py backend/app/api/drafts.py backend/tests/integration
git commit -m "feat: add ai gateway and draft generation workflow"
```

### Task 7: 审校能力与问题清单输出

**PRD 对应：**
- R05
- R14

**Files:**
- Create: `backend/app/services/review_service/review_engine.py`
- Create: `backend/app/agents/review_agent.py`
- Create: `backend/app/api/review.py`
- Create: `frontend/src/pages/review-results.tsx`
- Create: `backend/tests/integration/test_review_flow.py`

**Step 1: 实现审校引擎**

Run: `touch backend/app/services/review_service/review_engine.py`
Expected: 检查项目事实一致性、招标要求覆盖、规范引用

**Step 2: 建立审校 Agent**

Run: `touch backend/app/agents/review_agent.py backend/app/api/review.py`
Expected: 可对指定草稿批量生成 `review_issue`

**Step 3: 建立审校结果页**

Run: `touch frontend/src/pages/review-results.tsx`
Expected: 展示问题级别、章节、问题内容和修复状态

**Step 4: 验证审校结果落库**

Run: `pytest backend/tests/integration/test_review_flow.py -v`
Expected: 审校问题可生成、查询、回显

**Step 5: Commit**

```bash
git add backend/app/services/review_service backend/app/agents/review_agent.py backend/app/api/review.py frontend/src/pages/review-results.tsx backend/tests/integration
git commit -m "feat: add review workflow and issue tracking"
```

### Task 8: 表格人工纠错与解析结果页

**PRD 对应：**
- R07
- R08
- R11

**Files:**
- Create: `backend/app/api/table_overrides.py`
- Create: `frontend/src/pages/parse-results.tsx`
- Create: `frontend/src/components/table-override-editor.tsx`
- Create: `backend/tests/integration/test_table_override.py`

**Step 1: 暴露表格纠错接口**

Run: `touch backend/app/api/table_overrides.py`
Expected: 支持读取原表格、提交修正结果、查询当前生效版本

**Step 2: 实现解析结果页和编辑器**

Run: `touch frontend/src/pages/parse-results.tsx frontend/src/components/table-override-editor.tsx`
Expected: 可查看 section/table/page 并编辑表格内容

**Step 3: 验证覆盖生效**

Run: `pytest backend/tests/integration/test_table_override.py -v`
Expected: 修正后再次读取优先返回 `document_table_override`

**Step 4: Commit**

```bash
git add backend/app/api/table_overrides.py frontend/src/pages/parse-results.tsx frontend/src/components/table-override-editor.tsx backend/tests/integration
git commit -m "feat: add parse results page and table override flow"
```

### Task 9: 导出服务、模板替换与导出门禁

**PRD 对应：**
- R02
- R09
- R14

**Files:**
- Create: `backend/app/services/export_service/docx_exporter.py`
- Create: `backend/app/services/export_service/pdf_exporter.py`
- Create: `backend/app/api/exports.py`
- Create: `frontend/src/pages/export.tsx`
- Create: `backend/tests/integration/test_export_gate_and_render.py`

**Step 1: 封装 Word 模板导出**

Run: `touch backend/app/services/export_service/docx_exporter.py`
Expected: 基于占位符 `{{SECTION_xxx}}` 渲染 DOCX

**Step 2: 增加 PDF 导出与导出记录**

Run: `touch backend/app/services/export_service/pdf_exporter.py backend/app/api/exports.py`
Expected: 成功导出后写入 `export_record`

**Step 3: 在导出前执行门禁**

Run: `touch backend/tests/integration/test_export_gate_and_render.py`
Expected: 未确认否决项、缺失章节、关键审校问题未处理时导出失败

**Step 4: 建立导出页**

Run: `touch frontend/src/pages/export.tsx`
Expected: 可选择模板、触发导出、下载文件、查看导出记录

**Step 5: Commit**

```bash
git add backend/app/services/export_service backend/app/api/exports.py frontend/src/pages/export.tsx backend/tests/integration
git commit -m "feat: add gated docx and pdf export"
```

### Task 10: 前端主链路页面补齐与端到端联调

**PRD 对应：**
- R11
- R14

**Files:**
- Create: `frontend/src/pages/project-list.tsx`
- Create: `frontend/src/pages/upload.tsx`
- Create: `frontend/src/pages/chapter-editor.tsx`
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/tests/e2e/tender-flow.spec.ts`
- Create: `docs/tracking/uat-checklist.md`

**Step 1: 补齐 7 个一期页面**

Run: `touch frontend/src/pages/project-list.tsx frontend/src/pages/upload.tsx frontend/src/pages/chapter-editor.tsx`
Expected: 7 个页面全部具备入口和路由

**Step 2: 对接 API**

Run: `touch frontend/src/lib/api.ts`
Expected: 文件上传、解析、确认、检索、生成、审校、导出接口全部串通

**Step 3: 编写 E2E 主链路测试**

Run: `touch frontend/tests/e2e/tender-flow.spec.ts`
Expected: 自动覆盖“建项目 -> 上传 -> 解析 -> 确认 -> 生成 -> 审校 -> 导出”

**Step 4: 编写 UAT 清单**

Run: `touch docs/tracking/uat-checklist.md`
Expected: 每个 Req ID 均有业务验收项和证据链接

**Step 5: 运行端到端验收**

Run: `pytest backend/tests/integration -v && npm --prefix frontend test`
Expected: 集成测试与前端测试全部通过

**Step 6: Commit**

```bash
git add frontend docs/tracking
git commit -m "feat: complete frontend flow and uat checklist"
```

## 4. 周度跟踪机制

### 周报字段

- `Week`
- `Milestone`
- `Req ID`
- `Work Package`
- `Owner`
- `Planned End`
- `Actual End`
- `Status`：`todo / doing / blocked / done`
- `Evidence`：测试报告、截图、接口日志、演示链接
- `Risk`
- `Next Action`

### 状态更新规则

- 每周一更新计划值和本周目标。
- 每周三更新阻塞项、风险和需求偏差。
- 每周五更新证据链接和阶段结论。
- 任一 `Req ID` 未绑定到工作包时，不允许宣告阶段完成。
- 任一关键门禁测试失败时，不允许进入下一里程碑。

## 5. 验收基线

### 功能验收

- 招标文件上传后 30 分钟内可查看解析结构化结果。
- 否决项必须人工确认后才能导出。
- 至少 1 个真实样本项目完成“解析 -> 生成 -> 审校 -> 导出”闭环。
- 检索支持 BM25 + 同义词，验证样例命中符合预期。
- 章节草稿、审校问题、导出记录均可回溯到项目维度。

### 技术验收

- 本地或测试环境可通过 `docker compose` 启动核心依赖。
- 核心 API 具备健康检查、日志、超时和失败重试。
- 数据库迁移可重复执行。
- 集成测试覆盖主链路关键门禁。

## 6. 主要风险与应对

| 风险 | 影响 | 应对措施 |
|---|---|---|
| MinerU 解析质量不稳定 | 影响抽取和生成质量 | 先建立解析结果回显与表格纠错，再做下游自动化 |
| 同义词库初期覆盖不足 | 影响检索命中率 | Week 5 即建立维护表和人工增补流程 |
| AI 生成不稳定 | 影响章节可用性 | 强制检索证据输入、降低 temperature、增加审校门禁 |
| 导出模板与章节命名不一致 | 影响导出成功率 | 建立模板占位符命名规范和导出前校验 |
| 仓库从零启动，工期紧 | 前两周易延误 | M0/M1 必须先完成工程骨架和数据流闭环，不提前分散做高级能力 |

## 7. 完成判定

- 所有 `Req ID` 均在 `docs/tracking/requirements-traceability.csv` 中标记为 `done` 或有明确延期说明。
- M0-M9 里程碑均有证据。
- 至少完成一轮真实样本 UAT。
- 无阻断导出的 P0/P1 缺陷遗留。
- 交付包含运行说明、测试结果、模板样例和演示记录。
