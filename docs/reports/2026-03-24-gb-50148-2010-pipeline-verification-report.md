# GB 50148-2010 解析链路验证报告

- **日期：** 2026-03-24
- **标准：** `GB 50148-2010`
- **standard_id：** `dae12cd4-d8d7-417b-b436-1b7e54a11b49`
- **document_id：** `bb1c0345-7969-4d3b-8274-169655b53a0d`
- **当前主链路：** `mineru -> structured scopes -> deepseek -> validation -> targeted repair -> persist`
- **结论：** `可完成技术入库，但暂不建议作为正式可用结果入库`

## 1. 背景

本次验证目标是确认 `MinerU + DeepSeek` 新主链路在同一份 PDF 上是否已摆脱“只产出表格条目、正文无法入库”的故障模式，并评估当前结果是否具备正式入库条件。

在本轮验证前，数据库中的结果仅有 `4` 条条文，且全部来自表格，正文条文为 `0`。

## 2. 根因

根因不在 DeepSeek 侧，而在 AI 前的文档资产构建阶段：

1. `document.raw_payload.pages` 在这份 MinerU 输出中实际是 layout blocks。
2. 这些 page 记录没有可用的 `page_number` 和 `markdown`。
3. `build_document_asset()` 仅因为 `raw_payload.pages` 存在，就把它当成权威页数据。
4. `build_structural_nodes()` 因页面文本为空，未生成任何文本 page node。
5. 最终 AI 处理 scope 只剩 `1` 个表格 scope，导致只入库 `4` 条表格结果。

受影响代码：

- `backend/tender_backend/services/norm_service/document_assets.py`

## 3. 修复

已新增回退逻辑：

- 当 `raw_payload.pages` 存在但不含可用 markdown 文本时，回退到 `document_section` 组装的页面资产。

对应提交：

- `cd3be47` `fix: fall back to section pages when raw payload pages lack markdown`

对应回归测试：

- `backend/tests/unit/test_document_assets.py`
- 用例：`test_build_document_asset_falls_back_to_sections_when_raw_pages_are_layout_blocks`

本地验证：

- `PYTHONPATH=backend .venv/bin/pytest backend/tests/unit/test_document_assets.py backend/tests/unit/test_structural_nodes.py -q`
- 结果：`10 passed`

## 4. 重跑结果

使用修复后的代码，对同一份 PDF 直接重跑 AI 阶段，实际执行耗时约 `1985.8` 秒，约 `33` 分钟。

重跑完成后数据库结果如下：

- 总条文数：`140`
- `commentary`：`128`
- `normative`：`12`
- 文本来源：`136`
- 表格来源：`4`

说明：

1. 本次已不再是“只有表格 scope”。
2. 现场日志显示实际共处理 `41` 个 scope。
3. 主体文本条文已进入数据库，说明原始阻断故障已解除。

## 5. 抽样

### 文本条文

- `1.0.1` `commentary`
  - `为保证电力变压器、油浸电抗器及互感器的施工安装质量，促进安装技术进步，确保设备安全运行，制定本规范。`
- `1.0.2` `commentary`
  - `本规范适用于交流 3kV~750kV 电压等级电力变压器（以下简称变压器）、油浸电抗器（以下简称电抗器）、电压互感器及电流互感器（以下简称互感器）施工及验收...`
- `4.8.1` `normative`
  - `220kV 及以上变压器本体露空安装附件应符合下列规定：`
- `5.2.1` `commentary`
  - `互感器可不进行器身检查，但在发现有异常情况时，应在厂家技术人员指导下按产品技术文件要求进行下列检查：`

### 表格条文

- `电气强度（750kV）标准值应≥70kV，平板电极间隙。`
- `电气强度（500kV）标准值应≥60kV，平板电极间隙。`
- `含水量（750kV）标准值应≤10μL/L。`
- `含水量（500kV）标准值应≤10μL/L。`

## 6. 质量评估

当前结果虽然已经完成写库，但质量仍不足以作为正式入库基线。

持久化后结构校验结果：

- issue 总数：`78`
- `error`：`0`
- `warning`：`78`

主要问题：

1. 页锚点不完整。
   - `63` 条记录 `page_start <= 0` 或缺失。
   - `140` 条记录 `page_end` 为空。
2. 编号结构异常明显。
   - 存在 `numbering.missing_parent`
   - 存在 `numbering.gap`
   - 存在 `numbering.non_monotonic`
3. `normative/commentary` 判型仍偏差较大。
   - 当前仅有 `12` 条 `normative`
   - 大量真实规范条文被落成 `commentary`

典型告警示例：

- `Clause 4.8.8: missing parent clause 4.8`
- `Clause 4.8.5: numbering is not increasing`
- `Clause 4: page_start must be > 0`

## 7. 结论

### 已确认解决

1. 原先“正文在 AI 前丢失”的主阻断故障已修复。
2. 当前链路可以完成整份标准的技术入库。
3. 数据库已不再只有 `4` 条表格结果，正文条文已进入结果集。

### 尚未解决

1. 页锚点传递不完整，导致大量 `page_start/page_end` 不可用。
2. 结构编号与父子关系恢复不稳定。
3. `normative` 召回明显不足，正式质量仍不达标。

### 最终判断

- **技术上：** 可以入库。
- **业务上：** 暂不建议作为正式可用结果入库。

## 8. 建议后续动作

建议下一步优先处理以下两项，而不是继续更换 OCR：

1. 修复 `source_ref/page anchor` 在 scope -> clause 持久化链路中的传递，先把页码锚点补齐。
2. 针对 `normative/commentary` 判型增加基于 AST/grammar/phrase 的二次校验与纠偏，减少真实条文被落入 `commentary`。
