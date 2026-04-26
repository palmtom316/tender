# GB 50168-2018 全流程解析测试与对比报告

- 日期：`2026-04-26`
- 目标文件：`/Users/palmtom/Downloads/GB 50168-2018 电气装置安装工程电缆线路施工及验收标准.pdf`
- 执行链路：`MinerU v4 batch zip -> layout.json/pdf_info -> canonical raw-payload -> standard bundle -> clean bundle -> production mirror -> quality report`

## 1. 本次实际执行结果

### 50168 OCR zip 结构

实测当前 MinerU v4 zip 不再提供 `*_middle.json`，但 `layout.json` 已包含可直接消费的 `pdf_info`。

诊断产物：

- [zip-summary.json](/Users/palmtom/Projects/tender/tmp/mineru_standard_bundle/50168_raw_zip/zip-summary.json)
- [layout.json](/Users/palmtom/Projects/tender/tmp/mineru_standard_bundle/50168_raw_zip/layout.json)
- [full.md](/Users/palmtom/Projects/tender/tmp/mineru_standard_bundle/50168_raw_zip/full.md)

### 50168 fresh full mirror 结果

产物：

- [pipeline-result.json](/Users/palmtom/Projects/tender/tmp/mineru_standard_bundle/50168/pipeline-result.json)
- [quality-report-production.json](/Users/palmtom/Projects/tender/tmp/mineru_standard_bundle/50168/quality-report-production.json)
- [production-clauses.json](/Users/palmtom/Projects/tender/tmp/mineru_standard_bundle/50168/production-clauses.json)

核心指标：

| 指标 | 结果 |
| --- | --- |
| `page_count` | `79` |
| `normalized_section_count` | `495` |
| `table_count` | `10` |
| `clause_count` | `334` |
| `commentary_clause_count` | `111` |
| `table_clause_count` | `52` |
| `section_anchor_coverage` | `99.0%` |
| `clause_anchor_coverage` | `100%` |
| `validation_issue_count` | `0` |
| `ai_fallback_ratio` | `0.0%` |
| 总评 | `pass` |

门禁结论：

- `section_anchor_coverage`：`pass`
- `clause_anchor_coverage`：`pass`
- `structured_validation`：`pass`
- `table_capture`：`pass`
- `ocr_cleanup`：`pass`
- `ai_fallback_ratio`：`pass`

## 2. 本轮修复内容

本次不是只重跑，而是先修了两类根因后再 fresh 验证：

1. `commentary tail` 边界识别
   - 允许从说明封面页文本中的 `条文说明` 触发 commentary 区域，而不再要求标题必须精确等于 `条文说明`。
2. `commentary inline clause split`
   - 允许 commentary scope 按 `5.1.1 / 7.1.5` 这类内嵌条号做确定性拆分。
   - 对 `1.5`、`1.5倍` 这类数值续行增加保护，避免误修成 `5.1.5`、`7.1.5`。
3. `back matter / sparse table fallback` 收敛
   - 允许 `本标准用词说明` 变体进入 non-clause 吸收逻辑，不再误生成伪规范 scope。
   - 只有表头骨架、无有效数据行的弱表格直接跳过，不再触发 AI fallback。

相关代码：

- [block_segments.py](/Users/palmtom/Projects/tender/backend/tender_backend/services/norm_service/block_segments.py)
- [norm_processor.py](/Users/palmtom/Projects/tender/backend/tender_backend/services/norm_service/norm_processor.py)
- [test_block_segments.py](/Users/palmtom/Projects/tender/backend/tests/unit/test_block_segments.py)
- [test_norm_processor.py](/Users/palmtom/Projects/tender/backend/tests/unit/test_norm_processor.py)

## 3. 修复前后对比

| 指标 | 修复前 | 修复后 |
| --- | --- | --- |
| `status` | `fail` | `pass` |
| `normalized_section_count` | `498` | `495` |
| `clause_count` | `343` | `334` |
| `commentary_clause_count` | `0` | `111` |
| `validation_issue_count` | `38` | `0` |
| `ai_fallback_ratio` | `0.9%` | `0.0%` |

结论：

- 50168 已从“正文/条文说明混号”的失败态修到 `pass`。
- 当前门禁项已全部通过，不再依赖 AI fallback。

## 4. 与 147 / 148 / 150 / 173 的对比

| 标准 | 基线来源 | 页数/规范页 | sections | clauses | commentary | validation issues | AI fallback | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GB50168-2018` | 本次 fresh local full mirror | `79` | `495` | `334` | `111` | `0` | `0.0%` | `pass` |
| `GB50173-2014` | fresh local full mirror | `86` | `963` | `1223` | `180` | `0` | `0.7%` | `review` |
| `GB50147-2010` | cleaned bundle baseline | `107` canonical pages | `129` cleaned sections | `-` | `-` | `-` | `-` | `bundle clean` |
| `GB50148-2010` | historical pipeline verification | `-` | `-` | `140` | `128` | `78` | `-` | `not recommended` |
| `GB50150-2016` | canonical bundle baseline | `170` canonical pages | `1102` | `-` | `-` | `-` | `-` | `bundle baseline` |

对比判断：

1. `50168` 当前状态已优于 `50173` 的本地基线：`50168 = pass`，`50173 = review`。
2. `50168` 明显优于 `50148` 的历史持久化结果。
3. `50147 / 50150` 现有 artifact 主要说明 bundle 层稳定，不能直接与 `50168/50173` 的 full mirror 条款质量一一对应。

## 5. 入库判断

当前结论：**可以入库。**

理由：

1. `structured_validation = 0`
2. `commentary` 已正确分流，`commentary_clause_count = 111`
3. 页锚点覆盖正常，`clause_anchor_coverage = 100%`
4. `ai_fallback_ratio = 0`

如果要做上线前抽查，优先看 `production-clauses.json` 中 `commentary` 和 `table` 两类条款即可。

## 6. 验证方法归档

本轮使用过的一次性 `tmp` 验证脚本不再保留在工作区。

其方法已整理入正式开发文档：

- [2026-04-26-standard-pdf-local-verification-playbook.md](/Users/palmtom/Projects/tender/docs/reports/2026-04-26-standard-pdf-local-verification-playbook.md)

后续执行本地规范解析验收时，应以该手册中的正式链路与门禁项为准。
