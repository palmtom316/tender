# 配网工程完整技术标 Gap 报告

> **日期:** 2026-05-18
> **范围:** 评估 tender 系统输出"国网公司配网工程完整技术标"（16 章）的覆盖能力与缺口
> **对照基准:** `docs/samples/国网公司配网工程技术标目录.md` + `backend/tender_backend/services/bid_outline_templates.py:94-134`（SGCC_DISTRIBUTION_TECHNICAL_CHAPTERS）
> **审阅方式:** 只读代码盘点，无修改

---

## 一、章节维度 Gap

完整国网配网技术标 16 章对照系统当前覆盖：

| 章号 | 章节标题 | 大纲注册 | 内容生成策略 | Longform | 缺口 |
|---|---|---|---|---|---|
| 1 | 技术偏差表 | ✅ | ✅ `api/deviation_table.py` | — | 无 |
| 2 | 监理人员执业合规承诺函 | ✅ | ❌ | — | **缺承诺函模板生成** |
| 3 | 工期响应 | ✅ | ❌ | — | **缺工期响应表生成** |
| 4 | 资质情况 | ✅ | ⚠️ companybase 拉取 | — | 资质类型枚举弱、无证书自动组装 |
| 5 | 业绩情况（5.1-5.4）| ✅ | ⚠️ companybase 拉取 | — | 缺 kV/容量/回路自动筛选、业绩证明 DOCX 组装 |
| 6 | 项目团队情况 | ✅ | ✅ 短策略 (`registry.py:303`) | ❌ | **未启用 longform**，无人员证书自动组装 |
| 7 | 其他资格条件 | ✅ | ❌ | — | **完全空白** |
| 8 | 施工方案与技术措施（8.1-8.15）| ✅ | ✅ | ✅ ≥80 页 | 完整 |
| 9 | 工作规划描述（9.1-9.8）| ✅ | ✅ | ✅ ≥30 页 | 完整 |
| 10.1 | 质量保证措施（共 15 子节）| ✅ | ✅ | ✅ ≥35 页 | 完整 |
| 10.2 | 安全与绿色施工（共 16 子节）| ✅ | ✅ | ✅ ≥35 页 | 完整 |
| 10.3 | 工程进度计划（共 15 子节）| ✅ | ✅ | ✅ ≥35 页 | 完整 |
| 11 | 服务承诺 | ✅ | ❌ | ❌ | **缺生成策略**（与 8.12 存重叠风险） |
| 12 | 技术评分支撑材料 | ✅ | ✅ 短策略 (`registry.py:396`) | ❌ | 仅占位，无评分点扫描+材料索引 |
| 13 | 技术规范书响应 | ✅ | ✅ 短策略 (`registry.py:409`) | ❌ | 仅占位，无逐条响应生成 |
| 14 | 履约评价证明材料 | ✅ | ❌ | — | 仅 companybase 选择，无 DOCX 注入 |
| 15 | 其他 | ✅ | ❌ | — | 缺补充材料容器 |
| 16 | 履约承诺函 | ✅ | ❌ | — | **缺承诺函模板** |

**核心结论:** 16 章中
- **5 章 longform 完备**（8、9、10.1/10.2/10.3，合计约 215 页）
- **3 章短策略占位**（6、12、13）
- **8 章完全无生成逻辑**（2、3、7、11、14、15、16；4、5 仅靠 companybase 选择）

---

## 二、领域纵深 Gap（配网行业专属）

| 维度 | 现状 | 缺口 |
|---|---|---|
| 配网业务线切片 | 仅 5 章 prompt 通用文本（`docs/samples/配网*.md`） | 缺**架空线 / 电缆 / 配电站房 / 台区** 4 大业务线的子工序切片、专用 SOP 数据模型 |
| 工序级 spec | `CHAPTER_8_CHILD_CHARTS` 仅 9 个子节挂图 | 缺基础 / 电杆组立 / 架线 / 电缆敷设（直埋/排管/拉管/顶管）/ 接地 / 调试 子工序结构化 spec |
| 不停电/带电作业 | 仅 prompt 提及 | 无专项方案 spec 与风险数据模型 |
| 配网自动化（FA/三遥）| 仅 prompt 提及 | 无终端清单 / 通信链路 / 调试用例数据结构 |
| 停电窗口排程 | 文本承诺 | 无停电时序数据模型（时段、回路、设备、用户影响） |

---

## 三、图表 Gap

