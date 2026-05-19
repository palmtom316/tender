# 2026-05-18 配网工程商技标 Gap 修订计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 2026-05-19 ~ 2026-06-15 窗口内闭环 2026-05-18 两份 gap 报告识别的关键缺口，使 tender 系统具备产出"国网配网工程完整商务标 + 完整技术标"DOCX 的端到端能力；同时清掉 2026-05-17 三份计划遗留中尚未完成的 Track 3 T9 / Track 4 工作。

**Architecture:** 五条 Track 并行，但 P0 主链路调整为当前代码已经支持的"统一单 DOCX 样章导入 + `single_docx_section` 章节渲染 + 商务整卷导出"。商务标现状不是 docxtpl 管线完整，而是 importer 已能从单 DOCX 标题拆出 `single_docx_section` 模板项，renderer/exporter/assembler 尚未打通；多 DOCX 目录包仍被 importer 明确拒绝，作为 P1 扩展而非 P0 前置。

**Tech Stack:** Python（pydantic / pytest / SQLAlchemy / Alembic）、docxtpl、python-docx、PostgreSQL、deepseek-v4-pro/flash、vl-convert / mermaid / @antv/gpt-vis-ssr。

**关联输入文档:**
- `docs/reports/2026-05-18-distribution-business-bid-full-coverage-gap.md`（商务标 24 章 gap v1.2）
- `docs/reports/2026-05-18-distribution-tender-full-coverage-gap.md`（技术标 16 章 gap v1.1）
- `docs/superpowers/plans/2026-05-18-prior-plans-closure.md`（v1.1，Track 3 T9 / Track 4 未完成）
- `docs/superpowers/plans/2026-05-17-chapter-8-followup-quality-roadmap.md`（D-1/D-2/E-5 evidence 待出）
- `docs/plans/2026-05-17-chart-rendering-refactor-plan.md`（v4，改造 2 POC decision 待落）

---

## 0. 审查结论与修订原则

本次核查以现有代码为准，原计划有 7 类需要修订的问题：

- `package_importer.py` 当前只接受单 DOCX；目录内多 DOCX 会报错"Single-DOCX template packages are required"。因此 P0 不应依赖多 DOCX importer，P1 才扩展多 DOCX。
- importer 已能把单 DOCX 标题拆成 `render_mode="single_docx_section"`、`relative_path="docx#code"` 的模板项；真正 P0 blocker 是 `docx_renderer.py` 没有处理 `single_docx_section`，会落到泛化表格/上下文渲染。
- `docx_renderer.py` 当前只把 `single_docx` / `document` 送入 DocxTemplate，且 `_resolve_item_template_path` 不能直接处理带 `#` 的 `relative_path`；章节渲染必须先拆分 `docx_path` 与 `chapter_code`。
- `BusinessBidAssembler` 目前只返回 chapters / response matrix / missing materials / run，不会调用 docxtpl，也不会写 `chapter_draft`。
- `chapter_draft` 没有 `attachment_bytes`，当前也没有 `metadata_json`；0056 增加的是 longform evidence 字段，`metadata_json` 加在 `export_record` 上。二进制 DOCX 不应塞入草稿表，需新增明确命名的 `rendered_docx_path` / `rendered_artifact_json` 列或独立 artifact 表。
- Alembic 版本当前已到 `0056_longform_generation_evidence.py`；原计划中的 `0050_*` / `0051_*` 文件名已被占用，必须从当前 head 后创建下一版本。
- 技术标/验收路径需修正：暗标质量模块是 `backend/tender_backend/services/longform_quality.py`；`scripts/run_longform_multi_chapter_acceptance.py` 使用重复 `--chapter-code`，不是 `--chapters`。

后续实施必须遵循两条硬约束：

- 未经脱敏或用户明确批准，不提交原始客户 DOCX 样章；样章入库前必须扫描公司名、项目名、法人、手机号、身份证号等敏感文本。
- P0 只打通统一单 DOCX 商务样章闭环；多 DOCX 目录包、无损 DOCX 合并、额外领域数据模型作为 P1/P2，不阻塞首个可验收整卷。

---

## 当前执行状态（2026-05-18 核查）

