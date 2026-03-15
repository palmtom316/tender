# AI辅助投标系统一期 —— 专家审批意见书

**审批日期：** 2026-03-15
**审批范围：** PRD v1.1、架构设计 v2.1、实施计划、技术选型、基线摘要、待拍板清单、MinerU 异步解析设计
**审批基线：** 当前仓库已完成 Phase 0 骨架搭建（3 次提交），含 12 张数据表迁移、4 个后端 API 路由、AI Gateway 合约桩、前端壳工程

---

## 一、建设工程投标专家审批意见

### 1.1 肯定项

- **否决项防线设计到位。** `human_confirmed` + 导出门禁 + 复核人二次确认的三道闸门，符合实际投标风控需求，可有效降低废标率。
- **结构化优先的核心原则正确。** 技术标编制本质是"结构化信息组装"而非自由写作，系统定位准确。
- **表格纠错机制务实。** 招标文件中评分表、资质表解析错误是最常见的上游风险，提供人工覆盖正确。

### 1.2 问题与修订要求

| 编号 | 严重度 | 问题 | 修订要求 |
|---|---|---|---|
| B-01 | **P0** | **D08 验收样本仍为 pending**，是唯一未决关键项。无样本则解析调优、检索评估、章节生成验收、导出比对全部无法闭环 | Week 1 结束前必须落实 2-3 份真实招标文件 + 1 套期望导出样例，否则项目不应进入 Week 3（解析阶段） |
| B-02 | **P1** | **缺少评分标准（评分办法）结构化处理。** 技术标投标最核心的得分依据是评分表，当前 PRD 只提到"资格与业绩要求"，未将评分标准单独建模 | 在 `project_requirement` 中增加 `scoring` 类别，或新增 `scoring_criteria` 表，将评分维度、分值、评分方式结构化入库，供生成和审校引用 |
| B-03 | **P1** | **缺少响应矩阵（Compliance Matrix）。** 投标实务中需要逐条对照招标要求生成响应条目，当前系统无此机制 | 增加"响应矩阵"视图：每条招标要求 → 对应章节 → 响应状态（已覆盖/部分覆盖/未覆盖），作为审校的核心输入 |
| B-04 | **P2** | **同义词种子词 100-200 条偏少。** 建设工程常用术语跨专业（土建、安装、市政、装饰）差异大，100 条难以覆盖主要词汇鸿沟 | 一期种子词建议提升至 **300-500 条**，按专业分类组织，并在 Week 5 前由业务侧完成初版交付 |
| B-05 | **P2** | **未考虑投标截止时间紧迫性。** 投标项目天然有截止日期压力，系统无优先级队列和紧急通道 | 在 `project` 表的 `tender_deadline` 基础上，增加项目紧急程度标识，影响解析和生成任务的调度优先级 |
| B-06 | **P2** | **缺少标书格式要求处理。** 许多招标文件对页面格式（字体、字号、行距、页边距）有明确要求，这些需要反映到 Word 模板中 | 在要求抽取中增加"格式要求"类别，导出时校验模板是否符合格式要求 |

---

## 二、AI 技术专家审批意见

### 2.1 肯定项

- **"Workflow 优先于自由 Agent" 原则正确。** 在投标文档这种高准确性要求的场景，固定工作流比自主 Agent 可控得多。
- **AI Gateway 独立服务设计合理。** 模型路由与业务逻辑解耦，便于后续切换供应商。
- **Trace / Eval 从一期就规划**，这对于 AI 系统的持续改进至关重要。

### 2.2 问题与修订要求

