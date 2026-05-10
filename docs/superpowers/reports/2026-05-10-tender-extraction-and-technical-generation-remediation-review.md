# Tender Extraction And Technical Generation Remediation 计划审查报告

**Date:** 2026-05-10

**Subject:** `docs/superpowers/plans/2026-05-10-tender-extraction-and-technical-generation-remediation.md`

**Reviewer Notes:** 已核对计划中关键事实（`format_passed=true` 硬编码、`charts_approved` 未导出至 `frontend/src/lib/api.ts`、`bid_outline_planner.py` 的 `CATEGORY_CHAPTER` 仅按 category 粗映射、`workflows/generate_section.py` 仍使用 `uuid4().hex`、`tender_documents.py:1084` 仍走旧规则抽取路径、`tender_constraint_set` 已在 alembic 0037 落库），均与计划描述一致。

---

## 总体评价

计划质量较高：根因清单完整、范围边界清晰、可验证 acceptance 明确。最值得肯定的几点：

1. **明确"模板优先、冲突显式覆盖"**（Scope Decisions 第 3-5 条 + Phase 4）。这是当前最容易被 AI 自由发挥破坏的地方，计划把它升级为硬规则并要求 conflict record 留痕，逻辑闭环。
2. **把 `tender_constraint_set` 设为下游唯一真实源**（Phase 3）。把 `BusinessBidAssembler`、`ComplianceCheckService`、`SubmissionChecklistService`、`DeliveryPackage`、`ComplianceMatrix` 全部纳入改造范围，避免半改状态。
3. **图表从可选装饰升级为章节内容**（Phase 8）。`{{chart:*}}` 占位 + 仅引用 chart 才阻断 export 的 gate 设计务实。
4. **Phase 12 验证矩阵覆盖回归 fixture（pricing 噪声、模板字节级保留、冲突覆盖）**，可作为合并门槛。

---

## 必须修正的问题

### 1. Phase 1 验收标准过强

> "AI 和 rule fallback 对代表性样本产生相同 active/ignored 决策"

AI 和规则 fallback 在语义边界本就会分歧（这正是要 AI 的原因）。建议改为单向不变量：**rule fallback 的 active 集合 ⊆ AI 的 active 集合**（即规则不得扩大范围），更符合 fallback 语义且可机械验证。

### 2. Phase 2 subtype 落点未明

Phase 2 引入 15 个 subtype，但未声明存储位置：

- 是覆盖 `project_requirement.category`？
- 还是新增 `constraint_subtype` 列？
- 还是只存 `tender_constraint_item.metadata_json`？

每种选择对 Phase 11 backfill 和 Phase 3 下游消费者改造路径完全不同。建议在 Phase 2 开头就敲定为**新增 `tender_constraint_item.constraint_subtype` 列**（保持 `project_requirement.category` 向后兼容），否则 Phase 3 改造会反复返工。

### 3. Phase 3 "explicit conflict" 信号源不明

> "Detect explicit conflicts between confirmed tender constraints and the business/technical directory templates"

冲突是 AI 判定还是规则判定？如果留给 AI，"模板默认保留"的承诺会被 AI 的判断悄悄稀释。建议明确：

- 冲突触发器**只能**是规则化信号：subtype = `mandatory_attachment` 但模板无对应章节、subtype = `submission_format` 中"独立成册/单独密封"等显式锚点词、`veto_rejection` 要求未覆盖。
- AI 只负责**起草冲突描述**，不负责**触发**冲突。

### 4. Phase 7 与 Phase 6 fallback 关系未声明

Phase 6 已定义 chapter strategy templates 骨架，Phase 7 又要"deterministic fallback when AI Gateway unavailable"。两者应明确为：**Phase 7 fallback = Phase 6 strategy 渲染结果（不调用 AI）**，否则会出现两套确定性骨架代码。

### 5. Phase 3 "compatibility guard" 例外定义缺失

> "blocks generation/export when no current confirmed constraint set exists, except for explicitly marked legacy projects"

