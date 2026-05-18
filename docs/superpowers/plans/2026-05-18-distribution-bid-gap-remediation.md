# 2026-05-18 配网工程商技标 Gap 修订计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 2026-05-19 ~ 2026-06-15 窗口内闭环 2026-05-18 两份 gap 报告识别的关键缺口，使 tender 系统具备产出"国网配网工程完整商务标 + 完整技术标"DOCX 的端到端能力；同时清掉 2026-05-17 三份计划遗留中尚未完成的 Track 3 T9 / Track 4 工作。

**Architecture:** 五条 Track 并行。
- **Track A 商务标模板闭环**：补齐样章 DOCX 入库 + `single_docx_section` 渲染 + 章节↔数据源绑定 + 整卷导出
- **Track B 商务标专项台账与正文生成**：6 项缺失专项台账模型 + 4 类承诺/说明文 + 4 个正文型章节
- **Track C 技术标交付闭环加固**：8 章专用生成与交付语义 + 完整 16 章交付验收入口 + 章节级暗标校验
- **Track D 配网行业纵深**：4 业务线切片 + 工序级 spec + 单线图/平面布置图等 5 类缺失 chart_type + companybase 电力枚举
- **Track E 收口 2026-05-17 遗留**：Track 3 T9 真实 50 flow 样本 POC + 30 对盲评、Track 4 综合 e2e + 评标专家盲评

**Tech Stack:** Python（pydantic / pytest / SQLAlchemy / Alembic）、docxtpl、python-docx、PostgreSQL、deepseek-v4-pro/flash、vl-convert / mermaid / @antv/gpt-vis-ssr。

**关联输入文档:**
- `docs/reports/2026-05-18-distribution-business-bid-full-coverage-gap.md`（商务标 24 章 gap v1.2）
- `docs/reports/2026-05-18-distribution-tender-full-coverage-gap.md`（技术标 16 章 gap v1.1）
- `docs/superpowers/plans/2026-05-18-prior-plans-closure.md`（v1.1，Track 3 T9 / Track 4 未完成）
- `docs/superpowers/plans/2026-05-17-chapter-8-followup-quality-roadmap.md`（D-1/D-2/E-5 evidence 待出）
- `docs/plans/2026-05-17-chart-rendering-refactor-plan.md`（v4，改造 2 POC decision 待落）

---

## 当前执行状态（2026-05-18 核查）

| Track | 状态 | 备注 |
|---|---|---|
| Track A 商务标模板闭环 | ⛔ 未启动 | 样章 DOCX 物理文件未入库；importer 多 DOCX 不支持；`single_docx_section` renderer 未实现 |
| Track B 商务标台账与正文 | ⛔ 未启动 | 6 项专项台账无表；4 类承诺函无 context_builder；正文型 4 章无生成路径 |
| Track C 技术标交付闭环 | ⚠️ 部分完成 | 5 章 longform 完备；剩余 8 章缺专用交付语义与验收入口 |
| Track D 配网行业纵深 | ⛔ 未启动 | 5 套通用 prompt 已存在；缺业务线切片、专用 chart_type、companybase 电力枚举 |
| Track E 2026-05-17 遗留收口 | ⚠️ 阻塞 | Track 3 T9 缺真实样本；Track 4 缺真实 project-id + DOCX + 专家评分输入 |

---

## 一、Track A — 商务标模板闭环（P0，预计 1.5 周）

**Goal:** 让 24 章样章 DOCX 真正进入数据库并能按章节渲染输出，BusinessBidAssembler 调 docxtpl 形成整卷交付。

### Task A.1：补齐样章 DOCX 物理文件

**Files:**
- Restore: `docs/samples/sgcc_distribution_business_1_3/*.docx`（3 份）
- Restore: `docs/samples/sgcc_distribution_business_4_24/*.docx`（约 57 份，参考 `manifest.json` 清单）
- Restore: `docs/samples/template_import_ready/sgcc_distribution_business_1_24_package/国网配网工程商务标1-24章.docx`（整卷 60 章）
- Modify: `.gitignore` 增加例外 `!docs/samples/sgcc_distribution_business_*/*.docx`、`!docs/samples/template_import_ready/**/*.docx`

