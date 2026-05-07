# 公司资产管理 + 投标主要施工设备表自动生成 — 设计文档

**日期:** 2026-05-07

**目标:** 在公司库下增加"公司资产"模块（4 类：车辆 / 施工机械 / 施工工器具 / 安全设施设备及器具），用表单录入 + 4 tab 表格管理；投标编制阶段从公司库按招标要求自动筛选已选清单，确认冻结后生成"投标主要施工设备表"，输出为技术标章节嵌入表格 + Excel 独立附件。

**适用范围:** tender 当前 4 类电力施工业务线（变电劳务及专业分包 / 10kV 项目 / 电力运维 / 用户高低压供配电）。

---

## 0. 关键设计决策（已与用户确认）

| 决策项 | 选择 | 来源 |
|---|---|---|
| 投标设备表输出形态 | 技术标章节嵌入 + Excel 独立附件，双输出同源 | Q1 → C |
| 投标时设备选择策略 | 系统按规则自动筛选 + 用户增删确认 | Q2 → B |
| 投标已选清单存储模型 | 引用 + 关键字段冻结到 JSONB（混合）| Q3 → C |
| 首期范围 | 4 类资产同时上线，全字段一次到位 | Q4 → A |
| Schema 维护位置 | 前端 TS 配置 + 后端轻量基线（asset_type 合法 + extras JSON 结构 + 关键字段强类型）| Q5 → A |
| 附件结构 | 核心槽（按类型预定义）+ 累积附件区开放 | Q6 → C |
| 自动筛选规则 | 基础三条（合规硬性）+ 招标显式映射（硬性）+ 业务线匹配（软筛 chip）| Q7 → D |
| 设备表列模板 | 4 类各自一张子表，技术标分 4 子段、Excel 4 sheet | Q8 → B |

---

## 1. 数据层

### 1.1 公司库资产主表

```sql
CREATE TABLE company_asset (
  id              UUID PRIMARY KEY,
  library_company_id UUID NOT NULL REFERENCES library_company(id) ON DELETE CASCADE,
  asset_type      TEXT NOT NULL CHECK (asset_type IN ('vehicle','machine','tool','safety')),
  name            TEXT NOT NULL,
  spec_model      TEXT,
  serial_no       TEXT,                    -- 出厂编号 / 车牌号 / 设备编码
  manufacturer    TEXT,
  quantity        NUMERIC(12,2) NOT NULL DEFAULT 1,
  unit            TEXT NOT NULL,           -- 辆 / 台 / 件 / 把 / 付
  ownership       TEXT NOT NULL CHECK (ownership IN ('self','leased','third_party')),
  acquired_at     DATE,                    -- 购置 / 获取日期
  expires_at      DATE,                    -- 检验/年检/试验有效期(月精度,统一字段,投标筛选用)
  technical_condition TEXT,                -- 完好 / 良好 / 一般
  status          TEXT NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active','maintenance','retired')),
  location        TEXT,
  extras          JSONB NOT NULL DEFAULT '{}'::jsonb,    -- 类型特化字段
  notes           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_company_asset_lib_type ON company_asset(library_company_id, asset_type);
CREATE INDEX idx_company_asset_expires  ON company_asset(expires_at);
CREATE INDEX idx_company_asset_status   ON company_asset(status);
```

`expires_at`、`technical_condition`、`unit`、`ownership` 提为顶层列：投标设备表必出现且废标扫描会查。`extras` 仅装类型特化字段（电压等级 / 防护等级 / 适用工种 / 是否绝缘类等）。

### 1.2 资产附件关联（核心槽 + 累积区）

