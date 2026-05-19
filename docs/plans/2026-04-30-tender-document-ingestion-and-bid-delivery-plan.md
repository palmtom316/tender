# 招标文件上传解析与投标文件交付实施计划

> **创建日期：** 2026-04-30
> **计划类型：** 可跟踪 to-do 实施计划
> **范围：** ZIP/PDF 招标文件上传、Office/PDF 解析、投标约束抽取、人工确认、AI 编写、Word 交付、审查与最终交付包

## Goal

支持两类招标文件上传：

- ZIP 招标包：包含 Word、Excel、WPS、内层 ZIP、签名文件等。
- PDF 招标文件：包含文本型 PDF 与扫描型 PDF。

系统需将不同来源统一解析为可追溯的结构化内容，抽取投标文件 AI 编写所需的硬约束，并最终生成以 Word 为核心的投标交付物。报价不纳入投标正文生成与审查范围。

## Core Principles

- [x] ZIP 和 PDF 是两条输入链路，但必须归一化到同一套解析块模型。
- [x] Office-first：ZIP 包内 Word/Excel 是主路径，PDF 统一走 MinerU v4 解析链路。
- [x] 所有 AI 抽取结果必须保留来源文件、段落、页码、sheet、行列或表格定位。
- [x] 报价相关内容允许识别和标记，但不进入投标正文生成约束。
- [x] 业绩要求、项目管理团队要求、特殊要求是一类核心约束。
- [x] 最终交付以 Word 为核心，必要时兼容 `.doc` 转换。
- [x] 否决项、资格、业绩、项目团队、特殊要求必须经过人工确认后才能进入最终导出。

## Target Deliverables

- [x] ZIP/PDF 统一上传入口。
- [x] ZIP 递归解包与文件分类。
- [x] Office 文档解析能力。
- [x] PDF 统一 MinerU v4 解析能力。
- [x] 统一 source chunk 数据模型。
- [x] AI 结构化约束抽取。
- [x] 约束确认与编辑页面。
- [x] 企业库、业绩库、人员库匹配。
- [x] 投标文件目录与章节规划。
- [x] 章节级 AI 编写。
- [x] Word 投标文件生成。
- [x] 投标文件审查。
- [x] 响应矩阵、缺失清单、来源追溯清单。
- [x] 最终交付包 ZIP 下载。

## Phase 1: 上传与文件识别

**目标：** 建立统一上传入口，支持 ZIP 和 PDF，并能展示 ZIP 解包后的文件清单。

- [x] 新增统一上传接口：`POST /api/projects/{project_id}/tender-documents`。
- [x] 支持上传 `.zip` 招标包。
- [x] 支持上传 `.pdf` 招标文件。
- [x] 保存原始上传文件到对象存储或本地存储。
- [x] 创建上传批次记录，记录文件名、大小、类型、hash、上传时间。
- [x] 识别上传类型：`zip | pdf`。
- [x] 定义处理状态：`uploaded | extracting | parsing | extracting_constraints | completed | failed`。
- [x] ZIP 文件名编码兼容 `GBK/UTF-8`。
- [x] ZIP 递归解包，支持内层 ZIP。
- [x] 跳过危险路径：`../`、绝对路径、控制字符文件名。
- [x] 登记 `.sign` 签名文件，但不进入解析流程。
- [x] 对解包文件进行初步分类：
  - [x] 招标公告
  - [x] 招标文件/采购文件
  - [x] 技术规范书
  - [x] 合同文件
  - [x] 需求一览表
  - [x] 专用资格要求
  - [x] 商务评分细则
  - [x] 技术评分细则
  - [x] 投标文件制作及递交要求
  - [x] 最高限价/保证金文件
  - [x] 未识别文件

**验收标准：**

- [x] 上传 ZIP 后能看到完整解包文件清单。
- [x] 上传 PDF 后能创建解析任务。
- [x] 文件名中文显示正常。
- [x] `.sign` 文件只登记，不解析。
- [x] 文件分类结果可人工修正。

## Phase 2: 文本与表格解析

**目标：** 将 ZIP/PDF 中的内容统一解析为结构化文本块和表格块。