- [ ] **Step 1:** 与用户确认 docx 本体存放位置（本地桌面 / SharePoint / 历史 commit），拷贝到对应目录。
- [ ] **Step 2:** 用 `git check-ignore -v docs/samples/sgcc_distribution_business_1_3/1.商务偏差表.docx` 验证排除规则；按上面修改 `.gitignore` 加白名单。
- [ ] **Step 3:** `git add -f` 三个目录的 docx 文件；Commit：`chore(samples): restore sgcc distribution business 1-24 docx templates`。
- [ ] **Step 4:** 验证：`find docs/samples -name "*.docx" | wc -l` ≥ 60。

### Task A.2：扩展 importer 支持多 DOCX 章节包

**Files:**
- Modify: `backend/tender_backend/services/template_service/package_importer.py:168-234`
- Test: `backend/tests/unit/test_bid_template_package_importer.py`

- [ ] **Step 1:** 写失败测试：`test_import_multi_docx_directory_creates_one_item_per_docx` — 给定目录含 3 个 docx，断言生成 3 个 `bid_template_item` 且 `source_kind='docx'` / `render_mode='single_docx'` / `item_code` 来自文件名前缀（如 `5.1`、`8.1.1`）。
- [ ] **Step 2:** 实现：在 importer 中识别"目录下多 DOCX"模式，按文件名提取 `item_code`（正则 `^(\d+(?:\.\d+){0,2})\.`）；调用 `_extract_placeholders` 抽 `{{ company.* }}` / `{{ asset.* }}` 占位符存入 `placeholder_schema`（若字段不存在则新增 alembic 列）。
- [ ] **Step 3:** 跑：`pytest backend/tests/unit/test_bid_template_package_importer.py -v`，全绿。
- [ ] **Step 4:** Commit：`feat(template-service): importer supports multi-docx chapter package`。

### Task A.3：实现 `single_docx_section` 章节抽取与渲染

**Files:**
- Modify: `backend/tender_backend/services/template_service/docx_renderer.py:339-372`
- Test: `backend/tests/unit/test_template_docx_renderer.py`

- [ ] **Step 1:** 写失败测试：`test_render_single_docx_section_extracts_chapter_by_code` — 给定整卷 docx + `relative_path="国网配网工程商务标1-24章.docx#5.1"`，断言渲染出仅含 5.1 章正文的 docx，且 `{{ company.company_name }}` 已替换。
- [ ] **Step 2:** 实现 `_render_single_docx_section`：用 python-docx 按"标题级别 + 章节号正则"切段，提取目标段落 → 写入临时 docx → DocxTemplate.render(context) → 返回 bytes。
- [ ] **Step 3:** 在 `render_template_item_docx:339-372` 加 `render_mode == "single_docx_section"` 分支。
- [ ] **Step 4:** Commit：`feat(template-service): single_docx_section chapter extraction and render`。

### Task A.4：seed migration 升级商务模板项为 docx

**Files:**
- Create: `backend/tender_backend/db/alembic/versions/0050_sgcc_distribution_business_docx_templates.py`

- [ ] **Step 1:** 新 migration `revises = "<latest>"`，对 `package_key='sgcc_distribution_business_v1'` 下的 `bid_template_item` UPDATE：`source_kind='docx'`、`render_mode='single_docx_section'`、`relative_path='国网配网工程商务标1-24章.docx#{item_code}'`、`filename='国网配网工程商务标1-24章.docx'`。
- [ ] **Step 2:** 跑 `alembic upgrade head`；用 `psql` 抽样查 5 条记录字段。
- [ ] **Step 3:** Commit：`feat(db): migrate sgcc business template items to docx source_kind`。

### Task A.5：章节↔数据源↔渲染器绑定层

**Files:**
- Create: `backend/tender_backend/services/template_service/business_chapter_bindings.py`
- Test: `backend/tests/unit/test_business_chapter_bindings.py`

