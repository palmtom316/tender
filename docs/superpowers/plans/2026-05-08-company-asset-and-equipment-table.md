# 公司资产表 + 投标设备表 MVP Implementation Plan

**日期:** 2026-05-08

**状态:** 简化版计划，替代原 13 phase 全量实现计划。

**Spec:** `docs/superpowers/specs/2026-05-07-company-asset-and-equipment-table-design.md`

## 目标

首期目标不是一次性完成资产规则引擎，而是先把投标编制中最直接的价值闭环做出来：

1. 公司库能维护 4 类资产：车辆 / 施工机械 / 施工工器具 / 安全设施设备及器具。
2. 项目中能从公司资产库手动选择设备，形成投标主要施工设备表。
3. 确认时保存一份快照，避免后续公司库变更影响历史投标。
4. 同一份设备清单可以导出 Excel，并通过模板锚点插入技术标或商务标 DOCX。

## 首期明确不做

这些能力有价值，但不进入 MVP，避免把公司资产表做成过重的平台工程：

- 不做 `equipment_requirement` 招标约束 predicate 映射。
- 不做覆盖度计算、自动排除、自动重筛和 diff 合并。
- 不做强制纳入风险理由流程。
- 不新增 `equipment_selection` 工作流状态。
- 不接入符合性检查 P0/P1 阻断 `final_layout`。
- 不做核心槽 + 历史累积附件的完整附件体系。
- 不做 AI 自动抽取设备要求。

## 设计原则

- **人工确认优先:** 首期允许系统辅助筛选，但不自动替用户做不可解释的判断。
- **模板驱动插表:** 商务标和技术标都支持插入设备表，但只有模板存在锚点时才插入。
- **同源输出:** 页面预览、DOCX 插表、Excel 附件必须读取同一份已确认快照。
- **低侵入集成:** 先少碰工作流、审查引擎和终稿打包链路，把功能控制在资产库、项目设备清单和导出服务内。
- **保留扩展口:** 表结构和快照模型要能承接后续自动筛选、覆盖度和合规检查。

## MVP 范围

### 公司资产库

- 在公司资料库下增加 `公司资产` 区域。
- 4 个 tab：车辆 / 施工机械 / 施工工器具 / 安全设施设备及器具。
- 支持新增、编辑、删除或退役。
- 支持搜索、状态筛选、有效期 badge。
- 每类资产首期只展示公共字段 + 少量关键特化字段。

### 项目设备清单

- 在投标编制侧增加设备清单页面或面板。
- 用户按资产类型、关键词、状态、有效期筛选资产。
- 用户用 checkbox 手动选择资产。
- 已选清单支持排序、移除、填写 `intended_role`。
- 点击确认后写入快照，后续导出读取快照。

### 输出

- Excel：导出 `<项目编号>_主要施工设备一览表.xlsx`，包含 4 个 sheet。
- DOCX：支持以下锚点，技术标或商务标模板中出现哪个就替换哪个：

```text
{{equipment_table:vehicle}}
{{equipment_table:machine}}
{{equipment_table:tool}}
{{equipment_table:safety}}
```

- 没有锚点时跳过，不报错，不强行插入。
- 某类无数据时输出表头 + `无` 占位行。

## 数据模型

### `company_asset`

公司资产主表保留长期可扩展结构，但首期只强依赖少量字段。

