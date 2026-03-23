# MinerU 结构化前端与局部 VL 补偿设计

## 背景

当前规范解析存在两条主要路径：

- `MinerU -> scope split -> AI` 的文本主管线
- `Qwen3-VL` 按页直接抽取条款的视觉主管线

现状问题不是 `MinerU` 没有结构，而是现有主管线在 `MinerU` 之后把结果过早压平成了 `document_section.text` 与 `document_table.table_html`，随后只把纯文本和 HTML 片段交给后续 AI。`MinerU` 返回的以下结构资产没有被继续利用：

- `full_markdown`
- 页级 `raw_payload`
- 原始表格块
- 页码锚点
- 文档布局上下文

这导致两个直接问题：

1. 入库前的条款提取缺少稳定的结构约束，只能依赖 LLM 从压平文本中重建层级。
2. 表格、跨页表格、数字、单位、符号等高风险区域没有专门的补偿链路，只能在整页视觉管线里粗暴重做。

用户已决定废弃 `Qwen-VL` 作为整本 PDF 的主管线，但保留 VL 能力，改为只处理：

- 表格与跨页表格
- 数字、单位、符号异常片段

并采用高召回策略，优先避免错误内容直接入库。

## 目标

- 以 `MinerU` 作为规范解析的唯一主前端。
- 将 `MinerU` 输出继续保留为结构化中间表示，而不是尽早压平成纯文本。
- 在入库前引入规范文档专用 `AST + grammar + phrase` 校验层。
- 将 VL 能力降级为局部补偿器，只处理高风险片段，而不再提供整页主管线。
- 最终入库的 `standard_clause` 必须来自经过结构校验与必要补偿后的 AST。

## 非目标

- 第一阶段不更换 `MinerU` OCR 服务。
- 第一阶段不做图像/示意图的通用识别，只处理表格和数字符号异常。
- 第一阶段不构建复杂的通用文档解析框架，只实现规范类文档需要的最小 AST。
- 第一阶段不保留 `Qwen-VL` 整页抽取入口用于生产流量。

## 方案选择

### 备选方案

1. 在当前 `MinerU -> 纯文本 AI` 管线上增加少量修补规则。
2. 将 `MinerU` 升级为结构化前端，并引入局部 VL 补偿器。
3. 直接重写为纯规则 AST 管线，仅在局部使用 LLM。

### 结论

采用方案 2。

原因：

- 现有系统已经能够稳定拿到 `MinerU` 的 `markdown + pages + tables`。
- 当前最大浪费是结构信息在主链路中被丢弃，而不是 OCR 本身缺能力。
- 方案 2 能在不重写全栈的前提下，显著提高结构稳定性、入库质量与补偿效率。
- 将 VL 降级为局部补偿器后，可以保留其对表格和复杂符号区域的优势，同时避免整页视觉主管线带来的高延迟与高失败率。

## 总体架构

目标主流程调整为：

`MinerU -> 结构化中间表示 -> AST 构建 -> grammar/phrase 校验 -> VL 定点补偿 -> AST 合并 -> 入库 -> 索引`

### 1. MinerU 作为唯一结构化前端

`MinerU` 仍负责 PDF 解析，但不再仅仅为后续步骤提供压平后的 `section.text`。主流程应持续携带以下结构资产：

- `full_markdown`
- 页级 `raw_payload`
- 表格块及其原始 JSON
- `page_start/page_end`
- 可回溯到页或块的 `source_ref`

### 2. 显式结构化中间层

在 `MinerU` 输出与 AST 构建之间，引入稳定的中间层对象，至少包括：

- `DocumentAsset`
- `StructuralNode`
- `ValidationIssue`
- `RepairTask`

主链路后续逻辑只能消费这些结构对象，不再直接拼接大段自由文本再让后续系统猜结构。

### 3. AST 与校验层

从结构化中间层构建规范文档专用 AST，然后用确定性规则做：

- 编号层级校验
- 标题闭合校验
- 页码锚点校验
- 表格挂接校验
- 条文说明映射校验
- 强制性条文短语检测
- 数字、单位、符号异常检测

### 4. VL 局部补偿

VL 不再负责整页抽取，只负责处理 `RepairTask`：

- `table_repair`
- `symbol_numeric_repair`

VL 仅能修补指定局部块，不能重写整章或整页结果。