- [ ] **Step 1:** 定义 `ChapterBinding(chapter_code, context_builder, asset_categories, fallback_chart=None)`，为 24 章逐一登记 context_builder（如章 5.1 → `build_company_basic_info_context(company_id, tender_id)`；章 6.1 → `build_personnel_summary_context(...)`；章 8.x → `build_financial_statement_context(year, statement_type)`；章 12.x → `build_qualification_certificate_context(certificate_type)`）。
- [ ] **Step 2:** 每个 context_builder 写最小单元测试，断言返回 `dict` 含模板 manifest 中声明的所有 `{{ asset.* }}` / `{{ company.* }}` / `{{ tender.* }}` key。
- [ ] **Step 3:** Commit：`feat(template-service): business chapter bindings registry`。

### Task A.6：BusinessBidAssembler 接 docxtpl 渲染

**Files:**
- Modify: `backend/tender_backend/services/business_bid_assembler.py:19-56`
- Test: `backend/tests/integration/test_business_bid_assembler_docx.py`

- [ ] **Step 1:** 写失败 e2e 测试：给定一个 mock company + tender，跑 `BusinessBidAssembler.assemble(...)`，断言每章 `chapter_draft.content_md` 或 `chapter_draft.attachment_bytes` 不为空，且 5.1 章渲染产物含 `company.company_name`。
- [ ] **Step 2:** 在 assembler 中：遍历 24 章 → 查 `business_chapter_bindings.get(chapter_code)` → 调 context_builder → 调 `render_template_item_docx` → 写入 `chapter_draft`（新增 `attachment_bytes` 列或复用 metadata_json）。
- [ ] **Step 3:** Commit：`feat(business-assembler): wire docxtpl rendering to chapter bindings`。

### Task A.7：整卷 DOCX 导出接 package_renderer

**Files:**
- Modify: `backend/tender_backend/services/export_service/docx_exporter.py:460-469`（`_render_plain_docx`）

- [ ] **Step 1:** 在 `_render_plain_docx` 中：若 `chapter_draft.attachment_bytes` 非空，则把该 bytes 合并入主 docx（用 python-docx 的 `Document(BytesIO(...))` 迭代 `paragraphs/tables`）；否则保留原 `content_md` 路径。
- [ ] **Step 2:** 跑回归：`pytest backend/tests/integration/test_docx_export.py -v`。
- [ ] **Step 3:** Commit：`feat(docx-export): merge per-chapter rendered docx into volume`。

### Task A.8：商务标 e2e 验收 + 落 evidence

**Files:**
- Create: `scripts/run_business_bid_acceptance.py`
- Create: `docs/acceptance/2026-05-XX-business-bid-24-chapter-evidence.json`

- [ ] **Step 1:** 脚本：给定 `--project-id` + `--company-id`，调 `BusinessBidAssembler` → `render_volume_docx(volume_type='business')` → 落 docx 到 `outputs/business-bid/{project_id}.docx`，并产 JSON：每章 `rendered=True/False`、`placeholders_filled`、`assets_attached_count`、`size_kb`。
- [ ] **Step 2:** 用一个真实 project + 公司库样本跑，全 24 章 rendered=True。
- [ ] **Step 3:** Commit：`feat(acceptance): business bid 24-chapter e2e script + evidence`。

---

## 二、Track B — 商务标专项台账与正文生成（P0/P1，预计 2 周）

**Goal:** 补 6 项缺失专项台账、4 类承诺/说明文 context_builder、4 个正文型章节生成路径。

### Task B.1：6 项专项台账数据模型

**Files:**
- Create: `backend/tender_backend/db/alembic/versions/0051_business_specialty_ledgers.py`
- Create: `backend/tender_backend/db/models/business_ledgers.py`

- [ ] **Step 1:** 6 张表：`bank_account`（章 10）、`tender_deposit`（章 23.1）、`green_certificate`（章 14）、`tech_achievement`（章 15、17、24.4）、`esg_report`（章 13.x）、`enterprise_award`（章 18，扩 `qualification_certificate.certificate_type='award'` + grade 子枚举）。每张表至少含 `company_id`、`year`、`evidence_asset_id` 外键、`metadata_json`。
- [ ] **Step 2:** 写 fixture 与单元测试覆盖每张表 CRUD。
- [ ] **Step 3:** Commit：`feat(db): six specialty ledgers for business bid`。