```sql
CREATE TABLE company_asset_attachment (
  id              UUID PRIMARY KEY,
  asset_id        UUID NOT NULL REFERENCES company_asset(id) ON DELETE CASCADE,
  evidence_asset_id UUID NOT NULL REFERENCES evidence_asset(id) ON DELETE CASCADE,
  attachment_kind TEXT NOT NULL,           -- driving_license / annual_inspection / insurance / certificate / inspection_report ...
  slot_role       TEXT NOT NULL CHECK (slot_role IN ('core','archive')),
  effective_at    DATE,                    -- 该附件本身的发证/检定日期
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_caa_asset ON company_asset_attachment(asset_id);
CREATE UNIQUE INDEX uq_caa_core_slot ON company_asset_attachment(asset_id, attachment_kind)
  WHERE slot_role = 'core';                -- 同一类型同一时间只挂一份核心槽
```

核心槽（slot_role='core'）保证唯一，导出和符合性扫描读核心槽；累积区（slot_role='archive'）按 effective_at 排序，UI 折叠。

### 1.3 投标侧已选设备表（引用 + 冻结）

```sql
CREATE TABLE project_equipment_selection (
  id              UUID PRIMARY KEY,
  project_id      UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  asset_id        UUID NOT NULL REFERENCES company_asset(id) ON DELETE RESTRICT,
                                           -- RESTRICT 防止公司库删资产污染历史投标
  asset_type      TEXT NOT NULL,           -- 冗余存,便于按类型导出
  selection_reason TEXT,                   -- 强制纳入未通过筛选时的理由
  exclusion_overridden BOOLEAN NOT NULL DEFAULT FALSE,
  intended_role   TEXT,                    -- 用途/拟用阶段(投标设备表第 12 列)
  frozen_snapshot JSONB NOT NULL,          -- 冻结字段:name, spec_model, quantity, unit,
                                           -- ownership, manufacturer, serial_no,
                                           -- acquired_at, expires_at, technical_condition,
                                           -- core_attachment_ids[], hash, extras
  display_order   INT NOT NULL DEFAULT 0,
  frozen          BOOLEAN NOT NULL DEFAULT FALSE,
  frozen_at       TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_pes_project ON project_equipment_selection(project_id, asset_type, display_order);

-- 冻结后字段不可改:由触发器或应用层校验兜底
```

frozen=FALSE 阶段：`frozen_snapshot` 跟随 library_company 字段最新值刷新；frozen=TRUE 后锁定字段、附件 hash、core_attachment_ids，库被改不影响该投标。

---

## 2. 前端 Schema 注册（核心配置）

`frontend/src/modules/database/schemas/assetTypeSchemas.ts`：

```ts
export type AssetTypeKey = "vehicle" | "machine" | "tool" | "safety";
export type ExtraFieldType = "text" | "number" | "date" | "select" | "boolean";

export type ExtraField = {
  key: string;
  label: string;
  type: ExtraFieldType;
  required?: boolean;
  options?: { value: string; label: string }[];
  hint?: string;
  computed_from?: string;            // 派生字段说明
};

export type CoreAttachmentSlot = {
  kind: string;
  label: string;
  required: boolean;
  determines_expires_at?: boolean;   // 该附件有效期回填 asset.expires_at
};

export type SoftFilterChip = {
  key: string;
  label: string;
  predicate: (asset: Asset, ctx: BidContext) => boolean;
};

export type ExportColumn = {
  key: string;
  label: string;
  source: "field" | "extra" | "computed";
  source_key?: string;
  formatter?: "date" | "ownership" | "tech_condition" | "voltage";
};

export type AssetTypeSchema = {
  key: AssetTypeKey;
  label: string;
  unit_default: string;
  core_attachments: CoreAttachmentSlot[];
  archive_attachment_kinds: { kind: string; label: string }[];
  extras: ExtraField[];
  soft_filter_chips: SoftFilterChip[];
  export_columns: ExportColumn[];
};

export const ASSET_TYPE_SCHEMAS: Record<AssetTypeKey, AssetTypeSchema> = { /* ... */ };
```

后端只导出 `ASSET_TYPE_KEYS` 常量与 `validate_common_fields()` 基线校验（asset_type 合法 + 必填顶层字段 + extras 是合法 JSON 对象）。类型特化字段不强类型校验。

### 2.1 4 类字段清单概要

#### 车辆 (vehicle) — 单位默认 "辆"

