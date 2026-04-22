# AI 条款抽取入库验收结论

- 日期：`2026-04-22`
- 范围：`GB 50147-2010`、`GB 50148-2010`、`GB 50150-2016`
- 验收层级：`AI 条款抽取入库验收`
- 上游前提：`MinerU cleaned bundle 上游资产质量已于 2026-04-22 单独验收通过`

## 1. 本层验收目标

本层验收的目标不是再次验证 MinerU 清洗质量，而是确认以下事项：

- 三本规范是否已经成功导入本地 Tender 数据库，形成可供 `process_standard_ai()` 直接消费的标准记录、文档记录、段落记录与表格记录。
- 本地 AI 执行链路是否具备真实运行条件，包括：
  - `agent_config.tag_clauses` 是否配置了真实主/备 API key
  - `ai-gateway` 是否能够返回真实 LLM JSON，而不是 stub 响应
- 若具备真实运行条件，是否能完成 `standard_clause` 持久化，并输出可用于正式入库验收的统计与问题清单。

## 2. 本轮已完成工作

### 2.1 数据库初始化

本地 `tender-postgres` 初始为空库，本轮已完成：

- Alembic `0001` 到 `0014` 全部迁移落库
- `alembic_version = 0014`
- `project / project_file / document / document_section / document_table / standard / standard_clause / standard_processing_job / agent_config` 等表全部建立完成

### 2.2 三本 cleaned bundle 已真实导入数据库

本轮新增导入工具：

- [backend/tender_backend/tools/import_standard_bundles.py](/home/palmtom/projects/tender/backend/tender_backend/tools/import_standard_bundles.py)

该工具已将三本 cleaned bundle 原样导入 Tender 本地库，并保留 bundle 内稳定 UUID。

导入汇总输出：

- [tmp/mineru_standard_bundle/import-summary.json](/home/palmtom/projects/tender/tmp/mineru_standard_bundle/import-summary.json)

导入后的标准记录如下：

- `GB 50147-2010`
  - `standard_id = 820ea6b2-91de-49ed-a86f-9fae86826fd9`
  - `document_id = b593b0fb-d68b-5da5-b3bb-1fdf69f53433`
  - `section_count = 781`
  - `table_count = 7`
- `GB 50148-2010`
  - `standard_id = d4961d55-a538-4a0d-bcc2-f426ab6cecdf`
  - `document_id = 25a9b5e0-3916-599f-90da-d1bf8842b82c`
  - `section_count = 413`
  - `table_count = 9`
- `GB 50150-2016`
  - `standard_id = af3bc5c7-aec4-4db9-a777-81c497cca648`
  - `document_id = 5489ee8d-2c82-5cd2-be65-2a4ae751720d`
  - `section_count = 1002`
  - `table_count = 60`

库内最终汇总计数：

- `standard_count = 3`
- `document_count = 3`
- `document_section_count = 2196`
- `document_table_count = 76`
- `standard_clause_count = 0`

### 2.3 已补齐本层可复用执行器

本轮新增真实 AI 验收执行器：

- [backend/tender_backend/tools/run_standard_ai_acceptance.py](/home/palmtom/projects/tender/backend/tender_backend/tools/run_standard_ai_acceptance.py)

该执行器会：

- 先校验 `agent_config.tag_clauses` 是否已有真实 key
- 若没有 key，直接明确报错，避免误把 stub 结果当成真实验收
- 若有 key，则顺序执行三本 `process_standard_ai()`
- 输出每本书的抽取汇总 JSON，供正式验收记录使用

## 3. 本轮阻断项

### 3.1 `tag_clauses` 无真实 API key

本轮在本地 Tender 数据库中检查 `agent_config`，结果如下：

- `agent_key = tag_clauses`
- `enabled = true`
- `base_url = https://api.siliconflow.cn/v1`
- `fallback_base_url = https://dashscope.aliyuncs.com/compatible-mode/v1`
- `length(api_key) = 0`
- `length(fallback_api_key) = 0`

也就是说：

- 主模型没有真实 key
- 备模型没有真实 key

### 3.2 `tender-ai-gateway` 容器环境同样没有 provider key

本轮检查 `tender-ai-gateway` 容器环境后确认：

- 容器内没有 `DEEPSEEK_API_KEY`
- 容器内没有 `QWEN_API_KEY`
- 容器内没有 `SILICONFLOW_API_KEY`

因此，即使直接调用 `ai-gateway`，返回的也会是 stub 响应，而不是可供 `_parse_llm_json()` 消费的真实 JSON。

## 4. 本轮未完成项

由于上述密钥阻断，本轮**未能完成**以下真实验收动作：

- 未执行三本 `process_standard_ai()`
- 未生成真实 `standard_clause`
- 未完成 `normative/commentary` 统计验收
- 未完成 warnings / validation / issues_after_repair 的真实检查
- 未能给出“达到正式入库质量”的最终 AI 层结论

## 5. 验收结论

### A. 本地 AI 入库前置准备是否完成

结论：**是。**

本地 Tender 环境已经完成：

- 数据库 schema 初始化
- 三本规范 cleaned bundle 的真实导入
- `process_standard_ai()` 所需的 `document / sections / tables / raw_payload` 资产准备
- 本层验收脚本与复跑工具补齐

因此，从“数据和工具链准备”的角度，本地环境已经达到**可执行 AI 入库验收**状态。

### B. 本轮是否已经完成真实 AI 条款抽取入库验收

结论：**否。**

原因不是 parse 资产质量，也不是导入链路缺失，而是：

- 当前本地环境没有任何真实 LLM provider key
- `ai-gateway` 只能返回 stub
- 继续执行只会得到伪结果，不能构成真实验收

### C. 三本规范当前是否可以判定“已达到正式入库质量”

结论：**暂不能下此结论。**

目前只能确认：

- 上游 cleaned bundle 质量已通过
- 本地数据库入库准备已通过

但下游 AI 抽取结果尚未真实生成，因此还不能正式宣布三本规范已经通过“AI 条款抽取入库验收”。

## 6. 最小解阻条件

只需补齐以下任一真实 AI 配置，即可继续本层正式验收：

- 为 `agent_config.tag_clauses.api_key` 填入可用主模型 key
- 或为 `agent_config.tag_clauses.fallback_api_key` 填入可用备模型 key
- 或在 `tender-ai-gateway` 容器环境中提供可用 provider key，并保证本地调用链实际使用它们

## 7. 解阻后的执行入口

准备好真实 key 后，可直接复用本轮已落地的执行器：

```bash
docker run --rm \
  --network container:tender-postgres \
  -v /home/palmtom/projects/tender:/workspace \
  -w /workspace/backend \
  python:3.12-slim \
  python -c "
import sys, runpy
sys.path.insert(0, '/workspace/backend')
sys.path.insert(0, '/workspace/.venv/lib/python3.12/site-packages')
sys.argv = [
  'run_standard_ai_acceptance',
  '--database-url', 'postgresql://tender:change-me@127.0.0.1:5432/tender',
  '--standard-code', 'GB 50147-2010',
  '--standard-code', 'GB 50148-2010',
  '--standard-code', 'GB 50150-2016',
  '--output', '/workspace/tmp/mineru_standard_bundle/ai-acceptance-summary.json',
]
runpy.run_module('tender_backend.tools.run_standard_ai_acceptance', run_name='__main__')
"
```

正式 AI 验收应以该输出为准，再补写最终“通过 / 不通过”结论。
