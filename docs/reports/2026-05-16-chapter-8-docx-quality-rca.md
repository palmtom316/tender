# 第 8 章 DOCX 质量根因分析报告

- 报告日期：2026-05-16
- 分析对象：`outputs/2026-sgcc-chongqing-10kv-chapter-8.docx`（145,762 bytes，生成时间 2026-05-15 00:18:31 +0800）
- 项目背景：国网重庆市区分公司 2026 年 10kV 配网工程年度框架协议技术标第 8 章「施工方案与技术措施」
- 触发场景：用户使用 codex 对该项目第 8 章端到端生成进行测试
- 调用入口：本地 codex 调用 tender 后端的项目导出链路（`render_docx → _render_plain_docx`）

## 一、现象与基线

### 1.1 用户反馈

> 完全不能满足要求，不管是篇幅、内容、图表都质量太差，完全不能使用。

### 1.2 验收基线（来自 prompt 模板与 acceptance 文档）

| 维度 | 基线要求 | 出处 |
| --- | --- | --- |
| 篇幅 | 100 页 A4 左右（最低 90 页） | `docs/samples/配网施工方案及技术措施提示词.md:54`、`docs/acceptance/2026-05-15-longform-launch-closure.md` |
| 子章节 | 8.1~8.15 共 15 个子目录，每节按"编写依据/实施方案/关键控制点/质量、安全、进度协同措施/风险与应对/图表/表格占位"6 段固定结构展开 | 同上提示词第 65~83 行 |
| 必需图表 | 至少包含 `construction_organization_chart`、`master_schedule`、`site_layout_plan`、`quality_management_flow`、`safety_management_flow`、`risk_matrix` 6 类与章节绑定的图，并在导出前完成 placeholder 关闭 | `backend/tender_backend/services/longform_section_generation.py:_DEFAULT_CHARTS` |
| 必需表格 | 工程概况表/资源配置计划表/主要施工方法表/质量控制点表/安全风险管控表/工期保证措施表/重点难点应对表共 7 张实数据表 | 同上 `_DEFAULT_TABLES` |
| 内容来源 | 来自 confirmed_constraints / tender_summary / standard_clauses / company_assets 等 normalized context，缺失项写"待补充确认"，**严禁编造** | 提示词第 27~40 行 |

## 二、产物事实分析（pixel-level 证据）

### 2.1 量化指标

```
段落总数: 502（非空 475，空 27）
正文字符总数: 10,883
表格数量: 5
图片数量: 7（image1.png 20,825 B 起，最大 image2.png 62,872 B）
分节数: 1
预估页数（700 字/页含表图）: ~16 页
```

→ **达到目标篇幅约 16%，亏空 84%**。

### 2.2 标题骨架

8.1~8.15 共 **15 个二级标题** 全部出现，且每节下三级标题严格为以下 6 个：

```
编写依据
实施方案
关键控制点
质量、安全、进度协同措施
风险与应对
图表/表格占位
```

合计 15 × 6 = **90 个三级标题**，正文字符 10,883 摊到 90 节平均 **121 字/节**——这不是"内容稀薄"，是**完全没有任何专业内容**，仅渲染了 prompt 模板第 58~83 行所定义的「输出格式骨架」。

### 2.3 表格状态

5 张表全部是后置附录骨架，**第二行（数据行）一律填充"无"**：

| 表序 | 表名 | 行 × 列 | 数据行 |
| --- | --- | --- | --- |
| 0 | 主要施工车辆表 | 2 × 9 | `['无','','','','','','','','']` |
| 1 | 主要施工机械表 | 2 × 9 | 同上 |
| 2 | 主要施工工器具表 | 2 × 9 | 同上 |
| 3 | 主要安全设施设备及器具表 | 2 × 9 | 同上 |
| 4 | 项目管理机构人员表 | 2 × 11 | 同上 |

**没有任何一张是 prompt 模板要求的 7 类内容表**（工程概况表、资源配置计划表、主要施工方法表、质量控制点表、安全风险管控表、工期保证措施表、重点难点应对表），全部缺失。