### Task B.2：4 类承诺/说明文 context_builder

**Files:**
- Modify: `backend/tender_backend/services/template_service/business_chapter_bindings.py`

- [ ] **Step 1:** 实现：`build_no_violation_commitment_context`（章 2）、`build_sgcc_personnel_relation_context`（章 7）、`build_company_name_change_context`（章 20）、`build_small_taxpayer_context`（章 21）。变量：`tender.purchaser_name` / `company.company_name` / `company.legal_representative` / `commit_date` / `signature_block`。
- [ ] **Step 2:** 写测试：4 类模板各跑一次，断言生成的 docx 含全部变量。
- [ ] **Step 3:** Commit：`feat(business-bindings): commitment letter context builders`。

### Task B.3：companybase 财务 + 6 张专项 sheet 接入

**Files:**
- Modify: `backend/tender_backend/services/companybase_import_service.py:26`（`MVP_SHEETS`）

- [ ] **Step 1:** 把 `MVP_SHEETS` 扩到包含：`财务报表`、`银行账户`、`保证金`、`绿证`、`科技成果`、`ESG`、`奖项`。每 sheet 一个 parser/validator。
- [ ] **Step 2:** 用样例 xlsx 写集成测试。
- [ ] **Step 3:** Commit：`feat(companybase): import financial and six specialty sheets`。

### Task B.4：4 个正文型章节生成（章 11/13.1/15/17/24.5）

**Files:**
- Create: `backend/tender_backend/services/business_text_generators.py`

- [ ] **Step 1:** 复用 `technical_bid_writer` AI gateway，加 4 个 prompt：绿色发展规划、ESG 报告（摘要）、科技成果（摘要）、研发团队介绍、综合实力。Prompt 输入：companybase 数据 + 招标文件评分点。
- [ ] **Step 2:** 在 chapter binding 中将这 4 章 `context_builder` 指向 `business_text_generators`。
- [ ] **Step 3:** Commit：`feat(business): narrative chapter generators for 11/13.1/15/17/24.5`。

### Task B.5：商务/技术偏差表分离 + 三栏页眉 + 骑缝章

**Files:**
- Modify: `backend/tender_backend/api/deviation_table.py`、`services/export_service/docx_exporter.py:183, 211-247`

- [ ] **Step 1:** 在 `deviation_table` metadata 加 `volume_type ∈ {business, technical}`；UI/API 校验。
- [ ] **Step 2:** 页眉改为三栏：左 `投标人={{ company.company_name }}` / 中 `{{ tender.project_name }}` / 右 `{{ volume_label }}`。
- [ ] **Step 3:** 在每章末加骑缝章占位段落（设置段落属性 `keep_with_next=True`，写"骑缝章位置"文本框）。
- [ ] **Step 4:** Commit：`feat(docx-export): separate deviation tables + tri-column header + crimped seal placeholder`。

---

## 三、Track C — 技术标交付闭环加固（P0，预计 1 周）

**Goal:** 让 16 章中 8 章缺专用交付语义的章（2/3/7/11/14/15/16；6 章 longform 升级）落地，并建立完整 16 章交付验收入口。

### Task C.1：技术标 8 章专用交付语义

**Files:**
- Modify: `backend/tender_backend/services/technical_chapter_strategies/registry.py:302-422`

- [ ] **Step 1:** 为章 2（监理人员合规承诺函）、3（工期响应）、7（其他资格条件）、11（服务承诺）、14（履约评价证明材料）、15（其他）、16（履约承诺函）加 `TechnicalChapterStrategy` 条目；前置事实、模板路径、required_charts、self_check_rules 仿照 8/9。
- [ ] **Step 2:** 章 6（项目团队情况）从短策略升级为 longform，新增 SECTION_WEIGHTS / DEFAULT_CHARTS。
- [ ] **Step 3:** Commit：`feat(tech-strategies): wire 8 missing chapters with delivery semantics`。

