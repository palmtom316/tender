# 标准 PDF 本地全链路验证手册

- 日期：`2026-04-26`
- 适用范围：`tender` 系统内的规范规程 PDF 解析、入库、检索验收
- 背景：`GB 50173-2014` 与 `GB 50168-2018` 的本地修复验证已完成，临时 `tmp` 脚本中的有效方法现整理为正式开发手册

## 1. 目的

本手册用于替代一次性 `tmp/*.py` 验证脚本，明确后续应如何在本地验证：

1. 规范 PDF 上传是否走到正式标准处理链路
2. OCR 清洗、结构化抽取、质量门禁是否达标
3. 规范条款是否已经正确入库并可检索

## 2. 正式链路

标准 PDF 的正式生产链路如下：

1. 前端“规范规程库”上传 PDF
2. `POST /api/standards/upload`
3. 创建 `standard`、`document`、`standard_processing_job`
4. `StandardProcessingScheduler` 自动执行
5. OCR 阶段：`ensure_standard_ocr()` -> `_parse_via_mineru()`
6. AI/确定性抽取阶段：`process_standard_ai()`
7. 条款入库、质量报告生成、索引更新

关键代码入口：

- [standards.py](/Users/palmtom/Projects/tender/backend/tender_backend/api/standards.py)
- [standard_processing_scheduler.py](/Users/palmtom/Projects/tender/backend/tender_backend/services/norm_service/standard_processing_scheduler.py)
- [norm_processor.py](/Users/palmtom/Projects/tender/backend/tender_backend/services/norm_service/norm_processor.py)
- [section_cleaning.py](/Users/palmtom/Projects/tender/backend/tender_backend/services/norm_service/section_cleaning.py)
- [mineru_client.py](/Users/palmtom/Projects/tender/backend/tender_backend/services/parse_service/mineru_client.py)

## 3. 本地验收标准

一次本地全链路验证至少应确认以下项目：

1. 状态流转正确
   `queued_ocr -> parsing -> queued_ai -> processing -> completed`
2. 解析资产存在
   `/api/standards/{id}/parse-assets`
3. 质量报告通过
   `/api/standards/{id}/quality-report`
4. 条款树存在
   `/api/standards/{id}` 或 `/api/standards/{id}/viewer`
5. PDF 可预览
   `/api/standards/{id}/pdf`
6. 搜索可命中
   `/api/standards/search?q=...`

## 4. 建议验证顺序

### A. 首选：前端上传全链路验收

适用于验证“系统正式实现是否可用”。

步骤：

1. 启动前后端及依赖服务
2. 在“规范规程库”上传目标 PDF，并填写 `standard_code` / `standard_name`
3. 轮询 `/api/standards/{id}/status`
4. 状态进入 `completed` 后，检查：
   - `/api/standards/{id}/parse-assets`
   - `/api/standards/{id}/quality-report`
   - `/api/standards/{id}/viewer`
   - `/api/standards/search`

通过条件：

1. `processing_status=completed`
2. `quality-report.report.overview.status=pass`，或至少没有阻塞性 `fail`
3. 条款树与 PDF 分页可对应
4. 搜索能命中新入库规范条款

### B. 次选：已入库标准的 AI 重跑验收

适用于 OCR 已完成、只需要验证标准条款抽取质量。

官方工具：

- [run_standard_ai_acceptance.py](/Users/palmtom/Projects/tender/backend/tender_backend/tools/run_standard_ai_acceptance.py)

用途：

1. 对数据库中已存在的标准重跑 `process_standard_ai()`
2. 输出每个标准的抽取结果摘要

限制：

1. 这不是原始上传/OCR 全链路
2. 仅适合验证 AI/确定性抽取与门禁结果

## 5. 173 / 168 修复后应特别关注的门禁

在 `50173/50168` 修复中，以下指标最关键：

1. `structured_validation`
   预期：`0 issues`
2. `ai_fallback_ratio`
   预期：尽量接近 `0`
3. `commentary_clause_count`
   预期：条文说明标准不应为 `0`
4. `section_anchor_coverage`
   预期：接近 `100%`
5. `clause_anchor_coverage`
   预期：`100%`

## 6. 临时脚本处置

以下 `tmp` 脚本只用于本轮诊断，现不再作为正式仓库能力保留：

- `tmp/inspect_mineru_zip.py`
- `tmp/run_standard_pipeline.py`
- `tmp/run_full_parse_pipeline.py`
- `tmp/run_production_pipeline.py`
- `tmp/run_parse_pipeline_v2.py`
- `tmp/fix_table_parsing.py`

处置原则：

1. 其验证结论已沉淀到正式代码与测试
2. 其使用方式已由本手册替代
3. 其包含一次性路径和硬编码敏感配置，不应继续留在仓库工作区

## 7. 本轮证据文档

本轮已保留的正式报告：

- [2026-04-26-gb50168-pipeline-comparison-report.md](/Users/palmtom/Projects/tender/docs/reports/2026-04-26-gb50168-pipeline-comparison-report.md)

该报告可作为：

1. `50168` 本地 full mirror 通过证据
2. 与 `147/148/150/173` 的横向对比参考

## 8. 当前建议

后续若再做规范解析验收，优先级应固定为：

1. 前端上传全链路
2. API 状态/质量报告核对
3. 条款树与搜索抽查
4. 单测/集成测试回归

不再新增新的 `tmp` 一次性验证脚本，除非要隔离一个尚未进入正式实现的新假设。