### 2.4 图片状态

7 张 PNG 图，文件大小区间 10K~62K bytes，与 `chart_service` 在缺数据情况下用 `default_chart_spec` 渲染的"骨架占位 SVG"特征吻合。**没有 chart-by-chart 对应到具体施工方案内容**，更没有暗标脱敏审计，与 `docs/reviews/2026-05-11-...审查报告.md` 提到的 CR-1（flow 拓扑塌缩为竖线）、CR-2（甘特图无依赖无刻度）、CR-5（暗标未脱敏）三大已知缺陷完全一致。

## 三、时间线对照（关键证据）

### 3.1 docx 生成时刻 vs git HEAD

| 时间 | 事件 |
| --- | --- |
| 2026-05-14 17:52:44 | `b147b5c Remove icons from workspace buttons` 进入 main |
| **2026-05-15 00:18:31** | **codex 生成 chapter-8.docx**（此刻仓库 HEAD = `b147b5c`） |
| 2026-05-15 00:47:17 | `9a9b931 Implement project template propagation workflow` |
| 2026-05-15 00:51:41 | `b8afa45 Document unresolved launch issues` |
| 2026-05-15 10:49:09 | `18f034e feat: add longform generation evidence schema` |
| 2026-05-15 11:07:01 | `29c5431 feat: add deterministic longform quality checks` |
| 2026-05-15 11:29:59 | `0a18da8 fix: tighten longform quality edge cases` |
| 2026-05-15 12:19:27 | `d0876b4 fix: support longform mapping assets and section boundaries` |
| 2026-05-15 12:23:42 | `c2691b7 feat: add longform subsection generation loop` |
| 2026-05-15 12:28:53 | `07f45f5 fix: harden longform subsection planning` |
| 2026-05-15 14:22:58 | `4b03b5e feat: route long technical chapters through subsection loop` |
| 2026-05-15 14:24:37 | `ce0e91d feat: add docx page count evidence` |
| 2026-05-15 14:28:07 | `712edfc feat: gate final export on longform quality evidence` |
| 2026-05-15 14:31:36 | `7e8ac11 feat: persist docx render quality evidence` |
| 2026-05-15 14:34:33 | `05e1530 feat: show longform export gate evidence` |
| 2026-05-15 14:36:24 | `06681fa docs: track longform launch closure acceptance` |

→ **测试发生在 longform 整套机制合并前 10 ~ 14 小时**。当时仓库**根本不存在**：
  - `LongformSectionGenerator`（分节循环 + min_chars 续写直至达标）
  - `plan_chapter_8_sections`（按目标页数拆 15 节预算）
  - `estimate_markdown_pages` / `count_docx_pages`（页数验证）
  - `coverage_report` / `chart_closure_report`（覆盖率与图表关闭门控）
  - `export_gate` 对长技术章的拦截
  - `render_evidence` 落库

### 3.2 acceptance 自身的告警

`docs/acceptance/2026-05-15-longform-launch-closure.md` 末尾明确写：

> Do not promise production-grade 100-page chapter generation until the real sample evidence shows:
> 1. `page_count_passed = true` with actual counted pages, not only estimate.
> 2. `coverage_passed = true` with zero P0 gaps.
> 3. `chart_closure_passed = true` with zero residual `{{chart:*}}` placeholders.
> 4. Final export succeeds without bypassing gates.

该 acceptance 文档自身签发时间是 2026-05-15 14:36（commit `06681fa`），**比 codex 测试晚 14 小时 18 分**。**测试运行在系统自己宣告"未达到生产可用门槛"之前**。

## 四、调用路径还原

codex 走的是项目导出链路 `tender_backend/services/export_service/docx_exporter.py`：

