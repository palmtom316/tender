# `bid-template-packages` 审查问题核实与修订计划

**日期**: 2026-04-29  
**基准文档**: `docs/code-review-bid-template-packages-2026-04-29.md`  
**当前结论**: 原审查报告中的高风险问题大多属实；其中安全性、数据完整性和关键正确性问题已完成第一轮修复，剩余工作以模块拆分、预检能力和配置化收尾为主。

---

## 1. 核实结论

### 已核实且已修复

1. **P0-1 证据资产 `file_path` 路径穿越**
   - 结论: 属实。
   - 修订: 在渲染与预览链路增加受控根目录校验，限制文件必须位于证据上传目录内。
   - 相关文件:
     - `backend/tender_backend/core/path_safety.py`
     - `backend/tender_backend/services/template_service/package_renderer.py`
     - `backend/tender_backend/services/template_service/context_preview.py`

2. **P0-2 模板包导入 `source_dir` 任意目录遍历**
   - 结论: 属实。
   - 修订: 增加导入根目录白名单配置 `TEMPLATE_IMPORT_ROOTS`，导入时校验真实路径必须位于允许目录内。
   - 相关文件:
     - `backend/tender_backend/core/config.py`
     - `backend/tender_backend/services/template_service/package_importer.py`

3. **P0-3 `replace_items()` 重导入破坏绑定规则**
   - 结论: 属实。
   - 修订: 重导入时按 `relative_path` 保留既有 `template_item_id`，避免先删后插导致绑定规则失效。
   - 相关文件:
     - `backend/tender_backend/db/repositories/bid_template_package_repo.py`

4. **P0-4 `selection_mode="by_id"` 死代码**
   - 结论: 属实。
   - 修订: `by_id` 已按 `record_ids` 过滤；`latest` 也不再无条件返回第一条记录。
   - 相关文件:
     - `backend/tender_backend/services/template_service/context_preview.py`

5. **P0-6 证据资产上传无类型/大小校验**
   - 结论: 属实。
   - 修订: 增加扩展名白名单、魔数校验、Content-Type 校验和大小限制；新增配置 `EVIDENCE_UPLOAD_DIR`、`EVIDENCE_UPLOAD_MAX_BYTES`。
   - 相关文件:
     - `backend/tender_backend/core/config.py`
     - `backend/tender_backend/api/master_data_evidence.py`

6. **P1-1 模板包列表 N+1 统计**
   - 结论: 属实。
   - 修订: 改为批量统计模板项数量，消除逐包查询。
   - 相关文件:
     - `backend/tender_backend/db/repositories/bid_template_package_repo.py`
     - `backend/tender_backend/api/template_packages.py`

7. **P1-2 新增 API 缺少鉴权保护**
   - 结论: 基本属实。原实现仅依赖固定开发令牌，无法兼容登录态。
   - 修订:
     - `get_current_user()` 同时支持 `dev-token` 和数据库 `user_session` 令牌。
     - `template_packages`、`master_data`、`template_bindings` 路由统一加上鉴权依赖。
   - 相关文件:
     - `backend/tender_backend/core/security.py`
     - `backend/tender_backend/api/template_packages.py`
     - `backend/tender_backend/api/template_bindings.py`
     - `backend/tender_backend/api/master_data.py`

8. **P1-4 `DatabaseModule.tsx` 过大**
   - 结论: 属实。
   - 修订: 已拆分为独立工作台组件，`DatabaseModule.tsx` 保留为薄路由层。
   - 相关文件:
     - `frontend/src/modules/database/DatabaseModule.tsx`
     - `frontend/src/modules/database/components/UploadForm.tsx`
     - `frontend/src/modules/database/components/StandardsWorkbench.tsx`
     - `frontend/src/modules/database/components/CompanyLibraryWorkbench.tsx`
     - `frontend/src/modules/database/components/PersonnelLibraryWorkbench.tsx`

9. **P1-6 字段映射建议缺少置信度信息**
   - 结论: 属实。
   - 修订: 建议结果已补充 `confidence` 元数据，前端已展示置信度标识。
   - 相关文件:
     - `backend/tender_backend/services/template_service/context_preview.py`
     - `frontend/src/modules/database/components/TemplateFieldWorkbench.tsx`

10. **审查报告外补充修正**
   - 证据资产 API 响应已移除服务端 `file_path` 暴露。
   - 设置页和数据库模块已用共享 `ConfirmDialog` 替换 `window.confirm()`。
   - 标准库轮询逻辑已修复 effect 重建问题。
   - 字段映射草稿默认值与日期格式默认值已纠正。

### 已核实但未完全关闭

1. **P1-5 `master_data.py` 过大**
   - 结论: 属实。
   - 当前进度:
     - 已拆出 `master_data_evidence.py`
     - 已拆出 `master_data_companies.py`
     - 已拆出 `master_data_people.py`
     - 已拆出 `master_data_performances.py`
     - 已拆出 `master_data_certificates.py`
     - 已拆出 `master_data_financials.py`
   - 当前状态: 已基本关闭；`master_data.py` 现仅保留资产分类与子路由聚合。

2. **P1-7 附件项无资产时缺少明确预检能力**
   - 结论: 属实。
   - 修订: 已新增模板包渲染预检接口，可在导出前按模板项报告缺失绑定、附件缺失和路径安全问题。
   - 相关文件:
     - `backend/tender_backend/services/template_service/package_renderer.py`
     - `backend/tender_backend/api/template_bindings.py`
     - `frontend/src/modules/database/components/TemplateFieldWorkbench.tsx`
     - `frontend/src/lib/api.ts`

