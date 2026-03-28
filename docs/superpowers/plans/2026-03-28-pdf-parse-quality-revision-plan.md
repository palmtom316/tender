# PDF规范文件AI解析质量修订计划

**日期:** 2026-03-28
**依据:** `docs/superpowers/reports/2026-03-28-pdf-parse-quality-root-cause-analysis.md`

## Context

当前管道的核心问题是：LLM同时承担"条款边界识别"和"条款内容提取"，在chapter级大文本上不稳定。修订方向是 **"确定性条款分割优先，LLM仅做内容规范化"**，与已有设计文档 `2026-03-25-single-standard-parse-quality-design.md` 一致。

本计划分5个阶段，每阶段独立可测试、可回滚。

---

## 阶段 1: 确定性条款边界识别（根因 1+2 修复）

**目标**: 在LLM调用之前，用正则+规则把页面文本拆到单条款粒度。

**修改文件**:
- `backend/tender_backend/services/norm_service/outline_rebuilder.py`
- `backend/tender_backend/services/norm_service/structural_nodes.py`
- `backend/tests/unit/test_outline_rebuilder.py` (新建)

**具体改动**:

1. **`outline_rebuilder.py` — 放开条款级识别**
   - 当前 `collect_outline_markers_from_pages()` 第144行 `if code.count(".") > 1: continue` 跳过了所有 ≥3级编号
   - 改为：识别所有 `\d+(\.\d+)*` 格式的行首编号（1级到N级），包括 `3.1.1`、`4.2.3` 等
   - 新增 `collect_clause_markers_from_pages()` 函数，专门返回叶子级条款标记（与现有 `collect_outline_markers_from_pages` 共存，不破坏现有大纲功能）
   - 对每个标记增加 confidence 字段：有明确编号+短标题 → high；编号+长文本 → medium；模糊 → low

2. **`structural_nodes.py` — 按条款标记构建细粒度scope**
   - `_build_outline_leaf_scopes()` 当前以2级标题为叶子切scope
   - 改为：优先使用 `collect_clause_markers_from_pages()` 的结果，让每个scope只包含1~2个条款
   - 对 high confidence 标记：scope直接包含条款文本，`scope_type` 标记为 `"normative_determined"`（后续可跳过LLM或用轻量prompt）
   - 对 medium/low confidence：保持当前行为送LLM，但scope粒度从chapter缩小到几个条款

3. **新增单元测试**:
   - 用 GB 50148-2010 的典型页面文本作为fixture
   - 验证 `4.1.1`、`4.2.3`、`A.0.1` 等条款被正确识别
   - 验证正文中的数字开头句子不被误判为条款标题

---

## 阶段 2: 缩小LLM scope粒度 + prompt分离（根因 1 修复）

**目标**: LLM每次只处理1~3个条款的文本，而非整章。

**修改文件**:
- `backend/tender_backend/services/norm_service/scope_splitter.py`
- `backend/tender_backend/services/norm_service/prompt_builder.py`
- `backend/tender_backend/services/norm_service/norm_processor.py`

**具体改动**:

1. **`scope_splitter.py` — 调整 rebalance 默认参数**
   - `_DEFAULT_SCOPE_MAX_CHARS`: 3000 → 1500
   - `_DEFAULT_SCOPE_MAX_CLAUSE_BLOCKS`: 4 → 2
   - 确保 `rebalance_scopes()` 按条款边界（而非纯字符数）切分

2. **`prompt_builder.py` — 新增确定性条款的轻量prompt**
   - 对 `scope_type == "normative_determined"` 的scope，使用简化prompt：只要求LLM规范化字段（summary、tags、children拆分），不要求LLM判断条款边界
   - 现有3个prompt模板（normative/commentary/table）保持不变，新增第4个 `CLAUSE_NORMALIZE_PROMPT`
   - 新prompt的 `max_tokens` 可降至 4096（当前8192），减少延迟

3. **`norm_processor.py` — 对确定性scope跳过重试级联**
   - 在 `_process_scope_with_retries()` 中，对 `normative_determined` scope 超时时不做 `rebalance_scopes` 二分，直接重试（因为scope已经很小）
   - 降低 `temperature` 从 0.1 → 0.0 用于确定性scope