### Task C.2：完整 16 章交付验收入口

**Files:**
- Create: `scripts/run_technical_bid_full_acceptance.py`

- [ ] **Step 1:** 入参 `--project-id`；遍历 16 章 → 检查 `chapter_draft` 存在 + 附件绑定 + 签章/承诺函模板 + 暗标风险扫描 + 页数/图表/表格占位 + 导出结果非空。
- [ ] **Step 2:** 产 JSON evidence：每章 5 维度通过/失败 + 阻塞清单。
- [ ] **Step 3:** Commit：`feat(acceptance): technical bid 16-chapter full acceptance entrypoint`。

### Task C.3：章节级暗标校验扩展

**Files:**
- Modify: `backend/tender_backend/services/longform/longform_quality.py`（或对应暗标过滤模块）

- [ ] **Step 1:** 把当前 longform 5 章的暗标过滤规则（公司名/项目名/日期等敏感词）扩到全 16 章 + 商务 24 章。
- [ ] **Step 2:** 写测试覆盖 8 个新增章节场景。
- [ ] **Step 3:** Commit：`feat(quality): blind-bid filter covers all chapters in both volumes`。

---

## 四、Track D — 配网行业纵深（P1，预计 2 周）

**Goal:** 补 4 业务线切片 + 工序级 spec + 5 类缺失 chart_type + companybase 电力枚举。

### Task D.1：4 业务线 sub-section 切片

**Files:**
- Modify: `backend/tender_backend/services/technical_chapter_strategies/registry.py:45-61`（CHAPTER_8_SECTIONS）

- [ ] **Step 1:** 在 8.4"主要施工方法及技术要求"下增 4 个工序子节：8.4.1 架空线、8.4.2 电缆、8.4.3 配电站房、8.4.4 台区改造；各含基础/电杆组立/架线/电缆敷设（直埋/排管/拉管/顶管）/接地/调试 SOP。
- [ ] **Step 2:** 配套 prompt 与 fixture。
- [ ] **Step 3:** Commit：`feat(tech-strategies): four distribution business line workflow slices`。

### Task D.2：5 类缺失 chart_type

**Files:**
- Modify: `backend/tender_backend/services/chart_service/specs.py`、`vega_mapper.py`、`render_strategy.py`、`renderers.py`

- [ ] **Step 1:** 新增 spec：`single_line_diagram`（单线图）、`site_layout`（平面布置图）、`outage_timeline`（停电窗口时序图）、`wbs_tree`（WBS）、`fmea_matrix`（FMEA）。
- [ ] **Step 2:** 各类挑一个渲染路径：单线图/平面布置图用 vl_convert+vega-lite；停电时序用甘特扩展；WBS 用 mermaid；FMEA 用矩阵复用。
- [ ] **Step 3:** 写 fixture + 单元测试。
- [ ] **Step 4:** Commit：`feat(chart): add 5 distribution-specific chart types`。

### Task D.3：companybase 电力施工资质 + 业绩字段

**Files:**
- Modify: `backend/tender_backend/db/models/qualification_certificate.py`、`project_performance.py`

- [ ] **Step 1:** `certificate_type` 加枚举：`承装电力设施许可证`、`承修电力设施许可证`、`承试电力设施许可证`、`输变电专业承包`、`电力工程总承包`；加 `grade ∈ {一级,二级,三级,四级,五级}`。
- [ ] **Step 2:** `project_performance` 加字段：`voltage_level_kv`、`circuit_count`、`capacity_mva`、`distribution_type ∈ {overhead, cable, mixed, substation, taiqu}`、`is_live_work`。
- [ ] **Step 3:** Migration + 测试。
- [ ] **Step 4:** Commit：`feat(companybase): power industry qualification enums + performance fields`。

### Task D.4：不停电作业 / 配网自动化 / 停电窗口 数据模型

**Files:**
- Create: `backend/tender_backend/db/models/outage_window.py`、`live_work_plan.py`、`distribution_automation.py`

