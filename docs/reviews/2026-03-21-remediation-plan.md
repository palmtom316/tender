# Tender 项目代码整改计划

**基于审查报告**: docs/reviews/2026-03-21-full-code-review.md
**制定日期**: 2026-03-21
**目标**: 分阶段修复审查发现的问题，优先保障安全性

---

## 第一阶段：安全加固 (P0)

> 目标：消除所有可被外部利用的安全漏洞
> 预估工作量：集中 2-3 天

### 1.1 后端 API 全面添加认证

**范围**: `backend/tender_backend/api/` 下所有未保护端点

**方案**:
- 在 `main.py` 添加全局认证中间件，仅放行 `/api/health` 和 `/api/auth/login`
- 或逐个端点添加 `Depends(get_current_user)` (更精细控制)

**文件清单**:
```
backend/tender_backend/api/files.py        → 添加认证
backend/tender_backend/api/parse.py        → 添加认证
backend/tender_backend/api/projects.py     → 添加认证
backend/tender_backend/api/users.py        → 添加认证 + require_role(ADMIN)
backend/tender_backend/api/settings.py     → 添加认证 + require_role(ADMIN)
backend/tender_backend/api/compliance.py   → 验证已有认证
backend/tender_backend/api/drafts.py       → 验证已有认证
backend/tender_backend/api/exports.py      → 验证已有认证
backend/tender_backend/api/requirements.py → 验证已有认证
backend/tender_backend/api/review.py       → 验证已有认证
backend/tender_backend/api/scoring.py      → 验证已有认证
```

**验收标准**:
- [ ] 所有端点 (除 health/login) 需要有效 Bearer token
- [ ] 用户管理和 agent 配置端点需要 ADMIN 角色
- [ ] 无 token 请求返回 401
- [ ] 无权限请求返回 403

### 1.2 AI Gateway 添加服务间鉴权

**方案**: API Key 鉴权 (内部服务调用)

**实现**:
1. 在 `ai_gateway/tender_ai_gateway/core/config.py` 添加 `service_api_key` 配置项
2. 创建 `ai_gateway/tender_ai_gateway/core/security.py` - API Key 校验依赖
3. 在 `chat.py` 和 `credentials.py` 的 router 添加鉴权依赖
4. 后端调用 AI Gateway 时在 header 中携带 service API key

**文件清单**:
```
ai_gateway/tender_ai_gateway/core/config.py    → 添加 service_api_key
ai_gateway/tender_ai_gateway/core/security.py  → 新建，API Key 校验
ai_gateway/tender_ai_gateway/api/chat.py       → 添加 Depends(verify_service_key)
ai_gateway/tender_ai_gateway/api/credentials.py → 添加 Depends(verify_service_key)
backend/tender_backend/core/config.py          → 添加 ai_gateway_api_key
infra/.env.example                              → 添加 AI_GATEWAY_SERVICE_KEY
```

**验收标准**:
- [ ] 无有效 API Key 的请求返回 401
- [ ] 后端可正常调用 AI Gateway

### 1.3 SSRF 防护 - Override URL 白名单

**文件**: `ai_gateway/tender_ai_gateway/fallback.py`

**实现**:
1. 在 config 中定义允许的 base_url 列表 (或域名白名单)
2. 在 `_build_provider_chain` 中校验 override URL
3. 拒绝 localhost、私有 IP、云元数据端点

**验收标准**:
- [ ] `base_url` 为 localhost/私有 IP/169.254.x.x 时返回 400
- [ ] 仅白名单域名可通过

### 1.4 移除 .env 敏感信息

**实现**:
1. 将 `infra/.env` 从 Git 追踪中移除 (`git rm --cached`)
2. 确保 `.gitignore` 正确忽略 `infra/.env`
3. 更新 `infra/.env.example` 为纯占位示例 (所有密码留空)
4. README 中添加环境配置说明

**验收标准**:
- [ ] `infra/.env` 不再被 Git 追踪
- [ ] `.env.example` 不含任何实际密码

### 1.5 前端移除 dev-token 回退

**文件**: `frontend/src/lib/api.ts`

**实现**:
1. 移除 `?? "dev-token"` 回退
2. 无 token 时抛出错误或重定向至登录页
3. 添加 token 过期处理 (401 响应时清除 token 并跳转登录)

**验收标准**:
- [ ] 无 token 时不发送请求，提示登录
- [ ] 401 响应自动清除 token 并跳转

---

## 第二阶段：安全增强 (P1)

> 目标：修复高风险问题，增强系统健壮性
> 预估工作量：3-4 天

### 2.1 修复默认密码策略

**文件**: `backend/tender_backend/db/alembic/versions/0005_system_user.py`

**方案**:
- 迁移中读取环境变量 `ADMIN_INITIAL_PASSWORD` 等
- 若未设置则使用 `secrets.token_urlsafe(16)` 生成随机密码并打印到日志
- 使用随机 salt 替代固定 `"0" * 32`

