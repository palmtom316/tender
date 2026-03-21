# Tender 项目全面代码审查报告

**审查日期**: 2026-03-21
**审查范围**: 整个项目 (backend, ai_gateway, frontend, infra)
**审查版本**: 98e6d4b (main)

---

## 总体评估

| 维度 | 评级 | 说明 |
|------|------|------|
| 架构设计 | **A** | 清晰的 monorepo 三服务架构，关注点分离良好 |
| 后端代码 | **B** | SQL 注入防护好，但认证覆盖不足 |
| AI Gateway | **B-** | 功能完整，安全防护薄弱 |
| 前端代码 | **B+** | TypeScript strict 模式，无 XSS，但缺认证守卫 |
| 测试覆盖 | **C+** | 仅约 40% 端点有测试，AI Gateway 几乎无测试 |
| 配置/DevOps | **C** | 无 CI/CD，弱默认密码，.env 已提交 |

---

## P0 - 必须修复的安全问题

### 1. 15+ API 端点缺少认证

多个关键端点未使用 `Depends(get_current_user)`：

**backend/tender_backend/api/files.py** (lines 20-77):
- `POST /projects/{project_id}/files` - 文件上传
- `GET /projects/{project_id}/files` - 文件列表

**backend/tender_backend/api/parse.py** (lines 18-77):
- `POST /documents/{document_id}/parse-jobs` - 创建解析任务
- `GET /parse-jobs/{parse_job_id}` - 查看解析任务
- `GET /documents/{document_id}/parse-result` - 查看解析结果
- `POST /parse-jobs/{parse_job_id}/retry` - 重试解析

**backend/tender_backend/api/projects.py** (lines 27-36):
- `POST /projects` - 创建项目
- `GET /projects` - 项目列表

**backend/tender_backend/api/users.py** (lines 53-103):
- `GET/POST/PUT/DELETE /users` - 用户管理全开放

**backend/tender_backend/api/settings.py** (lines 66-131):
- `GET/PUT/POST /settings/agents` - AI agent 配置

**影响**: 未认证用户可创建项目、上传文件、管理用户和 agent 配置
**建议**: 添加 `Depends(get_current_user)` 到所有敏感端点，或应用全局认证中间件

### 2. AI Gateway 完全无认证

**ai_gateway/tender_ai_gateway/api/chat.py** (line 42):
- `POST /api/ai/chat` - LLM 推理接口

**ai_gateway/tender_ai_gateway/api/credentials.py** (line 23):
- `POST /api/credentials` - 凭据管理

**影响**: 任何人可直接调用 chat 端点消耗 API 额度，可能导致费用失控
**建议**: 实现服务间鉴权 (JWT, API Key, 或内网隔离)

### 3. SSRF 风险 - Override URL 未校验

**ai_gateway/tender_ai_gateway/fallback.py** (lines 53-73):
```python
if primary_override and primary_override.base_url and primary_override.api_key:
    primary = ProviderConfig(
        name="override-primary",
        base_url=primary_override.base_url,  # 未校验
        api_key=primary_override.api_key,
        model=primary_override.model or primary_model,
    )
```

**影响**: 攻击者可将请求重定向至内部服务 (localhost, 169.254.169.254)
**建议**: 校验 base_url 白名单，拒绝私有 IP 和云元数据端点

### 4. infra/.env 已提交到 Git

**infra/.env** 包含:
- `POSTGRES_PASSWORD=change-me` (line 3)
- `MINIO_ROOT_PASSWORD=change-me` (line 8)
- `OPENSEARCH_INITIAL_ADMIN_PASSWORD=ChangeMe_123!` (line 16)

**建议**: 从 Git 历史中移除，使用 `.env.example` + 自动生成脚本

### 5. 前端硬编码 dev-token

**frontend/src/lib/api.ts** (line 9):
```typescript
function getToken(): string {
  return localStorage.getItem("tender_token") ?? "dev-token";
}
```

**影响**: 未认证用户可能使用 dev-token 访问 API
**建议**: 移除回退值，无 token 时重定向至登录页

---

## P1 - 应尽快修复

### 6. 迁移文件中硬编码默认密码

**backend/tender_backend/db/alembic/versions/0005_system_user.py** (lines 52-54):
- admin: `admin123`
- editor: `editor123`
- reviewer: `reviewer123`
- 使用固定 salt: `salt = "0" * 32` (line 23)

