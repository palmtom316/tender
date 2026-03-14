# AI辅助投标系统一期基线摘要

## 1. 当前状态

截至当前，一期实施所需的主要技术与业务边界已基本确认，除 `D08` 验收样本外，其余关键决策均已拍板。

本摘要用于作为后续工程实施、任务拆解、团队同步和验收准备的统一口径。

## 2. 已确认的核心技术基线

### 前端

- 框架：`React 18 + TypeScript + Vite`
- 路由：`TanStack Router`
- 数据请求：`TanStack Query`
- 形态：内网业务台 SPA，不做 SSR

### 后端

- 业务后端：`FastAPI`
- 基础存储：`PostgreSQL + Redis + MinIO`
- 检索：`OpenSearch`
- 导出：`docxtpl`

### AI Gateway

- 独立轻服务，不承载业务 workflow
- 主模型：`DeepSeek`
- 备模型：`Qwen`
- 兼容：`ccswitch` 中转的 `OpenAI-compatible` 与 `Claude-compatible` 模型

### API Key / BYOK

- 允许前端录入 API Key
- 仅允许服务端代理 BYOK
- 禁止前端直连上游模型
- 开发环境可使用 BYOK
- 测试/生产环境默认平台托管 Key

### 文档解析

- 使用 `MinerU Commercial API`
- 采用“后端申请上传链接并直传文件”的模式
- `MinIO` 仅用于内部留档，不承担给 MinerU 分发文件
- 解析链路：`上传文件 -> 申请上传链接 -> 后端直传 -> 异步轮询 -> 结果落库`

### 部署

- 开发与测试环境：单机 `Docker Compose`
- 测试环境先用 `IP + 端口` 联调
- OpenSearch：本地开发关闭安全插件，进入共享测试环境前开启 `TLS/Auth`

## 3. 已确认的业务基线

### 角色与权限

- 一期角色：`项目编辑 / 复核人 / 管理员`
- 否决项可由项目编辑先确认
- 导出前必须由复核人或管理员二次确认

### 模板与导出

- 一期先使用 `1` 套默认技术标 Word 模板
- 模板原始样板由现有常用 Word 样板提供，需在 `Week 2` 前补齐
- 占位符同时支持：
  - 章节名占位符，例如 `{{SECTION_施工组织设计}}`
  - 章节编码占位符，例如 `{{SECTION_S01}}`
- 系统内部以章节编码作为稳定主键

### 检索与知识库

- 首批规范库：业务侧手工整理高频规范 PDF
- 同义词库：一期先做 `100-200` 条高频种子词
- 企业知识库：接入少量精选历史标书，不接全量历史标书库

### 审校与导出门禁

- `P0/P1` 问题阻断导出
- `P2/P3` 问题仅提示

### 表格纠错

- 一期只支持整张表 JSON 覆盖
- 不做单元格级编辑
- 不做版本对比

### 内容生成

- 一期目标是尽量全量生成所有技术标章节正文

### 数据保留

- 原始文件、解析结果、草稿、导出件默认长期保留
- 一期不做自动清理

## 4. 当前唯一关键未决项

### D08 验收样本

仍需补齐：

- `2-3` 份真实招标文件
- 最好附 `1` 套期望导出样例

这个决策直接影响：

- 解析验收
- 检索质量评估
- 章节生成验收
- 审校规则调优
- 导出结果比对

## 5. 对实施的直接影响

### 已可以开始的工作

- 搭建 `backend / frontend / ai_gateway` 工程骨架
- 落数据库迁移与 `parse_job` 异步状态模型
- 落 `docker-compose` 基础环境
- 落 OpenSearch 索引与同义词导入逻辑
- 落 MinerU 异步解析接口与 worker
- 落 AI Gateway 的 provider 抽象和凭据管理接口

### 仍需等待样本后再做深调的工作

- 解析效果调优
- 同义词词库补齐
- 审校规则阈值优化
- 模板映射与导出验收
- 历史标书参考知识库质量评估

## 6. 关联文档

- 实施计划：[2026-03-14-ai-tender-v1-implementation-plan.md](/Users/palmtom/Projects/tender/docs/plans/2026-03-14-ai-tender-v1-implementation-plan.md)
- 技术选型：[2026-03-14-technical-stack-design.md](/Users/palmtom/Projects/tender/docs/plans/2026-03-14-technical-stack-design.md)
- MinerU 异步解析设计：[2026-03-14-mineru-async-parse-design.md](/Users/palmtom/Projects/tender/docs/plans/2026-03-14-mineru-async-parse-design.md)
- 待拍板清单：[2026-03-14-decision-checklist.md](/Users/palmtom/Projects/tender/docs/plans/2026-03-14-decision-checklist.md)
