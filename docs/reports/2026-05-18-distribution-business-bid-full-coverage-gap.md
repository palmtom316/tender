# 配网工程完整商务标 Gap 报告

> **日期:** 2026-05-18
> **范围:** 评估 tender 系统输出"国网公司配网工程完整商务标"（24 章）的覆盖能力与缺口
> **对照基准:** `docs/samples/国网公司配网工程商务标目录.md` + `backend/tender_backend/services/bid_outline_templates.py:30-91`（SGCC_DISTRIBUTION_BUSINESS_CHAPTERS）
> **审阅方式:** 只读代码盘点，无修改

---

## 总览结论

商务标 24 章 **0 章有内容生成策略**，与技术标 5 章 longform 完备形成强反差。当前 `BusinessBidAssembler` 仅产出"目录 + 响应矩阵 + 缺料清单 + run 记录"（`business_bid_assembler.py:31-56`），不读公司库、不写 `chapter_draft.content_md`、不嵌附件。商务标本质上是 **少量正文 + 大量附件**（证件扫描件、财务报表、认证证书），系统目前对附件型章节既无"章节↔数据源↔渲染器"绑定层，也无承诺函/说明文模板渲染器。

---

## 一、章节维度 Gap

| 章号 | 章节标题 | 大纲注册 | 内容生成 | 数据填充 | 缺口 |
|---|---|---|---|---|---|
| 1 | 商务偏差表 | ✅ | ✅ `api/deviation_table.py` | ✅ 通用 | 商务/技术偏差不区分 |
| 2 | 无违法失信承诺函 | ✅ | ❌ | — | **缺承诺函模板** |
| 3 | 营业执照 | ✅ | ❌ | ⚠️ evidence_asset 可承载 | **缺章节↔附件绑定**、PDF/图片嵌入未接入整卷渲染 |
| 4 | 法人身份证明 | ✅ | ❌ | ⚠️ 同上 | 同上 |
| 5.1 | 基本情况表 | ✅ | ❌ | ⚠️ `company_profile` 仅基础工商字段 | 缺法定代表人/成立日/注册地全要素 + 表格渲染器 |
| 5.2 | 安全质量事故响应表 | ✅ | ❌ | ❌ 无台账 | **完全缺失** |
| 6 | 信用信息公示报告 | ✅ | ❌ | ⚠️ evidence_asset | 缺附件绑定 |
| 6.1 | 人员汇总+简历 | ✅ | ❌ | ⚠️ `person_profile.resume_text` | **商务卷被 `_should_include_personnel_table` 排除**（`docx_exporter.py:254`）；无简历卡片渲染器 |
| 7 | 与国网系统人员关系说明 | ✅ | ❌ | — | **缺承诺函模板** |
| 8.1-8.3 | 三年×四表（资产负债/现金流/利润/其他）| ✅ | ❌ | ⚠️ `financial_statement` 表结构存在 | companybase 导入未覆盖财务（`MVP_SHEETS` 仅 4 sheet 不含财务）；4 表×3 年科目结构未约束；无渲染器 |
| 9 | 联合体协议 | ✅ | ❌ | ⚠️ evidence_asset | 缺附件绑定 + 协议模板 |
| 10 | 银行开户许可证 | ✅ | ❌ | ❌ 无银行账户台账 | **缺台账** |
| 11 | 绿色发展顶层规划 | ✅ | ❌ | ❌ | **正文型，完全缺生成** |
| 12.1-12.4 | 绿色管理体系四认证 | ✅ | ❌ | ⚠️ `qualification_certificate` | 缺章节↔证书 category 映射 |
| 13.1-13.4 | ESG / 环评 / 排放 / 处罚 | ✅ | ❌ | ❌ | **缺 ESG/环评台账** |
| 14 | 绿证 | ✅ | ❌ | ❌ 无绿证台账 | **缺台账** |
| 15 | 科技成果 | ✅ | ❌ | ❌ 无科技成果台账 | **正文+台账双缺** |
| 16 | 创新激励政策 | ✅ | ❌ | ❌ | 正文型缺失 |
| 17 | 研发团队规模 | ✅ | ❌ | ❌ 无研发投入字段 | **正文+台账双缺** |
| 18 | 质量奖项 | ✅ | ❌ | ⚠️ qualification_certificate | 无奖项专项台账与章节绑定 |
| 19 | 高新企业证书 | ✅ | ❌ | ⚠️ qualification_certificate | 缺章节绑定 |
| 20 | 企业名称变更 | ✅ | ❌ | ❌ | 缺说明文模板 |
| 21 | 小规模纳税人说明 | ✅ | ❌ | ❌ | **缺承诺/说明文模板** |
| 22 | 其他税率佐证 | ✅ | ❌ | ⚠️ evidence_asset | 缺章节绑定 |
| 23.1 | 保证金明细表 | ✅ | ❌ | ❌ 无保证金台账 | **缺台账+表渲染** |
| 23.2 | 投标保证金缴纳证明 | ✅ | ❌ | ⚠️ evidence_asset | 缺章节绑定 |
| 24.1-24.8 | 其他商务内容（不良行为/信用/科研经费占比/综合实力/投标响应/经营状况等）| ✅ | ❌ | ❌ | **混合型，几乎全缺** |