- [x] `.docx` 段落抽取。
- [x] `.docx` 标题层级识别。
- [x] `.docx` 表格抽取。
- [x] `.docx` 页眉页脚和封面关键文本抽取。
- [x] `.xlsx` sheet 抽取。
- [x] `.xlsx` 表头识别。
- [x] `.xlsx` 合并单元格还原。
- [x] `.xlsx` 行列定位保留。
- [x] `.xlsx` 多 sheet 类型识别。
- [x] `.doc` 通过 LibreOffice headless 转 `.docx` 后解析。
- [x] `.xls` 通过 LibreOffice headless 转 `.xlsx` 后解析。
- [x] `.wps` 尝试通过 LibreOffice 转 `.docx`。
- [x] `.wps` 转换失败时标记为人工确认。
- [x] 文本型 PDF 走 MinerU v4 解析。
- [x] 扫描型 PDF 走 MinerU v4 解析。
- [x] PDF 表格通过 MinerU v4 抽取并保留页码。
- [x] ZIP 内 PDF 自动进入 PDF 解析分支。
- [x] 定义统一解析块模型：
  - [x] `source_file`
  - [x] `document_type`
  - [x] `section_title`
  - [x] `text`
  - [x] `table_json`
  - [x] `page_start`
  - [x] `page_end`
  - [x] `sheet_name`
  - [x] `row_start`
  - [x] `row_end`
  - [x] `paragraph_index`
  - [x] `source_locator`
  - [x] `confidence`

**验收标准：**

- [x] ZIP 和 PDF 都能产出统一解析块。
- [x] Excel 表格不丢 sheet、行列定位。
- [x] Word 表格可被后续 AI 抽取使用。
- [x] `.doc/.wps` 转换失败不会阻断整个任务。
- [x] 解析结果可按来源文件查看。

## Phase 3: 核心约束抽取

**目标：** 从解析块中抽取投标文件编写约束，形成固定 JSON schema。

- [x] 招标文件 AI 解析默认模型为 `deepseek-v4-pro`，并使用 `reasoning_effort=max`。
- [x] 建立规则预抽取器，定位候选片段。
- [x] 建立 AI 结构化抽取 prompt。
- [x] 建立抽取结果 JSON schema。
- [x] 每条抽取结果必须包含来源。
- [x] 抽取项：项目信息。
- [x] 抽取项：时间要求。
- [x] 抽取项：资格要求。
- [x] 抽取项：业绩要求。
- [x] 抽取项：项目管理团队要求。
- [x] 抽取项：技术要求。
- [x] 抽取项：商务要求。
- [x] 抽取项：评分办法。
- [x] 抽取项：否决项。
- [x] 抽取项：格式要求。
- [x] 抽取项：合同约束。
- [x] 抽取项：特殊要求。
- [x] 识别报价相关内容并标记 `ignored_for_pricing=true`。
- [x] 报价内容不进入投标正文生成上下文。
- [x] 对低置信度约束标记 `requires_human_confirm=true`。
- [x] 对否决项自动标记 `is_veto=true`。

**核心分类定义：**

- [x] `project_info`: 项目名称、招标编号、包号、招标人、采购范围、实施地点。
- [x] `schedule`: 投标截止、开标、工期、服务期、交付期。
- [x] `qualification`: 企业资质、认证、许可、联合体限制。
- [x] `performance`: 类似项目业绩、金额/规模、时间范围、证明材料。
- [x] `project_team`: 项目经理、技术负责人、安全员、施工员、资料员、证书、社保、经验要求。
- [x] `technical`: 技术规范、施工/服务范围、质量标准、验收标准。
- [x] `business`: 保证金、履约保证、响应文件组成等非报价商务要求。
- [x] `scoring`: 商务评分、技术评分、响应重点。
- [x] `veto`: 废标、无效投标、不予受理、实质性不响应。
- [x] `format`: 目录、章节、签章、盖章、页码、文件命名、上传方式。
- [x] `contract`: 质量、安全、进度、违约、质保、验收。
- [x] `special`: 分包限制、现场踏勘、澄清答疑、保密、属地化、材料品牌、特殊工艺、平台上传规则。

**验收标准：**

- [x] 每条约束可追溯到来源。
- [x] 业绩要求可独立筛选。
- [x] 项目管理团队要求可独立筛选。
- [x] 特殊要求可独立筛选。
- [x] 报价字段不会出现在投标正文生成输入中。

## Phase 4: 约束入库与人工确认

