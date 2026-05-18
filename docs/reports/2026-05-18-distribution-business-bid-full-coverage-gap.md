# 配网工程完整商务标 Gap 报告

> **日期:** 2026-05-18
> **范围:** 评估 tender 系统输出"国网公司配网工程完整商务标"（24 章）的覆盖能力与缺口
> **对照基准:** `docs/samples/国网公司配网工程商务标目录.md` + `backend/tender_backend/services/bid_outline_templates.py:30-91`（SGCC_DISTRIBUTION_BUSINESS_CHAPTERS）
> **审阅方式:** 只读代码盘点；2026-05-18 结合 docxtpl 管线与样章模板二次核实后修订

---

## 总览结论

**docxtpl 渲染管线已完整接入**（model / renderer / importer / API / 单元测试齐全），且 `docs/samples/sgcc_distribution_business_{1_3,4_24}/README.md + manifest.json` 已沉淀 1-24 章共约 50 个 DOCX 样章模板的占位符设计与资料位规范。但目前：

1. **1-24 章 docx 模板物理文件未入库**：`.gitignore` 排除 `docs/samples/**/*.docx`，仓库中只有 README/manifest，没有 docx 本体
2. **未运行过 import**：migration `0043` 仅以 `source_kind='md'`、`render_mode='outline'` 录入了 24 个目录条目，从未调用 `import_template_package_from_directory` 把 docx 写入 `bid_template_item`
3. **BusinessBidAssembler 不调用 docxtpl 渲染**：`business_bid_assembler.py:19-56` 只产出"目录 + 响应矩阵 + 缺料清单 + run 记录"，不触发 docxtpl 模板渲染
4. **章节↔数据源↔渲染器绑定层缺失**：`evidence_asset`、`company_profile`、`person_profile`、`financial_statement`、`qualification_certificate` 五张通用表存在，但无章节维度的资料筛选/绑定规则

商务标本质上是 **少量正文 + 大量附件**（证件扫描件、财务报表、认证证书）。**底层管线已就位**，差的是模板入库 + 章节-数据-资料的编排闭环，而非渲染器/导出器本身。

---

## 一、章节维度 Gap