| 编号 | 严重度 | 问题 | 修订要求 |
|---|---|---|---|
| A-01 | **P0** | **主模型策略文档冲突。** PRD v1.1 第八章写"主模型: Qwen"；技术选型和决策清单 D02 写"主模型: DeepSeek, 备: Qwen"；架构 v2.1 写"Qwen / DeepSeek / GLM"未明确主备。**三份文档口径不一致** | 统一所有文档为已拍板结论：**DeepSeek 主、Qwen 备**。修订 PRD v1.1 第八章和架构 v2.1 相关段落 |
| A-02 | **P0** | **OpenSearch 中文分词器缺失。** 架构 v2.1 的 `cn_with_synonym` analyzer 使用 `standard` tokenizer，该分词器对中文只做字符级切分，**不做词级分词**，将严重影响 BM25 检索质量 | 必须引入中文分词插件（如 `ik_max_word` 或 `analysis-smartcn`），在 `cn_with_synonym` 中替换 `standard` 为中文分词 tokenizer。这是检索质量的基础 |
| A-03 | **P1** | **Prompt 版本管理机制不完整。** 架构 v2.1 提到 jinja2 模板和 `prompt_template` 表，但实施计划中未安排 Prompt 版本化、灰度切换和效果对比的具体工作 | 在 Week 6-7（AI 集成阶段）增加 prompt 版本化管理任务：prompt 模板入库、版本号与 trace 关联、支持按版本回溯生成效果 |
| A-04 | **P1** | **AI Gateway 当前实现过于单薄。** 合约桩缺少：streaming 支持、token 计数、cost 追踪、provider fallback 逻辑、限流实现 | 在 Task 6 中明确 AI Gateway 的最小可用能力：(1) 实际调用至少一个 provider (2) fallback 切换 (3) token/cost 记录 (4) 超时重试 |
| A-05 | **P2** | **Eval 体系排在 Week 10 过晚。** 评测集应在生成能力开发同期建立，否则无法迭代改进 prompt 和检索策略 | 将 Eval 基础框架（测试集管理、评分脚本）提前到 Week 7，与章节生成同步迭代 |

---

## 三、资深架构师审批意见

### 3.1 肯定项

- **Monorepo 组织清晰。** `backend / ai_gateway / frontend / infra / docs` 分层合理。
- **Docker Compose 基础设施完整。** 9 个服务定义齐全，profile 分离、MinIO 自动初始化等工程细节到位。
- **Repository 模式 + 依赖注入模式** 为后续测试和替换打下良好基础。

### 3.2 问题与修订要求

| 编号 | 严重度 | 问题 | 修订要求 |
|---|---|---|---|
| C-01 | **P0** | **数据库 Schema 严重不一致。** 架构 v2.1 定义 25 张表，实际迁移仅 12-13 张表。缺失的关键表包括：`workflow_run`、`workflow_step_log`、`task_trace`、`standard`、`standard_clause`、`project_outline_node`、`human_confirmation`、`section_template`、`prompt_template`、`model_profile`、`tool_definition`、`skill_definition` | 分两阶段补齐：(1) Week 2 迁移中补充 `standard`、`standard_clause`、`project_outline_node`、`human_confirmation`、`section_template` (2) Week 6 补充 `workflow_run`、`workflow_step_log`、`task_trace`、配置表。并明确文档以实际迁移为准 |
| C-02 | **P0** | **代码包结构与架构文档不一致。** 架构 v2.1 写 `backend/app/`，实际代码用 `backend/tender_backend/`。PRD v1.1 写 `backend/api/`。**三份文档三种路径** | 以实际代码 `tender_backend/` 为准，统一回写所有架构文档的目录结构 |
| C-03 | **P1** | **Celery Worker 架构未落地。** 架构 v2.1 明确规划了 `worker-workflow`、`worker-io`、`worker-gpu` 三个 Worker，但 Docker Compose 无 worker 服务，backend requirements 无 Celery 依赖 | 在 Task 1 补充中加入 Celery + Redis broker 依赖，Docker Compose 中至少添加 `worker-io`（处理解析任务）。完整 worker 分拆可推迟到 Week 7 |
| C-04 | **P1** | **缺少数据库迁移工具。** 当前使用裸 SQL 文件，无版本管理和可重复执行保障 | 引入 Alembic 或至少实现一个有序迁移执行脚本（`apply_migrations.py`），确保迁移可追踪、可重复执行 |
| C-05 | **P1** | **Workflow Engine 排期过晚。** 当前排在 Week 7，但 Week 3 的解析流程、Week 4 的抽取流程、Week 6 的生成流程都需要 workflow 编排能力 | Workflow Engine 基座（`BaseWorkflow`、`WorkflowContext`、`workflow_run` 表）应提前到 **Week 2-3** 完成，Week 7 做完整的 generate_section / review workflow |
| C-06 | **P1** | **前端页面集中在 Week 10，风险极高。** 7 个页面全部推迟到最后一周，任何后端接口问题都将导致前端无法联调 | 前端开发应与后端同步推进：(1) Week 2-3 完成项目列表+上传页 (2) Week 4-5 完成解析结果+确认页 (3) Week 7-8 完成编辑+审校页 (4) Week 9 完成导出页 |
| C-07 | **P2** | **认证授权未规划。** 架构 v2.1 的代码结构包含 `security.py`，三角色模型已确认，但实施计划中无 auth 实现任务 | 在 Week 2 增加基础认证（至少 session/token），Week 4 增加角色权限控制。一期可简化为固定 token + 角色标记 |
| C-08 | **P2** | **缺少结构化日志和错误处理中间件。** 当前 FastAPI 应用无统一日志格式、无全局异常处理 | 在 Task 1 补充中加入 structlog 或 loguru 配置、全局异常处理中间件，确保所有请求可追踪 |