### 2.2 错误信息脱敏

**文件清单**:
```
ai_gateway/tender_ai_gateway/api/chat.py:68-69
  → detail="AI 服务暂时不可用" + logger.exception(...)
backend/tender_backend/api/settings.py:103-131
  → detail="连接测试失败" + logger.exception(...)
```

### 2.3 前端认证路由守卫

**实现**:
1. 创建 `frontend/src/components/auth/ProtectedRoute.tsx`
2. 认证失败时重定向至登录页
3. 替换 `Sidebar.tsx` 中的静默 `.catch(() => {})`

### 2.4 添加 CORS 配置

**文件**: `backend/tender_backend/main.py`

```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # 从配置读取
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 2.5 AI Gateway 速率限制

**方案**: 使用 SlowAPI 或自定义中间件

**实现**:
1. 安装 slowapi
2. 在 chat 端点添加限流 (如 60 次/分钟/IP)
3. 配置项可从环境变量读取

### 2.6 AI Gateway 异常处理精细化

**文件**: `ai_gateway/tender_ai_gateway/fallback.py:137-148`

**实现**:
- 捕获 `openai.APITimeoutError` → 重试
- 捕获 `openai.AuthenticationError` → 不重试，立即报错
- 捕获 `openai.RateLimitError` → 等待后重试
- 添加请求级 `asyncio.timeout`

---

## 第三阶段：代码质量提升 (P2)

> 目标：提升代码可维护性和一致性
> 预估工作量：2-3 天

### 3.1 请求体类型化

**优先文件**:
```
backend/tender_backend/api/parse.py
  → payload: dict → ParseJobRequest(BaseModel)
```

### 3.2 异常处理规范化

```
backend/tender_backend/api/users.py:73-76
  → except psycopg.errors.UniqueViolation
```

### 3.3 文件上传大小限制

```
backend/tender_backend/api/files.py
  → 添加 MAX_UPLOAD_SIZE 校验 (如 50MB)
```

### 3.4 数据库事务模式统一

**方案**: 统一采用 repository 内 commit 模式，移除 API 层显式 commit

### 3.5 AI Gateway 消息验证

```python
# ai_gateway/tender_ai_gateway/api/chat.py
class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(max_length=100_000)

class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(max_length=100)
```

---

## 第四阶段：测试补全

> 目标：关键路径测试覆盖率达 80%+
> 预估工作量：5-7 天

### 4.1 创建共享测试基础设施

**实现**:
1. 创建 `backend/tests/conftest.py` - 共享 fixtures (conn, client, schema setup)
2. 提取重复的 `_ensure_schema`, `_reset_standard_tables` 到 conftest
3. 添加 pytest 插件配置 (asyncio, timeout, cov)

### 4.2 补充后端端点测试

**按优先级**:
1. 认证流程 (login, register, me, logout)
2. 项目 CRUD (create, list, update, delete)
3. 文件上传和管理
4. 用户管理 (CRUD + 角色权限)
5. 错误场景 (401, 403, 404, 422)

### 4.3 AI Gateway 测试补全

1. chat 端点 - 正常/超时/认证失败/限流
2. credentials 端点 - 创建/验证
3. fallback 逻辑 - 主备切换/全部失败
4. SSRF 防护 - 白名单校验

### 4.4 前端测试启动

1. 安装 Vitest + React Testing Library
2. 优先测试: api.ts (请求/错误处理), NavigationContext, ProtectedRoute

---

## 第五阶段：DevOps 完善

> 目标：自动化测试和部署流程
> 预估工作量：2-3 天

### 5.1 创建 CI/CD Pipeline

**文件**: `.github/workflows/ci.yml`

```yaml
# PR 检查: lint + type check + unit tests + integration tests
# Main 合并: 以上 + build + smoke test
```

### 5.2 Docker 配置加固

1. Redis, Worker-IO, Frontend 添加 healthcheck
2. 关键服务添加 `restart: unless-stopped`
3. OpenSearch 堆内存参数化
4. 弱默认密码替换为生成脚本

### 5.3 安全扫描集成

1. 依赖漏洞扫描 (pip-audit / npm audit)
2. 代码扫描 (bandit for Python)
3. Secret scanning (pre-commit hook)

---

## 执行时间线

```
第 1 周: 第一阶段 (P0 安全加固) + 第二阶段开始
第 2 周: 第二阶段 (P1 安全增强) + 第三阶段 (P2 代码质量)
第 3 周: 第四阶段 (测试补全)
第 4 周: 第五阶段 (DevOps) + 回归验证
```

## 执行原则

1. **每个阶段独立分支**, 完成后合并到 main
2. **每个修复附带测试**, 确保不引入回归
3. **安全修复优先**, P0 项在任何新功能之前完成
4. **渐进式推进**, 每个 PR 聚焦单一问题域