**目标：** 将抽取结果持久化，并提供人工确认、编辑、驳回能力。

- [x] 扩展 `project_requirement` 或新增约束表。
- [x] 增加字段：`category`。
- [x] 增加字段：`title`。
- [x] 增加字段：`requirement_text`。
- [x] 增加字段：`source_file`。
- [x] 增加字段：`source_locator`。
- [x] 增加字段：`source_text`。
- [x] 增加字段：`confidence`。
- [x] 增加字段：`is_veto`。
- [x] 增加字段：`requires_human_confirm`。
- [x] 增加字段：`human_confirmed`。
- [x] 增加字段：`ignored_for_pricing`。
- [x] 增加字段：`applies_to_chapter`。
- [x] 增加字段：`review_status`。
- [x] 增加字段：`review_note`。
- [x] 支持约束确认。
- [x] 支持约束驳回。
- [x] 支持约束编辑。
- [x] 支持约束合并。
- [x] 支持约束拆分。
- [x] 支持标记硬约束。
- [x] 支持标记特殊要求。
- [x] 需求确认页按分类筛选。
- [x] 需求确认页展示来源片段。
- [x] 需求确认页展示置信度。
- [x] 未确认否决项阻止最终导出。

**验收标准：**

- [x] 用户可逐条确认关键投标约束。
- [x] 用户可修正 AI 抽取错误。
- [x] 未确认否决项时导出失败。
- [x] 低置信度约束提示人工复核。
- [x] 完成解析的结构化结果可下载。

## Cross-cutting Rule: 招标解析优先于模板

- [x] 招标文件解析出的投标内容要求优先于模板默认内容。
- [x] 招标文件解析出的投标格式要求优先于模板默认格式。
- [x] 模板渲染上下文暴露 `tender_requirement_priority`、`tender_content_requirements`、`tender_format_requirements`。
- [x] 普通 DOCX 导出追加“招标文件解析要求优先响应”章节，避免模板遗漏解析要求。
- [x] 报价相关解析项不进入投标正文生成和模板优先级上下文。

## Phase 5: 知识库匹配

**目标：** 将招标约束与企业资料、业绩、人员、标准规范进行匹配。

- [x] 企业资质匹配。
- [x] 企业认证匹配。
- [x] 企业许可匹配。
- [x] 企业业绩匹配。
- [x] 人员库匹配。
- [x] 人员证书匹配。
- [x] 人员社保/任职信息匹配。
- [x] 标准规范库匹配。
- [x] 技术条款匹配。
- [x] 验收标准匹配。
- [x] 匹配状态定义：`satisfied | likely_satisfied | missing | needs_review`。
- [x] 生成缺失资料清单。
- [x] 生成需人工确认清单。
- [x] 匹配结果进入章节生成上下文。

**验收标准：**

- [x] 业绩要求能匹配企业业绩库。
- [x] 项目管理团队要求能匹配人员库。
- [x] 缺失资料能生成待补清单。
- [x] 不得虚构缺失的资质、业绩、人员。

## Phase 6: 投标文件结构规划

**目标：** 根据招标文件要求规划投标文件目录、分册和章节约束映射。

- [x] 抽取投标文件组成要求。
- [x] 抽取商务文件目录要求。
- [x] 抽取技术文件目录要求。
- [x] 抽取资格审查文件目录要求。
- [x] 自动生成投标文件目录草案。
- [x] 支持商务文件分册。
- [x] 支持技术文件分册。
- [x] 支持资格文件分册。
- [x] 建立章节与约束映射。
- [x] 否决项必须映射到响应章节。
- [x] 评分项必须映射到响应章节。
- [x] 特殊要求必须映射到响应章节。
- [x] 生成章节写作大纲。
- [x] 允许人工调整章节顺序。
- [x] 允许人工调整约束与章节映射。

**验收标准：**

- [x] 能根据招标要求生成投标文件目录。
- [x] 每个章节能看到输入约束。
- [x] 每条硬约束能追踪到响应章节。

## Phase 7: AI 编写投标内容

**目标：** 以确认后的约束和知识库事实为输入，生成章节级投标内容。

