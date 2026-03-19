# 标准规范批量上传与串行流水线处理设计

## 背景

当前规范规程处理流程是单个 PDF 上传，上传后由用户手动触发处理。后端会为单个标准起一条后台线程，串行执行 OCR 与后续 AI 条款解析。该模型不支持批量上传，也没有显式的排队机制，无法满足多个标准文件自动排队处理的需求。

本设计将流程改为批量上传后自动入队，并通过两段单并发流水线完成处理：

- OCR 阶段全局同一时刻只处理 1 个 PDF 文件
- AI 解析阶段全局同一时刻只处理 1 个 OCR 输出文件
- 两个阶段彼此独立，因此允许形成流水线：文件 A 进入 AI 解析时，文件 B 可以开始 OCR

## 目标

- 支持一次上传多个标准 PDF
- 上传前必须逐条填写每个文件的规范编号与规范名称
- 上传后自动入队，无需手动点击“开始 AI 处理”
- 保证 OCR 单并发、AI 单并发
- 支持失败文件单独重试，不阻塞后续文件
- 前端可清晰展示排队、OCR、AI、完成、失败等状态

## 非目标

- 第一版不引入 Celery/Redis 等独立队列基础设施
- 第一版不做自动重试
- 第一版不支持从文件名自动解析规范编号或名称
- 第一版不做多实例部署下的跨实例协调优化

## 方案选择

### 备选方案

1. 仅复用 `standard.processing_status` 做状态轮询
2. 引入显式队列表 + 应用内调度器
3. 使用 Celery 两条队列与两类单并发 worker

### 结论

采用方案 2：引入显式队列表 `standard_processing_job`，由应用内调度器负责唤醒与认领任务。

原因：

- 能明确表达 OCR 与 AI 两段状态，避免单字段状态混杂
- 能精确保证 `OCR=1`、`AI=1` 的全局并发限制
- 不依赖新的外部基础设施，适合当前项目现状
- 失败重试、排队顺序、状态展示都更稳定

## 用户流程

### 批量上传

用户在“规范规程库”页面一次选择多个 PDF 文件。前端根据选择结果生成逐条编辑列表，每个文件一行，要求用户在提交前填写：

- `规范编号`，必填
- `规范名称`，必填
- `版本年份`，可选
- `专业类别`，可选

只有所有行的必填项都完整时，才允许提交。

### 自动排队处理

提交成功后，后端为每个文件创建：

- 文件记录
- 文档记录
- 标准记录
- 处理队列记录

并立即唤醒调度器开始处理。用户不再手动触发“开始 AI 处理”。

### 失败重试

若某文件 OCR 失败或 AI 失败，仅该文件进入失败状态。用户可在列表中对失败项执行“重新入队”：

- OCR 失败时，从 OCR 重新排队
- AI 失败时，仅 AI 重新排队，复用已有 OCR 结果

## 架构设计

### 核心组件

#### 1. 批量上传接口

负责接收多个 PDF 与对应元数据，校验请求，批量创建标准相关记录，并为每个标准写入一条处理队列任务。

#### 2. 处理队列表

新增 `standard_processing_job` 表，作为标准处理流水线的事实来源，记录 OCR 与 AI 两段状态、错误、时间戳与重试次数。

#### 3. 调度器

新增应用内调度器，采用幂等唤醒模型。调度器内部维护两个独立循环：

- `ocr_loop`：从队列表中认领最早的 OCR 待处理任务
- `ai_loop`：从队列表中认领最早的 AI 待处理任务

两个循环彼此独立，但各自全局单并发。

#### 4. 前端状态展示

规范卡片和详情页显示更细粒度的状态信息，包括 OCR 状态、AI 状态、总体处理状态和错误信息。前端轮询逻辑覆盖排队中和处理中状态。

## 数据模型

### 新增表：`standard_processing_job`

建议字段：

- `id`
- `standard_id`
- `document_id`
- `ocr_status`：`queued | running | completed | failed`
- `ocr_error`
- `ocr_started_at`
- `ocr_finished_at`
- `ocr_attempts`
- `ai_status`：`blocked | queued | running | completed | failed`
- `ai_error`
- `ai_started_at`
- `ai_finished_at`
- `ai_attempts`
- `created_at`
- `updated_at`

说明：

- `document_id` 冗余存储，便于调度执行时直接定位文档
- FIFO 可基于 `created_at` 排序，无需额外 `queue_order` 字段
- 每个 `standard` 对应 1 条队列表记录；重试更新原记录，不重复插入新记录

### 现有表：`standard`

保留 `processing_status` 作为面向前端的汇总状态字段，建议取值扩展为：

- `queued_ocr`
- `parsing`
- `queued_ai`
- `processing`
- `completed`
- `failed`

`error_message` 保留为当前最终失败信息或当前阶段错误摘要。

## 状态机设计

### 初始状态

上传成功后：

- `ocr_status = queued`
- `ai_status = blocked`
- `standard.processing_status = queued_ocr`

### OCR 阶段

调度器认领任务后：

- `ocr_status = running`
- `standard.processing_status = parsing`

OCR 成功后：

- `ocr_status = completed`
- `ai_status = queued`
- `standard.processing_status = queued_ai`

OCR 失败后：

- `ocr_status = failed`
- `ai_status = blocked`
- `standard.processing_status = failed`

### AI 阶段

调度器认领任务后：

- `ai_status = running`
- `standard.processing_status = processing`

AI 成功后：