**Extras**: vehicle_type (select 必填; 货车 / 工程车 / 抢修车 / 斗臂车 / 高空作业车 / 起重车 / 普通乘用车 / 其他) · driving_license_no (text 必填) · insurance_expires_at (date) · technical_grade (select; 优 / 良 / 合格 / 不合格)

**Core attachments (3 槽)**: driving_license (行驶证, 必填) · annual_inspection (年检报告, 必填, determines_expires_at=true) · insurance (保险单)

**Archive kinds**: maintenance_record / historical_inspection / historical_insurance

**Soft filter chips**: 仅自有 / 仅斗臂车 / 仅 10kV 适用 / 一年内购置

#### 施工机械 (machine) — 单位默认 "台"

**Extras**: machine_category (select 必填) · capacity_value (text) · capacity_unit (select; t/kW/kVA/m³/m/kN) · is_special_equipment (boolean) · inspection_required (boolean 必填) · last_inspection_at (date) · inspection_period_months (number) · inspection_authority (text)

**Core attachments (3 槽)**: factory_certificate (出厂合格证, 必填) · inspection_report (本周期检定报告, determines_expires_at=true) · purchase_voucher (购置发票/租赁合同, 必填)

**Archive kinds**: historical_inspection / maintenance_record

**Soft filter chips**: 仅自有 / 仅特种设备 / 检定有效期 ≥30 天

#### 施工工器具 (tool) — 单位默认 "件"

**Extras**: tool_category (select 必填; 绝缘类 / 接地类 / 验电类 / 登高类 / 通用工具 / 其他) · voltage_level (select; 0.4kV / 10kV / 20kV / 35kV / 110kV / 220kV / 500kV / N/A; 绝缘/接地/验电类必填) · inspection_period_months (number 必填; 6 或 12) · last_inspection_at (date 必填) · inspection_authority (text) · batch_no (text)

> `expires_at` = `last_inspection_at + inspection_period_months`，前端派生显示但允许覆盖。

**Core attachments (2 槽)**: inspection_report (本周期试验报告, 必填, determines_expires_at=true) · factory_certificate (出厂合格证)

**Archive kinds**: historical_inspection (历年试验报告)

**Soft filter chips**: 仅 10kV / 仅绝缘类 / 试验有效期 ≥30 天 / 仅自有

#### 安全设施设备及器具 (safety)

**Extras**: safety_category (select 必填) · protection_standard (text) · applicable_work (text) · mandatory_retirement_months (number) · production_batch (text)

> 若填 mandatory_retirement_months 且 acquired_at 存在，`expires_at` 自动 = acquired_at + mandatory_retirement_months。

**Core attachments (2 槽)**: factory_certificate (出厂/检验合格证, 必填) · inspection_report (周期检验报告; determines_expires_at=true)

**Archive kinds**: batch_acceptance (批量验收) / retirement_record (报废处理)

**Soft filter chips**: 仅 PPE / 仅 1 年内生产 / 报废日期 ≥30 天

---

## 3. 公司库资产工作台 UI

### 3.1 入口

不新增一级 tab。投标资料库 → 公司资料 tab 内增加二级区域 `公司资产`，与现有"公司基础资料""公司业绩"平行。

### 3.2 整体布局

```
公司库选择器
└── 4 类 tab（车辆 / 施工机械 / 施工工器具 / 安全设施设备及器具，含数量 badge）
    └── 工具栏（[+ 新增]、批量导入 P2、状态筛选、有效期筛选、搜索）
        └── 资产表格（公共列 + 特化列 + 有效期 badge + 操作）
```

### 3.3 表单（新增 / 编辑抽屉，从右侧滑出）

四区分组：
- 基础信息（共性顶层字段）
- 类型特化字段（从 `schema.extras` 动态渲染）
- 核心附件（4 卡片网格，沿用 `company-contract-upload-card` 样式 + 已修复的按钮溢出 CSS）
- 历史与补充附件（折叠默认关，[+ 添加附件] + 类别下拉 + 生效日期）

