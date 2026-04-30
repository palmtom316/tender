# `bid-template-packages` 审查报告核实与整改计划

**日期**: 2026-04-30  
**基准报告**: `docs/reviews/2026-04-30-code-review-bid-template-packages.md`  
**核实范围**: 抽查 P0/P1 全部高风险项、P2/P3 中影响安全/一致性/测试覆盖的代表项，并对照当前代码实现确认证据。

## 1. 核实结论摘要

审查报告的主要风险判断成立。P0 中 5 项均有代码证据支撑；P1 中鉴权、上传大小、设置接口、异常处理、外部进程阻塞、前端保存闭包和错误边界问题也成立。需要调整表述的是“项目所有权检查”：当前代码没有统一的项目成员/所有权模型，不能只在 `source_chunk` 单点修补，应先建立统一项目访问控制依赖，再接入所有项目域 API。

## 2. 已核实属实的问题

### P0 阻塞项

1. **招标文件路由缺少鉴权**
   - 证据: `backend/tender_backend/api/tender_documents.py:38` 的 router 没有 `Depends(get_current_user)`；上传、解析、source chunk 更新等接口也没有逐接口用户依赖。
   - 风险: 未登录用户可上传、读取、解析和修改招标文件数据。
   - 结论: 属实，部署前必须修复。

2. **报价关键词污染非报价需求**
   - 证据: `requirements_extractor.py:135-153` 先按 chunk 计算 `pricing_hits`，随后对所有匹配 category 使用 `ignored_for_pricing = bool(pricing_hits)`。
   - 风险: 同一段同时出现“报价”和“资质/业绩/人员”等关键词时，资格类约束会被错误排除；下游多处过滤 `ignored_for_pricing=false`。
   - 结论: 属实，属于业务正确性阻塞项。

3. **前端静默使用 `dev-token`**
   - 证据: `frontend/src/lib/api.ts:8-9` 在 localStorage 无 token 时默认返回 `dev-token`。
   - 风险: 前端会掩盖未登录状态，并与后端开发 token 后门叠加。
   - 结论: 属实。另需同步处理 `backend/tender_backend/core/security.py:37-44` 在无 `AUTH_TOKENS` 时启用 `dev-token` 的生产环境风险。

4. **交付包服务无直接测试**
   - 证据: `backend/tender_backend/services/delivery_package.py` 约 189 行，`rg` 未发现对应测试；代码包含 ZIP 打包、DOCX/DOC 转换、审查报告和矩阵生成。
   - 风险: 关键交付链路依赖 LibreOffice 和文件系统，无回归保护。
   - 结论: 属实。

5. **招标文件入库事务边界不一致**
   - 证据: `TenderDocumentRepository.create_document/create_file/update_*` 内部多处 `conn.commit()`；`ingest_upload()` 中 `_extract_zip()` 失败后，前面的 document/file 已提交。
   - 风险: 调用方看到异常，但数据库已有半成品记录；文件系统也可能残留。
   - 结论: 属实，应改为 service 级显式事务。

### P1 高优先级项

1. **招标文件上传无大小限制**
   - 证据: `tender_documents.py:324-325` 直接 `await file.read()`，配置中只有 `evidence_upload_max_bytes`，没有 `tender_document_upload_max_bytes`。
   - 结论: 属实。

2. **同步 `subprocess.run()` 可能阻塞事件循环**
   - 证据: `office_document_parser.py:181`、`delivery_package.py:172` 直接调用 LibreOffice。
   - 结论: 属实。`parse_tender_document_file()` 是 async handler，风险更直接；交付包接口同样在 async handler 中调用同步服务。

3. **设置接口无鉴权且存在 SSRF 面**
   - 证据: `settings.py:21` router 无鉴权；`test_agent_connection()` 会请求数据库中配置的 `base_url`。
   - 结论: 属实。读接口需登录，写接口与连通性测试需管理员权限；连通性测试还需 URL allowlist 或内网地址拒绝。