| 章号 | 章节标题 | 大纲注册 | docxtpl 样章设计 | 模板入库 | 数据填充 | 缺口 |
|---|---|---|---|---|---|---|
| 1 | 商务偏差表 | ✅ | ✅ 1_3 README | ❌ | ✅ 通用偏差表 API | 商务/技术偏差不区分 |
| 2 | 无违法失信承诺函 | ✅ | ✅ 1_3 README | ❌ | — | **样章入库 + 承诺函变量绑定 + 截图资料位** |
| 3 | 营业执照 | ✅ | ✅ 1_3 README | ❌ | ⚠️ evidence_asset | **样章入库 + 章节↔附件类型绑定** |
| 4 | 法人身份证明 | ✅ | ✅ 4_24 manifest (2 资料位) | ❌ | ⚠️ evidence_asset + company_profile | 同上 |
| 5.1 | 基本情况表 | ✅ | ✅ 4_24 manifest (16 资料位 / 37 占位) | ❌ | ⚠️ company_profile 字段不全 | **样章入库 + 法人/成立日/注册地字段补齐** |
| 5.2 | 安全质量事故响应表 | ✅ | ✅ 4_24 manifest (3 资料位 / 4 占位) | ❌ | ❌ 无台账 | **样章入库 + 事故台账模型** |
| 6 | 信用信息公示报告 | ✅ | ✅ 4_24 (40 资料位) | ❌ | ⚠️ evidence_asset | 缺章节绑定 |
| 6.1 | 人员汇总+简历 | ✅ | ✅ 4_24 manifest | ❌ | ⚠️ person_profile.resume_text | **商务卷被 `_should_include_personnel_table` 排除 (`docx_exporter.py:254`)** + 简历卡片渲染 |
| 7 | 与国网系统人员关系说明 | ✅ | ✅ 4_24 (1 占位) | ❌ | — | **样章入库 + 承诺函变量绑定** |
| 8.1-8.3 | 三年×四表 | ✅ | ✅ 12 张 docx 设计 | ❌ | ⚠️ financial_statement 表结构在 | companybase 导入未覆盖财务（`MVP_SHEETS` 不含财务）；4 表×3 年科目结构未约束 |
| 9 | 联合体协议 | ✅ | ✅ 4_24 | ❌ | ⚠️ evidence_asset | 缺章节绑定 + 协议模板入库 |
| 10 | 银行开户许可证 | ✅ | ✅ 4_24 (1 资料位) | ❌ | ❌ 无银行账户台账 | **样章入库 + 账户台账** |
| 11 | 绿色发展顶层规划 | ✅ | ✅ 4_24 (33 资料位) | ❌ | ❌ | 正文+附件型，模板入库后还需正文生成 |
| 12.1-12.4 | 绿色管理体系四认证 | ✅ | ✅ 4_24 (各 2-4 资料位) | ❌ | ⚠️ qualification_certificate | 缺章节↔证书 category 映射 |
| 13.1-13.4 | ESG / 环评 / 排放 / 处罚 | ✅ | ✅ 4_24 (各 33-35 资料位) | ❌ | ❌ | **样章入库 + ESG/环评台账** |
| 14 | 绿证 | ✅ | ✅ 4_24 (1 资料位 / 7 占位) | ❌ | ❌ 无绿证台账 | **样章入库 + 绿证台账** |
| 15 | 科技成果 | ✅ | ✅ 4_24 (13 资料位 / 3 占位) | ❌ | ❌ | **样章入库 + 科技成果台账** |
| 16 | 创新激励政策 | ✅ | ✅ 4_24 (31 资料位) | ❌ | ❌ | 正文型，模板入库后还需正文生成 |
| 17 | 研发团队规模 | ✅ | ✅ 4_24 (5 资料位 / 3 占位) | ❌ | ❌ 无研发投入字段 | **样章入库 + 研发投入台账** |
| 18 | 质量奖项 | ✅ | ✅ 4_24 (28 资料位 / 11 占位) | ❌ | ⚠️ qualification_certificate | 缺奖项专项分类 + 章节绑定 |
| 19 | 高新企业证书 | ✅ | ✅ 4_24 (1 资料位 / 2 占位) | ❌ | ⚠️ qualification_certificate | 缺章节绑定 |
| 20 | 企业名称变更 | ✅ | ✅ 4_24 (4 资料位 / 4 占位) | ❌ | ❌ | **样章入库 + 说明文模板** |
| 21 | 小规模纳税人说明 | ✅ | ✅ 4_24 (1 资料位 / 1 占位) | ❌ | ❌ | **样章入库 + 承诺/说明文模板** |
| 22 | 其他税率佐证 | ✅ | ✅ 4_24 (0 资料位) | ❌ | ⚠️ evidence_asset | 缺章节绑定 |
| 23.1 | 保证金明细表 | ✅ | ✅ 4_24 (0 资料位 / 0 占位) | ❌ | ❌ 无保证金台账 | **样章入库 + 保证金台账 + 表渲染** |
| 23.2 | 投标保证金缴纳证明 | ✅ | ✅ 4_24 | ❌ | ⚠️ evidence_asset | 缺章节绑定 |
| 24.1-24.8 | 其他商务内容 | ✅ | ✅ 4_24 (各 0-23 资料位) | ❌ | ❌ | 24.4/24.5 缺研发/综合实力台账 |

**核心结论:**
- **24 章 100% 在 README/manifest 中沉淀了占位符与资料位设计**，但**0 章** docx 模板入库到 `bid_template_item`（`source_kind='md'` 而非 `'docx'`）
- **附件型章节**（约 11 章）有 `evidence_asset` 表与 `package_renderer.py:179-300` PDF/图片嵌入能力，但**章节↔asset_category 绑定层缺失**
- **台账型章节**：5.2/8.x/10/14/15/17/23.1 等共 6 项专项台账无对应数据模型
- **承诺/说明文 4 类**（章 2/7/20/21）：样章已设计变量占位符，缺 importer 录入与签章/日期变量填充闭环

---

## 二、docxtpl 管线接入度（已具备的底层能力）

| 组件 | 文件 | 状态 |
|---|---|---|
| 数据模型 | `db/alembic/versions/0016_bid_template_packages.py:43-45` (`source_kind`/`render_mode`) | ✅ 支持 `docx` / `single_docx` |
| Repo | `db/repositories/bid_template_package_repo.py:34-104` | ✅ |
| DocxTpl 渲染器 | `services/template_service/docx_renderer.py:8` (`from docxtpl import DocxTemplate`)、`_render_single_docx_template:283-314` | ✅ |
| 包渲染器 | `services/template_service/package_renderer.py:580` 调 `render_template_item_docx`；`:179-300` 已实现 PDF/图片附件嵌入 | ✅ |
| Importer | `services/template_service/package_importer.py:172-176,229-233` 写入 `source_kind="docx"`、`render_mode="single_docx_section"` | ✅ |
| API | `api/template_packages.py:367-419` `import_template_package_from_directory` | ✅ |
| 单元测试 | `tests/unit/test_template_docx_renderer.py:174-216` 覆盖 `{{ company.company_name }}` 渲染 | ✅ |

**底层管线完整可用**，差的只是把 1-24 章 docx 文件放到 source_root 并跑一次 import。

---

## 三、承诺函/说明文模板 Gap

