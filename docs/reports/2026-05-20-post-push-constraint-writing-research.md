# Push 后约束写作项目研究报告

日期：2026-05-20  
背景：完成 `cf75105 Implement ad hoc chapter task cards and templates` 提交并推送后，研究 MuMuAINovel 及 GitHub 上类似“约束写作 / 长文档生成 / RAG 合规写作”项目，判断 tender 可借鉴机制。

## 1. 总结论

`tender` 不应继续朝“AI 帮我写标书”这个泛化方向走，而应明确定位为：

> AI 编译招标要求，受控生成可追溯响应文件。

真正可借鉴的不是小说写作、RFP 写作或聊天式 RAG 的内容形态，而是这些项目背后的约束写作机制：

1. 结构化上下文组装；
2. 分优先级 Prompt Contract；
3. 需求 / 承诺 / 评分点台账；
4. 证据引用和来源反查；
5. Schema-first 抽取与校验；
6. Gap Engine 规则化缺口检测；
7. 局部重写 + 保留事实 + Diff 确认；
8. 生成审计日志。

## 2. MuMuAINovel 研究结论

项目：`https://github.com/xiamuceer-j/MuMuAINovel`  
定位：小说写作项目。

### 2.1 可借鉴点

#### 2.1.1 分优先级 Prompt Contract

MuMuAINovel 的提示词大量使用：

```text
<outline priority="P0">
<characters priority="P1">
<memory priority="P2">
<constraints>
<output>
```

`tender` 可转换为：

```text
<tender_requirements priority="P0">
招标文件强制要求、废标项、实质性响应点
</tender_requirements>

<scoring_points priority="P0">
技术评分标准、得分点、证明材料要求
</scoring_points>

<technical_spec priority="P0">
技术规范书要求
</technical_spec>

<selected_company_assets priority="P1">
用户选择的业绩、人员、资质、设备、体系证明
</selected_company_assets>

<template_structure priority="P1">
章节模板、固定文字、表格格式、分页规则
</template_structure>

<style_and_expression priority="P2">
表达风格、排版语气、措辞偏好
</style_and_expression>

<forbidden priority="P0">
不得编造业绩、不得编造人员、不得替换固定承诺、不得遗漏强制响应
</forbidden>
```

原则：标书里 P0 永远是招标文件和事实资料，不是风格。

#### 2.1.2 章节上下文构建器

MuMuAINovel 有章节上下文构建服务，按 P0/P1/P2 组织：

- P0：章节大纲、衔接锚点、字数要求；
- P1：角色、关系、职业；
- P2：记忆、伏笔。

`tender` 可落为：

```text
BidChapterContextBuilder
```

每章生成前组装：

- 本章招标要求；
- 本章评分点；
- 本章技术规范条款；
- 本章模板固定文字；
- 本章允许使用的公司资料；
- 本章禁止使用的资料；
- 上下章节引用关系；
- 已生成内容中的承诺事项。

#### 2.1.3 局部重写 + 保留元素 + Diff 对比

MuMuAINovel 支持章节重新生成、保留元素、新旧内容对比。

`tender` 应改成标书语义：

```text
章节局部重写
- 保留固定承诺
- 保留已选业绩 / 人员 / 资质事实
- 保留表格结构
- 保留招标响应点
- 允许优化表达
- 生成后重新跑 coverage gate
- 用户确认 diff 后替换
```

适用场景：

- 强化第 10.2 章安全措施；
- 按技术规范书重写第 8 章局部段落；
- 不改表格，只优化说明文字；
- 保留人员 / 业绩事实，重写表达。

#### 2.1.4 AI 调用审计

MuMuAINovel 记录 provider、model、prompt length、token usage、success/error、tool usage 等。

`tender` 更需要 Generation Evidence Ledger：

```text
project_id
chapter_id
template_version
prompt_template_version
model
source_requirements_hash
selected_assets_hash
generated_at
coverage_report
operator
input_context_snapshot
output_hash
```