表单交互：
- 必填红星 `*` 来自 schema
- ⏰ 标记 `determines_expires_at` 的核心槽，附件上传后自动回填顶层 `expires_at`，提示一行"已自动填入有效期 YYYY-MM-DD，可在上方手工修改"
- 派生字段（如工器具 `expires_at = last_inspection_at + inspection_period_months`、安全设施 `expires_at = acquired_at + mandatory_retirement_months`）表单 onChange 自动算，仍允许覆盖

### 3.4 表格视图

**所有 tab 公共列**: 序号 / 名称 / 规格型号 / 数量&单位 / 所有权 / 有效期 badge / 状态 / 操作

**特化列（每类 2-3 列）**:

| Tab | 特化列 |
|---|---|
| 车辆 | 车牌号 (serial_no) · 车辆类型 · 技术等级 |
| 施工机械 | 出厂编号 · 机械类别 · 容量 (capacity_value+capacity_unit) · 是否特种设备 |
| 施工工器具 | 出厂编号 · 工器具类别 · 电压等级 · 下次试验 |
| 安全设施 | 安全类别 · 防护标准 · 强制报废日期 |

**有效期 badge 颜色规则**（基于 `expires_at`）:

| 距投标常规截止日 | Badge variant | 文案 |
|---|---|---|
| 已过期 | danger | "已过期 N 天" |
| ≤30 天 | warning | "N 天内到期" |
| 31–90 天 | default | "N 天" |
| >90 天 | success | "N 天" |
| 无 expires_at | default | "—" |

颜色 token 沿用现有 `Badge` 组件，无新 CSS。

### 3.5 CRUD 与防误删

- 新增：右上 `+ 新增 XX` 按钮，开抽屉
- 编辑：行点击或行末铅笔图标，抽屉同表单复用
- 删除：弹 ConfirmDialog；`project_equipment_selection.asset_id ON DELETE RESTRICT` 触发删除失败时，前端展示"该资产已被 N 个投标项目引用，不能删除。可改 status=retired 退役"
- 退役：`status='retired'`，表格灰显并默认隐藏，提供"显示已退役"切换

### 3.6 现有大文件拆分（顺手做的目标改进）

`CompanyLibraryWorkbench.tsx` 已 700+ 行，再加资产部分难维护。本次设计同时拆分为：

```
frontend/src/modules/database/components/
├── CompanyLibraryWorkbench.tsx          (容器: 公司库选择 + tab 路由)
├── CompanyProfileSection.tsx            (公司基础资料)
├── ContractPerformanceSection.tsx       (公司业绩)
├── CompanyAssetSection.tsx              (新增,资产工作台容器)
├── asset/
│   ├── AssetTypeTabs.tsx
│   ├── AssetTable.tsx                   (按 schema 动态出列)
│   ├── AssetFormDrawer.tsx              (按 schema 动态出表单)
│   ├── AssetCoreAttachments.tsx
│   └── AssetArchiveAttachments.tsx
└── schemas/
    └── assetTypeSchemas.ts
```

---

## 4. 投标主要施工设备表生成工作台

### 4.1 工作流位置

整合进 spec §2.1 的项目工作流，在 `drafting` 与 `draft_reviewing` 之间插入：

```
... → drafting → equipment_selection (草稿+确认) → draft_reviewing → ...
```

进入条件：招标约束已确认（`constraints_pending_confirmation` 已完成）。

### 4.2 筛选规则（Q7 D 模式：3 + 显式映射 硬筛 + 业务线软筛）

#### A. 基础硬筛（全资产）

```python
P = project.submission_deadline + project.bid_validity_period   # 投标有效性截止日

A1. asset.status == 'active'
A2. asset.expires_at IS NULL OR asset.expires_at >= P
A3. asset.ownership in project.allowed_ownerships               # 来自 tender_constraint type='qualification', label 含 "ownership_restriction"
```

#### B. 招标显式映射的硬筛

招标解析阶段把"主要施工设备/工器具/安全配置"类要求打成 `equipment_requirement` 类型的 `tender_constraint`：