涉及章 2、7、20、21（共 4 章）：

**已有设计**（README + manifest）：
- 章 2/3 占位符已定义（`docs/samples/sgcc_distribution_business_1_3/README.md:13-22`）：`{{ tender.purchaser_name }}` / `{{ company.company_name }}` / `{{ deviation_table.rows[*].* }}` / `{{ asset.business_license_scan }}` / `{{ asset.credit_china_report }}`
- 章 4-24 占位符设计（`docs/samples/sgcc_distribution_business_4_24/README.md`）：`{{ company.* }}` / `{{ asset.* }}`

**缺口:**
- 4 类承诺/说明 docx 模板本体未入库
- `business_bid_assembler` 不构造 `context = {"company": ..., "tender": ..., "asset": ..., "deviation_table": ...}` 上下文调 `render_template_item_docx`

---

## 四、数据底座 Gap

### 已有通用表（5 张）

| 实体 | migration | 用途 | 局限 |
|---|---|---|---|
| `company_profile` | `0017:23-40` | 公司工商基础信息 | 缺法定代表人/成立日/注册地全要素 |
| `person_profile` | `0017:43-60` | 人员简历 | 6.1 章无渲染入口 |
| `qualification_certificate` | `0017:85-100` | 资质证书 | 缺章节↔category 映射 |
| `financial_statement` | `0017:104-114` | 财务报表 | companybase 导入未覆盖（`MVP_SHEETS` 4 sheet 不含财务）；4 表科目结构未约束 |
| `evidence_asset` | `0019:23-39` + `0021:91-103` | 通用附件 | 缺章节绑定层 |

### 缺失专项台账（6 项）

| 业务 | 涉及章 | 当前状态 |
|---|---|---|
| 银行账户 | 10 | **无表** |
| 保证金缴纳 | 23.1 | **无表** |
| 绿证 / 绿电交易 | 14 | **无表** |
| 科技成果 / 研发投入 | 15、17、24.4 | **无表** |
| ESG / 环评 / 排放 / 行政处罚 | 13.1-13.4 | **无表** |
| 奖项（质量奖/工业大奖等）| 18 | **无专项分类** |

---

## 五、DOCX 导出 Gap

| 能力 | 现状 | 缺口 |
|---|---|---|
| 整卷渲染 | ✅ `render_volume_docx(..., volume_type='business')` (`docx_exporter.py:460-469` → `_render_plain_docx`) | `_render_plain_docx` 只读 `chapter_draft.content_md`；**未调 `package_renderer` 走 docxtpl 路径** |
| 章节分隔页 | ✅ `_add_chapter_divider_page` (`docx_exporter.py:211-247`) | — |
| 偏差表 | ✅ `_add_deviation_table` | 商务/技术偏差未区分 |
| PDF/图片附件嵌入 | ✅ `package_renderer.py:179-300` | **未接入商务卷整卷渲染流程** |
| 三栏页眉 | ❌ 仅固定字符串"投标文件"（`docx_exporter.py:183`）| 招标常见三栏（投标人/项目名/卷别）缺失 |
| 骑缝章占位 | ❌ 仅 `project_template_instance_service.py:28,260` 作关键字识别 | **未实际渲染骑缝占位** |
| 人员表注入 | ❌ 商务卷被 `_should_include_personnel_table` 排除（`docx_exporter.py:254`）| 6.1 章无法注入 |

---

## 六、BusinessBidAssembler 现状

`backend/tender_backend/services/business_bid_assembler.py:19-56` 当前只产出 4 类输出：
1. 目录占位
2. 响应矩阵（商务条款响应）
3. 缺料清单（提示需要补充的资料）
4. run 记录（执行轨迹）

**不做的事:**
- 不查询 `company_profile` / `person_profile` / `financial_statement` / `qualification_certificate` / `evidence_asset`
- 不构造 docxtpl 渲染上下文，不调 `render_template_item_docx`
- 不写 `chapter_draft.content_md`
- 不组装承诺函
- 不嵌入附件

---

## 七、优先级建议

