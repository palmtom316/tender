# 代码审查报告

- **项目：** Tender
- **审查日期：** 2026-03-18
- **审查范围：** 整个仓库现状代码（`backend/`、`ai_gateway/`、`frontend/`）
- **审查结论：** `REQUEST CHANGES`

## 总结

当前代码库存在阻断上线的结构性问题，主要集中在三类：

1. 鉴权和权限边界不完整，存在默认管理员后门和大面积未鉴权接口。
2. AI Gateway 暴露面过大，可被滥用为未受控代理和内网探测入口。
3. 文档解析主链路未真正打通，同时前后端 API 契约已有明显漂移。

## 主要问题

### CRITICAL

1. `backend/tender_backend/api/auth.py:72`
   - `auth_me` 仍接受固定 `dev-token` 并直接返回 `admin` 身份。
   - 风险：任何知道该固定值的人都能绕过正常登录。

2. `backend/tender_backend/core/security.py:33`
   - 未配置 `AUTH_TOKENS` 时会自动注入 `dev-token` 管理员。
   - `frontend/src/lib/api.ts:8` 还会在本地无登录态时默认发送该 token。
   - 风险：前后端共同构成默认管理员后门。

### HIGH

1. `backend/tender_backend/api/users.py:53`
   - 用户管理接口未挂鉴权或角色校验。
   - 风险：匿名用户可直接列出、创建、修改、删除系统用户。

2. `backend/tender_backend/api/settings.py:66`
   - Agent 配置读取、更新、连通性测试接口均未鉴权。
   - 风险：匿名用户可修改模型配置、触发带真实密钥的外部请求。

3. `backend/tender_backend/api/files.py:20`
   - 文件上传和列表接口未鉴权。
   - 风险：匿名用户可写入项目文件元数据并读取文件清单。

4. `backend/tender_backend/api/parse.py:18`
   - 解析任务相关接口未鉴权。
   - 风险：匿名用户可触发解析任务、查询任意解析状态。

5. `backend/tender_backend/api/standards.py:29`
   - 规范库上传、查看、处理接口未鉴权。
   - 风险：匿名用户可写入本地文件系统、污染规范库数据。

6. `backend/tender_backend/api/settings.py:86`
   - “测试连接”接口会读取数据库中的真实密钥并对可配置地址发请求。
   - 风险：结合无鉴权配置更新，形成 SSRF 和凭证滥用链路。

7. `ai_gateway/tender_ai_gateway/api/chat.py:41`
   - AI Gateway 聊天接口无鉴权，且允许传 `primary_override` / `fallback_override`。
   - `ai_gateway/tender_ai_gateway/fallback.py:53`
   - `ai_gateway/tender_ai_gateway/fallback.py:104`
   - 风险：网关可被滥用为任意外部代理、成本出口和内网探测入口。

8. `backend/tender_backend/api/parse.py:18`
   - 解析任务创建只落库，不投递实际 worker。
   - `backend/tender_backend/workers/tasks_parse.py:12` 仍返回 `pending_implementation`。
   - 风险：投标文档解析主链路实际上未完成，前端会停留在伪进行中状态。

### MEDIUM

1. `frontend/src/lib/api.ts:124`
   - 前端请求 `/documents/{id}/sections`。
   - 后端不存在对应路由。

2. `frontend/src/lib/api.ts:133`
   - 前端请求 `/documents/{id}/tables`。
   - 后端不存在对应路由。

3. `frontend/src/modules/authoring/UploadContent.tsx:106`
   - 前端依赖 `created_at` 显示上传时间。
   - `backend/tender_backend/api/files.py:64` 返回体不含该字段。
   - 风险：文件页会出现运行时数据不一致或显示异常。

## 测试与覆盖缺口

1. `backend/tests/integration/test_project_file_flow.py:35`
   - 集成测试把匿名访问项目和文件接口当作正确行为。
   - 问题：测试在固化越权现状，而不是约束安全边界。

2. `backend/tests/integration/test_parse_pipeline.py:19`
   - 只验证 workflow 注册和步骤名，不验证任务调度和状态推进。
   - 问题：无法覆盖真正的解析主链路是否可用。

3. `ai_gateway/tests/smoke/test_gateway.py:14`
   - 仅覆盖健康检查和凭证契约。
   - 问题：缺少鉴权、override 安全边界、滥用风险相关测试。

## 验证情况

- `frontend/` 执行 `npm run build` 失败：环境缺少 `tsc`。
- `backend/` 与 `ai_gateway/` 预期的 `../.venv/bin/pytest` 不存在，未能执行测试。
- 本报告基于静态代码审查和现有测试代码本身形成。

## 建议修复顺序

1. 去掉 `dev-token` 默认管理员链路，并统一后端与前端鉴权入口。
2. 给后端管理类、写操作类、配置类接口补齐 `get_current_user` / `require_role`。
3. 给 AI Gateway 增加鉴权，并移除或严格限制任意 `override` 能力。
4. 打通真实解析任务调度，避免“接口成功但业务未执行”的假闭环。
5. 修正前后端 API 契约，并为鉴权和关键流程补集成测试。