```sql
CREATE TABLE company_asset (
  id UUID PRIMARY KEY,
  library_company_id UUID NOT NULL REFERENCES library_company(id) ON DELETE CASCADE,
  asset_type TEXT NOT NULL CHECK (asset_type IN ('vehicle','machine','tool','safety')),
  name TEXT NOT NULL,
  spec_model TEXT,
  serial_no TEXT,
  manufacturer TEXT,
  quantity NUMERIC(12,2) NOT NULL DEFAULT 1,
  unit TEXT NOT NULL,
  ownership TEXT NOT NULL CHECK (ownership IN ('self','leased','third_party')),
  acquired_at DATE,
  expires_at DATE,
  technical_condition TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','maintenance','retired')),
  location TEXT,
  extras JSONB NOT NULL DEFAULT '{}'::jsonb,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

索引：

```sql
CREATE INDEX idx_company_asset_lib_type ON company_asset(library_company_id, asset_type);
CREATE INDEX idx_company_asset_expires ON company_asset(expires_at);
CREATE INDEX idx_company_asset_status ON company_asset(status);
```

### `company_asset_attachment`

首期只做简单附件挂载，不实现核心槽唯一约束和历史累积区 UI。保留 `attachment_kind` 以便以后升级。

```sql
CREATE TABLE company_asset_attachment (
  id UUID PRIMARY KEY,
  asset_id UUID NOT NULL REFERENCES company_asset(id) ON DELETE CASCADE,
  evidence_asset_id UUID NOT NULL REFERENCES evidence_asset(id) ON DELETE CASCADE,
  attachment_kind TEXT NOT NULL DEFAULT 'general',
  effective_at DATE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `project_equipment_selection`

首期采用“引用 + 确认快照”。不做 DB trigger，先由应用层控制确认后写入快照。

```sql
CREATE TABLE project_equipment_selection (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  asset_id UUID NOT NULL REFERENCES company_asset(id) ON DELETE RESTRICT,
  asset_type TEXT NOT NULL,
  intended_role TEXT,
  snapshot_json JSONB,
  display_order INT NOT NULL DEFAULT 0,
  confirmed BOOLEAN NOT NULL DEFAULT FALSE,
  confirmed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

索引：

```sql
CREATE INDEX idx_pes_project ON project_equipment_selection(project_id, asset_type, display_order);
```

## 字段策略

首期字段要足够生成投标设备表，但不要把所有专业字段一次性做满。

### 公共字段

- 名称 `name`
- 规格型号 `spec_model`
- 编号 / 车牌 / 出厂编号 `serial_no`
- 厂家 `manufacturer`
- 数量 `quantity`
- 单位 `unit`
- 所有权 `ownership`
- 购置日期 `acquired_at`
- 有效期 `expires_at`
- 技术状况 `technical_condition`
- 状态 `status`
- 存放地点 `location`
- 备注 `notes`

### 类型特化字段

车辆：

- `vehicle_type`
- `technical_grade`

施工机械：

- `machine_category`
- `capacity`
- `is_special_equipment`

施工工器具：

- `tool_category`
- `voltage_level`
- `last_inspection_at`

安全设施设备及器具：

- `safety_category`
- `protection_standard`
- `applicable_work`

其余字段留到 v2，不进入首期表单。

## API

### 公司资产

```text
GET    /api/master-data/library-companies/{library_company_id}/assets?asset_type=&q=&status=
POST   /api/master-data/library-companies/{library_company_id}/assets
PUT    /api/master-data/assets/{asset_id}
DELETE /api/master-data/assets/{asset_id}
POST   /api/master-data/assets/{asset_id}/retire
```

### 项目设备清单

```text
GET    /api/projects/{project_id}/equipment/assets?asset_type=&q=&status=&valid_only=
GET    /api/projects/{project_id}/equipment/selections
POST   /api/projects/{project_id}/equipment/selections
PUT    /api/projects/{project_id}/equipment/selections/{selection_id}
DELETE /api/projects/{project_id}/equipment/selections/{selection_id}
POST   /api/projects/{project_id}/equipment/selections/confirm
```

### 输出

```text
GET    /api/projects/{project_id}/equipment/preview
GET    /api/projects/{project_id}/equipment/attachment-xlsx
```

DOCX 插表走现有商务标/技术标导出链路，不单独暴露新接口。

## 前端文件

### 新建

```text
frontend/src/modules/database/schemas/assetTypeSchemas.ts
frontend/src/modules/database/components/CompanyAssetSection.tsx
frontend/src/modules/database/components/asset/AssetTable.tsx
frontend/src/modules/database/components/asset/AssetFormDrawer.tsx
frontend/src/modules/database/components/asset/expiryBadge.ts
frontend/src/modules/authoring/EquipmentSelectionWorkbench.tsx
frontend/src/modules/authoring/equipment/EquipmentAssetPicker.tsx
frontend/src/modules/authoring/equipment/EquipmentSelectedTable.tsx
frontend/src/modules/authoring/equipment/EquipmentPreviewTable.tsx
```

### 修改

```text
frontend/src/lib/api.ts
frontend/src/modules/database/components/CompanyLibraryWorkbench.tsx
```

如果 `CompanyLibraryWorkbench.tsx` 已经过大，可以只做最小拆分：把资产区域抽成 `CompanyAssetSection`，不要顺手重构公司基础资料和公司业绩。

## 后端文件

### 新建

```text
backend/tender_backend/db/alembic/versions/0040_company_assets_mvp.py
backend/tender_backend/db/repositories/company_asset_repo.py
backend/tender_backend/db/repositories/project_equipment_selection_repo.py
backend/tender_backend/api/master_data_assets.py
backend/tender_backend/api/equipment_selection.py
backend/tender_backend/services/asset_schema.py
backend/tender_backend/services/export_service/equipment_table_renderer.py
backend/tender_backend/services/export_service/equipment_table_injector.py
backend/tests/integration/test_company_asset_api.py
backend/tests/integration/test_equipment_selection_api.py
backend/tests/integration/test_equipment_table_export.py
```

### 修改

```text
backend/tender_backend/main.py
backend/tender_backend/api/master_data.py
backend/tender_backend/services/export_service/docx_exporter.py
```

不要在 MVP 修改：

```text
backend/tender_backend/services/review_service/review_engine.py
backend/tender_backend/services/project_setup_service.py
backend/tender_backend/services/tender_constraint_service.py
backend/tender_backend/services/delivery_package.py
```

## 实施阶段

### Phase 1: 数据库和后端资产 CRUD

目标：公司资产能通过 API 增删改查。

任务：

- 新建 migration：`company_asset`、`company_asset_attachment`、`project_equipment_selection`。
- 新建 `asset_schema.py`，定义资产类型、所有权、状态枚举和轻量校验。
- 新建 `company_asset_repo.py`。
- 新建 `master_data_assets.py` router。
- 在主 API 中注册 router。
- 测试资产创建、查询、更新、删除、退役。

验收：

- 能为某个 `library_company` 创建 4 类资产。
- 能按 `asset_type`、`status`、关键词查询。
- 被项目引用的资产删除失败，提示改为退役。

### Phase 2: 公司资产 UI

目标：公司库内可以实际维护资产台账。

任务：

- 新建 `assetTypeSchemas.ts`，只包含 MVP 字段。
- 新建 `CompanyAssetSection`。
- 新建 `AssetTable`，支持 tab、搜索、状态筛选、有效期 badge。
- 新建 `AssetFormDrawer`，按 schema 渲染公共字段和少量特化字段。
- 接入 `frontend/src/lib/api.ts`。

验收：

- 公司资料库下能看到 `公司资产` 区域。
- 4 类 tab 能切换。
- 新增、编辑、退役能落库并刷新表格。
- 表格在窄屏不出现按钮和文本重叠。

### Phase 3: 项目设备清单选择

目标：项目中可以从公司资产库手动选择设备并确认快照。

任务：

- 新建 `project_equipment_selection_repo.py`。
- 新建 `equipment_selection.py` router。
- `GET /equipment/assets` 返回可选公司资产，支持基础筛选。
- `POST /equipment/selections` 添加资产到项目清单。
- `PUT /equipment/selections/{id}` 更新用途和排序。
- `POST /equipment/selections/confirm` 根据当前资产写入 `snapshot_json`，设置 `confirmed=true`。
- 新建前端 `EquipmentSelectionWorkbench`。

验收：

- 用户能按类型搜索资产并勾选加入项目。
- 已选清单能移除、排序、填写用途。
- 确认后每行都有 `snapshot_json`。
- 确认后公司资产再修改，不影响该项目预览数据。

### Phase 4: Excel 和预览

目标：同一份快照可以预览并导出 Excel。

任务：

- 新建 `EquipmentTableRenderer`。
- `render_equipment_preview(project_id)` 返回 4 类结构化表格数据。
- `render_attachment_xlsx(project_id)` 生成 4 sheet Excel。
- 新增 `/equipment/preview` 和 `/equipment/attachment-xlsx`。
- 前端增加预览表和下载按钮。

验收：

- 未确认时提示先确认设备清单。
- 已确认后预览显示 4 类表格。
- Excel 包含 4 个 sheet：车辆、施工机械、施工工器具、安全设施设备及器具。
- Excel 与页面预览数据一致。

### Phase 5: 商务标 / 技术标 DOCX 锚点插表

目标：商务标和技术标模板中出现设备表锚点时，导出 DOCX 自动替换为 Word 原生表格。

任务：

- 新建 `equipment_table_injector.py`。
- 支持扫描并替换：

```text
{{equipment_table:vehicle}}
{{equipment_table:machine}}
{{equipment_table:tool}}
{{equipment_table:safety}}
```

- 在现有 DOCX 导出流程末尾调用 injector。
- 保持模板兼容：没有锚点则不处理。
- 商务标和技术标走同一套锚点规则。

验收：

- 技术标模板含锚点时，导出 DOCX 出现原生表格。
- 商务标模板含锚点时，导出 DOCX 出现原生表格。
- 模板没有锚点时，导出结果不变。
- 某类无数据时输出表头 + `无`。

## 测试策略

首期测试聚焦主链路，不追求规则引擎覆盖。

### 后端

- 资产 CRUD API 集成测试。
- 项目设备选择 API 集成测试。
- 确认快照测试：确认后公司资产变更不影响预览。
- Excel 导出测试：4 sheet、表头、数据行。
- DOCX 插表测试：有锚点替换，无锚点跳过。

### 前端

- `assetTypeSchemas` 字段基本自洽测试。
- `AssetFormDrawer` 基础渲染和提交测试。
- `EquipmentSelectionWorkbench` 选择、移除、确认流程测试。

### 手工验收

- 在公司库新增 1 辆车、1 台机械、1 件工器具、1 件安全设施。
- 在项目设备清单中选中它们并确认。
- 下载 Excel，检查 4 sheet。
- 在技术标模板放 4 个锚点，导出 DOCX 检查表格。
- 在商务标模板放其中 1 个锚点，导出 DOCX 检查只插入对应表格。

## 后续阶段

### v2: 基础自动筛选

- 根据 `status=active`、`expires_at`、`ownership` 做候选提示。
- 显示“可能不适用”的弱提醒，但不阻断用户。
- 增加“只看有效资产”“只看自有资产”等快捷筛选。

### v3: 招标要求覆盖度

- 扩展 `tender_constraint` 支持 `equipment_requirement`。
- 用户在约束确认工作台手工标注 `asset_type`、`predicate`、`min_quantity`。
- 项目设备清单显示覆盖度。
- 不足时提醒，但是否阻断另行决定。

### v4: 合规检查和工作流闸门

- 接入 `review_engine`，扫描过期资产、缺附件、覆盖度不足。
- 评估是否新增 `equipment_selection` 工作流状态。
- 评估是否在 `final_layout` 前阻断 P0。

### v5: 附件体系增强

- 恢复核心槽 + 历史累积区。
- 核心附件参与快照。
- 后续可对行驶证、年检、试验报告做缺失检查。

## 风险和注意事项

- `extras` 首期由前端 schema 控制，后端只做 JSON 对象校验。若后续出现脏数据，再考虑同步 schema 到后端。
- DOCX 插表要避免破坏既有商务标/技术标导出流程。没有锚点必须保持完全兼容。
- `snapshot_json` 是投标历史一致性的关键，确认动作必须明确，不能在预览或导出时偷偷刷新。
- 商务标和技术标不要默认强制插入设备表。模板锚点才是唯一插入依据。

## 最小交付顺序

1. 资产 CRUD API。
2. 公司资产 UI。
3. 项目设备选择和确认快照。
4. 预览 + Excel。
5. DOCX 锚点插表。

完成前 4 步即可形成可用 MVP；第 5 步把设备表直接进入商务标/技术标，作为首期增强一起交付。
