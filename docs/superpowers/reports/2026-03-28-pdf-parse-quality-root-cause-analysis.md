# PDF规范文件AI解析质量根因分析报告

**日期:** 2026-03-28

**分析范围:** 项目全部PDF规范文件AI解析路径（MinerU OCR → AI Gateway → 条款提取 → 持久化）

---

## 解析管道总览

```
PDF上传 → MinerU OCR (VLM模式) → full.md + pages JSON + tables JSON
    → 持久化到 document_section / document_table / document.raw_payload
    → 构建 DocumentAsset (pages + tables + full_markdown)
    → 构建 StructuralNodes → 构建 ProcessingScopes (normative/commentary/table)
    → rebalance_scopes (按字符/条款块数拆分)
    → 逐scope调用 AI Gateway (DeepSeek-chat / Qwen-plus fallback)
    → LLM返回JSON条款数组
    → build_tree → link_commentary → validate → repair (VL模型) → persist + index
```

### 关键文件清单

| 阶段 | 文件 | 职责 |
|------|------|------|
| OCR调度 | `services/norm_service/norm_processor.py` | MinerU上传/轮询/结果解析，AI提取编排 |
| OCR结果切分 | `norm_processor._mineru_to_sections()` | 将full.md按heading正则切分为sections |
| 资产构建 | `services/norm_service/document_assets.py` | 组装PageAsset/TableAsset/DocumentAsset |
| 大纲识别 | `services/norm_service/outline_rebuilder.py` | 从page文本提取章节标题(1~2级) |
| 结构节点 | `services/norm_service/structural_nodes.py` | 将资产转为StructuralNode，构建scope |
| Scope拆分 | `services/norm_service/scope_splitter.py` | 按章/段/字符拆分ProcessingScope |
| LLM Prompt | `services/norm_service/prompt_builder.py` | 条款/说明/表格提取提示词模板 |
| AI调用 | `norm_processor._call_ai_gateway()` | 通过AI Gateway发LLM请求 |
| AI Gateway | `ai_gateway/tender_ai_gateway/fallback.py` | primary(DeepSeek) → fallback(Qwen) |
| 模型配置 | `ai_gateway/tender_ai_gateway/task_profiles.py` | tag_clauses: deepseek-chat / qwen-plus |
| JSON解析 | `norm_processor._parse_llm_json()` | 从LLM响应提取JSON |
| AST构建 | `services/norm_service/ast_builder.py` | 条款层级树构建 + 去重 |
| 树投影 | `services/norm_service/tree_builder.py` | AST → 扁平化持久化格式 |
| 验证 | `services/norm_service/validation.py` | 编号连续性/页码/表格/数字异常检查 |
| VL修复 | `services/vision_service/repair_service.py` | Qwen3-VL-8B渲染PDF页修复 |
| 修复提示词 | `services/vision_service/repair_prompt.py` | 多模态修复任务提示词 |
| 后端配置 | `core/config.py` | timeout/delay/DPI等参数 |

---

## 解析质量差的五大根因

### 根因 1: LLM作为主提取器，scope粒度过大（核心瓶颈）

**位置**: `norm_processor.py:919-965`, `scope_splitter.py:388-522`

LLM在chapter级别接收整章文本（`_DEFAULT_SCOPE_MAX_CHARS = 3000`，`_DEFAULT_SCOPE_MAX_CLAUSE_BLOCKS = 4`），一次性从大块文本中提取全部条款。导致：

- **超时与递归拆分**: 大章节超时后通过 `rebalance_scopes()` 递归二分，但拆分是按字符/段落机械切割，不考虑语义边界，条款被切断
- **重试雪崩**: 一个scope超时→拆成2个→每个又可能超时→继续拆，`_MAX_SCOPE_RETRY_ATTEMPTS = 2` 只控制重试次数，不控制级联深度
- **跨scope重复/遗漏**: 相邻scope边界处条款可能被两个scope都提取（重复）或都遗漏

### 根因 2: 条款边界完全依赖LLM判断，无确定性预处理

