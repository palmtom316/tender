# AI辅助投标系统一期技术选型设计

## 1. 设计目标

本设计用于确定一期实施中的三个关键技术决策：

- 前端框架
- AI Gateway 接入方式
- MinerU 与 OpenSearch 的实际部署方式

设计目标不是追求“长期最全”，而是在当前约束下选择最低风险、最快落地、后续仍可扩展的方案。

## 2. 已确认约束

- 产品一期形态：内网业务台，以表单、表格、流程和审校为主，不要求 SEO。
- 模型接入：一期统一走云上模型 API。
- 主备模型策略：`DeepSeek` 主、`Qwen` 备，并兼容 `ccswitch` 提供的 OpenAI 与 Claude 模型接入。
- 文档解析：MinerU 使用商业 API，不自建解析服务。
- 部署形态：单机 Docker Compose。
- 当前仓库状态：仅有 PRD，无现成工程代码，需要从零搭建工程骨架。

## 3. 方案比较

### 方案 A：React + Vite SPA，独立 FastAPI 后端，独立 AI Gateway

**适用方式**

- 前端作为纯 SPA 内网台
- FastAPI 承载业务 API 和工作流
- AI Gateway 作为独立轻服务
- MinerU 作为外部商业 API
- OpenSearch、PostgreSQL、Redis、MinIO 单机容器部署

**优点**

- 与当前“内网台 + 单机 Compose + 云 API”约束最匹配
- 运行面较小，部署与排障都简单
- 前后端边界清晰，便于分工
- 后续要替换前端框架或扩展 AI provider，改动局部可控

**缺点**

- 需要单独处理前后端鉴权、CORS 和 API 代理
- 不提供 SSR / BFF 能力

### 方案 B：Next.js 全栈，AI Gateway 并入 BFF 或主后端

**优点**

- 如果未来转门户或需要 SSR，会更顺手
- 前端聚合接口能力更强

**缺点**

- 对当前内部流程产品是过度设计
- 单机部署时服务拓扑更复杂
- 不能直接降低当前一期的核心交付风险

### 方案 C：Vue 3 + Vite SPA，其他保持不变

**优点**

- 如果团队 Vue 积累更强，会更顺手

**缺点**

- 当前没有来自团队偏好的强约束支持该方案
- 相对 React 方案，没有显著降低一期架构风险

## 4. 最终决策

### 4.1 前端框架

定版为：

- `React 18`
- `TypeScript`
- `Vite`
- `TanStack Router`
- `TanStack Query`

**决策理由**

- Vite 官方将其定位为提供更快、更轻量现代 Web 开发体验的构建工具，适合中后台 SPA。  
  来源：<https://vite.dev/guide/>
- TanStack Router 官方文档强调类型安全导航、内建 loader 缓存、搜索参数状态管理，适合项目列表、解析结果、确认页、编辑页、审校页这类 URL 状态和筛选条件较重的业务台。  
  来源：<https://tanstack.com/router/latest/docs/overview>

**落地要求**

- 前端不做 SSR
- 采用 SPA 部署到静态资源容器或 Nginx
- 页面以“项目列表、上传、解析结果、否决项核验、章节编辑、审校结果、导出”7 页为一级路由
- 列表筛选、审校筛选、章节定位等状态尽量落到 URL search params

### 4.2 AI Gateway 接入方式

定版为：`独立轻量 AI Gateway 服务`

**职责边界**

- provider 路由
- 模型与任务类型映射
- 兼容 OpenAI-compatible 与 Claude 风格上游接口
- API Key / Token 管理
- retry / timeout / 限流
- 统一 trace_id、审计日志、错误包装

**明确不做**

- 不承载业务工作流编排
- 不管理项目状态
- 不直接落业务数据库
- 不实现章节生成、审校等业务逻辑

**调用链**

`frontend -> backend -> ai-gateway -> cloud model api`

**这样设计的原因**

- 一期只接云上模型 API，没有必要一开始做重网关平台
- 把模型配置与业务流程拆开，后续替换 Qwen / DeepSeek / GLM 时不需要大改业务层
- 兼容 `ccswitch` 的 OpenAI 与 Claude 模型后，可在不改业务接口的前提下切换上游
- 统一超时、重试、限流和日志，对后续线上稳定性更有价值

**当前模型策略**

- 默认主模型：`DeepSeek`
- 默认备模型：`Qwen`
- API Key 管理：
  - 开发环境允许前端录入 API Key，但仅作为服务端代理 BYOK 输入
  - 测试/生产环境默认平台托管 Key
  - 所有环境均禁止前端直连上游模型
- 网关兼容：
  - OpenAI-compatible provider
  - Claude provider
  - `ccswitch` 作为统一中转入口时的路由与鉴权

**BYOK 边界**

- 前端可以提供“录入个人 Key”界面
- Key 只提交给 `backend/ai-gateway`
- 后端返回 `credential_id` 或同类引用标识
- 后续业务请求仅传引用标识，不回传明文 Key
- 真正访问上游模型的一直是 `ai-gateway`

### 4.3 MinerU 接入方式

定版为：`MinerU 商业 API + 后端直传上传链接 + 异步任务封装`