```sql
INSERT INTO tender_constraint (project_id, type, category, source_ref, label, extras_json) VALUES
  ('proj-1', 'substantive_response', 'qualification',
   '投标人须知前附表 §3.4',
   '不少于 5 台 10kV 绝缘斗臂车',
   '{
      "asset_type": "vehicle",
      "predicate": {"vehicle_type": "斗臂车", "voltage_level_min": "10kV"},
      "min_quantity": 5
    }');
```

筛选服务按 `predicate` 过滤候选，按 `min_quantity` 校验覆盖度，**不满足时不阻断录入但顶部"覆盖度"红色警示**。

> **首期范围**：`equipment_requirement` 约束的自动 AI 抽取作为 P2；P1 由用户在约束确认工作台手工补打 `predicate` + `min_quantity`（提供模板下拉）。

#### C. 业务线软筛 chip

每类 schema 的 `soft_filter_chips`，前端过滤候选区可视范围（不写 DB），不改变硬筛结果。与硬筛 `equipment_requirement.predicate`（JSON 化、入库、影响"覆盖度"判定）严格区分。

### 4.3 筛选执行时机

- **首次进入工作台**：项目无 `project_equipment_selection` 时，触发首轮自动筛选写入草稿
- **招标约束变更后**：顶部展示"招标约束已变更（diff: X 条），建议重筛"按钮；点"重筛"按规则合并新候选 + 保留用户已加项 + 标注新被排除项
- **关闭重开**：从草稿恢复，无重新筛选

### 4.4 工作台 UI

```
┌── 设备清单工作台 ─────────────────────────────────┐
│ 项目:XX 10kV配网新建工程   投标截止:2026-06-15    │
│ 投标有效期:90天   有效性截止日:2026-09-13          │
│                              [按招标约束重筛]       │
└────────────────────────────────────────────────────┘

┌── 招标硬条件覆盖度 ──────────────────────────────┐
│ ✓ 不少于 5 台 10kV 斗臂车         已选 5/需 5    │
│ ✗ 配置 ≥10 套绝缘手套(10kV)        已选 6/需 10 ▶│
│ ✓ 配置安全带/安全帽                已选 12/—      │
│ 自动排除 3 项(年检过期/电压不符)  [展开]          │
└────────────────────────────────────────────────────┘

┌── 4 类 tab ────────────────────────────────────┐
│ [车辆 5/12] [机械 3/8] [工器具 28/56] [安全 12/24]│
└────────────────────────────────────────────────┘

┌── 候选区(左) ──────────────┬── 已选区(右) ──────┐
│ 软筛chip:[仅斗臂车][仅10kV] │ 已选 5 项            │
│ ───────────────────────── │ ───────────────────  │
│ ◯ DFL5160 斗臂车 苏A12345  │ ✓ DFL5160 …          │
│   自有/年检60天/优          │   用途[配电主线…]    │
│   [+ 加入] [详情]           │   [移除]             │
│                             │ ✓ XCMG-25 …          │
│ ▶ 自动排除(折叠) 3 项        │                      │
│   ─ XCMG-25 起重车 (年检过期)│                     │
│     [仍要纳入(需理由)]       │                      │
└─────────────────────────────┴──────────────────────┘

┌── 操作 ──────────────────────────────────────┐
│ [保存草稿] [生成预览] [确认并冻结快照(进入审查)] │
└────────────────────────────────────────────────┘
```

### 4.5 强制纳入流程

弹 ConfirmDialog：

```
该资产被自动排除：
  原因:年检已过期 (2026-02-15)
  招标约束:"投标设备须在投标有效期内有效"

继续纳入此资产可能导致：
  • 评分扣分
  • 实质性偏离风险

如仍要纳入,请说明理由(投标负责人签字归档)：
  [_____________________________________]
  [取消]   [确认纳入并标记风险]
```

确认后：
- `exclusion_overridden = TRUE`
- `selection_reason = <理由>`
- 已选区显示橙色 `⚠ 风险已知`
- 符合性检查（spec §6）扫到此条列入 P1 风险清单