**已支持 15 类**（`backend/tender_backend/services/chart_service/specs.py:10-26`）：
- 流程类 7：`org_chart` / `construction_flow` / `quality_system` / `safety_system` / `emergency_org` / `closure_flow` / `data_flow`
- 甘特/路径 2：`schedule_gantt` / `critical_path`
- 矩阵 2：`risk_matrix` / `responsibility_matrix`
- 表格 4：`response_matrix` / `indicator_table` / `interface_table` / `equipment_table`

**配网技术标常用但缺失：**
- **单线图 / 电气主接线图**（10kV 进线、母线、馈线结构）
- **平面布置图**（站房设备布置、临设 / 料场 / 办公区）
- **停电窗口时序图**（按回路 / 时段 / 影响用户）
- **WBS 分解树**（仅 prompt 提及，无 spec）
- **FMEA 矩阵**（风险矩阵的失效模式版本）
- **网络计划图 PERT**（current `critical_path` 是甘特变体，非真正 PERT）

---

## 四、数据 / companybase Gap

| 数据类 | 现状 | 缺口 |
|---|---|---|
| 电力施工资质 | 通用 `certificate_type ∈ {construction, safety, license, system_cert}` | 缺枚举：承装/承修/承试（一/二/三/四/五级）、输变电专业承包、电力工程总承包等级 |
| 业绩 | 通用 `project_performance` | 缺 kV 等级、回路数、容量（MVA）、配网类型（架空/电缆/混合）、是否带电作业筛选字段 |
| 工器具 / 检测设备 | `asset_type ∈ {vehicle, machine, tool, safety}` | 缺电力专用细分：试验设备（耐压/绝缘/接地电阻）、安全工器具（绝缘杆/验电器/接地线）、登高器具、个体防护 |
| 人员证书 | 通用 `person_profile` | 缺特种作业操作证（高压电工/低压电工/登高架设）、进网作业许可证、安规复训记录字段 |

---

## 五、流程 / 工具 Gap

| 项 | 现状 | 缺口 |
|---|---|---|
| 多章节 e2e 入口 | `scripts/run_longform_multi_chapter_acceptance.py` 默认 5 章（8、9、10.1、10.2、10.3）| **不能产出"完整 16 章 DOCX"**，无 1-7/11-16 章组装入口 |
| DOCX 组装 | `docx_exporter` 支持 longform 5 章 + 偏差表 | 缺承诺函、工期响应、资质/业绩附件、评分支撑、规范响应 章节的组装与版式 |
| 暗标合规 | longform 5 章已接入 | 1-7/11-16 章未做暗标过滤 |

---

## 六、优先级建议

| 优先级 | 项 | 影响 |
|---|---|---|
| **P0** | 第 2 章合规承诺函、第 3 章工期响应、第 11 章服务承诺、第 16 章履约承诺函 模板化（变量填充） | "能不能交出完整标书" |
| **P0** | 第 12 章评分点扫描 + 材料索引、第 6 章人员证书自动组装 | "评分能否拿到" |
| **P1** | 配网 4 业务线（架空/电缆/站房/台区）子工序切片、停电窗口数据模型、单线图/平面布置图 chart_type | 行业纵深与专业表现力 |
| **P1** | companybase 电力施工资质枚举 + 业绩 kV/容量/回路字段 | 数据底座完整度 |
| **P2** | WBS / FMEA chart_type、第 13 章规范响应自动比对 | 创新与评分加分项 |

---

## 七、References

- 系统注册表：`backend/tender_backend/services/technical_chapter_strategies/registry.py:144-150`（LONGFORM_CHAPTER_CONFIG）、`:302-422`（CHAPTER_STRATEGIES）
- 完整大纲：`backend/tender_backend/services/bid_outline_templates.py:94-134`（SGCC_DISTRIBUTION_TECHNICAL_CHAPTERS）
- 图表 spec：`backend/tender_backend/services/chart_service/specs.py:10-43`
- e2e 入口：`scripts/run_longform_multi_chapter_acceptance.py:22`（DEFAULT_CHAPTER_CODES）
- 行业 prompt：`docs/samples/配网*.md`（5 套）、`docs/samples/technical-bid-quality-assurance-template.md`
- 数据库模板：`backend/tender_backend/db/alembic/versions/0045_sgcc_distribution_technical_template.py`
- companybase 字段：`companybase/docs/02-字段字典与示范表.md`

---

## 八、修订记录

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| v1.0 | 2026-05-18 | 初版。基于 2026-05-18 仓库代码盘点，对照国网配网技术标 16 章目录输出 gap。|