| Track | 状态 | 修订后判断 |
|---|---|---|
| Track A 商务标模板闭环 | ⛔ 未闭环 | 单 DOCX importer 基础已具备；缺 `single_docx_section` renderer、BusinessBidAssembler 写草稿、整卷导出读取渲染产物 |
| Track B 商务标台账与正文 | ⛔ 未启动 | companybase MVP 只导入 `公司主体/公司资料/人员资料/附件索引`；财务与专项 sheet 未接入 |
| Track C 技术标交付闭环 | ⚠️ 部分完成 | 5 章 longform 完备；非 longform 章节有通用 fallback，但缺承诺函/证照/人员附件等专用交付语义 |
| Track D 配网行业纵深 | ⛔ 未启动 | 5 套通用 prompt 已存在；缺业务线切片、专用 chart_type、companybase 电力枚举 |
| Track E 2026-05-17 遗留收口 | ⚠️ 阻塞 | Track 3 T9 缺真实样本；Track 4 缺真实 project-id + DOCX + 专家评分输入 |

---

## 一、Track A - 商务标模板闭环（P0，预计 1.5 周）

**Goal:** 基于统一单 DOCX 样章，使 24 章模板项可按章节抽取、渲染、记录为草稿 artifact，并能导出可验收的商务整卷 DOCX。

### Task A.1：补齐统一单 DOCX 样章文件

**Files:**
- Restore: `docs/samples/template_import_ready/sgcc_distribution_business_1_24_package/国网配网工程商务标1-24章.docx`
- Review: `docs/samples/template_import_ready/sgcc_distribution_business_1_24_package/manifest.json`
- Modify only if approved: `.gitignore`

- [ ] **Step 1:** 与用户确认 `国网配网工程商务标1-24章.docx` 来源位置和脱敏状态。若样章含客户真实信息，先生成脱敏副本，不提交原件。
- [ ] **Step 2:** 用 `python-docx` 扫描样章全文，至少检查公司名、项目名、法人、手机号、身份证号、统一社会信用代码等敏感模式；把扫描摘要落入本地 evidence，不把敏感文本写入仓库。
- [ ] **Step 3:** 将脱敏后的统一单 DOCX 放入 `docs/samples/template_import_ready/sgcc_distribution_business_1_24_package/`，核对 `manifest.json` 中声明的文件名与实际文件一致。
- [ ] **Step 4:** 若 `.gitignore` 排除了该路径，只为脱敏样章增加最小白名单；不对 `docs/samples/**/*.docx` 做宽泛放行。
- [ ] **Step 5:** 验证：`find docs/samples/template_import_ready/sgcc_distribution_business_1_24_package -maxdepth 1 -name "*.docx" -print` 只显示已脱敏的统一样章。

### Task A.2：稳定单 DOCX import，保留多 DOCX 明确错误

**Files:**
- Modify: `backend/tender_backend/services/template_service/package_importer.py`
- Test: `backend/tests/unit/test_bid_template_package_importer.py`

- [x] **Step 1:** 写失败测试 `test_import_single_docx_creates_section_items_with_docx_anchor`：给定单 DOCX 包，断言生成的模板项包含 `source_kind="docx"`、`render_mode="single_docx_section"`、`relative_path="<docx>#<chapter_code>"`。
- [x] **Step 2:** 写回归测试 `test_import_multi_docx_directory_returns_clear_error`：给定目录含 2 个 DOCX，断言抛出包含"Single-DOCX template packages are required"的错误。该测试固定当前 P0 边界，避免误以为多 DOCX 已支持。
- [x] **Step 3:** 如标题识别漏掉商务 1-24 章中的合法标题，只调整 `_docx_heading_match` 的章节号识别规则，并保留对正文编号条款的过滤。
- [x] **Step 4:** 跑：`pytest backend/tests/unit/test_bid_template_package_importer.py -v`。

### Task A.3：实现 `single_docx_section` 章节抽取与渲染

**Files:**
- Modify: `backend/tender_backend/services/template_service/docx_renderer.py`
- Test: `backend/tests/unit/test_template_docx_renderer.py`