### 4.6 快照写入与冻结时机

```
草稿阶段 (frozen=FALSE):
  user 增删勾选
  → 实时 INSERT/UPDATE project_equipment_selection
  → frozen_snapshot 含当时 company_asset 字段最新值

确认并冻结:
  → frozen_snapshot 锁定(字段值 + core_attachment 的 evidence_asset_id + 文件 hash)
  → frozen = TRUE, frozen_at = now()
  → workflow 推进 equipment_selection → draft_reviewing

递交后 (workflow → bid_submitted):
  → 所有行不可 UPDATE/DELETE (应用层 + DB trigger)
  → company_asset 在 library 端被改/删不影响该投标
```

### 4.7 数据流

```
[ company_asset (库,可变) ]
        │
        ▼ EquipmentFilterService.filter(project, constraints)
[ 候选清单 + 排除清单 ]
        │
        ▼ 用户增删 + 强制纳入
[ project_equipment_selection (草稿) ]
        │
        ▼ "确认并冻结快照"
[ project_equipment_selection (frozen=TRUE) ]
        │
        ├──→ 技术标章节 4 子段嵌入
        └──→ Excel 附件 4 sheet
```

### 4.8 与符合性检查的对接

| 扫描项 | 严重级 | 阻断 final_layout |
|---|---|---|
| `frozen_snapshot.expires_at < submission_deadline + bid_validity_period` | P0 | 是（除非显式确认风险）|
| `exclusion_overridden = TRUE` | P1 | 否（已"风险已知"，需投标负责人复核）|
| `equipment_requirement` 覆盖度未达 `min_quantity` | P0 | 是 |
| 核心附件缺失（如行驶证未上传）| P1 | 否 |

---

## 5. 输出层：技术标章节嵌入 + Excel 附件

### 5.1 同源双路渲染

```
[ project_equipment_selection (frozen=TRUE) ]
                │
                ▼
      [ EquipmentTableRenderer ]
        │                       │
        ▼                       ▼
[ DOCX 章节 4 子段嵌入 ]  [ Excel 附件 4 sheet ]
   (DOCX native table)    (xlsx 工作簿)
```

两路共享：数据装配 + 列定义解析 + 格式化器。

### 5.2 渲染服务

`backend/tender_backend/services/export_service/equipment_table_renderer.py`：

```python
class EquipmentTableRenderer:
    def render_equipment_preview(project_id) -> dict[str, list[dict]]:
        """4 类各一份结构化预览数据,前端工作台 HTML 渲染。"""
    
    def render_subsection_table(doc, project_id, asset_type) -> Table:
        """DOCX native table,供章节注入器调用。"""
    
    def render_attachment_xlsx(project_id) -> bytes:
        """完整 Excel 附件,4 sheet。"""
```

### 5.3 DOCX 章节嵌入：锚点字符串

模板章节里写：

```
本投标项目拟投入主要施工设备如下：

#### 5.1 车辆
{{equipment_table:vehicle}}

#### 5.2 施工机械
{{equipment_table:machine}}

#### 5.3 施工工器具
{{equipment_table:tool}}

#### 5.4 安全设施设备及器具
{{equipment_table:safety}}
```

`docx_exporter.py` 末尾加 `EquipmentTableInjector` 后处理 pass：扫段落文本匹配 `\{\{equipment_table:(vehicle|machine|tool|safety)\}\}`，原位置替换为 native table。

表格的列由 `ASSET_TYPE_SCHEMAS[asset_type].export_columns` 解析，应用 formatter。

### 5.4 Excel 附件

独立文件 `<项目编号>_主要施工设备一览表.xlsx`，4 sheet（车辆 / 施工机械 / 施工工器具 / 安全设施设备及器具）。

实现：openpyxl 直接构造 .xlsx，每 sheet 表头加粗 + 冻结首行 + 列宽自适应。

附件挂载：在 `bid_delivery_package` 登记 `attachment_kind='equipment_table_xlsx'`，终稿打包随同 DOCX/PDF 进 ZIP。