4. **唯一约束错误处理过宽**
   - 证据: `template_bindings.py:131-134/147-150`、`master_data_financials.py:78-81/93-96` 捕获 `Exception` 后做字符串匹配。
   - 结论: 属实，应改为 `psycopg.errors.UniqueViolation`。

5. **`TemplateFieldWorkbench.tsx` 过大且 mutation 读取闭包状态**
   - 证据: 文件 1233 行；`saveMutation.mutationFn` 从闭包读取 `draft/selectedItemId/selectedBindingId`。
   - 结论: 属实。拆分组件是维护性整改；保存逻辑应先修。

6. **ErrorBoundary 重试不强制重新挂载**
   - 证据: `ErrorBoundary.tsx:31-33` 仅清除 error state。
   - 结论: 属实。

7. **项目级授权应统一整改**
   - 证据: `source-chunks/{id}` 可按 UUID 更新；同时 `projects.py`、`exports.py`、`bid_outline.py` 等项目域接口也缺少所有权/成员模型。
   - 结论: 原报告指出的风险方向属实，但整改范围应扩大为“统一项目访问控制”，不能仅修 source chunk。

## 3. 部分属实或降级处理

1. **`delivery_package.py` 失败静默继续**
   - `delivery_package.py:100-103` 确实吞掉 volume 渲染异常。建议 P1 处理为“降级产物必须写入 metadata/status/warnings”，不一定阻塞主包生成。

2. **`/tmp` 默认目录**
   - `template_render_root`、`template_bundle_root` 已配置化，但默认仍是 `/tmp`。生产环境应在 `.env`/部署文档中强制覆盖到权限受限目录；代码层可在创建目录后设置 `0700`。

3. **项目所有权检查**
   - 当前不是单个接口遗漏，而是权限模型尚不完整。应作为横向安全能力建设，优先覆盖本分支新增的 tender documents 和 delivery/export，再逐步覆盖旧接口。

## 4. 整改计划

### Phase 0: 发布阻断修复

1. **关闭未授权访问**
   - `tender_documents.py` router 增加 `dependencies=[Depends(get_current_user)]`。
   - `settings.py` 增加登录依赖；`PUT/POST/DELETE/sync/test` 使用 `require_role(Role.ADMIN)`。
   - 后端 `dev-token` 只允许 `app_env=development/test`；生产环境无 `AUTH_TOKENS` 时启动或请求失败。

2. **修复 token 行为**
   - `frontend/src/lib/api.ts` 的 `getToken()` 返回 `string | null`。
   - 无 token 时不发送 `Authorization: Bearer dev-token`，由应用统一进入登录态或抛出 401。

3. **修复 `ignored_for_pricing`**
   - 将报价过滤改成按 category/命中来源计算：仅报价专属 requirement 标记 `ignored_for_pricing=true`。
   - 混合 chunk 中的 `qualification/performance/project_team/technical/format` 等非报价 category 必须保留为 false。
   - 新增单测覆盖“报价 + 资质”同段文本。

4. **收敛招标文件入库事务**
   - 移除 `TenderDocumentRepository` 写方法内部 `commit()`。
   - `TenderDocumentIngestionService.ingest_upload()` 使用 `with conn.transaction()` 包裹 document、file、zip extraction、最终状态更新。
   - 失败时回滚数据库记录，并清理本次写入的 `document_root`；若要保留失败审计，另开显式失败记录流程。

5. **上传大小与路径安全**
   - 新增 `tender_document_upload_max_bytes` 配置。
   - 上传读取改为分块读取并在超过阈值时返回 413，避免先读完整文件。
   - `_parse_file()` 使用 `ensure_path_within_root(file_row["storage_key"], settings.tender_document_storage_root)`，禁止直接信任 DB 路径。

6. **交付包最低测试**
   - 添加 `test_delivery_package.py`：无 LibreOffice 返回无 `.doc`、正常打包包含核心清单、volume 渲染失败写入 warning/metadata。

### Phase 1: 本迭代高优先级修复

1. **外部进程异步隔离**
   - Office 解析和交付包生成中的 LibreOffice 调用放到 `asyncio.to_thread()` 或 executor。
   - 长任务接口后续可迁移到后台 job；本阶段先避免阻塞事件循环。