---

## 四、综合审批结论

### 审批结果：有条件批准

项目文档体系完整、技术路线合理、核心原则正确。但在文档一致性、架构落地和实施排期方面存在 **3 个 P0 问题**和 **8 个 P1 问题**，需在开工前完成修订。

### 批准条件（开工前必须完成）

1. **解决 D08：** 在 Week 1 结束前落实验收样本（2-3 份真实招标文件）
2. **统一主模型策略文档：** PRD v1.1、架构 v2.1 与决策清单口径统一为"DeepSeek 主、Qwen 备"
3. **修复 OpenSearch 中文分词：** 将 `standard` tokenizer 替换为中文分词器
4. **对齐 Schema 与迁移：** 制定分阶段补表计划，明确文档以实际迁移为准
5. **统一代码包路径：** 所有文档回写实际路径 `tender_backend/`

### 实施计划修订要求

| 修订项 | 原排期 | 建议调整 | 理由 |
|---|---|---|---|
| Workflow Engine 基座 | Week 7 | **Week 2-3** | 解析/抽取/生成均依赖 workflow 编排 |
| 前端页面开发 | Week 10 集中 | **Week 2-9 分散同步** | 降低最后一周联调风险 |
| Celery Worker 引入 | 未排期 | **Week 2** | 异步解析任务需要 worker |
| 数据库迁移工具 | 未排期 | **Week 1 补充** | 保障迁移可追踪可重复 |
| Eval 基础框架 | Week 10 | **Week 7** | 与生成能力同步迭代 |
| 基础认证 | 未排期 | **Week 2** | 三角色模型需要 auth 支撑 |
| 评分标准结构化 | 未排期 | **Week 4** | 与要求抽取同期完成 |
| 响应矩阵 | 未排期 | **Week 8** | 与审校同期完成 |

---

## 五、问题汇总清单

| 编号 | 来源 | 严重度 | 状态 |
|---|---|---|---|
| B-01 | 投标专家 | P0 | pending |
| B-02 | 投标专家 | P1 | pending |
| B-03 | 投标专家 | P1 | pending |
| B-04 | 投标专家 | P2 | pending |
| B-05 | 投标专家 | P2 | pending |
| B-06 | 投标专家 | P2 | pending |
| A-01 | AI专家 | P0 | pending |
| A-02 | AI专家 | P0 | pending |
| A-03 | AI专家 | P1 | pending |
| A-04 | AI专家 | P1 | pending |
| A-05 | AI专家 | P2 | pending |
| C-01 | 架构师 | P0 | pending |
| C-02 | 架构师 | P0 | pending |
| C-03 | 架构师 | P1 | pending |
| C-04 | 架构师 | P1 | pending |
| C-05 | 架构师 | P1 | pending |
| C-06 | 架构师 | P1 | pending |
| C-07 | 架构师 | P2 | pending |
| C-08 | 架构师 | P2 | pending |