## 中间表示设计

## DocumentAsset

`DocumentAsset` 表示 `MinerU` 产出的原始结构资产集合，至少应包含：

- `document_id`
- `full_markdown`
- `pages`
- `tables`
- `parser_name`
- `parser_version`

其中 `pages` 的元素至少应保留：

- `page_number`
- `raw_page`
- `normalized_text`

其中 `tables` 的元素至少应保留：

- `table_id` 或稳定定位键
- `page_start/page_end`
- `table_title`
- `table_html`
- `raw_json`

## StructuralNode

`StructuralNode` 是从 `MinerU` 结构资产提取出的初始节点，不直接等价于最终 `standard_clause`。节点类型至少包括：

- `chapter`
- `section`
- `clause`
- `item`
- `subitem`
- `table`
- `commentary_ref`
- `appendix`

每个节点至少包含：

- `node_type`
- `node_key`
- `node_label`
- `title`
- `text`
- `page_start`
- `page_end`
- `source_ref`
- `children`

`source_ref` 必须可回溯到原始页或块，以便后续补偿和问题定位。

## ValidationIssue

`ValidationIssue` 表示结构校验阶段发现的问题，至少包含：

- `issue_type`
- `severity`
- `page_start/page_end`
- `source_ref`
- `snippet`
- `message`

## RepairTask

`RepairTask` 表示发往 VL 的局部补偿任务。第一阶段只支持：

- `table_repair`
- `symbol_numeric_repair`

任务至少包含：

- `task_type`
- `source_ref`
- `page_start/page_end`
- `input_payload`
- `trigger_reasons`

## AST 设计

第一阶段只实现规范文档专用 AST，不追求通用性。

### 节点集合

- `chapter`
- `section`
- `clause`
- `item`
- `subitem`
- `table`
- `commentary_ref`
- `appendix`

### 字段要求

每个 AST 节点至少包含：

- `node_type`
- `node_key`
- `node_label`
- `title`
- `text`
- `page_start/page_end`
- `source_ref`
- `children`

### 设计原则

- AST 是入库前的唯一结构真相来源。
- `standard_clause` 由 AST 投影生成，而不是由任意 LLM 直接输出。
- 子节点页码与父节点页码关系必须可校验。
- 表格节点必须能被挂接到明确的上下文节点。

## 校验规则

## grammar 规则

第一阶段实现确定性最强的规则：

### 编号层级规则

- `1 -> 1.1 -> 1.1.1`
- `1、 -> 1) -> a)` 这类项级关系按固定模式映射
- 不允许无依据跳级

### 标题闭合规则

- 章、节、条不允许无故中断
- 同级编号必须具备稳定递进关系

### 页码锚点规则

- 子节点页码不得明显早于父节点
- 跨页节点必须具备连续页码范围

### 表格挂接规则

- 表格必须能挂接到某个章节或条文上下文
- 连续页中标题相同或列头近似的表格视为跨页候选

### 条文说明映射规则

- `条文说明` 必须能映射到对应正文条号
- 无法映射的说明节点输出异常，不直接入库

## phrase 规则

第一阶段实现短语与模式层检测：

### 强制性短语

- `必须`
- `应`
- `不得`
- `严禁`
- `禁止`

### 推荐性短语

- `宜`
- `可`
- `不宜`

### 数值约束短语

- `不应小于`
- `不应大于`
- `不得超过`
- `应符合`

### 引用短语

- `见表`
- `按表`
- `应符合表`
- `见图`
- `按图`

phrase 层的输出不直接改写 AST，而是为以下动作提供依据：

- 标注强制性条文
- 生成 `ValidationIssue`
- 生成 `RepairTask`

## VL 局部补偿策略

## 原则

- 先规则触发，再调用 VL。
- 只做块级或片段级补偿，不做整页或整本重跑。
- VL 返回结果只能修补指定 `source_ref` 对应片段，不能覆盖其他节点。

## 补偿范围

### 表格与跨页表格

以下情况进入高召回候选：

- 所有表格默认进入候选池
- 相邻页表格标题相同
- 相邻页表格列头相似
- 表格列数明显波动
- HTML 结构残缺
- 表格中存在大量空单元格

对候选表格，优先做：

- 跨页合并判断
- 表头补全
- 单元格值修复
- 数字与单位校正

### 数字、单位、符号异常