3. **P2-1 渲染输出目录硬编码 `/tmp`**
   - 结论: 属实。
   - 修订: 已新增 `TEMPLATE_RENDER_ROOT`、`TEMPLATE_BUNDLE_ROOT` 配置，渲染与打包输出目录改由 `Settings` 注入。
   - 相关文件:
     - `backend/tender_backend/core/config.py`
     - `backend/tender_backend/services/template_service/docx_renderer.py`
     - `backend/tender_backend/services/template_service/package_renderer.py`

### 需要重新界定/不作为当前阻塞项处理

1. **P1-3 `latest` 选择逻辑**
   - 结论: 审查意见方向正确，但具体“按哪一个日期字段排序”需按不同数据域定义。
   - 修订: 已按 `source_type` 定义 `latest` 排序语义。
   - 当前规则:
     - `company_profile` / `person_profile`: `updated_at` → `created_at`
     - `project_performance`: `ended_on` → `started_on` → `updated_at`
     - `qualification_certificate`: `valid_to` → `valid_from` → `updated_at`
     - `financial_statement`: `fiscal_year` → `updated_at`
     - `evidence_asset`: `issued_on` → `expires_on` → `updated_at`
   - 相关文件:
     - `backend/tender_backend/services/template_service/context_preview.py`
     - `backend/tests/unit/test_template_context_preview.py`

### 已核实并完成策略澄清

1. **P0-5 `upsert_package` 未显式 `commit()`**
   - 结论: 原审查把“缺少 `commit()`”识别成问题，但真正的问题是事务边界未显式定义。
   - 修订:
     - `upsert_package()` 保持不自行提交。
     - `replace_items()` 移除内部 `commit()`。
     - `import_template_package_from_directory()` 改为使用单个显式事务包裹整次导入。
   - 当前策略: 模板包导入属于 service 级原子操作，由 service 统一管理事务，不再让 repository 方法各自提交。
   - 相关文件:
     - `backend/tender_backend/db/repositories/bid_template_package_repo.py`
     - `backend/tender_backend/services/template_service/package_importer.py`
     - `backend/tests/unit/test_bid_template_package_importer.py`

---

## 2. 已完成验证

### 后端测试

执行结果:

```bash
.venv/bin/python -m pytest backend/tests/integration/test_master_data_api.py -q
# 2 skipped, 0 failed

.venv/bin/python -m pytest \
  backend/tests/unit/test_bid_template_package_importer.py \
  backend/tests/unit/test_package_renderer.py \
  backend/tests/unit/test_template_context_preview.py -q
# 20 passed, 0 failed

.venv/bin/python -m pytest backend/tests/integration/test_template_package_api.py -q
# 1 skipped, 0 failed

.venv/bin/python -m pytest backend/tests/unit/test_template_context_preview.py backend/tests/unit/test_package_renderer.py -q
# 18 passed, 0 failed
```

说明:

- `test_master_data_api.py` 在当前环境下因缺少 `DATABASE_URL` 跳过集成场景，但路由导入、测试收集和应用装配均正常。
- 模板包导入、渲染和上下文预览相关单测已通过，可覆盖本轮多数高风险修订。

### 前端验证

- `npm run build` 已在本轮前序修订中通过。
- 本轮新增模板包预检结果展示后，前端 `npm run build` 再次通过。

---

## 3. 后续修订计划

### Phase 1: 收尾高优先级后端结构问题

1. 继续拆分 `master_data.py`
   - 状态: 已完成。
   - 结果: `master_data.py` 已收缩为聚合路由层，后续仅需按需要提炼共享模型或公共错误处理。

2. 补充渲染前预检接口
   - 状态: 已完成。
   - 结果: 已能在实际导出前报告附件缺失、文件不存在、缺失绑定和路径安全问题。

3. 统一事务边界策略
   - 状态: 已完成第一轮收敛。
   - 结果: 模板包导入链路已收敛为 service 单事务，关闭 P0-5 的争议性结论。

### Phase 2: 配置化与运行环境适配

1. 配置化渲染输出目录
   - 状态: 已完成。
   - 新增配置:
     - `TEMPLATE_RENDER_ROOT`
     - `TEMPLATE_BUNDLE_ROOT`

2. 为路径安全配置补充文档
   - 状态: 已完成。
   - 结果: 已在 `README.md`、`backend/README.md`、`infra/.env.example` 中记录 `TEMPLATE_IMPORT_ROOTS`、`EVIDENCE_UPLOAD_DIR`、`EVIDENCE_UPLOAD_MAX_BYTES`、`TEMPLATE_RENDER_ROOT`、`TEMPLATE_BUNDLE_ROOT` 的默认值和部署要求。

### Phase 3: 审查报告同步与验收

1. 回写审查状态
   - 在原审查报告旁维护“已修复/待处理/不采纳”状态，避免后续重复审计。

2. 增加针对已修复缺陷的回归测试
   - 路径穿越拒绝场景
   - 非法上传类型与超大文件场景
   - 模板重导入保留绑定规则场景
   - `selection_mode="by_id"` 精确命中场景

3. 合并前验收清单
   - 关键接口鉴权验证
   - 安全路径白名单验证
   - 模板导入/导出端到端验证
   - 前端字段映射与确认弹窗交互回归

---

## 4. 当前建议

如果继续按最稳妥的节奏推进，下一步优先做两件事:

1. 视需要为模板包预检结果补导出/下载能力，方便离线核对问题清单。
2. 如后续引入新主数据域，为 `latest` 增补对应排序规则和单元测试。