```
render_docx(project_id, format="single_docx")
  └─ _render_plain_docx(conn, project_id, output_path)
        ├─ SELECT cd.content_md FROM chapter_draft cd ...      ← 来源：chapter_draft 表
        ├─ _add_markdown_content(document, draft.content_md)    ← 仅做 # / ## / ### / - 转换
        ├─ _append_equipment_table_anchors(document)            ← 写"无"占位 4 张表
        ├─ _append_personnel_table_anchor(document)             ← 写"无"占位 1 张表
        └─ ChartAssetInjector / EquipmentTableInjector / PersonnelTableInjector
              └─ chart_assets 表无内容 → 用 default_chart_spec 渲染骨架 SVG
```

而 `chapter_draft.content_md` 的填充链路是 `services/bid_chapter_generation.py::generate_bid_chapter_draft`：

```
generate_bid_chapter_draft
  └─ _strategy_lines(chapter, requirements, matches, recommended_charts)
        └─ for each (heading, default_body) in strategy["sections"]:
              lines.append(f"## {heading}")
              lines.append(default_body)
              lines.extend(_substantial_strategy_lines(...))    ← 全部都是固定话术（"由项目经理统筹..."）
```

**这条路径里没有任何对 LLM 的调用**：`_strategy_lines` 是确定性函数，输入是模板 + 已确认约束，输出是骨架文本。也就是说 docx 中所有内容都是"模板 + 占位"的拼装产物，**LLM 完全没有参与第 8 章正文写作**。

> 旁路存在但未被触发：`scripts/generate_sgcc_chapters_docx.py` 是一个独立 LLM 直生脚本（DeepSeek v4-pro，max_tokens=64000），但它独立运行、产物落到本地路径而非数据库 chapter_draft；codex 走的是项目导出 API，不会触发此脚本。即使触发，单次 LLM 调用 64K tokens 也无法稳定产出 100 页。

## 五、根因（按层次）

### 5.1 Root cause（架构层）

**测试时刻系统不具备长技术章（chapter 8 ~100 页）内容生成能力**：

- `chapter_draft` 表内的 `content_md` 仅由 `_strategy_lines` 拼接的"骨架 + 固定话术"填充；
- 没有"按目标页数预算 → 子节迭代生成 → 续写到达标 → 页数/覆盖率/图表关闭三重门控 → 通过后才允许导出"的闭环；
- 导出层 `_render_plain_docx` **无条件信任 `chapter_draft.content_md`**，导出空白骨架既不警告也不阻断。

### 5.2 Contributing factors（流程层）

| # | 描述 | 责任域 |
| --- | --- | --- |
| C1 | 在 longform 闭环代码合入主干**之前**就用 codex 跑了 e2e 抽样，期望与系统能力错配 | 流程 |
| C2 | acceptance 文档自身 14:36 才落库，"100 页生产承诺前置门槛"未在测试前传达 | 文档 |
| C3 | 项目模板 `chapter_draft.content_md` 在没有真实 LLM 内容的情况下也能直接进入导出，**没有"内容空白"前置闸** | 后端 |
| C4 | 5 张设备/人员表全部"无"填充直接通过——`_append_equipment_table_anchors` 永远写锚点，injector 在数据缺失时静默写"无"，与 longform_quality 中 `coverage_passed` 不联动 | 后端 |
| C5 | 7 张图全是 `default_chart_spec` 骨架渲染，`chart_closure_report_json` 当时尚未实现，残留占位无法被识别 | 后端 |
| C6 | 已知图表渲染缺陷（CR-1 flow 拓扑塌缩、CR-2 甘特图无依赖无刻度、CR-5 暗标未脱敏）尚未修复——见 `docs/reviews/2026-05-11-...整改方案.md` 中 P0 任务 REM-C-1/2/3 | 后端 |
| C7 | DeepSeek 单次 LLM 输出物理上限 ~32K tokens / 单次 ≈ 30~40 页 A4，**架构上必须分节循环**——`scripts/generate_sgcc_chapters_docx.py` 即使被调用也无法独立交付 100 页 | 架构 |

### 5.3 直接触发