用途：追溯、stale 判断、合规审计、问题定位。

#### 2.1.5 “伏笔管理”类比为“未覆盖要求 / 未履行承诺”管理

小说里的伏笔状态可映射为 tender 的 Requirement / Promise Ledger：

```text
pending             待响应
covered             已覆盖
partially_covered   部分覆盖
needs_evidence      缺证明材料
conflicted          与其他章节冲突
waived/manual       人工确认不适用
```

这比单次 coverage report 更有长期价值。

#### 2.1.6 SSE 进度与后台任务体验

适合 tender 的场景：

- 招标文件解析；
- 模板导入；
- 章节生成；
- 全文合规扫描；
- docx 输出；
- 覆盖报告生成。

### 2.2 不建议照搬

1. 不要照搬“写作风格最高优先级”；标书 P0 必须是招标文件 / 技术规范 / 事实资料 / 固定承诺。
2. 不要开放社区 Prompt 工坊；如做模板库，也必须内部受控、版本化、审核后启用。
3. 不要默认启用 MCP / 外部工具；必须审计、数据边界明确、默认关闭。
4. 不要自由创作式生成；标书生成必须被事实和招标要求约束。

## 3. GitHub 横向项目研究

### 3.1 DocForge

项目：`yoligehude14753/docforge`  
定位：标书、方案、Proposal 文档生成。

可借鉴：

- 用 JSON 定义文档模板结构；
- 每章有 `title / level / description / children`；
- 可扩展不同文档类型。

局限：

- 模板只是目录结构；
- 缺招标条款映射；
- 缺评分点覆盖；
- 缺公司资料选择；
- 缺事实校验和导出 gate。

`tender` 不应回退到这种轻模板，而应坚持：

```text
章节模板 = 结构 + 固定文字 + 表格 + 资料占位符 + 生成策略 + 校验策略
```

### 3.2 AI RFP Response Generator

项目：`Satyapraveenv/ai-rfp-response-generator`  
定位：RFP 响应大纲生成。

可借鉴：

- AI 不直接生成最终文件，而是生成结构化大纲；
- 使用 `[CUSTOMIZE]` 标记人工补充点；
- 生成 Compliance Matrix；
- 输出质量评分；
- 强调 AI 做结构性工作，人做战略性定稿。

`tender` 对应原则：

```text
生成前：解析评分点、技术规范，建立响应矩阵
生成中：只基于已选公司资料写，缺资料则留任务卡 / 占位符
生成后：输出 coverage score、缺口清单、人工确认项
```

### 3.3 Tender Intelligence Assistant

项目：`adhirajbane13/tender-response-generator-GenAI`  
定位：上传招标 PDF 后做问答和证据定位。

可借鉴：

- PDF 视觉切块：字号、粗体、标题结构；
- RAG 回答显示 supporting context；
- 多 tender 文件切换；
- 低温度事实回答。

建议 tender 增加：

```text
TenderDocumentStructureExtractor
```

输出示例：

```json
{
  "section_title": "技术评分标准",
  "page": 12,
  "level": 2,
  "content": "...",
  "tables": [],
  "source_bbox": "...",
  "confidence": 0.91
}
```

原因：评分表、技术规范、附件清单不能只靠普通文本切块。

### 3.4 SpecBuilder

项目：`dshills/specBuilder`  
定位：把问答编译成机器可用规格书。

最值得借鉴。

核心思想：

> LLM 是 constrained compiler，不是聊天机器人。

可借鉴：

- 问答式补齐需求；
- 答案有版本；
- 编译成结构化 JSON；
- JSON Schema 校验；
- 输出字段带 trace；
- 生成 issues；
- 导出 decisions log；
- 记录 model、prompt version、temperature、snapshot id。

`tender` 可建立：

```text
BidCompiler
```

输入：

```text
招标文件解析结果
技术评分标准
技术规范书
用户选择的公司资料
用户回答的任务卡
模板章节定义
```