- [ ] **Step 1:** 3 个领域模型：`outage_window(start_time, end_time, circuit_id, affected_users, ...)`、`live_work_plan(method, equipment, risk_level, ...)`、`distribution_automation(terminal_count, comm_link_type, commissioning_cases, ...)`。
- [ ] **Step 2:** 接入相关章节 binding。
- [ ] **Step 3:** Commit：`feat(domain): outage/live-work/automation data models`。

---

## 五、Track E — 收口 2026-05-17 遗留（与 Track A-D 并行）

**Goal:** 在 Track A/C 完成到一定阶段后，跑通 2026-05-17 三份计划遗留的 Track 3 T9 与 Track 4 e2e + 盲评。

### Task E.1：Track 3 T9 真实样本 POC（50 flow + 50 gantt）

**Files:**
- Use: `backend/scripts/run_gpt_vis_poc.py`（2026-05-18 已创建）
- Create: `docs/acceptance/2026-05-XX-gpt-vis-poc-evidence.json`
- Create: `docs/reports/2026-05-XX-gpt-vis-poc-report.md`

- [ ] **Step 1:** 从历史项目 chart_assets 抽 50 flow + 50 gantt 真实 spec。
- [ ] **Step 2:** 双引擎跑（mermaid_sidecar / gpt_vis），落 SVG + 量化指标（T16 5 项）。
- [ ] **Step 3:** 业务方盲评 30 对（A/B 双盲）。
- [ ] **Step 4:** 写报告 + decision = adopt/reject。
- [ ] **Step 5:** 若 reject 执行容器下线。
- [ ] **Step 6:** Commit。

### Task E.2：Track 4.1 第 8 章 final e2e

**前置:** Track A.8 完成（真实 project_id 可用）

- [ ] **Step 1:** 跑 `scripts/run_chapter_8_acceptance.py --project-id <真实> --target-pages 100`。
- [ ] **Step 2:** 落 `docs/acceptance/2026-05-XX-chapter-8-followup-final-evidence.json`。

### Task E.3：Track 4.2 第 9/10.1/10.2/10.3 章 longform e2e

- [ ] **Step 1:** 跑 `scripts/run_longform_multi_chapter_acceptance.py --project-id <真实> --chapters 8,9,10.1,10.2,10.3`。
- [ ] **Step 2:** 落 evidence JSON。

### Task E.4：Track 4.3 评标专家盲评

- [ ] **Step 1:** 选 3 个真实项目（含 1 暗标）的完整商务+技术标 DOCX（已由 Track A.8 + C.2 产出）。
- [ ] **Step 2:** 评标专家盲评 4 维（篇幅完整/专业表现/图表可读/暗标合规），各 1~5 分。
- [ ] **Step 3:** 落 `docs/reviews/2026-05-XX-followup-blind-review.md`。

### Task E.5：Followup Roadmap + longform-launch-closure 收口

- [ ] **Step 1:** 把 Followup Roadmap D-1/D-2/E-5 全部 `- [x]`，追加 v1.4。
- [ ] **Step 2:** 在 `2026-05-15-longform-launch-closure.md` 追加 Phase 2 Final Decision。

---

## 六、依赖图

```
Track A 商务标模板闭环 ────┐
  A.1 docx 入库 ─→ A.2 多 DOCX importer ─→ A.3 section renderer
  ─→ A.4 migration ─→ A.5 bindings ─→ A.6 assembler ─→ A.7 export
  ─→ A.8 商务 e2e
                          │
Track B 商务台账与正文 ────┤ (B 可与 A.5 并行启动)
  B.1 6 表 ─→ B.2 承诺函 builders ─→ B.3 companybase 扩 sheet
  ─→ B.4 4 章正文 ─→ B.5 偏差表分离+页眉+骑缝
                          │
Track C 技术标交付闭环 ────┤ (与 A/B 完全并行)
  C.1 8 章策略 ─→ C.2 技术 e2e ─→ C.3 暗标校验扩展
                          │
Track D 配网行业纵深 ─────┤ (低耦合，与 A/B/C 并行)
  D.1 业务线切片 ─→ D.2 5 类 chart ─→ D.3 companybase 电力枚举 ─→ D.4 领域模型
                          │
Track E 2026-05-17 遗留 ──┘
  E.1 GPT-Vis POC (独立)
  E.2 ←── blockedBy A.8 + C.2 (需真实 project_id 与 DOCX)
  E.3 ←── blockedBy C.2
  E.4 ←── blockedBy E.2 + E.3 (盲评对象齐全)
  E.5 ←── blockedBy E.1 + E.4
```