- [x] **Step 1:** 写失败测试 `test_render_single_docx_section_splits_relative_path_anchor`：构造 `relative_path="国网配网工程商务标1-24章.docx#5.1"`，断言 renderer 会拆分出 `docx_path` 与 `chapter_code`，不会把带 `#` 的字符串直接传给路径解析。
- [x] **Step 2:** 写失败测试 `test_render_single_docx_section_extracts_target_chapter_only`：给定包含 `5.1` 与 `5.2` 的样章，渲染 `#5.1` 后输出只包含 5.1 段落，不包含 5.2 标题。
- [x] **Step 3:** 实现 `_render_single_docx_section_template(conn, item, context, output_dir, output_filename)`：按 `relative_path` 拆分 anchor；解析源 DOCX 的段落与表格；从目标章节标题开始，到下一同级或上级章节标题前结束；生成临时 DOCX 后再执行 DocxTemplate.render(context)。
- [x] **Step 4:** 在 `render_template_item_docx` 中把 `item.render_mode == "single_docx_section"` 接入新分支；保留 `single_docx` / `document` 既有行为。
- [x] **Step 5:** 跑：`pytest backend/tests/unit/test_template_docx_renderer.py -v`。

### Task A.4：商务模板项导入/升级为单 DOCX section

**Files:**
- Use: existing package import API/script path for `bid_template_package`
- Create only if needed: `backend/tender_backend/db/alembic/versions/<next>_sgcc_distribution_business_docx_templates.py`

- [ ] **Step 1:** 优先通过现有 template package import 流程重新导入 `sgcc_distribution_business_v1`，使数据库中的 `bid_template_item` 来自单 DOCX 标题拆分结果。
- [ ] **Step 2:** 若必须用 migration 更新 seed 数据，版本号必须从当前 Alembic head 后创建；当前核查 head 为 `0056_longform_generation_evidence.py`，不得创建 `0050_*` 或 `0051_*`。
- [ ] **Step 3:** migration 不得无条件把所有商务项改为 DOCX；必须先检查目标样章文件存在，或只更新已确认属于 `sgcc_distribution_business_v1` 且 `item_code` 能在单 DOCX 中匹配到的记录。
- [ ] **Step 4:** 验证抽样 SQL：`source_kind='docx'`、`render_mode='single_docx_section'`、`relative_path` 形如 `国网配网工程商务标1-24章.docx#5.1`。

### Task A.5：章节与上下文绑定层

**Files:**
- Create: `backend/tender_backend/services/template_service/business_chapter_bindings.py`
- Test: `backend/tests/unit/test_business_chapter_bindings.py`

- [x] **Step 1:** 定义 `ChapterBinding(chapter_code, context_builder, asset_categories, narrative_generator=None)`，为 24 章建立最小可运行映射。
- [x] **Step 2:** 先覆盖已存在主数据：公司主体、人员资料、公司资料、附件索引、资质证书、业绩、财务附件；缺失专项台账的章节返回明确 `missing_materials`，不得伪造数据。
- [x] **Step 3:** 每个 context builder 单测断言返回 dict 中包含模板占位符需要的 `company`、`tender`、`asset` 等顶层 key；缺失数据以结构化缺口返回。
- [x] **Step 4:** 跑：`pytest backend/tests/unit/test_business_chapter_bindings.py -v`。

### Task A.6：BusinessBidAssembler 接入 docxtpl 渲染并记录 artifact

**Files:**
- Create: `backend/tender_backend/db/alembic/versions/<next>_chapter_draft_rendered_artifacts.py`
- Modify: `backend/tender_backend/services/business_bid_assembler.py`
- Test: `backend/tests/integration/test_business_bid_assembler_docx.py`

- [x] **Step 1:** 写失败测试：给定 mock project/company/template item，调用 `BusinessBidAssembler.assemble(...)` 后，断言每个可渲染章节会 upsert 一条 `chapter_draft(volume_type='business')`。
- [x] **Step 2:** 新 migration 给 `chapter_draft` 增加 `rendered_docx_path TEXT`、`rendered_artifact_json JSONB NOT NULL DEFAULT '{}'::jsonb`；不新增 `attachment_bytes`，也不假设已有 `chapter_draft.metadata_json`。
- [x] **Step 3:** 渲染出的 DOCX 文件写入受控输出目录，`chapter_draft.content_md` 写入章节摘要/占位状态，`rendered_docx_path` 写文件路径，`rendered_artifact_json` 写 `template_item_id`、`render_mode`、`missing_materials`、`placeholder_status`。
- [x] **Step 4:** 增加灰度开关 `BUSINESS_BID_DOCXTPL_ENABLED`，默认先关闭；测试中显式打开。关闭时保留当前 response matrix / missing materials 行为。
- [x] **Step 5:** 跑 migration up/down 与 `pytest backend/tests/integration/test_business_bid_assembler_docx.py -v`。