| 优先级 | 项 | 影响 |
|---|---|---|
| **P0** | 把 1-24 章 docx 模板从交付物（用户桌面/SharePoint）入库到 `source_root`，调 `import_template_package_from_directory`，把 `bid_template_item.source_kind` 从 `md` 改为 `docx`、`render_mode` 改为 `single_docx` | 让 24 章具备"模板渲染入口"——**当前最快路径** |
| **P0** | "章节↔数据源↔渲染器"绑定层：定义 `chapter_code → (template_item, context_builder, asset_categories)` 映射；BusinessBidAssembler 调 `render_template_item_docx` | 接通 docxtpl 渲染与公司库 |
| **P0** | 承诺函/说明文 4 类（章 2/7/20/21）context_builder：投标人/项目名/日期/法人签章变量填充 | 4 类必填章节 |
| **P0** | 5.1 基本情况表渲染器 + company_profile 字段补齐；6.1 人员汇总+简历渲染（解除 `_should_include_personnel_table` 商务卷排除）| 5.1 必填章 + 6.1 评分章 |
| **P1** | 财务报表 8.1-8.3 三年×四表：companybase MVP_SHEETS 加财务 sheet，4 表科目结构约束 + 渲染器 | 必填章，工作量大 |
| **P1** | 整卷渲染流程接入 `package_renderer` PDF/图片嵌入，让附件型 11 章自动嵌入 evidence_asset 附件 | 商务标核心交付形态 |
| **P1** | 商务偏差表与技术偏差表分离；三栏页眉 + 骑缝章占位 | 评标合规与版式 |
| **P2** | 6 项专项台账（银行/保证金/绿证/科技/ESG/奖项）+ 正文型章节生成（11/13.1/15/17/24.5）| 评分加分项与企业宣传章 |
| **P2** | 安全质量事故响应表（5.2）台账 | 必填但偏少使用 |

---

## 八、技术标 vs 商务标 覆盖度对比

| 维度 | 技术标（16 章） | 商务标（24 章） |
|---|---|---|
| Longform 完备章数 | 5（8、9、10.1/10.2/10.3，约 215 页）| 0（商务标走"模板填充"形态而非长文生成）|
| 短策略章数 | 3（6、12、13）| 0 |
| 大纲注册 | 16/16 | 24/24 |
| docxtpl 样章设计（README + manifest）| ⚠️ 部分 | ✅ 24/24 全覆盖 |
| docxtpl 模板入库 | — | **0/24（最大缺口）** |
| 章节↔数据源绑定 | longform 章节有 required_facts | **0 章有绑定** |
| 偏差表 | ✅ | ✅（通用） |
| 行业 prompt | 5 套配网专用 | 0 套（商务标无需行业 prompt）|
| 主要缺口 | 行业纵深 + 部分章节模板化 | **样章入库 + 编排闭环**（底层管线已具备） |

商务标与技术标形态不同：技术标核心是"长文生成"，商务标核心是"模板填充 + 附件编排"。底层 docxtpl 管线已就位，**最大缺口是 1-24 章 docx 模板入库 + 章节维度的资料编排闭环**。

---

## 九、References

- 大纲注册：`backend/tender_backend/services/bid_outline_templates.py:30-91`（SGCC_DISTRIBUTION_BUSINESS_CHAPTERS）
- 样章模板设计：`docs/samples/sgcc_distribution_business_1_3/README.md`、`docs/samples/sgcc_distribution_business_4_24/README.md` + `manifest.json`
- docxtpl 渲染器：`backend/tender_backend/services/template_service/docx_renderer.py:283-314`（`_render_single_docx_template`）、`:339-372`（`render_template_item_docx` 分发）
- 包渲染器：`backend/tender_backend/services/template_service/package_renderer.py:179-300, 400-435, 580`
- Importer：`backend/tender_backend/services/template_service/package_importer.py:172-176, 229-233`
- API：`backend/tender_backend/api/template_packages.py:367-419`
- BusinessBidAssembler：`backend/tender_backend/services/business_bid_assembler.py:19-56`
- DOCX 导出：`backend/tender_backend/services/export_service/docx_exporter.py:82-469`
- 数据底座：`backend/tender_backend/db/alembic/versions/0017_company_master_data.py`、`0019_evidence_assets.py`、`0021_template_taxonomy_and_company_libraries.py`、`0040_company_asset_models.py`
- companybase 导入：`backend/tender_backend/services/companybase/companybase_import_service.py:26,185-252`
- 数据库模板：`backend/tender_backend/db/alembic/versions/0043_sgcc_distribution_business_template.py`（仅录目录条目，`source_kind='md'`）
- 单元测试：`backend/tests/unit/test_template_docx_renderer.py:174-216`

---

## 十、修订记录

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| v1.0 | 2026-05-18 | 初版。基于 2026-05-18 仓库代码盘点，对照国网配网商务标 24 章目录输出 gap。|
| v1.1 | 2026-05-18 | 经"docxtpl 管线已接入"核实后修订：(1) 收紧"0 章有内容生成策略"等绝对化表述，明确底层管线（model/renderer/importer/API/单元测试）完整可用；(2) 区分"样章设计已沉淀（README+manifest 24/24）"与"模板入库（0/24）"两层；(3) P0 重排为模板入库 + 章节↔数据源绑定层 + 4 类承诺/说明文 context_builder；(4) 校正与技术标对比口径——商务标形态是"模板填充"，与技术标"长文生成"不同源。|