**核心结论:**
- **0 章**有 prompt 模板 / required_facts / required_charts 配置
- **24 章中 23 章无内容生成路径**（仅 1 商务偏差表通用可用）
- 附件型章节（3/4/6/9/10/12/14/18/19/22/23.2 等 11 章）有 `evidence_asset` 表但**无章节绑定层**
- 台账型章节（5.2/8.x/10/14/15/17/23.1）**6 个专项台账完全缺失**

---

## 二、承诺函/说明文模板 Gap

涉及章 2、7、20、21（共 4 章），状态：

- 全仓 grep `commitment_letter` / `letter_template` **零命中**
- 模板包导入流程仅把承诺函正文作为 docx 段落直接复制（`tests/unit/test_bid_template_package_importer.py:99-100`），**无 placeholder 渲染机制**（投标人/项目名/日期 等变量未抽取）

**缺口:** 缺统一承诺函/说明文 placeholder 渲染器，至少需覆盖 4 类模板：
1. 无违法失信承诺函（章 2）
2. 与国网系统人员关系说明（章 7）
3. 企业名称变更说明（章 20）
4. 小规模纳税人说明（章 21）

---

## 三、数据底座 Gap

### 已有通用表（5 张）

| 实体 | migration | 用途 | 局限 |
|---|---|---|---|
| `company_profile` | `0017:23-40` | 公司工商基础信息 | 缺法定代表人/成立日/注册地全要素 |
| `person_profile` | `0017:43-60` | 人员简历 | 6.1 章无渲染器 |
| `qualification_certificate` | `0017:85-100` | 资质证书 | 缺章节↔category 映射 |
| `financial_statement` | `0017:104-114` | 财务报表 | companybase 导入未覆盖；4 表科目结构未约束 |
| `evidence_asset` | `0019:23-39` + `0021:91-103` | 通用附件 | 缺章节绑定 |

### 缺失专项台账（6 项）

| 业务 | 涉及章 | 当前状态 |
|---|---|---|
| 银行账户 | 10 | **无表** |
| 保证金缴纳 | 23.1 | **无表** |
| 绿证 / 绿电交易 | 14 | **无表** |
| 科技成果 / 研发投入 | 15、17、24.4 | **无表** |
| ESG / 环评 / 排放 / 行政处罚 | 13.1-13.4 | **无表** |
| 奖项（质量奖/工业大奖等）| 18 | **无专项表** |

---

## 四、DOCX 导出 Gap

| 能力 | 现状 | 缺口 |
|---|---|---|
| 整卷渲染 | ✅ `render_volume_docx(..., volume_type='business')` (`docx_exporter.py:460-469` → `_render_plain_docx`) | `_render_plain_docx` 只读 `chapter_draft.content_md`，**不读 evidence_asset、不嵌附件** |
| 章节分隔页 | ✅ `_add_chapter_divider_page` (`docx_exporter.py:211-247`) | — |
| 偏差表 | ✅ `_add_deviation_table` | 商务/技术偏差未区分 |
| 附件嵌入 | ⚠️ `template_service/package_renderer.py:179-300` 已实现 PDF/图片嵌入 | **未接入商务卷整卷渲染流程** |
| 三栏页眉 | ❌ 仅固定字符串"投标文件"（`docx_exporter.py:183`）| 招标常见三栏（投标人/项目名/卷别）缺失 |
| 骑缝章占位 | ❌ 仅 `project_template_instance_service.py:28,260` 作为关键字识别 | **未实际渲染骑缝占位** |
| 人员表注入 | ❌ 商务卷被 `_should_include_personnel_table` 排除（`docx_exporter.py:254`）| 6.1 章无法注入 |