### Task A.7：商务整卷 DOCX 导出读取章节 artifact

**Files:**
- Modify: `backend/tender_backend/services/export_service/docx_exporter.py`
- Test: `backend/tests/integration/test_docx_export.py`

- [x] **Step 1:** `_load_chapter_drafts` 增加读取 `cd.rendered_docx_path`、`cd.rendered_artifact_json`。
- [x] **Step 2:** `_render_plain_docx` 在 `volume_type='business'` 且 `rendered_docx_path` 存在时，按章节顺序把渲染产物合并进整卷；缺失 artifact 时继续使用 `content_md` 路径并在导出日志/evidence 中记录 warning。
- [x] **Step 3:** 明确 python-docx 合并是 MVP：段落/表格基础内容可合并，但页眉页脚、复杂样式、图片锚定不保证完全无损。若验收要求保真，另起 P1 使用 OpenXML package 级合并或输出章节 DOCX zip 包。
- [x] **Step 4:** 将 `_should_include_personnel_table(volume_type)` 调整为业务分册也可注入人员表，或在商务导出路径通过 artifact 自带人员表，避免章 6 只有技术标人员表。
- [x] **Step 5:** 跑：`pytest backend/tests/unit/test_docx_exporter.py -v`（当前仓库无 `backend/tests/integration/test_docx_export.py`，使用既有 DOCX exporter 回归测试文件）。

### Task A.8：商务标 e2e 验收与 evidence

**Files:**
- Create: `scripts/run_business_bid_acceptance.py`
- Create: `docs/acceptance/2026-05-XX-business-bid-24-chapter-evidence.json`

- [ ] **Step 1:** 脚本入参：`--project-id`、`--company-id`、`--output-dir`、`--enable-docxtpl`。
- [ ] **Step 2:** 脚本执行：打开灰度开关 -> `BusinessBidAssembler.assemble(...)` -> `render_volume_docx(volume_type='business')` -> 输出 DOCX。
- [ ] **Step 3:** evidence JSON 至少包含每章 `chapter_code`、`rendered`、`rendered_docx_path`、`missing_material_count`、`placeholder_unfilled_count`、`size_kb`。
- [ ] **Step 4:** hard stop：24 章均有章节记录，关键章节 1/2/5/6/8/10/23/24 无未填占位符，整卷 DOCX 非空且可由 python-docx 打开。

---

## 二、Track B - 商务标专项台账与正文生成（P0/P1，预计 2 周）

**Goal:** 补齐商务标全章闭环所需的财务、资质、奖项、承诺函、说明文和正文生成能力；首轮以不破坏 companybase MVP 为约束。

### Task B.1：专项台账 schema 与 repository

**Files:**
- Create: `backend/tender_backend/db/alembic/versions/<next>_business_specialty_ledgers.py`
- Modify: `backend/tender_backend/db/repositories/master_data_repo.py`
- Test: `backend/tests/unit/test_master_data_repo.py`

- [ ] **Step 1:** 从当前 Alembic head 后创建下一版本，不使用已占用的 `0051_project_template_instances.py`。
- [ ] **Step 2:** 新增或扩展 6 类专项数据：银行账户、保证金、绿证、科技成果、ESG 报告、企业奖项。每类至少含 `company_id/company_key`、`year`、`evidence_asset_id` 或 `metadata_json.evidence_asset_ids`、`metadata_json`。
- [ ] **Step 3:** repository 层遵循现有 `master_data_repo.py` dataclass + SQL 风格；当前仓库没有独立 `db/models/*.py` 实体，不新建不存在的 ORM 模型目录作为主路径。
- [ ] **Step 4:** 写 CRUD 单测并跑：`pytest backend/tests/unit/test_master_data_repo.py -v`。

### Task B.2：4 类承诺/说明文 context builder