- [x] 建立章节级生成 workflow。
- [x] 输入已确认约束。
- [x] 输入企业资料。
- [x] 输入业绩资料。
- [x] 输入人员资料。
- [x] 输入技术规范。
- [x] 输入评分细则。
- [x] 输入特殊要求。
- [x] 输入格式要求。
- [x] 先生成章节草稿。
- [x] 按评分细则强化章节。
- [x] 按否决项检查章节。
- [x] 按格式要求调整章节。
- [x] 支持单章重写。
- [x] 支持单章审查。
- [x] 支持人工编辑章节内容。
- [x] 禁止生成报价内容。
- [x] 禁止虚构企业资质。
- [x] 禁止虚构业绩。
- [x] 禁止虚构项目团队人员。

**验收标准：**

- [x] 每个章节可单独生成、重写、审查。
- [x] 特殊要求在相关章节中明确响应。
- [x] 生成内容使用真实企业、业绩、人员数据。
- [x] 报价不出现在生成结果中。

## Phase 8: Word 文件生成

**目标：** 生成符合招标文件格式要求的 Word 投标文件。

- [x] 输出 `.docx` 文件。
- [x] 支持封面生成。
- [x] 支持目录生成。
- [x] 支持标题层级。
- [x] 支持页眉页脚。
- [x] 支持页码。
- [x] 支持表格。
- [x] 支持附件清单。
- [x] 支持签章位置占位。
- [x] 支持商务投标文件分册。
- [x] 支持技术投标文件分册。
- [x] 支持资格审查文件分册。
- [x] 支持按招标要求设置字体字号。
- [x] 支持按招标要求设置页边距。
- [x] 支持按招标要求设置行距。
- [x] 支持按招标要求设置文件命名。
- [x] 必须 `.doc` 时，通过 LibreOffice 从 `.docx` 转 `.doc`。
- [x] 转换失败时保留 `.docx` 并提示人工处理。

**验收标准：**

- [x] 能下载 Word 文件。
- [x] Word 文件结构符合解析到的格式要求。
- [x] 支持多个分册输出。
- [x] `.doc` 兼容转换有明确状态。

## Phase 9: 投标文件审查

**目标：** 在导出前检查投标文件是否覆盖关键约束，并生成审查报告。

- [x] 否决项覆盖检查。
- [x] 资格要求覆盖检查。
- [x] 业绩要求覆盖检查。
- [x] 项目管理团队要求覆盖检查。
- [x] 技术要求覆盖检查。
- [x] 评分项覆盖检查。
- [x] 特殊要求覆盖检查。
- [x] 格式要求覆盖检查。
- [x] 文件组成检查。
- [x] 章节顺序检查。
- [x] 附件缺失检查。
- [x] 签章位置检查。
- [x] 页码/目录检查。
- [x] 企业名称一致性检查。
- [x] 资质证书一致性检查。
- [x] 人员证书一致性检查。
- [x] 业绩信息一致性检查。
- [x] 生成审查报告。
- [x] P0/P1 问题阻断最终导出。
- [x] P2/P3 问题提示但不阻断。

**验收标准：**

- [x] 未覆盖硬约束不得导出最终版。
- [x] 缺失资料生成补充清单。
- [x] 审查报告可下载。
- [x] 每个审查问题能定位到约束或章节。

## Phase 10: 最终交付包

**目标：** 一键生成完整投标交付包。

- [x] 生成最终 Word 文件。
- [x] 生成分册 Word 文件。
- [x] 生成审查报告。
- [x] 生成约束响应矩阵。
- [x] 生成资料缺失清单。
- [x] 生成来源追溯清单。
- [x] 生成人工确认记录。
- [x] 可选生成 `.doc` 文件。
- [x] 打包 ZIP 下载。
- [x] 记录交付包版本。
- [x] 记录交付包生成时间。
- [x] 记录交付包生成用户。
- [x] 支持重新生成。

**验收标准：**

- [x] 一键生成最终交付包。
- [x] 所有交付物可追溯到招标文件要求。
- [x] 报价文件不生成、不修改、不参与审查。
- [x] 交付包版本可回溯。

## Implementation Waves

### Wave 1: 最小闭环

- [x] Phase 1 上传与文件识别。
- [x] Phase 2 文本与表格解析。
- [x] Phase 3 核心约束抽取。
- [x] Phase 4 约束入库与人工确认。
- [x] Phase 8 基础 `.docx` 输出。

**完成标志：**