- `ai_status = completed`
- `standard.processing_status = completed`

AI 失败后：

- `ai_status = failed`
- `standard.processing_status = failed`

## 调度与并发模型

### 单并发约束

- 任意时刻只能有 1 个 `ocr_status = running`
- 任意时刻只能有 1 个 `ai_status = running`

### 流水线行为

允许以下并行场景：

- 文件 A 正在执行 AI 解析
- 文件 B 同时执行 OCR

不允许以下情况：

- 两个文件同时 OCR
- 两个文件同时 AI 解析

### 任务认领

调度器需通过数据库原子更新认领任务，确保同一阶段不会重复认领同一条任务。认领规则：

- OCR：选择最早的 `ocr_status = queued`
- AI：选择最早的 `ai_status = queued`

认领后立刻更新为 `running` 并写入开始时间。

### 崩溃恢复

应用启动时或调度器唤醒时，检查长时间停留在 `running` 的任务：

- 第一版按超时回收为 `queued`
- 对应开始时间保留，错误信息写明是崩溃恢复回收

这样即使进程异常退出，也不会让队列永久卡死。

## 后端接口设计

### `POST /standards/upload`

改为批量上传接口，接收：

- 多个 PDF 文件
- 对应的逐条标准元数据

响应返回本次创建的标准列表，每条包含：

- `id`
- `standard_code`
- `standard_name`
- `document_id`
- `processing_status`
- `ocr_status`
- `ai_status`

接口职责：

- 校验文件数量与元数据数量一致
- 校验每一条元数据的必填项
- 批量创建文件、文档、标准、队列记录
- 成功后唤醒调度器

### `GET /standards`

扩展列表返回字段：

- `processing_status`
- `ocr_status`
- `ai_status`
- `error_message`
- `queue_position`，可选

### `GET /standards/{standard_id}`

扩展详情返回字段：

- `processing_status`
- `ocr_status`
- `ai_status`
- `error_message`
- `ocr_started_at`
- `ocr_finished_at`
- `ai_started_at`
- `ai_finished_at`

### `POST /standards/{standard_id}/process`

保留接口，但语义改为“失败后重新入队”：

- 若 OCR 失败，则重置为 OCR 待处理
- 若 AI 失败且 OCR 已完成，则仅重置 AI 待处理
- 若任务仍在排队或处理中，则返回冲突错误

该接口不再作为新上传标准的主入口。

## 前端设计

### 上传区

将现有单文件表单改为批量上传编辑器：

- 选择多个 PDF 后生成逐条行项目
- 每行展示文件名
- 每行提供 `规范编号`、`规范名称`、`版本年份`、`专业类别` 输入框
- 支持删除某一行
- 所有行校验通过后才能提交

### 列表卡片

卡片显示：

- 规范编号
- 规范名称
- 条款数
- 汇总状态标签
- 阶段状态提示，例如“OCR 排队中”“AI 排队中”“OCR 处理中”“AI 处理中”

按钮规则：

- 移除“开始 AI 处理”
- `failed` 显示“重新入队”
- 其他状态不提供手动开始按钮

### 轮询

前端轮询条件扩展为以下任一状态存在时持续轮询：

- `queued_ocr`
- `parsing`
- `queued_ai`
- `processing`

轮询目标仍以 `GET /standards` 为主，详情页可按需补充读取单条状态。

## 错误处理

### 上传阶段

- 文件数与元数据数不一致时拒绝请求
- 任意标准缺少必填字段时拒绝请求
- 单次请求中的数据库写入需尽量保证一致性，避免出现半成功状态

### OCR 阶段

- OCR 失败仅影响当前文件
- 错误信息写入 `ocr_error` 和 `standard.error_message`
- 调度器继续推进后续任务

### AI 阶段

- AI 失败仅影响当前文件
- 错误信息写入 `ai_error` 和 `standard.error_message`
- 不重复跑 OCR

## 测试策略

### 后端测试

- 迁移测试：新增队列表结构存在且字段正确
- 仓储测试：任务创建、认领、状态流转、失败重置
- 接口测试：批量上传成功、校验失败、重试接口行为
- 调度测试：
  - OCR 全局仅认领 1 条
  - AI 全局仅认领 1 条
  - OCR 与 AI 可同时各跑 1 条
  - OCR 成功后推进 AI 排队
  - AI 失败后只重试 AI
  - 崩溃恢复能回收卡死任务

### 前端测试

- 批量选择文件后正确生成编辑行
- 未填写完整时禁用提交
- 提交成功后清空表单并刷新列表
- 列表正确展示排队/处理中/失败状态
- 失败项显示“重新入队”

## 实施注意点

- 尽量复用现有 `norm_processor` 中 OCR 与 AI 解析逻辑，但将整条串行流程拆成显式的两段 worker 调用
- 避免继续沿用“每触发一次起一条后台线程”的模型；调度器应是长期存在、可幂等唤醒的单实例组件
- 保持第一版边界清晰：先做稳定的单进程 DB 队列调度，不提前设计分布式复杂度

## 验收标准

- 用户可一次上传多个 PDF
- 每个文件必须在上传前逐条填写规范编号与规范名称
- 上传后文件自动进入处理队列
- 全局始终满足：OCR 单并发、AI 单并发
- 允许 OCR 与 AI 流水线并行
- 文件失败不会阻塞队列中其他文件
- 失败文件支持重新入队，且 AI 失败时不会重复 OCR
- 前端可清晰展示队列状态与处理进度