**Files:**
- Modify: `backend/tender_backend/services/template_service/business_chapter_bindings.py`
- Test: `backend/tests/unit/test_business_chapter_bindings.py`

- [ ] **Step 1:** 实现 `build_no_violation_commitment_context`（章 2）、`build_sgcc_personnel_relation_context`（章 7）、`build_company_name_change_context`（章 20）、`build_small_taxpayer_context`（章 21）。
- [ ] **Step 2:** 上下文字段固定为 `tender.purchaser_name`、`tender.project_name`、`company.company_name`、`company.legal_representative`、`commit_date`、`signature_block`；缺失值必须进入 `missing_materials`。
- [ ] **Step 3:** 单测覆盖 4 类 builder 的完整数据与缺失数据场景。

### Task B.3：companybase 财务与专项 sheet 接入

**Files:**
- Modify: `backend/tender_backend/services/companybase_import_service.py`
- Test: `backend/tests/integration/test_companybase_import_service.py`

- [ ] **Step 1:** 现状 `MVP_SHEETS={"公司主体","公司资料","人员资料","附件索引"}`。新增 sheet 必须保持旧 MVP sheet 行为不变。
- [ ] **Step 2:** 分批接入 `财务报表`、`银行账户`、`保证金`、`绿证`、`科技成果`、`ESG`、`奖项` parser/validator。
- [ ] **Step 3:** 如果当前系统已有财务 API 或附件能力，仅在 importer 中建立映射，不重复发明平行数据源。
- [ ] **Step 4:** 用样例 xlsx 跑集成测试，断言旧 4 sheet + 新 sheet 可同时导入。

### Task B.4：正文型章节生成

**Files:**
- Create: `backend/tender_backend/services/business_text_generators.py`
- Modify: `backend/tender_backend/services/template_service/business_chapter_bindings.py`
- Test: `backend/tests/unit/test_business_text_generators.py`

- [ ] **Step 1:** 为章 11、13.1、15、17、24.5 定义生成器；输入为 companybase 数据、招标文件评分点、章节模板要求。
- [ ] **Step 2:** 复用现有 AI gateway/technical writer 调用模式，输出结构为 `{"content_md": "...", "evidence_refs": [...], "missing_materials": [...]}`。
- [ ] **Step 3:** 单测使用 fake gateway，断言 prompt 不泄露暗标敏感字段，且缺失材料不会被模型编造。

### Task B.5：商务/技术偏差表分离、页眉与骑缝章占位

**Files:**
- Modify: `backend/tender_backend/api/deviation_table.py`
- Modify: `backend/tender_backend/services/export_service/docx_exporter.py`
- Test: `backend/tests/integration/test_docx_export.py`

- [ ] **Step 1:** 在 deviation table metadata 或持久化字段中区分 `volume_type in {"business","technical"}`；API 校验非法值。
- [ ] **Step 2:** 页眉改为三栏：左 `投标人={{ company.company_name }}`，中 `{{ tender.project_name }}`，右 `{{ volume_label }}`。
- [ ] **Step 3:** 每章末尾增加骑缝章占位段落；不使用会破坏 Word 兼容性的浮动文本框作为 P0。
- [ ] **Step 4:** 回归 business/technical 两个分册导出。

---

## 三、Track C - 技术标交付闭环加固（P0，预计 1 周）

**Goal:** 补齐非 longform 章节的专用交付语义，建立完整 16 章验收入口，并把暗标校验扩到全分册。

### Task C.1：技术标非 longform 章节专用交付语义

**Files:**
- Modify: `backend/tender_backend/services/technical_chapter_strategies/registry.py`
- Test: `backend/tests/unit/test_technical_chapter_strategies.py`

- [ ] **Step 1:** 为章 2、3、7、11、14、15、16 建立专用 strategy：前置事实、模板/附件要求、required_assets、self_check_rules。
- [ ] **Step 2:** 章 6 优先补项目团队人员、证书、任命/承诺附件装配和验收规则；是否升级 longform 作为 P1 决策，不作为本轮 P0 blocker。
- [ ] **Step 3:** 单测断言 16 章均能从 registry 查到 strategy，且 2/3/7/11/14/15/16 不再只依赖泛化 fallback。

### Task C.2：完整 16 章交付验收入口