### 5.5 与工作台预览的衔接

§4 工作台"生成预览"按钮调 `render_equipment_preview` 返回结构化数据，前端按 `export_columns` HTML 渲染。**预览与最终件读同一份 schema 的同一份 export_columns**，永远不出现"预览看到的与最终件不一致"。

### 5.6 表格样式

- DOCX：模板包定义命名样式 `EquipmentTableStyle`，fallback 到 `Table Grid`。
- Excel：标题行加粗 + 冻结首行 + 列宽自适应，无复杂样式。

### 5.7 错误与降级

| 情况 | 处理 |
|---|---|
| 项目无 frozen 快照（用户没点确认） | 渲染器空表 + 章节注入告警 P1，禁止 final_layout |
| 模板章节无 `{{equipment_table:xxx}}` 锚点 | 跳过该类，不报错（兼容老模板） |
| 某类资产已选数为 0 | 渲染表头空表 + 一行"无"占位 |
| 渲染异常 | DOCX 章节内插红字告警 + 主流程不中断；导出审查阶段强制阻断 final_layout |

---

## 6. 集成点 + 测试与验收

### 6.1 后端 API（新增）

```
# 公司库资产 CRUD
GET    /master-data/library-companies/{id}/assets?asset_type=vehicle
POST   /master-data/library-companies/{id}/assets
PUT    /master-data/assets/{id}
DELETE /master-data/assets/{id}

# 资产附件
POST   /master-data/assets/{id}/attachments
DELETE /master-data/assets/{id}/attachments/{attachment_id}

# 投标设备选择
GET    /projects/{id}/equipment/candidates?asset_type=vehicle
POST   /projects/{id}/equipment/selections
PUT    /projects/{id}/equipment/selections/{selection_id}
DELETE /projects/{id}/equipment/selections/{selection_id}
POST   /projects/{id}/equipment/selections/refilter
POST   /projects/{id}/equipment/selections/freeze

# 输出
GET    /projects/{id}/equipment/preview
GET    /projects/{id}/equipment/attachment-xlsx
```

### 6.2 前端 API 客户端

```ts
fetchCompanyAssets(libraryId, assetType?)
createCompanyAsset(libraryId, payload)
updateCompanyAsset(assetId, payload)
deleteCompanyAsset(assetId)
uploadAssetAttachment(assetId, { kind, slot_role, file, effective_at? })
removeAssetAttachment(assetId, attachmentId)

fetchEquipmentCandidates(projectId, assetType)
selectEquipment(projectId, payload)
updateEquipmentSelection(projectId, selectionId, patch)
removeEquipmentSelection(projectId, selectionId)
refilterEquipment(projectId)
freezeEquipmentSelection(projectId)
fetchEquipmentPreview(projectId)
downloadEquipmentXlsx(projectId)
```

### 6.3 与现有模块的集成点

| 现有模块 | 触点 |
|---|---|
| `library_company` | `company_asset.library_company_id` 外键 |
| `evidence_asset` | `company_asset_attachment.evidence_asset_id` 外键 |
| `tender_constraint` | 增加约束 type `equipment_requirement` |
| `bid_chapter_template` | 模板章节里写 `{{equipment_table:<asset_type>}}` 锚点 |
| `docx_exporter` | 末尾加 `EquipmentTableInjector` 后处理 pass |
| `delivery_package` | 终稿打包时挂 `equipment_table_xlsx` |
| 符合性检查 (spec §6) | 扫 `project_equipment_selection`，按 §4.8 表校验 |
| 项目工作流 (spec §2.1) | 在 `drafting` 与 `draft_reviewing` 之间插 `equipment_selection` |

### 6.4 测试范围

**单元**
- 4 类 schema 字段定义自洽（required + select options 完备）
- `EquipmentFilterService.filter()` 基础三条 + `equipment_requirement` 覆盖度计算
- `_resolve_column()` / `_format_value()` 各 formatter
- `EquipmentTableInjector` 锚点替换：单/多/缺锚点兼容
- `frozen_snapshot` 写入：未冻结跟随 library，冻结后锁定