**位置**: `structural_nodes.py:349-419`, `outline_rebuilder.py:110-173`

`outline_rebuilder` 只识别1~2级标题（`code.count(".") > 1` 直接 `continue`，第144行），即只识别"3 结构设计"和"3.1 一般规定"这类粗粒度标题，不识别具体条款编号（如"3.1.1"、"3.1.2"）。

这意味着：
- 所有 `x.y.z` 级条款的边界判断完全交给LLM
- LLM在长文本中容易漏掉条款、错分层级、合并相邻条款
- 条文说明中条款编号与正文的对应关系也全靠LLM推断

### 根因 3: MinerU OCR到LLM之间的信息损失严重

**位置**: `norm_processor.py:105-117`, `norm_processor.py:570-643`

`_extract_markdown_from_zip()` 从MinerU结果中只取 `full.md`，而 `_mineru_to_sections()` 按heading正则切分markdown。问题：

- **full.md丢失结构信息**: MinerU的page-level JSON包含bbox/block类型/表格结构，但转成markdown后全部丢失
- **heading正则不可靠**: 正则 `r"^(#{1,6})\s+(.+)$|^(\d+(?:\.\d+)*)\s+(\S.*)$"` 容易将正文中数字开头句子误判为标题
- **page与section对齐不准**: `_find_section_page_index()` 用文本子串匹配确定页码，大量条款的 `page_start` 为 `None` 或错误值
- **表格从markdown中脱落**: 表格在full.md中可能被渲染为不完整文本行，与原始HTML表格结构不一致

### 根因 4: 去重策略过于简单

**位置**: `ast_builder.py:49-74`

去重依据是 `{clause_type}:{node_key}`，其中 `node_key` 主要由 `clause_no` 构成。问题：

- **合法重复被误删**: 不同章节可能有相同编号（如附录A.0.1和正文条款），按 `clause_no` 去重会丢失
- **相邻scope发出的祖先节点重复**: 两个scope可能都输出父条款（如"3.2"），只保留第一个，第二个scope的子条款失去父节点
- **node_key构建未充分考虑 `parent_key` 和 `source_ref` 组合**

### 根因 5: repair阶段用错了模型，且不稳定

**位置**: `repair_service.py:99-110`, `task_profiles.py:16-22`

- **VL修复模型**: 硬编码使用 `Qwen/Qwen3-VL-8B-Instruct`（8B参数量），对复杂工程表格和数字/单位的修复能力有限
- **repair失败不阻塞但浪费时间**: repair_error被记录但clauses仍按修复前状态持久化
- **repair覆盖面不足**: 只对表面症状做修复，不触及条款遗漏/错分问题

---

## 次要问题

| 问题 | 位置 | 影响 |
|------|------|------|
| LLM system prompt 过于笼统 | `prompt_builder.py:11-58` | "建筑工程规范条款提取助手"没有给出足够的领域约束 |
| `max_tokens: 8192` 可能不够 | `norm_processor.py:835` | 大章节输出条款多时JSON被截断 |
| `temperature: 0.1` 仍有随机性 | `norm_processor.py:834` | 同一文档多次运行结果不同（360/369/375条） |
| 无gold-set基线 | 设计文档承认 | 无法量化衡量质量改善 |
| Commentary分割靠关键词 | `scope_splitter.py:20-25` | "条文说明"出现在正文目录中时导致提前分割 |

---

## 根本结论

解析质量差的核心根因是架构性的，不是参数调优能解决的：

当前管道让LLM同时承担"条款边界识别"和"条款内容提取"两个任务，而这两个任务的可靠性差距极大——边界识别可以用确定性规则高精度完成，内容提取才需要LLM。把两件事揉在一起，让LLM在大段文本中同时做pattern matching和语义理解，必然导致不稳定。

已有设计文档 `2026-03-25-single-standard-parse-quality-design.md` 已正确诊断出方向："rule-first structural recovery with AI fallback"。当前代码的 `outline_rebuilder` 是朝这个方向走的第一步，但它只到2级标题就停了，没有深入到条款级别的确定性分割。