**Files:**
- Create: `scripts/run_technical_bid_full_acceptance.py`
- Test: `backend/tests/integration/test_technical_bid_full_acceptance.py`

- [ ] **Step 1:** 入参 `--project-id`、`--output-dir`；遍历 16 章检查 `chapter_draft`、附件绑定、签章/承诺函模板、暗标风险、页数/图表/表格占位。
- [ ] **Step 2:** 输出 JSON evidence：每章 `draft_exists`、`required_assets_ready`、`blind_check_passed`、`charts_ready`、`export_ready`。
- [ ] **Step 3:** hard stop：16 章均有结果；P0 章节失败时脚本返回非 0。

### Task C.3：章节级暗标校验扩展

**Files:**
- Modify: `backend/tender_backend/services/longform_quality.py`
- Test: `backend/tests/unit/test_longform_quality.py`

- [ ] **Step 1:** 将公司名、项目名、法人、联系方式、具体日期等敏感词规则扩到技术 16 章与商务 24 章。
- [ ] **Step 2:** 暗标规则作为可配置输入，不在代码中硬编码真实客户名称。
- [ ] **Step 3:** 写测试覆盖新增章节与商务承诺函场景。

---

## 四、Track D - 配网行业纵深（P1，预计 2 周）

**Goal:** 补 4 业务线切片、工序级 spec、5 类缺失 chart_type、companybase 电力施工枚举和专项领域数据。

### Task D.1：4 业务线 sub-section 切片

**Files:**
- Modify: `backend/tender_backend/services/technical_chapter_strategies/registry.py`
- Test: `backend/tests/unit/test_technical_chapter_strategies.py`

- [ ] **Step 1:** 在 8.4"主要施工方法及技术要求"下增 4 个工序子节：架空线、电缆、配电站房、台区改造。
- [ ] **Step 2:** 每个子节附最小 SOP、风险点、质量控制点和可用 chart placeholders。
- [ ] **Step 3:** 用 fixture 验证 prompt 输入包含配网工序信息，而不是泛化施工描述。

### Task D.2：5 类缺失 chart_type

**Files:**
- Modify: `backend/tender_backend/services/chart_service/specs.py`
- Modify: `backend/tender_backend/services/chart_service/vega_mapper.py`
- Modify: `backend/tender_backend/services/chart_service/render_strategy.py`
- Modify: `backend/tender_backend/services/chart_service/renderers.py`
- Test: `backend/tests/unit/test_chart_service.py`

- [ ] **Step 1:** 新增 `single_line_diagram`、`site_layout`、`outage_timeline`、`wbs_tree`、`fmea_matrix` spec。
- [ ] **Step 2:** 渲染路径：停电时序复用甘特，WBS 用 mermaid，FMEA 复用矩阵；单线图/平面布置图若 vega-lite 表达不足，P0 只输出结构化占位图并标记需要人工复核。
- [ ] **Step 3:** 每类 chart 至少一个 fixture 和 SVG 非空测试。

### Task D.3：companybase 电力施工资质与业绩字段

**Files:**
- Create: `backend/tender_backend/db/alembic/versions/<next>_power_industry_master_data.py`
- Modify: `backend/tender_backend/db/repositories/master_data_repo.py`
- Modify as needed: `backend/tender_backend/api/master_data_certificates.py`
- Test: `backend/tests/unit/test_master_data_repo.py`

- [ ] **Step 1:** 不引用不存在的 `db/models/qualification_certificate.py`、`project_performance.py`。按当前 repository + migration 模式扩展。
- [ ] **Step 2:** 资质枚举扩展：承装/承修/承试电力设施许可证、输变电专业承包、电力工程总承包；等级支持一级至五级。
- [ ] **Step 3:** 业绩 metadata 增加 `voltage_level_kv`、`circuit_count`、`capacity_mva`、`distribution_type`、`is_live_work`。
- [ ] **Step 4:** 保持字符串兼容，不把历史自由文本一次性硬切为 enum。

### Task D.4：不停电作业 / 配网自动化 / 停电窗口数据模型

**Files:**
- Create: `backend/tender_backend/db/alembic/versions/<next>_distribution_domain_ledgers.py`
- Modify: `backend/tender_backend/db/repositories/master_data_repo.py`
- Test: `backend/tests/unit/test_master_data_repo.py`