**集成**
- 完整流程：录入资产 + 上传附件 → 项目自动筛选 → 用户增删 + 强制纳入 → 冻结 → 导出 DOCX/Excel → 验证内容
- 招标约束变更后重筛：保留已有手工选项不丢失
- DELETE company_asset 在被引用时 409
- 工作流推进：未冻结时 final_layout 被符合性检查阻断

**端到端 fixture**
- 1 套 10kV 业务线 fixture：3 辆车 + 5 台机械 + 30 件工器具 + 12 件安全设施 + 招标约束 5 条 `equipment_requirement` → 走完工作台并产出 DOCX + Excel，黑盒比对内容

### 6.5 验收清单

- [ ] 公司库 → 公司资料 → 公司资产，4 个 tab 内 CRUD 资产、附件、累积区折叠、有效期 badge
- [ ] 进入项目设备清单工作台，自动筛选生成候选 + 排除 + 招标硬条件覆盖度
- [ ] 强制纳入未通过筛选的资产，必填理由后写入并标 `⚠ 风险已知`
- [ ] 招标约束变更后"重筛"按钮生效，已选项保留
- [ ] "确认并冻结快照"后工作流推进，冻结字段不可改
- [ ] 模板章节含 `{{equipment_table:xxx}}` 锚点时，导出 DOCX 出现 native 表格
- [ ] 终稿打包时附 `<项目编号>_主要施工设备一览表.xlsx`，4 sheet 与 DOCX 子段数据一致
- [ ] 符合性检查能扫到过期资产 / 强制纳入 / 招标硬条件未覆盖，按 P0/P1 分级阻断

### 6.6 风险与待定

- **`equipment_requirement` 约束的 AI 自动抽取**：首期手工标 `predicate + min_quantity`（带模板下拉），AI 抽取作 P2 增强。
- **模板包侧 `EquipmentTableStyle` 命名样式**：由模板包维护方提供；fallback 到 `Table Grid` 默认样式，不阻塞首期上线。
- **历史数据迁移**：现有 `evidence_asset` 里若已存"车辆类"附件，不强制迁入；用户可选择保留作为 generic 证据，或手工新建 `company_asset` 后挂同一个 `evidence_asset_id`（数据层允许多挂）。
- **资产 `extras` 强类型校验缺失**：依赖前端 schema 校验，绕过前端直接调 API 可写入任意 JSON。如出现数据质量问题再考虑 schema 同步到后端。

---

## 7. 实施依赖关系

实施顺序建议（writing-plans 阶段细化）：

```
1. DB migration: company_asset / company_asset_attachment / project_equipment_selection
2. 后端 schema 基线 (asset_type 常量 + validate_common_fields)
3. 后端资产 CRUD API + repo
4. 前端 schema 配置 (assetTypeSchemas.ts) + 4 类字段定义
5. 前端 CompanyLibraryWorkbench 拆分 + CompanyAssetSection
6. 前端资产 UI: AssetTable / AssetFormDrawer / AssetCoreAttachments / AssetArchiveAttachments
7. tender_constraint 类型扩展: equipment_requirement (含 predicate + min_quantity)
8. 后端 EquipmentFilterService
9. 后端投标设备选择 API
10. 前端设备清单工作台 (候选/已选/覆盖度/重筛/冻结)
11. 后端 EquipmentTableRenderer (preview + DOCX subsection + Excel attachment)
12. docx_exporter 集成 EquipmentTableInjector
13. delivery_package 集成 equipment_table_xlsx 附件
14. 符合性检查规则扩展 (4 项扫描)
15. 工作流状态扩展: equipment_selection
16. 端到端 fixture + 验收脚本
```

---

**附:** 本设计与 `2026-05-07-bid-generation-workflow-redesign-review.md` (review) 报告中"§3 §4 章节自动化的子能力"对齐；本次落地后，review 中"投标响应索引 / 设备表自动生成"由"概念描述"变为"已实现能力"。