---

## 阶段 3: 去重策略加固（根因 4 修复）

**目标**: 避免合法条款被误删，避免scope边界处祖先节点冲突。

**修改文件**:
- `backend/tender_backend/services/norm_service/ast_builder.py`
- `backend/tests/unit/test_ast_builder.py`

**具体改动**:

1. **`ast_builder.py` — 扩展去重身份**
   - `deduplicate_entries()` 的去重key从 `{clause_type}:{node_key}` 扩展为 `{clause_type}:{node_key}:{source_label}`
   - 这样不同scope/章节产出的同编号条款（如附录和正文）不会互相覆盖
   - 对 `node_type == "clause"` 且 `clause_text` 为空（纯祖先节点）的条目，允许后续scope更新其内容而非直接丢弃

2. **新增/扩展测试**:
   - 测试附录 `A.0.1` 与正文 `1.0.1` 不被互相去重
   - 测试两个相邻scope都输出 `3.2`（heading-only）时，第二个的子条款能正确挂载

---

## 阶段 4: OCR资产保真度提升（根因 3 修复）

**目标**: 在section持久化阶段保留更多MinerU结构信息。

**修改文件**:
- `backend/tender_backend/services/norm_service/norm_processor.py`
- `backend/tender_backend/services/norm_service/document_assets.py`

**具体改动**:

1. **`norm_processor._mineru_to_sections()` — 利用page-level JSON**
   - 当 `pages` 非空时，直接以page为单位构建sections（每页一个section），保留 `page_number` 和 `raw_page`
   - 仅在 pages 为空时 fallback 到 `full.md` 正则切分
   - 这避免了heading正则误判的问题

2. **`document_assets.py` — page_assets保留block类型标注**
   - `_pages_from_raw_payload()` 中，当 `raw_page` 包含 `blocks` 或 `layout_dets` 时，在 `PageAsset` 的 `raw_page` 中完整保留
   - 供阶段1的条款识别使用（block的 `type` 字段可区分text/title/table等）

---

## 阶段 5: repair模型配置化 + 降低repair权重（根因 5 修复）

**目标**: repair不再浪费不必要的时间，VL模型可配置。

**修改文件**:
- `backend/tender_backend/services/vision_service/repair_service.py`
- `backend/tender_backend/core/config.py`
- `ai_gateway/tender_ai_gateway/task_profiles.py`

**具体改动**:

1. **`repair_service.py` — VL模型名从硬编码改为配置**
   - 移除硬编码的 `"Qwen/Qwen3-VL-8B-Instruct"`
   - 使用 agent_config 中的 `primary_model` / `fallback_model`

2. **`config.py` — 新增repair开关**
   - 新增 `standard_repair_enabled: bool = True` 配置项
   - 当关闭时，`process_standard_ai()` 跳过repair阶段

3. **`task_profiles.py` — repair timeout 从300s降为60s**

---

## 实施顺序

```
阶段4 (OCR保真) ← 无依赖，最先做
    ↓
阶段1 (确定性分割) ← 依赖阶段4的page-level数据
    ↓
阶段2 (LLM scope缩小) ← 依赖阶段1的细粒度scope
    ↓
阶段3 (去重加固) ← 独立，但在阶段2后测试效果更明显
    ↓
阶段5 (repair优化) ← 独立，可并行
```

建议顺序: **4 → 1 → 2 → 3 → 5**

---

## 验证方案

每个阶段完成后运行：

```bash
pytest backend/tests/unit/ -q
pytest backend/tests/integration/test_standard_mineru_batch_flow.py -q
pytest backend/tests/integration/test_standard_repo.py -q
pytest backend/tests/integration/test_parse_pipeline.py -q
```

端到端验收指标（GB 50148-2010）：
- 总条款数稳定性（多次运行方差 < 5）
- 4.1.x / 4.2.x / 4.12.x / 5.3.x / A.0.x 区域条款完整性
- commentary分离正确率
- 表格归属正确率

---

## 不做的事

- 不替换MinerU（OCR层保持不变）
- 不引入新的外部依赖
- 不构建通用gold-set框架（本轮聚焦代码修复）
- 不改动数据库schema（使用现有字段）
- 不改动前端