- [ ] **Step 1:** 建立 `outage_window`、`live_work_plan`、`distribution_automation` 三类 ledger，均以 `company_key/project_id`、`metadata_json`、`evidence_asset_id` 为基础。
- [ ] **Step 2:** 接入章 8/9/10 相关 context builder，不阻塞 Track C 的基础交付。
- [ ] **Step 3:** 单测覆盖增删查改和缺失 evidence 的验收提示。

---

## 五、Track E - 收口 2026-05-17 遗留（与 Track A-D 并行）

**Goal:** 在 Track A/C 完成到一定阶段后，跑通 2026-05-17 三份计划遗留的 Track 3 T9 与 Track 4 e2e + 盲评。

### Task E.1：Track 3 T9 真实样本 POC（50 flow + 50 gantt）

**Files:**
- Use: `backend/scripts/run_gpt_vis_poc.py`
- Create: `docs/acceptance/2026-05-XX-gpt-vis-poc-evidence.json`
- Create: `docs/reports/2026-05-XX-gpt-vis-poc-report.md`

- [ ] **Step 1:** 从历史项目 chart_assets 抽 50 flow + 50 gantt 真实 spec；脱敏后再落 evidence。
- [ ] **Step 2:** 双引擎跑 mermaid_sidecar / gpt_vis，落 SVG + 量化指标。
- [ ] **Step 3:** 业务方盲评 30 对 A/B 样本。
- [ ] **Step 4:** 写报告并给出 `decision=adopt|reject|defer`。
- [ ] **Step 5:** 若 reject，执行容器下线并记录原因。

### Task E.2：Track 4.1 第 8 章 final e2e

**前置:** Track C.2 完成；需要真实 project_id。

- [ ] **Step 1:** 跑 `scripts/run_chapter_8_acceptance.py --project-id <真实> --target-pages 100`。
- [ ] **Step 2:** 落 `docs/acceptance/2026-05-XX-chapter-8-followup-final-evidence.json`。

### Task E.3：Track 4.2 第 8/9/10.1/10.2/10.3 章 longform e2e

- [ ] **Step 1:** 跑 `scripts/run_longform_multi_chapter_acceptance.py --project-id <真实> --chapter-code 8 --chapter-code 9 --chapter-code 10.1 --chapter-code 10.2 --chapter-code 10.3`。
- [ ] **Step 2:** 落 evidence JSON，确认每章 target/estimated pages、coverage、chart closure、model usage 均有值。

### Task E.4：Track 4.3 评标专家盲评

- [ ] **Step 1:** 选 3 个真实项目的完整商务+技术标 DOCX；若含暗标项目，先跑 C.3 暗标校验。
- [ ] **Step 2:** 专家按篇幅完整、专业表现、图表可读、暗标合规 4 维打分，各 1~5 分。
- [ ] **Step 3:** 落 `docs/reviews/2026-05-XX-followup-blind-review.md`，不得包含真实客户敏感字段。

### Task E.5：Followup Roadmap + longform-launch-closure 收口

- [ ] **Step 1:** 把 Followup Roadmap D-1/D-2/E-5 完成项勾选，追加 v1.4 修订记录。
- [ ] **Step 2:** 在 `2026-05-15-longform-launch-closure.md` 追加 Phase 2 Final Decision。

---

## 六、依赖图

```text
Track A 商务标模板闭环
  A.1 脱敏单 DOCX 样章
    -> A.2 单 DOCX import 回归
    -> A.3 single_docx_section renderer
    -> A.4 模板项导入/升级
    -> A.5 bindings
    -> A.6 assembler artifact
    -> A.7 export
    -> A.8 商务 e2e

Track B 商务台账与正文
  B.1/B.3 可与 A.5 并行
  B.2/B.4 依赖 A.5 的 binding 接口
  B.5 依赖 A.7 导出路径

Track C 技术标交付闭环
  C.1 -> C.2 -> C.3，可与 A/B 并行

Track D 配网行业纵深
  D.1/D.2/D.3/D.4 均为 P1，不能阻塞 A/C P0 验收

Track E 遗留收口
  E.1 独立
  E.2 依赖 C.2
  E.3 依赖 longform evidence schema
  E.4 依赖 A.8 + C.2
  E.5 依赖 E.1 + E.4
```