"explicitly marked legacy" 是什么？项目标志位？feature flag？建议在 Phase 11 定义为 **`project.metadata_json.legacy_pre_constraint_set = true`**，由 backfill 显式打标，且在 UI 上展示遗留状态横幅。

---

## 建议增强的问题

### 6. 缺乏 rollback / feature flag 策略

Phase 1 收紧抽取范围会立刻影响线上招标解析质量。建议在 Phase 1 增加：

- 新增 `EXTRACTION_SCOPE_POLICY=strict|legacy` 环境变量
- `extraction_mode_marker` 取值空间显式定义（`legacy_v0` / `scoped_v1`）
- 上线前先在影子模式跑一周对比 active/ignored 差异

### 7. Open Decisions 阻塞前置阶段

4 项产品待决项分别影响：

- 投标保证金 → Phase 2 subtype 列表
- 图表自动创建 vs 询问 → Phase 8 默认行为
- 溯源表可见性 → Phase 7 prompt 模板
- 标准库范围 → Phase 5 context loading

建议在启动 Phase 2 前先解决前两项（subtype 和图表行为），否则 Phase 2/8 都需要返工。

### 8. Phase 8 引用扫描的性能/一致性

> "scan current drafts and templates for `{{chart:*}}` placeholders and return referenced placeholder keys"

每次 gate fetch 都全文扫描所有 draft 在大项目会慢。建议：

- draft 保存时把引用 key 写入 `bid_chapter_draft.referenced_chart_keys`（数组列）
- gate 查询直接 join，不做全文 grep

### 9. Phase 5 personnel/equipment 数据源未确认

Phase 5 加载 personnel/equipment selections，但需先确认 `project_personnel_selection`、`project_equipment_selection` 等表存在。如果不存在，要么把建表纳入 Phase 11 migration，要么在 Phase 5 的"required facts"里允许这两类为空。

### 10. 缺少 MVP 切片

100+ 个 `[ ]` 任务无优先级。建议标记 P0 关键路径：

- **P0（不可删）**: Phase 1 + Phase 2 subtype 落库 + Phase 3 confirmed set 成为唯一源 + Phase 4 模板保留硬规则 + Phase 9 `format_passed` 真实化
- **P1（首版可省）**: Phase 6/7 部分 strategy、Phase 8 图表自动化、Phase 10 frontend 重命名

否则会陷入"全做不完、半做更糟"的状态。

### 11. Phase 4 旧 `CATEGORY_CHAPTER` 清理未声明

现 `bid_outline_planner.py:21` 的 `CATEGORY_CHAPTER` 在 Phase 4 被 subtype 映射替代后，必须**删除常量**而非保留作 fallback——否则 Phase 1 收紧后逃逸的 legacy `category` 仍会走旧映射。建议在 Phase 4 新增一条："移除 `CATEGORY_CHAPTER` 常量及其所有引用，遗留消费者改为 subtype 解析"。

### 12. Phase 6 strategy 落点未定

8 个 strategy template 是 Python 数据类、YAML 配置，还是数据库表？影响热更新和测试方式。建议明确为 `services/technical_chapter_strategies/*.py` 数据模块（可单元测试、随代码版本化），避免变成第二套 prompt 配置中心。

---

## 一致性观察

- 计划与 auto-memory 中"deepseek-v4-pro + max thinking"模型策略不冲突，Phase 7 的 AI 调用走现有 gateway 即可。
- 计划提到"Existing migrations must not be modified. Add new migrations" 与项目现状（alembic 已到 0046）一致。

---

## 建议下一步

1. 把"必须修正的问题"五项硬阻塞写入计划文档（subtype 落点、conflict 信号源、fallback 关系、legacy 标记、Phase 1 验收单向不变量）。
2. 解决 Open Decisions 中前两项（保证金归类、图表自动化策略）。
3. 给所有 task 加 P0/P1/P2 标记，先冻结一个 4-6 周的 P0 切片再启动。