输出：

```text
BidSpec.json
ChapterDrafts
CoverageMatrix
Issues
EvidenceLog
```

trace 示例：

```json
{
  "/chapters/5.1/performance_table/rows/0": [
    {
      "source_type": "company_performance",
      "source_id": "perf_123",
      "selected_by": "user",
      "version": 3
    }
  ],
  "/chapters/10.1/quality_measures/paragraphs/2": [
    {
      "source_type": "tender_requirement",
      "source_id": "req_089",
      "page": 42
    }
  ]
}
```

### 3.5 Procurement Contract Intelligence

项目：`victorgvc-hes/ai-procurement-contract-intelligence`  
定位：合同条款抽取 + 合规差异检测 + RAG。

可借鉴：

- 用 Pydantic schema 定义 clause 类型；
- LLM 只负责从 chunk 抽取结构化条款；
- 每个结果带 `source_text / page_number / confidence`；
- 用规则引擎做 gap detection；
- 不让 LLM 自己当最终合规裁判。

`tender` 的招标文件解析应输出结构化对象：

```json
{
  "requirement_id": "REQ-TECH-001",
  "type": "mandatory_response",
  "text": "投标人应提供类似工程业绩证明材料",
  "source_text": "...原文...",
  "page_number": 18,
  "section": "技术规范书",
  "evidence_required": true,
  "evidence_type": "performance",
  "confidence": 0.88
}
```

原则：

> LLM 抽取，规则判定。不要让 LLM 自己当最终裁判。

### 3.6 Atlas RAG

项目：`OneLastStop529/atlas-rag`  
定位：生产化 RAG，带引用、SSE、健康检查、检索策略。

可借鉴：

- 每个回答返回 citations；
- citations 可打开原始 chunk；
- RAG context 带 source 和 chunk index；
- 支持 streaming；
- 支持检索策略灰度；
- 有 readiness / health gate；
- 有 release gate、observability。

`tender` 对应：

生成段落应能反查来源，例如：

```text
来源：
- 技术规范书 第 4.2 条，第 18 页
- 评分标准“质量保障措施 5 分”
- 模板固定文字 v2
- 公司质量体系资料 QMS-001
```

## 4. 建议 tender 新增的核心机制

### 4.1 Requirement Ledger：招标要求台账

字段：

```text
要求 ID
来源文件
页码
章节
要求原文
要求类型
是否强制
是否评分点
是否需要证明材料
对应技术标章节
当前状态
证据资料
覆盖段落
风险等级
```

状态：

```text
pending               待响应
covered               已覆盖
partially_covered     部分覆盖
needs_evidence        缺证明材料
needs_user_selection  需用户选择资料
conflict              与其他章节冲突
manual_confirmed      人工确认
not_applicable        不适用
```

### 4.2 Evidence Citation：正文证据引用

内部记录每个段落 / 表格单元来源：

```json
{
  "draft_block_id": "ch10.1.p3",
  "text": "...",
  "sources": [
    {"type": "tender_requirement", "id": "REQ-090", "page": 42},
    {"type": "scoring_point", "id": "SCORE-010"},
    {"type": "company_asset", "id": "QMS-2024"}
  ]
}
```

### 4.3 Schema-first 招标文件抽取

AI 输出严格 JSON，并用 schema 校验：

```json
{
  "technical_scoring_items": [],
  "mandatory_materials": [],
  "qualification_requirements": [],
  "technical_spec_requirements": [],
  "submission_format_requirements": []
}
```

解析失败不能继续生成最终文件，只能进入人工校正。

### 4.4 Compliance Matrix 自动生成

统一形成：

```text
评分标准支撑材料矩阵
技术规范材料矩阵
强制响应矩阵
资格 / 资质矩阵
```

字段：

```text
序号
招标要求 / 评分点
资料名称
所在章节
页码
当前状态
备注
```

### 4.5 Gap Engine：规则化缺口检测

典型规则：