---

## 五、BusinessBidAssembler 现状

`backend/tender_backend/services/business_bid_assembler.py:19-56` 当前只产出 4 类输出：
1. 目录占位
2. 响应矩阵（商务条款响应）
3. 缺料清单（提示需要补充的资料）
4. run 记录（执行轨迹）

**不做的事:**
- 不查询 `company_profile` / `person_profile` / `financial_statement` / `qualification_certificate` / `evidence_asset`
- 不写 `chapter_draft.content_md`
- 不组装承诺函
- 不渲染基本情况表 / 财务报表 / 人员简历
- 不嵌入附件

---

## 六、优先级建议

| 优先级 | 项 | 影响 |
|---|---|---|
| **P0** | "章节↔数据源↔渲染器"绑定层 + 附件型 11 章接入整卷渲染（章 3/4/6/9/10/12/14/18/19/22/23.2）| "能不能交完整商务标"，附件型章数最多 |
| **P0** | 承诺函/说明文 placeholder 渲染器（章 2/7/20/21）| 4 类强制承诺章节 |
| **P0** | 基本情况表（5.1）、人员汇总+简历（6.1）渲染器 | 6.1 评分项；5.1 必填章 |
| **P1** | 财务报表三年×四表 companybase 导入 + 渲染（章 8.1-8.3）| 必填章，工作量大 |
| **P1** | 商务偏差表与技术偏差表分离 | 评审常见硬性区分 |
| **P1** | 三栏页眉 + 骑缝章占位 | 评标合规与版式 |
| **P2** | 6 项专项台账（银行/保证金/绿证/科技/ESG/奖项）+ 正文型 4 章生成（11/13.1/15/17/24.5）| 评分加分项与企业宣传章 |
| **P2** | 安全质量事故响应表（5.2）台账 | 必填但偏少使用 |

---

## 七、技术标 vs 商务标 覆盖度对比

| 维度 | 技术标（16 章） | 商务标（24 章） |
|---|---|---|
| Longform 完备章数 | 5（8、9、10.1/10.2/10.3，约 215 页）| **0** |
| 短策略章数 | 3（6、12、13）| **0** |
| 大纲注册 | 16/16 | 24/24 |
| 偏差表 | ✅ | ✅（通用） |
| 行业 prompt | 5 套配网专用 | **0 套** |
| 主要缺口 | 行业纵深 + 部分章节模板化 | **几乎全部章节** |

商务标整体成熟度远低于技术标，是当前系统**最大缺口**。

---

## 八、References

- 大纲注册：`backend/tender_backend/services/bid_outline_templates.py:30-91`（SGCC_DISTRIBUTION_BUSINESS_CHAPTERS）
- BusinessBidAssembler：`backend/tender_backend/services/business_bid_assembler.py:19-56`
- 章节策略（技术侧，对照空白）：`backend/tender_backend/services/technical_chapter_strategies/registry.py:302-422`
- DOCX 导出：`backend/tender_backend/services/export_service/docx_exporter.py:82-469`
- 附件嵌入：`backend/tender_backend/services/template_service/package_renderer.py:179-300`
- 数据底座：`backend/tender_backend/db/alembic/versions/0017_company_master_data.py`、`0019_evidence_assets.py`、`0021_template_taxonomy_and_company_libraries.py`、`0040_company_asset_models.py`
- companybase 导入：`backend/tender_backend/services/companybase/companybase_import_service.py:26,185-252`
- 数据库模板：`backend/tender_backend/db/alembic/versions/0043_sgcc_distribution_business_template.py`

---

## 九、修订记录

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| v1.0 | 2026-05-18 | 初版。基于 2026-05-18 仓库代码盘点，对照国网配网商务标 24 章目录输出 gap。|