**关键事实**

- MinerU 单文件解析接口要求 `url`，不支持直接上传文件
- MinerU 同时提供批量文件上传解析接口，可先申请上传链接，再由后端把本地文件直接上传到 MinerU
- 上传完成后，MinerU 会自动提交解析任务
- 单文件限制 200MB / 600 页

来源：

- <https://mineru.net/doc/docs/>
- <https://mineru.net/doc/docs/index_en/>

**落地流程**

1. 用户上传招标文件到系统
2. `backend` 将原文件存入 `MinIO` 作为内部留档
3. `backend` 调用 MinerU 批量上传接口申请上传链接
4. `backend` 使用返回的上传链接将文件直传到 MinerU
5. MinerU 自动创建解析任务
6. `backend` 轮询任务状态并拉取结果
7. 解析结果标准化后写入 `document`、`document_section`、`document_table`

**工程要求**

- 不再依赖 MinIO 文件对 MinerU 可见
- 后端必须做异步任务状态管理，不能把解析调用绑在同步请求上
- 需要对超限文件在上传前做本地校验
- 需要保存 MinerU `batch_id`、文件级任务 ID 与重试记录

**不建议的一期做法**

- 不自建 MinerU 服务
- 不在前端直接调用 MinerU API
- 不把 MinerU token 暴露到浏览器

### 4.4 OpenSearch 部署方式

定版为：`单机单节点 Docker Compose`

**关键事实**

- OpenSearch 官方当前支持 Docker 单节点部署
- 单节点场景需要 `discovery.type=single-node`
- OpenSearch 2.12+ 需要显式设置初始管理员密码
- 官方支持通过 volume 挂载自定义 `opensearch.yml`

来源：<https://docs.opensearch.org/latest/install-and-configure/install-opensearch/docker>

**部署基线**

- 单节点 `opensearch`
- 生产外的管理可选 `opensearch-dashboards`
- 自定义 `opensearch.yml`
- 挂载数据卷
- 挂载同义词文件
- JVM 堆内存先按单机资源设置，例如 `512m~1g`

补充说明：

- 本仓库当前补充的 `infra/docker-compose.yml` 采用“本地可直接启动”的初版配置，暂时关闭了 OpenSearch Security Plugin。
- 一旦进入共享测试环境或生产环境，需要切换到启用 TLS/Auth 的安全配置，并恢复 `OPENSEARCH_INITIAL_ADMIN_PASSWORD` 与证书挂载。

**一期范围**

- 只做单节点
- 只做 `section_index` 与 `clause_index`
- 同义词文件先走仓库版本 + 数据库维护表双轨
- 不做集群和冷热分层

### 4.5 部署拓扑

一期推荐拓扑：

`frontend + backend + ai-gateway + postgres + redis + opensearch + minio`

外部能力：

- `MinerU Commercial API`
- `Cloud Model APIs`

说明：

- `frontend` 产出静态资源，走 Nginx 或同类静态服务容器
- `backend` 为业务核心
- `ai-gateway` 为模型适配层
- `minio` 同时承担原始文件和导出文件存储，不承担对 MinerU 的文件分发

## 5. 对实施计划的影响

需要将原计划中的“推定 React 容器”和“MinerU 本地服务假设”改为以下明确决策：

- 前端固定为 `React 18 + TypeScript + Vite + TanStack Router + TanStack Query`
- AI Gateway 固定为独立轻服务
- MinerU 固定为商业 API 集成，采用后端直传上传链接模式，不纳入本地部署
- OpenSearch 固定为单机单节点 Docker Compose

同时补充业务约束：

- 一期角色固定为 `项目编辑 / 复核人 / 管理员`
- 否决项允许项目编辑先确认，但导出前必须由复核人或管理员二次确认
- 导出先落 1 套默认技术标模板
- 模板同时支持章节名与章节编码占位符，内部以章节编码为主键
- 首批规范库由业务侧手工整理高频规范 PDF
- 同义词库一期先做 `100-200` 条高频种子词
- 审校门禁采用 `P0/P1` 阻断、`P2/P3` 提示
- 文件默认长期保留，不做自动清理
- 开发与测试环境先统一使用单机 Compose
- 测试环境先以 `IP + 端口` 联调
- OpenSearch 在本地开发关闭安全插件，共享测试环境前开启 TLS/Auth
- 表格纠错一期仅支持整张表 JSON 覆盖
- 章节生成一期目标为尽量全量生成技术标正文
- 企业知识库一期接入少量精选历史标书，不接全量知识库

同时调整以下任务重点：

- Task 1 新增 `infra/opensearch/opensearch.yml`
- Task 3 新增 `申请 MinerU 上传链接 -> 后端直传 -> 异步轮询`
- Task 6 的 AI Gateway 仅做模型接入，不做 workflow 编排

## 6. 后续落地动作

1. 回写实施计划，替换待定技术假设
2. 补充 `infra/docker-compose.yml` 初版结构
3. 补充 `backend` 中 MinerU 异步解析流程设计
4. 补充 OpenSearch 配置文件与索引初始化策略
5. 开始按已定版选型创建工程骨架