2. **SSRF 防护**
   - `test_agent_connection()` 校验 URL scheme 仅允许 `https/http`。
   - 拒绝 localhost、loopback、link-local、private CIDR、metadata IP。
   - 可选增加 DeepSeek/MinerU endpoint allowlist。

3. **唯一约束异常收窄**
   - 替换字符串匹配为 `except errors.UniqueViolation as exc`。
   - 保留其他异常原样抛出。

4. **统一项目访问控制雏形**
   - 引入 `ProjectAccessRepository` 或等价依赖 `require_project_access(project_id, user)`。
   - 先覆盖 tender documents、requirements、bid outline、exports/delivery package。
   - 对仅有子资源 UUID 的接口，先 JOIN 回 project_id 再校验。

5. **前端保存与错误边界**
   - `TemplateFieldWorkbench` 的保存改为 `saveMutation.mutate(buildPayloadFromCurrentDraft())`，mutationFn 接收变量。
   - `ErrorBoundary` 增加 reset key 或改用 `react-error-boundary`，点击重试能重新挂载 children。

6. **交付包降级状态**
   - volume 渲染失败不再静默吞掉；写入 warnings，若全部 volume 失败则 status 使用 `degraded` 或返回 500，按产品策略定。

### Phase 2: 下一迭代质量与性能

1. 为 `path_safety.py`、`bid_outline.py`、`compliance_matrix.py`、`requirements_extractor.py` 增加单元/集成测试。
2. `replace_source_chunks()`、`RequirementRepository.create_many()`、`replace_items()` 改批量写入。
3. 增加缺失索引：`bid_template_item(package_id)`、`evidence_asset(library_company_id)`、`evidence_asset(owner_type, owner_id)` 及 master data 常用 FK。
4. `category_code` FK 明确 `ON DELETE SET NULL`。
5. 前端 API 增加请求超时/取消策略，长任务接口显示可恢复状态。
6. 拆分 `TemplateFieldWorkbench.tsx` 为上传、模板包列表、模板项列表、绑定编辑、预检、建议面板等组件。

### Phase 3: 后续清理

1. 将硬编码关键词、章节定义、ZIP 深度等迁移到配置或可版本化规则表。
2. 替换运行时 `assert row is not None` 为显式异常。
3. 合并重复测试 DDL 到 fixtures。
4. 清理重复 migration 字段与低风险前端重复模式。

## 5. 验收计划

### 必跑测试

```bash
.venv/bin/python -m pytest \
  backend/tests/unit/test_requirements_extractor.py \
  backend/tests/unit/test_tender_document_ingestion.py \
  backend/tests/unit/test_delivery_package.py \
  backend/tests/unit/test_path_safety.py -q

.venv/bin/python -m pytest \
  backend/tests/integration/test_tender_document_api.py \
  backend/tests/integration/test_settings_api.py \
  backend/tests/integration/test_bid_outline_api.py -q

npm --prefix frontend run build
```

### 关键验收断言

1. 未带 token 访问 tender documents/settings 返回 401。
2. 非管理员访问 settings 写接口和连通性测试返回 403。
3. 无 token 前端请求不会发送 `Bearer dev-token`。
4. “报价 + 资质”混合文本至少产生一个非 `ignored_for_pricing` 的 `qualification` requirement。
5. 超过 `tender_document_upload_max_bytes` 的上传返回 413，且数据库无半成品记录。
6. ZIP 解压失败时数据库与文件系统不留下本次上传的半成品。
7. 交付包缺 LibreOffice 时仍可生成 ZIP，并在 metadata 中记录 DOC 转换缺失；volume 失败有 warning。
8. source chunk 子资源更新会校验其所属 project 的访问权限。

## 6. 建议执行顺序

先合并 Phase 0 的安全与数据一致性修复，再进入 Phase 1。Phase 0 改动会影响接口鉴权和测试夹具，建议单独分支提交，避免与 `TemplateFieldWorkbench` 拆分这种大前端改动混在一个 PR 中。