**立即可开工起点:**
- A.1（需要用户提供或确认脱敏单 DOCX）
- A.2/A.3（可先用测试 fixture，不依赖真实样章）
- B.1/B.3（独立 DB 与 import 工作）
- C.1/C.3（纯代码）
- D.1/D.2（P1，可并行但不抢 P0）
- E.1（GPT-Vis-SSR POC 独立）

---

## 七、Success Criteria（hard stop）

- [ ] **Track A:** 单 DOCX 样章脱敏确认；`single_docx_section` 渲染单测全绿；`BusinessBidAssembler` 写入 24 章 business `chapter_draft`；`run_business_bid_acceptance.py` 在真实 project 上产出可打开的商务整卷 DOCX。
- [ ] **Track B:** 财务与 6 类专项 sheet 可导入；4 类承诺/说明文 context builder 单测全绿；正文型章节生成不编造缺失材料。
- [ ] **Track C:** 技术 16 章均有 strategy；非 longform 章节不只依赖泛化 fallback；`run_technical_bid_full_acceptance.py` 5 维门禁通过率 >= 90%；暗标校验覆盖技术 16 章 + 商务 24 章。
- [ ] **Track D:** 5 类新 chart_type 有 fixture 与非空渲染测试；电力资质/业绩字段兼容旧数据；4 业务线 fixture 每线 >= 1 套。
- [ ] **Track E:** GPT-Vis POC decision 落定；chapter-8 final / longform 8-9-10 / blind-review 三份 evidence 归档；Followup Roadmap v1.4 收口。

---

## 八、Risk Controls

- [ ] **样章合规:** 原始客户 DOCX 未脱敏或未获批准前不得提交；`.gitignore` 只加最小白名单。
- [ ] **renderer 兼容:** A.3 前后跑 `pytest backend/tests/unit/test_template_docx_renderer.py -v`，并补跑 package renderer 相关集成测试，避免破坏 `single_docx` 与通用渲染。
- [ ] **migration 编号:** 所有新 migration 从当前 head 后创建；实施前用 `rg --files backend/tender_backend/db/alembic/versions | sort | tail -20` 确认。
- [ ] **artifact 存储:** 不把 DOCX bytes 塞进不存在字段；优先 `chapter_draft.rendered_docx_path` + `rendered_artifact_json`，需要强一致再新增专门 artifact 表。
- [ ] **DOCX 合并保真:** python-docx 合并只作为 MVP；对页眉页脚、复杂样式、图片定位有保真要求时，改为 package 级合并或章节 DOCX zip 交付。
- [ ] **companybase 兼容:** 新 sheet 接入不得破坏现有 4 个 MVP sheet 导入。
- [ ] **枚举迁移:** 资质/业绩枚举先软约束，保留历史字符串兼容。
- [ ] **真实数据 evidence:** 所有 evidence JSON/报告落档前确认无 PII、客户名、项目名等敏感信息。

---

## 九、Reporting Cadence

- [ ] 每完成 1 个 Task：勾选本文件 checkbox，commit message 带 `[GAP-FIX-<Track>-<Task#>]`。
- [ ] 每完成 1 个 Track：在本文件"修订记录"追加完成日期、commit hash、验收 evidence 路径。
- [ ] 整体完成：在 `docs/reports/2026-05-18-distribution-tender-full-coverage-gap.md` 与 `docs/reports/2026-05-18-distribution-business-bid-full-coverage-gap.md` 各追加 "v2.0 - gap 闭环" 段，引用本计划。

---

## 十、修订记录

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| v1.0 | 2026-05-18 | 初版。基于 2026-05-18 两份 gap 报告（商务标 24 章 + 技术标 16 章）与 2026-05-17 三份计划遗留，编制五条 Track 修订计划。 |
| v1.1 | 2026-05-18 | 按现有代码复核后修订：P0 改为统一单 DOCX + `single_docx_section` 主链路；多 DOCX importer 降为 P1；修正 Alembic 编号、`chapter_draft.attachment_bytes/metadata_json` 假设、暗标模块路径、longform 验收命令、companybase/repository 实施路径和 DOCX 合并保真风险。 |