```text
如果 requirement.evidence_required = true 且没有 selected_asset_id，则 needs_evidence
如果第 5.1 章表格出现业绩但 selected_performance 里没有，则 fabricated_asset_risk
如果人员章节出现姓名但 selected_personnel 里没有，则 fabricated_personnel_risk
如果固定承诺函被改写，则 fixed_text_modified_risk
```

这类必须规则化，不靠 LLM 最终判断。

### 4.6 Question-driven 补资料流程

把 gap 转为用户可执行任务：

```text
问题：第 5.1 章需要类似工程业绩，请选择至少 1 个公司业绩。
原因：评分标准第 X 页要求“类似工程业绩”。
影响：未选择则第 5 章不能生成正式内容。
```

### 4.7 Generation Evidence Ledger：生成审计日志

字段：

```text
chapter_id
template_version
prompt_version
model
temperature
input_context_hash
selected_assets_hash
requirement_ids
coverage_result
created_by
created_at
output_hash
```

### 4.8 Layout-aware 招标文件解析

重点识别：

- 标题层级；
- 表格；
- 页码；
- 编号；
- “应 / 须 / 不得 / 必须”等强制词；
- 评分表；
- 附件清单；
- 投标文件格式要求。

## 5. 不建议 tender 借鉴的方向

1. 不要只做聊天式 RAG。核心不是问答，而是“要求 -> 响应章节 -> 证明材料 -> 覆盖状态 -> 导出 gate”。
2. 不要让 LLM 直接判定合规。LLM 可辅助解释，最终 gate 应由规则和结构化数据驱动。
3. 不要默认生成最终事实内容。业绩、人员、资质、设备必须来自公司资料库和用户选择。
4. 不要优先做 Prompt 工坊。先做 Schema、Ledger、Evidence、Gate、Audit。
5. 不要把风格优先级放到合规要求之上。

## 6. 建议实施顺序

### Phase 1：Requirement Ledger

把招标文件解析结果落成结构化台账。每条招标要求都有 ID、来源、页码、状态、目标章节。

### Phase 2：Evidence Citation

生成章节时，每个段落 / 表格单元绑定来源，能说明“为什么写、依据在哪、用了哪个资料”。

### Phase 3：Gap Engine

导出前跑规则：

```text
强制项未响应
评分点未覆盖
资料未选择
人员 / 业绩疑似编造
固定文字被改
表格缺行
```

### Phase 4：Question-driven 补缺口

把 gap 转成任务卡：

```text
请选择业绩
请选择项目经理
上传证明材料
确认该条不适用
补充工期承诺
```

### Phase 5：Context Pack + Local Rewrite

每章生成前展示 Context Pack；每次重写锁定固定文字、表格结构、已选资料、招标要求、证明材料。

## 7. 推荐参考优先级

1. `dshills/specBuilder`：结构化编译、trace、schema 校验、issues、决策日志；
2. `victorgvc-hes/ai-procurement-contract-intelligence`：schema 抽取、source_text/page/confidence、规则化 gap；
3. `OneLastStop529/atlas-rag`：citations、chunk 反查、SSE、health/release gate；
4. `adhirajbane13/tender-response-generator-GenAI`：PDF layout-aware chunking、证据上下文；
5. `Satyapraveenv/ai-rfp-response-generator`：human customization、compliance matrix、quality score；
6. `yoligehude14753/docforge`：模板 JSON 化，但深度不够，只能参考外围结构；
7. `xiamuceer-j/MuMuAINovel`：长文上下文、局部重写、记忆 / 伏笔机制、SSE 体验。

## 8. 最短决策

`tender` 下一步不应优先做 Prompt 工坊，也不应优先增强“聊天问答”。

最短路径是：

```text
Requirement Ledger
→ Evidence Citation
→ Gap Engine
→ Question-driven 补资料
→ Context Pack + 局部重写
```

这是从“能写”走向“可控、可审、可追溯、可导出”的关键路径。