**6 个立即可开工的起点（可并行）:**
- A.1（待用户提供 docx）
- B.1 / B.3（独立 DB 与 import 工作）
- C.1 / C.3（纯代码）
- D.1 / D.2 / D.3 / D.4（独立领域工作）
- E.1（GPT-Vis-SSR POC 独立）

---

## 七、Success Criteria（hard stop）

- [ ] **Track A:** 24 章 docx 入库 + `single_docx_section` 渲染单元测试全绿 + `run_business_bid_acceptance.py` 在一个真实 project 上产出 24 章 rendered=True 的整卷 DOCX
- [ ] **Track B:** 6 张专项台账表 migration upgrade head 成功 + 4 类承诺函 context_builder 单元测试全绿 + 4 个正文章节在 e2e 中生成 ≥3000 字
- [ ] **Track C:** 16 章 technical strategy 全部注册 + `run_technical_bid_full_acceptance.py` 5 维门禁通过率 ≥ 90% + 暗标校验覆盖 16+24 章
- [ ] **Track D:** 5 类新 chart_type 单元测试全绿 + companybase 电力枚举 + 业绩字段 migration 上线 + 4 业务线 fixture 真实样例 ≥1 套/线
- [ ] **Track E:** GPT-Vis POC decision 落定 + 三份 evidence（chapter-8 final / longform 8-9-10 / blind-review）归档 + Followup Roadmap v1.4 收口

---

## 八、Risk Controls

- [ ] **Track A.1:** docx 物理文件可能涉及客户敏感样章。入库前确认无客户名/项目名/法人姓名残留（用 `python-docx` 扫文本）；必要时脱敏后入库。
- [ ] **Track A.2/A.3:** importer 与 renderer 改动会影响现有 mermaid/sidecar 包；变更前跑 `pytest backend/tests/integration/test_template_*` 基线。
- [ ] **Track A.4:** migration 升级 `source_kind` 是不可回滚操作；务必写 downgrade。
- [ ] **Track A.6/A.7:** assembler/exporter 改动需保证旧 `content_md` 渲染路径仍可用，灰度开关 env `BUSINESS_BID_DOCXTPL_ENABLED=False`，默认关。
- [ ] **Track B.1:** 6 张新表上线前先用 fixture 跑 alembic up/down 两次。
- [ ] **Track D.3:** `certificate_type` / `distribution_type` 枚举从字符串收紧为 enum 会破坏旧数据；先 migration 软迁移（保留兼容字段），下版再硬切。
- [ ] **Track E.1:** GPT-Vis-SSR 容器资源占用，若 reject 立即下线。
- [ ] **Track E.2/E.3:** 真实 project 数据敏感，evidence JSON 落档前确认无 PII。

---

## 九、Reporting Cadence

- [ ] 每完成 1 个 Task：勾选 + commit message 带 `[GAP-FIX-<Track>-<Task#>]`
- [ ] 每完成 1 个 Track：在本文件 § 修订记录 追加完成日期与 commit hash
- [ ] 整体完成：在 `docs/reports/2026-05-18-distribution-tender-full-coverage-gap.md` 与 `2026-05-18-distribution-business-bid-full-coverage-gap.md` 各追加 "v2.0 — gap 闭环" 段，引用本计划

---

## 十、修订记录

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| v1.0 | 2026-05-18 | 初版。基于 2026-05-18 两份 gap 报告（商务标 24 章 + 技术标 16 章）与 2026-05-17 三份计划遗留，编制五条 Track 修订计划。|