以下情况进入高召回候选：

- 命中规范常见数值模式但不完整，如 `20~`、`0.5 1.0`
- 单位缺失或疑似错识别，如 `mm`、`m3`、`MPa`、`kN/m2`
- 比较符号异常，如 `>=`、`≤`、`≥`、`<`、`>`
- OCR 易错字符混淆，如 `O/0`、`1/l/I`、`×/x`
- 上下标、括号、范围表达不闭合
- 强制性语句中存在疑似错误数字或约束表达

## 高召回边界

用户已选择高召回策略，因此系统应倾向于：

- 多触发补偿任务
- 少让疑似错误内容直接入库

代价是：

- VL 调用次数上升
- 需要更严格的任务去重与回溯

该策略是可接受的，因为 VL 已从整页主管线降级为局部补偿器，整体成本仍可控。

## 入库策略

最终入库流程必须满足：

1. 初始 AST 已构建完成
2. grammar/phrase 校验已执行
3. 所需 `RepairTask` 已完成
4. 修补结果已 merge 回 AST
5. AST 已通过入库前强校验

只有通过强校验的 AST 才能投影生成 `standard_clause`。

`standard_clause` 中应继续保留以下可追踪信息：

- `page_start/page_end`
- `source_type`
- `source_label`
- 可映射回 AST 节点的稳定标识

## 现有代码改造方向

## 需要保留并重构的部分

- `backend/tender_backend/services/norm_service/norm_processor.py`
- `backend/tender_backend/services/norm_service/tree_builder.py`
- `backend/tender_backend/services/parse_service/parser.py`
- `backend/tender_backend/workflows/standard_ingestion.py`
- `backend/tender_backend/db/repositories/standard_repo.py`

## 需要退出主管线的部分

- `/api/standards/{standard_id}/process-vision`
- `StandardVisionIngestionWorkflow`
- `vision_service` 作为整页条款抽取主管线的职责

## 需要保留为局部能力的部分

- `vision_service` 中对视觉模型的调用能力
- 但接口语义应改为局部修补，而不是整本标准重解析

## 分阶段实施建议

### 第一阶段

- 保持 `MinerU` 解析入口不变
- 新增结构化中间层读取与构建
- 让主链路继续携带 `markdown + pages + tables + source_ref`
- 停止新增 `Qwen-VL` 整页测试流量

### 第二阶段

- 构建最小 AST
- 接入 grammar/phrase 校验器
- 在不调用 VL 的情况下先输出 `ValidationIssue`

### 第三阶段

- 实现 `table_repair` 与 `symbol_numeric_repair`
- 将 VL 修补结果 merge 回 AST
- 打通入库前强校验

### 第四阶段

- 下线整页视觉主管线 API、工作流、配置与无关测试
- 保留局部视觉补偿接口与监控

## 测试策略

需要覆盖以下测试层级：

- 单元测试
  - AST 构建
  - grammar 校验
  - phrase 检测
  - `RepairTask` 生成
  - VL 修补结果合并
- 集成测试
  - `MinerU -> AST -> 校验 -> 入库`
  - 表格补偿链路
  - 数字符号异常补偿链路
- 回归测试
  - 现有 `MinerU` 批量解析结果仍能持久化
  - 已修复的 `page_start/page_end` 空字符串问题不回归

## 风险与控制

### 风险 1：结构化主干改造范围扩大

控制方式：

- 第一阶段只补最小中间层和 AST，不重写所有下游逻辑
- 明确 AST 是入库前真相来源，避免双轨结构长期并存

### 风险 2：高召回导致 VL 调用过多

控制方式：

- 增加 `RepairTask` 去重
- 对相同 `source_ref` 避免重复触发
- 保留任务统计与超时保护

### 风险 3：局部修补污染主结构

控制方式：

- VL 返回只允许覆盖对应局部节点
- 修补后必须重新执行局部校验

## 决策摘要

- 保留 `MinerU`，废弃 `Qwen-VL` 作为整页主管线。
- 主链路升级为结构化前端，而不是继续把 `MinerU` 当纯 OCR。
- 入库前增加规范 AST 与 grammar/phrase 校验层。
- 保留 VL，但只用于表格、跨页表格、数字单位符号异常的局部补偿。
- 局部补偿采用高召回策略，优先保证质量与入库稳定性。
