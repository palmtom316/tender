# 全项目代码审查报告

**日期**: 2026-04-27
**范围**: 全项目源码审查（backend + ai_gateway + frontend）

## 项目概览

**tender** — 招投标辅助写作系统，包含：
- **backend/** (FastAPI + psycopg3 + Celery + structlog)
- **ai_gateway/** (LLM 提供商代理: DeepSeek 主 + Qwen 备)
- **frontend/** (React + Vite + TanStack Router/Query)
- **docs/** (详尽的计划、设计文档、验收报告)
- 工作流引擎、条款提取管线、标准 PDF 解析

代码整体质量较高：良好分层、类型注解齐全、使用 `from __future__ import annotations`、统一的 structlog 日志、清晰的模块划分。

---

## 🔴 高优先级

### 1. 关键 API 路由缺少认证

与 `standards.py`（router 级别加 `dependencies=[Depends(get_current_user)]`）、`scoring.py`（每个路由加）不同，以下 router **完全没有任何认证**：

| 文件 | 暴露的操作 |
|------|-----------|
| `api/users.py` | 用户 CRUD（创建、查询、修改、删除用户） |
| `api/settings.py` | AI 代理配置（含 API key）、技能管理 |
| `api/files.py` | 文件上传、列表 |
| `api/parse.py` | 文档解析任务管理 |
| `api/projects.py` | 项目创建、列表 |

**严重性**: 任何人都可以创建管理员账户、修改 AI 代理配置（含明文 API key）、查看项目文件。

**建议**: 要么全局加认证中间件，要么为所有 router 统一加 `dependencies=[Depends(get_current_user)]`。对于 Phase 1 若运行在内网，建议至少为 `/users` 和 `/settings` 加防护。

**涉及文件**:
- `backend/tender_backend/api/users.py:12` — `router = APIRouter(tags=["users"])`
- `backend/tender_backend/api/settings.py:16` — `router = APIRouter(tags=["settings"])`
- `backend/tender_backend/api/files.py:14` — `router = APIRouter(tags=["files"])`
- `backend/tender_backend/api/parse.py:13` — `router = APIRouter(tags=["parse"])`
- `backend/tender_backend/api/projects.py:13` — `router = APIRouter(tags=["projects"])`

---

### 2. 工作流中使用同步 psycopg 连接阻塞异步事件循环

`backend/tender_backend/workflows/` 下所有工作的 `execute()` 方法都是 `async def`，但内部使用通过 `ctx.data["_db_conn"]` 传入的**同步** psycopg 连接：

```python
# generate_section.py:32
async def execute(self, ctx: WorkflowContext) -> StepResult:
    conn = ctx.data.get("_db_conn")
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(...).fetchall()  # 阻塞事件循环！
```

在 `asyncio` 事件循环中执行阻塞的 `cur.execute()` 会**阻塞整个事件循环**，导致其他协程无法调度。高并发下所有工作流会串行执行。

**涉及文件**:
- `backend/tender_backend/workflows/generate_section.py` — `LoadProjectFacts`, `LoadSectionRequirements`, `SaveDraft`
- `backend/tender_backend/workflows/export_bid.py` — `CheckVetoGate`, `CheckReviewGate`, `SaveExportRecord`
- `backend/tender_backend/workflows/review_section.py` — `LoadDrafts`, `LoadReviewContext`, `BuildComplianceMatrix`, `PersistIssues`
- `backend/tender_backend/workflows/standard_ingestion.py` — `ParseStandardPdf`, `BuildClauseTree`

**建议**: 使用 `asyncio.to_thread()` 包装同步 DB 调用，或迁移至 `asyncpg`。

---

### 3. `uuid4().hex` 用于 PostgreSQL UUID 列

在 `generate_section.py:151` 和 `export_bid.py:130` 中：

```python
# generate_section.py
(uuid.uuid4().hex, ctx.project_id, chapter_code, content),
# export_bid.py
(uuid4().hex, ctx.project_id, "completed", ...),
```

`uuid4().hex` 生成 `"550e8400e29b41d4a716446655440000"`（32 字符无连字符）。项目其他部分用 `UUID(object)` 传入，psycopg3 会自动处理类型。使用 `.hex` 虽然 PG 理论上能解析，但隐式类型转换失败时可能产生错误数据，且与项目其余部分不一致。

**涉及文件**:
- `backend/tender_backend/workflows/generate_section.py:151`
- `backend/tender_backend/workflows/export_bid.py:130`
- `backend/tender_backend/workflows/base.py:37,78,98`（用于 trace_id/run_id 等非 DB 用途，这些 OK）

**建议**: 传入 `uuid4()` 本身，让 psycopg 处理序列化。

---

## 🟡 中优先级

### 4. 文件上传完全读入内存

```python
# standards.py:303
content = await file.read()  # 将整个文件读入内存
```

对于大 PDF 文件（数百 MB）或并发上传，可能导致容器 OOM。

**建议**: 通过流式写入磁盘缓冲区或分块处理，使用 `UploadFile.file` 的流式 API。

### 5. `import_standard_bundles.py` 使用 `assert` 做数据验证

```python
# import_standard_bundles.py:52-53
code_match = _CODE_RE.match(standard_code)
assert code_match is not None
```

Python `-O` 模式下 `assert` 被移除，生产运行时悄无声息地通过验证，后续代码使用 `code_match.group(2)` 会抛出 `AttributeError`。

**建议**: 改 `if code_match is None: raise ValueError(...)`。

### 6. Token 映射永久缓存

```python
# security.py:57-59
if _token_map is None:
    _token_map = _load_token_map()
```

运行时修改 `AUTH_TOKENS` 环境变量不会生效，需要重启进程。在动态环境（K8s ConfigMap 热更新）中不适用。

**建议**: 加 TTL 缓存或周期性刷新（如 `@lru_cache(maxsize=1)` 加 `get_settings()` 风格的主动失效）。

---

## 🔵 低优先级

### 7. 应用层无请求超时保护

所有 HTTP 请求和 AI 调用依赖下游超时（客户端库、代理网关），但应用层无硬性超时兜底。若 MinerU 或 AI 网关响应慢，Worker 线程可能被无限挂起。

### 8. `threadpool_compat.py` 依赖框架内部 API

`backend/tender_backend/core/threadpool_compat.py` 使用 monkey-patch 替换 6 个 starlette/fastapi 模块的 `run_in_threadpool`。这些是**内部非公开 API**，升级任何依赖（FastAPI/Starlette）时都可能断裂。

**建议**: 多用 FastAPI 官方的 `run_in_threadpool` 路由级控制，减少全局 monkey-patch 的必要。

### 9. 前端默认 dev-token

```typescript
// frontend/src/lib/api.ts:9
function getToken(): string {
  return localStorage.getItem("tender_token") ?? "dev-token";
}
```

无论用户是否登录，前端都以管理员身份发送 `dev-token`。生产部署时需移除或禁用此回退。

### 10. `TokenTracker` 内存单例

```python
# ai_gateway/tender_ai_gateway/token_tracker.py:92
tracker = TokenTracker()
```

重启后 token 计数和生产成本估算丢失。注释注明"生产环境应持久化到 task_trace 表"，但尚未实现。

### 11. 前端单一 `ErrorBoundary`

`App.tsx` 只有单个顶层 `ErrorBoundary`，一个模块的崩溃会卸载整个应用。建议每个模块（ProjectsModule / DatabaseModule / ExportModule 等）包裹独立的 `ErrorBoundary`。

---

## 综合评价

| 维度 | 评价 |
|------|------|
| 代码风格 | 统一、规范。类型注解齐全（`from __future__ import annotations`），Pydantic/FastAPI 模式良好 |
| 日志 | structlog 结构化日志贯穿全栈，request_id 链路追踪 |
| 文档 | 极其详尽——设计文档、计划、验收报告、历史审查报告完整 |
| 测试 | 有单元/集成/烟测试，但 `backend/tests/` 覆盖面需要增加 |
| 安全 | ✅ 散列密码 ✅ 角色权限模型 ❌ 多个 router 完全无认证 |
| 性能 | ❌ 同步 DB 阻塞异步事件循环 ❌ 文件上传全内存缓冲 ⚠️ monkey-patch 不推荐 |

**修复推荐优先级**：
1. 给所有业务 API router 加认证防护 → 最快消除安全隐患
2. 工作流 DB 调用改为异步或 `run_in_threadpool` → 性能最关键
3. 修复 `uuid4().hex` 和 `assert` 问题 → 简单且防止边界错误
4. 后续：流式文件上传、Token 映射热加载、移除 monkey-patch