**建议**: 使用环境变量注入初始密码，或强制首次登录改密

### 7. 异常信息泄露内部实现

**ai_gateway/tender_ai_gateway/api/chat.py** (lines 68-69):
```python
except Exception as exc:
    raise HTTPException(status_code=502, detail=f"All providers failed: {exc}")
```

**backend/tender_backend/api/settings.py** (lines 103-131):
```python
except Exception as e:
    return {"success": False, "message": f"连接失败: {e}"}
```

**建议**: 返回通用错误消息，详细信息仅记录到服务端日志

### 8. 前端无认证路由守卫

**frontend/src/components/layout/Sidebar.tsx** (line 17):
```typescript
fetchMe({ signal: controller.signal })
  .then(setCurrentUser)
  .catch(() => {}); // 静默忽略认证失败
```

**建议**: 实现 ProtectedRoute 组件，认证失败时重定向至登录页

### 9. 无 CORS 配置

**backend/tender_backend/main.py** - 未配置 CORSMiddleware

**建议**: 显式配置 CORS 允许的来源

### 10. 无速率限制

AI Gateway 的 chat 端点无请求频率限制，存在 DoS 和费用失控风险。

**建议**: 添加 per-user/per-IP 速率限制中间件

---

## P2 - 建议改进

### 代码质量

| 问题 | 位置 | 说明 |
|------|------|------|
| 无类型请求体 | `parse.py:19` | 使用 `dict` 而非 Pydantic model |
| 字符串匹配异常 | `users.py:73-76` | 应捕获 `psycopg.errors.UniqueViolation` |
| 文件上传无大小限制 | `files.py:21-61` | 未校验 size_bytes |
| 事务提交不一致 | 多个 API 文件 | 部分显式 commit，部分依赖 repo |
| 循环导入风险 | `exports.py:38-43` | 函数内 import |
| 无审计日志 | 所有 API | 敏感操作无审计追踪 |
| 宽泛异常捕获 | `fallback.py:137-148` | 未区分超时/认证/限流错误 |
| 请求级超时缺失 | `chat.py:41-90` | AI 调用可能无限阻塞 |
| API Key 在请求体 | `chat.py:11-26` | 易被日志/监控记录 |
| 消息列表无限制 | `chat.py:22` | 无 max_items，可能 DoS |

### 测试覆盖

| 问题 | 说明 |
|------|------|
| 端点覆盖率低 | 47 个端点仅约 40% 有集成测试 |
| AI Gateway 测试极少 | 仅 4 个测试 |
| 无 conftest.py | 4+ 个测试文件重复 schema 建表代码 |
| 无错误场景测试 | 400/401/403/404 路径未覆盖 |
| 无并发测试 | 竞态条件未验证 |
| pytest 配置简陋 | 缺少 asyncio, cov, timeout 插件 |
| 无前端测试 | 仅有 TypeScript 编译检查 |

### DevOps

| 问题 | 说明 |
|------|------|
| 无 CI/CD pipeline | 测试需手动运行 |
| Docker healthcheck 不全 | Redis, Worker-IO, Frontend 缺失 |
| 无 restart policy | 关键服务崩溃不会自动重启 |
| OpenSearch 堆内存 | 默认 512MB 可能不足 |
| 凭据管理 | MinIO, PostgreSQL 使用弱默认密码 |

### 前端

| 问题 | 说明 |
|------|------|
| Token 存储 | localStorage 易受 XSS 攻击 |
| 可访问性 | 缺少 ARIA labels 和键盘导航 |
| 错误消息 | 部分直接展示 API 原始错误 |
| 类型断言 | `(mutation.error as Error)` 未使用类型守卫 |

---

## 积极发现

- 所有 SQL 查询使用参数化查询，无注入风险
- 密码哈希使用 PBKDF2-HMAC-SHA256 + 随机 salt (100k iterations)
- Session token 使用 `secrets.token_hex(32)` (256-bit entropy)
- 前端无 `dangerouslySetInnerHTML`
- TypeScript strict mode 开启
- React Query + AbortController 资源管理良好
- 结构化日志 (structlog) + request_id 追踪
- Alembic 数据库迁移版本管理
- Pydantic BaseSettings 配置管理
- 数据库连接池管理 (min/max sizes)
- Celery 任务队列异步处理
- 多 LLM 提供商回退机制