codex 调用了"项目级 docx 导出"接口；该接口读取的是测试时点尚未跑过 LLM 生成的 `chapter_draft.content_md`；docx_exporter 把骨架原样拼装为 docx 并附加空表 + 占位图，最终落盘。**整条链路在当时不存在任何对"是否真的写出了第 8 章内容"的校验**。

## 六、二次审查（避免误判）

| 假设 | 验证 | 结论 |
| --- | --- | --- |
| 是不是 LLM 写了但被截断？ | docx 里没有任何项目化具体信息（无标准编号、无设备型号、无人员姓名、无工程量、无工期节点），且每节固定 6 个三级标题严格匹配 prompt 模板第 65~80 行的"输出格式"骨架。 | 否——LLM 未参与 |
| 是不是 codex 调用了 generate_sgcc_chapters_docx.py 但失败了？ | 该脚本输出落到 `--output` 指定路径，且其转换函数 `add_markdown` 不会写"主要施工设备表/项目管理机构人员表/附件清单/签章位置"等附录块；docx 中明确含这些附录 → 必然来自 `_render_plain_docx`。 | 否 |
| 是不是网络/API 错误？ | 文件大小 145KB、502 段、5 表 7 图，结构完整；如果是错误就不会落盘成功且包含完整骨架。 | 否——不是异常路径 |
| 是不是 codex 配置错了模型？ | 整条调用根本不走 LLM，模型选择无关。 | 不适用 |

## 七、影响评估

- **当前 docx 不可用于评标**：篇幅亏空 84%、内容专业度为 0、必需表格全部"无"、图表为占位、暗标合规未通过审计。
- **可信度风险**：若直接交给评标专家，会误判系统整体能力（实际能力的下限不应代表系统能力）。
- **数据完整性**：`chapter_draft.content_md` 确实是"骨架"，但这是 14 日尚未跑过 LLM 的预期状态，**数据本身没有损坏**。

## 八、解决方案与行动项

> 优先级口径：**P0 = 阻断生产可用，必须做**；**P1 = 影响交付质量**；**P2 = 长期治理**。

### 8.1 立刻行动（P0）

1. **重新生成验证样本**：在合入 `06681fa` 之后的 main HEAD（含全套 longform 闭环）上，按 `acceptance/2026-05-15-longform-launch-closure.md` 的"Real Sample Evidence"清单，**重新跑一次第 8 章端到端**，并落以下证据：
   - `chapter_draft.estimated_pages`、`chapter_draft.coverage_report_json`、`chapter_draft.chart_closure_report_json`
   - `export_record.metadata_json.render_evidence.page_count`
   - `GET /projects/{project_id}/export-gates` 响应快照
2. **不要把 `outputs/2026-sgcc-chongqing-10kv-chapter-8.docx` 当作系统能力证据**，建议归档到 `docs/reports/2026-05-16-chapter-8-docx-quality-rca/specimen/` 仅作根因附件保留。
3. **导出前置闸验证**：复测 `export_gate_service` 是否能在 `coverage_passed=false / chart_closure_passed=false / page_count_passed=false` 任一为假时**真的拦截**导出，不要只看代码合入而不验生效。

### 8.2 P1 修复

1. **`_render_plain_docx` 增加内容空白检测**：当 `chapter_draft.content_md` 仅由 `_strategy_lines` 模板骨架构成（可用启发：去骨架后字符 < 阈值，或缺少任何外部证据 hash）时，**禁止导出**并返回明确错误，避免再次出现"骨架直出"的误导样本。
2. **设备/人员表占位策略调整**：`equipment_selections / personnel_selections` 为空时，导出层应记入 `coverage_report` 的 P0 gap，而不是默默写"无"；与 longform_quality 联动后由 export_gate 阻断。
3. **图表占位策略调整**：缺图情况下，要么 chart_asset_injector 不写图（保留 `{{chart:*}}` placeholder 由 `chart_closure_report` 拦住），要么明确把"占位图"标记进 `chart_closure_report.unresolved`，二者必择其一，**不要默默渲染骨架 SVG**。
4. **执行 `docs/reviews/2026-05-11-...整改方案.md` 中 P0 任务**：REM-C-1（flow 拓扑）、REM-C-2（甘特图）、REM-C-3（暗标脱敏）、REM-C-4（图号规则）、REM-P-10.2-1（风险等级口径）。