- [ ] 上传真实国网 ZIP 样例后能抽取约束。
- [ ] 上传 PDF 样例后能抽取约束。
- [x] 约束可确认。
- [x] 可生成基础 Word 草稿。

### Wave 2: 编写增强

- [x] Phase 5 知识库匹配。
- [x] Phase 6 投标文件结构规划。
- [x] Phase 7 AI 编写投标内容。
- [x] Phase 8 Word 格式增强。

**完成标志：**

- [x] 业绩、人员、资质可与知识库匹配。
- [x] 可按招标文件目录生成章节。
- [x] 可生成分册 Word 文件。

### Wave 3: 交付质量

- [x] Phase 9 投标文件审查。
- [x] Phase 10 最终交付包。
- [x] `.doc` 兼容输出。
- [x] 响应矩阵和来源追溯完善。

**完成标志：**

- [x] 最终包可下载。
- [x] 审查报告可下载。
- [x] 未覆盖硬约束会阻断导出。
- [x] 输出可追溯、可复核、可重新生成。

## Data Model To-Do

- [x] 新增 `tender_document` 表。
- [x] 新增 `tender_document_file` 表。
- [x] 新增 `source_chunk` 表。
- [x] 新增或扩展 `project_requirement` 约束字段。
- [x] 新增 `requirement_match` 表。
- [x] 新增 `bid_outline` 表。
- [x] 新增 `bid_chapter` 表。
- [x] 新增 `bid_review_issue` 表。
- [x] 新增 `bid_delivery_package` 表。
- [x] 为来源定位字段建立索引。
- [x] 为项目、分类、确认状态建立索引。

## API To-Do

- [x] `POST /api/projects/{project_id}/tender-documents`
- [x] `GET /api/projects/{project_id}/tender-documents`
- [x] `GET /api/tender-documents/{id}`
- [x] `GET /api/tender-documents/{id}/files`
- [x] `POST /api/tender-documents/{id}/parse`
- [x] `GET /api/tender-documents/{id}/parse-status`
- [x] `GET /api/tender-documents/{id}/source-chunks`
- [x] `POST /api/tender-documents/{id}/extract-constraints`
- [x] `GET /api/projects/{project_id}/requirements`
- [x] `PATCH /api/requirements/{id}`
- [x] `POST /api/requirements/{id}/confirm`
- [x] `POST /api/requirements/{id}/reject`
- [x] `POST /api/projects/{project_id}/match-requirements`
- [x] `POST /api/projects/{project_id}/bid-outline`
- [x] `POST /api/projects/{project_id}/bid-chapters/{chapter_id}/generate`
- [x] `POST /api/projects/{project_id}/bid-review`
- [x] `POST /api/projects/{project_id}/delivery-package`
- [x] `GET /api/delivery-packages/{id}/download`

## Frontend To-Do

- [x] 上传页支持 ZIP/PDF。
- [x] 上传页展示解包文件树。
- [x] 文件分类可编辑。
- [x] 解析状态可视化。
- [x] 解析结果按文件查看。
- [x] 约束确认页按分类筛选。
- [x] 约束确认页支持来源预览。
- [x] 约束确认页支持编辑/确认/驳回。
- [x] 业绩匹配页。
- [x] 项目团队匹配页。
- [x] 投标目录规划页。
- [x] 章节编写页。
- [x] Word 预览/下载页。
- [x] 审查报告页。
- [x] 最终交付包页。

## Test And Acceptance To-Do

- [ ] 使用真实 ZIP 样例（本地放置于 `docs/国网招标文件/` 或通过 `SGCC_TENDER_SAMPLE_ZIP` 环境变量指定）。
- [ ] 准备至少 1 个 PDF 招标文件样例。
- [ ] ZIP 解包测试。
- [ ] GBK 文件名测试。
- [ ] 内层 ZIP 递归测试。
- [x] `.docx` 解析测试。
- [x] `.xlsx` 解析测试。
- [x] `.doc` 转换测试。
- [ ] `.wps` 转换失败降级测试。
- [ ] PDF 文本解析测试。
- [ ] 扫描型 PDF OCR 测试。
- [x] 约束抽取 schema 测试。
- [x] 报价忽略测试。
- [x] 来源追溯测试。
- [x] 人工确认门禁测试。
- [x] Word 生成测试。
- [x] 最终交付包测试。