### 8.3 P2 治理

1. **测试前置门控**：在 codex / 内部测试脚本里固化"acceptance 文档已通过"判断，避免在 launch closure 之前发起 e2e 样本采集。
2. **e2e 抽样标准化**：把"按 acceptance 清单采集 page_count / coverage / chart_closure / export_gate 四类证据"封装为脚本（建议放 `scripts/run_chapter_8_acceptance.py`），任何手动跑出来的 docx 旁挂一份证据 JSON。
3. **生成路径合并**：`scripts/generate_sgcc_chapters_docx.py`（LLM 直生 + 单脚本写 docx）与项目级导出链路（DB chapter_draft → docx_exporter）目前是两条平行路径。**长技术章只走"longform 分节循环 + DB 持久化 + 导出门控"主链路**；旁路脚本仅用于离线 prompt 调试，命名/README 上明确"非生产用、不交付"。

## 九、附录

### 9.1 复现命令

```bash
source .venv/bin/activate
python3 - <<'EOF'
from docx import Document
import zipfile

doc = Document('outputs/2026-sgcc-chongqing-10kv-chapter-8.docx')
print('paragraphs', len(doc.paragraphs))
print('tables', len(doc.tables))
text_chars = sum(len(p.text) for p in doc.paragraphs)
print('text_chars', text_chars)
with zipfile.ZipFile('outputs/2026-sgcc-chongqing-10kv-chapter-8.docx') as z:
    print('images', sum(1 for n in z.namelist() if n.startswith('word/media/')))
EOF
```

预期输出：

```
paragraphs 502
tables 5
text_chars 10883
images 7
```

### 9.2 关键代码位置

- 模板骨架来源：`docs/samples/配网施工方案及技术措施提示词.md:65-83`
- chapter_draft 拼接：`backend/tender_backend/services/bid_chapter_generation.py:185-216`（`_strategy_lines`）
- docx 导出主路径：`backend/tender_backend/services/export_service/docx_exporter.py:256-345`（`_render_plain_docx`）
- 设备/人员附录占位：同文件 `_append_equipment_table_anchors`、`_append_personnel_table_anchor`
- 长文本闭环（5/15 14:36 才齐）：`backend/tender_backend/services/longform_section_generation.py`、`longform_quality.py`、`export_service/page_counter.py`、`export_gate_service.py`
- 已知图表缺陷与整改：`docs/reviews/2026-05-11-配网技术标第8-10.3章提示词及图表整改方案.md`

### 9.3 相关 commits

```
06681fa 2026-05-15 14:36:24 docs: track longform launch closure acceptance
05e1530 2026-05-15 14:34:33 feat: show longform export gate evidence
7e8ac11 2026-05-15 14:31:36 feat: persist docx render quality evidence
712edfc 2026-05-15 14:28:07 feat: gate final export on longform quality evidence
ce0e91d 2026-05-15 14:24:37 feat: add docx page count evidence
4b03b5e 2026-05-15 14:22:58 feat: route long technical chapters through subsection loop
07f45f5 2026-05-15 12:28:53 fix: harden longform subsection planning
c2691b7 2026-05-15 12:23:42 feat: add longform subsection generation loop
d0876b4 2026-05-15 12:19:27 fix: support longform mapping assets and section boundaries
0a18da8 2026-05-15 11:29:59 fix: tighten longform quality edge cases
29c5431 2026-05-15 11:07:01 feat: add deterministic longform quality checks
18f034e 2026-05-15 10:49:09 feat: add longform generation evidence schema
```

### 9.4 一句话结论

**昨天 codex 测试时，系统正在补长文本生成闭环——测试 docx 是 LLM 完全没参与、导出层把"骨架模板 + 空表 + 占位图"原样拼装的产物，质量差不是 LLM 写不出来，而是当时根本没有跑 LLM。**
