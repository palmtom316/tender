# 04-18 MinerU 新输出兼容计划 — 修订补丁

- **对象计划**：[docs/superpowers/plans/2026-04-18-mineru-new-output-compatibility-plan.md](./2026-04-18-mineru-new-output-compatibility-plan.md)
- **修订日期**：2026-04-18
- **修订依据**：
  1. MinerU 官方文档（[API](https://mineru.net/apiManage/docs) · [Output File Format](https://opendatalab.github.io/MinerU/reference/output_files/) · [GitHub](https://github.com/opendatalab/MinerU)）
  2. 本地真实样本 `MinerU_GB50147_2010__20260418120949.json`（`_version_name=2.7.6`、`_backend=hybrid`）
- **执行指引**：本补丁优先级高于原计划。实施时以本补丁为准，原计划作为大框架参考。

---

## 1. 真实 middle.json 结构基线（执行计划前务必先读）

### 1.1 顶层

```json
{
  "pdf_info": [...],
  "_backend": "hybrid",            // 可能值：hybrid | vlm | pipeline
  "_ocr_enable": true,
  "_vlm_ocr_enable": true,
  "_version_name": "2.7.6"
}
```

### 1.2 每页

```json
{
  "page_idx": 0,                   // 0-based
  "page_size": [width, height],
  "para_blocks": [...],            // 主内容
  "discarded_blocks": [...]        // page_number / footer / header — 正文不消费
}
```

旧 pipeline backend 的 `preproc_blocks / layout_bboxes / tables / images / interline_equations` 在新 VLM/hybrid 后端**不存在**。

### 1.3 `para_blocks` 顶层 block 类型（实测）

| type | 是否嵌套 | 说明 |
|---|---|---|
| `text` | 否（直接有 `lines`） | 普通段落 |
| `title` | 否 | 标题（无 `text_level` 字段，仅通过 `type` 标识）|
| `list` | **是**（含 `blocks[]`） | 列表，含 `sub_type` 字段（如 `text`） |
| `table` | **是**（含 `blocks[]`） | 表格 |
| `interline_equation` | 否 | 行间公式，`lines[].spans[].type == "interline_equation"`，content 为 LaTeX |

### 1.4 嵌套 block 类型（出现在 `list.blocks[]` 或 `table.blocks[]`）

| nested type | 出现位置 | 说明 |
|---|---|---|
| `text` | list 或 table 里 | 普通文本子块 |
| `ref_text` | list 里 | 引用文本（列表项内部）|
| `table_caption` | table 里 | 表标题（文本 span）|
| `table_body` | table 里 | 表体（含 `type=table` 的 HTML span）|

### 1.5 Span 类型与取值

| span.type | 字段 | 示例 |
|---|---|---|
| `text` | `content` | `"电气装置安装工程"` |
| `inline_equation` | `content` | `"500\\mathrm{kV}"`（LaTeX）|
| `interline_equation` | `content` | LaTeX |
| `table` | `html`, `image_path` | `"<table>...</table>"` |

**结论：文本 / 公式用 `content`，表格 HTML 用 `html`。绝对不存在 `table_body`/`table_caption` 作为 block 直接字段的 shape。**

---

## 2. 对原计划的逐项修订

### 🔧 Task 1 — Canonical Normalizer（重写 fixture + 补助函数）

#### 2.1 Step 1 单测 fixture 修订

**❌ 原 fixture（错）**
```python
"para_blocks": [{
    "type": "table",
    "table_caption": "表1 参数",
    "table_body": "<table><tr><td>A</td></tr></table>",
}]
```

**✅ 修正后 fixture（对齐真实结构）**
```python
"para_blocks": [{
    "type": "table",
    "bbox": [44, 442, 342, 517],
    "index": 15,
    "blocks": [
        {
            "type": "table_caption",
            "lines": [{"spans": [{"content": "表1 参数", "type": "text"}]}],
        },
        {
            "type": "table_body",
            "lines": [{"spans": [{
                "type": "table",
                "html": "<table><tr><td>A</td></tr></table>",
                "image_path": "https://cdn-mineru.openxlab.org.cn/result/xxx.jpg",
            }]}],
        },
    ],
}]
```

断言相应更新：

```python
assert normalized["tables"] == [{
    "page_start": 2,
    "page_end": 2,
    "table_title": "表1 参数",
    "table_html": "<table><tr><td>A</td></tr></table>",
    "table_image_path": "https://cdn-mineru.openxlab.org.cn/result/xxx.jpg",
    "raw_json": {   # 原始 block 原样保留
        "type": "table", "bbox": [...], "index": 15,
        "blocks": [...],
    },
}]
```

新增字段 `table_image_path` 便于后续视觉 repair 复用。

#### 2.2 新增必须覆盖的 fixture（原计划缺失）

补充 **4 个** 单测（`backend/tests/unit/test_mineru_normalizer.py`）：

1. `test_normalize_recurses_into_list_block_children`
   - 输入 `list.blocks=[text, text, ref_text]`，断言 markdown 里三条子内容按顺序出现、中间换行。
2. `test_normalize_preserves_inline_equation_latex`
   - 输入 span 混合 `text` + `inline_equation`，断言 LaTeX 保留为 `$...$` 或原样（先定一种策略，见 §3.1）。
3. `test_normalize_skips_discarded_blocks`
   - 输入 `discarded_blocks` 含 `page_number/footer/header`，断言 markdown 里不包含这些内容。
4. `test_normalize_handles_empty_pages_gracefully`
   - 输入一页 `para_blocks=[]`、另一页 `para_blocks=[text]`，断言只输出一个 page 对象。

#### 2.3 Step 3 normalizer 实现细节（原计划只给了 `_extract_pages_from_pdf_info`，这里补齐）

```python
# mineru_normalizer.py

_INLINE_EQUATION_WRAP = "$"  # 决策：保留 LaTeX 但用 $ 包裹

def _span_text(span: dict) -> str:
    t = span.get("type")
    if t == "table":
        return ""  # 表格 HTML 走独立通道，不混入 markdown
    content = span.get("content") or ""
    if not isinstance(content, str):
        return ""
    if t in ("inline_equation", "interline_equation"):
        return f"{_INLINE_EQUATION_WRAP}{content}{_INLINE_EQUATION_WRAP}"
    return content


def _lines_text(lines: list) -> str:
    parts: list[str] = []
    for line in lines or []:
        spans = line.get("spans") or []
        joined = "".join(_span_text(s) for s in spans).strip()
        if joined:
            parts.append(joined)
    return "\n".join(parts)


def _collect_block_text(block: dict) -> list[str]:
    """Return text fragments (one per logical paragraph) in order."""
    btype = block.get("type")
    if btype == "table":
        return []  # 表格单独出 tables
    if btype == "list":
        # 递归 list.blocks；每个子 block 作为一个段落
        nested = []
        for child in block.get("blocks") or []:
            nested.extend(_collect_block_text(child))
        return nested
    # text / title / ref_text / interline_equation / nested children
    lines = block.get("lines")
    if lines:
        text = _lines_text(lines)
        return [text] if text else []
    # nested container with only .blocks (rare)
    if block.get("blocks"):
        nested = []
        for child in block["blocks"]:
            nested.extend(_collect_block_text(child))
        return nested
    return []


def _extract_tables_from_pdf_info(pdf_info: object) -> list[dict]:
    if not isinstance(pdf_info, list):
        return []
    tables: list[dict] = []
    for page in pdf_info:
        if not isinstance(page, dict):
            continue
        page_idx = page.get("page_idx")
        if not isinstance(page_idx, int):
            continue
        for block in page.get("para_blocks") or []:
            if not isinstance(block, dict) or block.get("type") != "table":
                continue
            caption = ""
            html = ""
            image_path = ""
            for child in block.get("blocks") or []:
                child_type = child.get("type")
                if child_type == "table_caption":
                    caption_text = _lines_text(child.get("lines") or [])
                    if caption_text:
                        caption = caption_text
                elif child_type == "table_body":
                    for line in child.get("lines") or []:
                        for span in line.get("spans") or []:
                            if span.get("type") == "table":
                                html = span.get("html") or html
                                image_path = span.get("image_path") or image_path
            if not html:
                continue  # 没有 HTML 的 table 不入库
            tables.append({
                "page_start": page_idx + 1,
                "page_end": page_idx + 1,
                "table_title": caption or None,
                "table_html": html,
                "table_image_path": image_path or None,
                "raw_json": block,
            })
    return tables
```

**注意**：`_backend == "pipeline"` 时上述逻辑无效（pipeline 后端用独立 `tables[]` 字段）。第一期明确**拒绝处理 pipeline backend**：

```python
def normalize_mineru_payload(payload: dict) -> dict:
    backend = payload.get("_backend")
    if backend not in (None, "hybrid", "vlm"):
        raise ValueError(
            f"Unsupported MinerU backend {backend!r}; normalizer handles hybrid/vlm only."
        )
    ...
```

---

### 🔧 Task 2 — 标准流水线接入（测试 shape 同步修正）

#### 2.4 Step 1 集成测试 fixture

把 `_parse_via_mineru` 的 mock zip 里的 `middle.json` 按 §1 的真实 shape 写（`pdf_info / para_blocks / discarded_blocks`），而不是原计划里那个简化 fixture。

具体：

```python
middle_json_bytes = json.dumps({
    "_backend": "hybrid",
    "_version_name": "2.7.6",
    "pdf_info": [{
        "page_idx": 0,
        "page_size": [612, 792],
        "discarded_blocks": [
            {"type": "page_number", "lines": [{"spans": [{"content": "1", "type": "text"}]}]},
        ],
        "para_blocks": [
            {
                "type": "title",
                "bbox": [...],
                "lines": [{"spans": [{"content": "1 总则", "type": "text"}]}],
            },
            {
                "type": "text",
                "lines": [{"spans": [{"content": "正文内容", "type": "text"}]}],
            },
        ],
    }],
}).encode("utf-8")
```

断言 `captured["raw_payload"]` 不再含 `pages=[{page_number:1, markdown:"1 总则\n正文内容"}]` 的简化形，而是完整规范化输出。

#### 2.5 Step 3 `_parse_via_mineru` 修改

除了原计划要求的 `normalize_mineru_payload` 调用，**必须额外**：

1. 读取 zip 时，除了 `full.md` 还要读 `*_middle.json`（文件名 pattern：`(.+)_middle\.json$`）。原计划的 `extracted_primary_json` 并未明示来源；真实 MinerU zip 里 JSON 名称是 `<file>_middle.json`，不是 `result.json`。
2. 对 `_backend` 做校验（见 §2.3 末尾）。
3. 只把 `normalize_mineru_payload()` 产出的规范化结果写入 `document.raw_payload`，不再把 `batch_id / result_item` 混进去。

---

### 🔧 Task 3 — document_assets 简化（新增 pipeline-backend 拒绝分支）

原计划的 `_pages_from_raw_payload` 只检查 `{page_number, markdown}`，没问题。但**需要**补一条单测：

```python
def test_build_document_asset_rejects_pipeline_backend_raw_payload() -> None:
    """pipeline backend 输出若误落入 raw_payload 时应回退到 section fallback。"""
    # 构造仅有 preproc_blocks 的 pages[0]
    document = {"raw_payload": {"pages": [{"preproc_blocks": [...]}]}, ...}
    asset = build_document_asset(...)
    assert asset.pages == []  # 走 section fallback
```

避免 pipeline 残余数据污染。

---

### 🔧 Task 4 — Tender client（新增公式/list fixture）

Step 1 的 `_zip_bytes` helper 构造的 `middle.json` 也要按真实 shape 写。否则 tender 侧会在真实流量下失败。

建议在 `backend/tests/unit/test_mineru_client.py` 里复用 `test_mineru_normalizer.py` 的 fixture builder（提炼成 `backend/tests/unit/_mineru_fixtures.py`）。

---

### 🔧 Task 5 — Migration 与 Config（禁止污染 + 补默认值）

#### 2.6 Alembic 0014 修订

**❌ 原 SQL 会把旧 `raw_payload.pages` 里的 layout block 残片原样搬到新 schema，造成"标 canonical 但实际内容垃圾"。**

**✅ 修正后：对 `raw_payload.pages` 做 shape 校验，不合规则清空，触发重跑。**

```sql
-- 0014_mineru_canonical_assets.py
UPDATE document SET raw_payload = jsonb_build_object(
    'parser_version', parser_version,
    'pages', CASE
        WHEN jsonb_typeof(raw_payload->'pages') = 'array'
         AND (
             SELECT bool_and(
                 (p ? 'page_number') AND
                 (p ? 'markdown') AND
                 jsonb_typeof(p->'markdown') = 'string'
             )
             FROM jsonb_array_elements(raw_payload->'pages') p
         ) IS TRUE
        THEN raw_payload->'pages'
        ELSE '[]'::jsonb
    END,
    'tables', COALESCE(raw_payload->'tables', '[]'::jsonb),
    'full_markdown', COALESCE(raw_payload->>'full_markdown', '')
)
WHERE raw_payload IS NOT NULL;
```

并在 migration 之后：

- 把所有 `raw_payload->pages = '[]'::jsonb` 的文档的 `standard.processing_status` 置为 `'needs_reparse'`（如果字段不存在，直接跳过，让人工处理）。

#### 2.7 Config 默认值补全

原计划 Step 3 给了 6 个 `standard_mineru_*` 字段，**补 2 个**：

```python
standard_mineru_backend: str = "hybrid"      # hybrid | vlm
standard_mineru_timeout_seconds: float = 600  # batch 轮询上限
```

---

## 3. 设计决策（需在执行前敲定）

### 3.1 LaTeX 公式落盘策略 ✅ 已决策：方案 A

| 策略 | 输出 | 适用场景 |
|---|---|---|
| **A. 保留 LaTeX + `$` 包裹 ✅** | `压力达到 $500\mathrm{kV}$ 时` | 下游 LLM 能识别 LaTeX |
| B. 剥去 LaTeX，只留文本 | `压力达到 500kV 时` | 需要正则抽数值 |
| C. 原样 LaTeX 不加包裹 | `压力达到 500\mathrm{kV} 时` | 保留最高保真度但混淆下游 |

**执行指引**：在 `mineru_normalizer.py` 顶部写：

```python
_INLINE_EQUATION_WRAP = "$"
_INTERLINE_EQUATION_WRAP_OPEN = "\n$$"
_INTERLINE_EQUATION_WRAP_CLOSE = "$$\n"
```

行内公式用 `$...$`，块公式用 `$$...$$`（前后各加一个换行让 markdown 渲染器识别为块元素）。

### 3.2 `ref_text` 子块的归属

`ref_text` 出现在 `list.blocks[]` 中，含义是列表项内部的引用文本。方案：

- 默认和其他 `list` 子块一样当普通段落输出。
- 如果后期规范里需要区分引用，再在 normalizer 里额外标记 `ref_text_blocks`。本期先合并。

### 3.3 `table_image_path` 落库位置

真实样本里 `table_body.span` 带 `image_path`（MinerU 服务端的 CDN URL）。这个 URL **会过期**。

方案：
- 第一期存进 `document_table.raw_json`，不单独建列，避免失效 URL 成为长期依赖。
- 修复工作流如需可视重解析时从 raw_json 里临时拿，不再刷新长期字段。

---

## 4. 与现有仓库状态的衔接

本次代码修订当前状态：
- ✅ P0（温度 0.0 + 去重 key）已合并进代码
- ✅ P1.1–P1.3（parse_profile 抽象、ContextVar、migration 0013）已合并
- 🔶 P1.4 部分合并：`_SINGLE_STANDARD_BLOCK_EXPERIMENT_*` 已删，但 `test_standard_mineru_batch_flow.py` 有 **9 个集成测试失败** 未修
- ⏸ P1.5 / P1.6 / P2.* / P3.* 未开始

**执行顺序调整**：

1. **立即**：本补丁审批通过 → 执行 04-18 计划 Task 1–5（按补丁修正后的内容）。
   - 单测先跑，Task 5 migration 先灰度。
   - 实施完毕后，新的 `_parse_via_mineru` 已产出 canonical payload。

2. **紧接**：回头修 P1.4 遗留的 9 个失败测试。修法：用 canonical payload fixture 重写它们（会比现在干净），而不是给旧 fixture 加 `parse_profile='legacy_llm'` 绕过。

3. **之后**：
   - 我原 P2.1/P2.2（MinerU layout block 持久化 + LayoutBlockAsset）**直接删除**——canonical `pages[].markdown` 已取代其全部价值。
   - 我原 P2.3（confidence 路由）/ P2.4（normalize prompt）/ P3.* 保持原样。
   - P1.5（commentary 召回）修订：原计划要利用 `raw_json.text_level`，但真实 MinerU 2.7.6 **不暴露 text_level**。降级方案：只用 clause_no 回退检测 + 章节号监控。

---

## 5. 验收门槛（补丁完成判据）

- `backend/tests/unit/test_mineru_normalizer.py`：≥ 6 条测试全绿（2 原 + 4 新）。
- 用真实本地样本 `MinerU_GB50147_2010_....json` 跑一次 `normalize_mineru_payload`，断言：
  - `pages` 数 ≥ 95（107 页扣掉 discarded）
  - `tables` 数 == 7
  - `full_markdown` 长度 > 60000
  - 所有 `tables[*].table_html` 以 `<table>` 开头
- `document.raw_payload` 在 migration 后只含 `{parser_version, pages, tables, full_markdown}` 四键；旧 `batch_id / result_item` 不再出现。
- 集成测试 `test_standard_mineru_batch_flow.py::test_parse_via_mineru_persists_canonical_payload_from_pdf_info` 绿。

---

## 6. 修订点一览（便于实施时对照）

| # | 修订点 | 涉及文件 | 严重度 |
|---|---|---|---|
| 1 | Table fixture 换成嵌套 `blocks[]` | `test_mineru_normalizer.py`, `mineru_normalizer.py` | 🔴 阻断 |
| 2 | `_collect_block_text` 递归 list.blocks | `mineru_normalizer.py` | 🔴 阻断 |
| 3 | inline/interline_equation 策略 A ($包裹) | `mineru_normalizer.py` | 🟡 可选 |
| 4 | 拒绝 `_backend=pipeline` | `mineru_normalizer.py` | 🟡 防御 |
| 5 | zip 内 JSON 名识别 `*_middle.json` | `norm_processor._parse_via_mineru` | 🔴 阻断 |
| 6 | Migration 0014 做 shape 校验不污染旧行 | `0014_mineru_canonical_assets.py` | 🟠 数据安全 |
| 7 | Config 补 `standard_mineru_backend` / `..._timeout_seconds` | `core/config.py` | 🟡 可选 |
| 8 | 新增 4 条单测（list/equation/discarded/empty） | `test_mineru_normalizer.py` | 🟠 覆盖 |
| 9 | `document_assets` 新增 pipeline 拒绝单测 | `test_document_assets.py` | 🟡 防御 |
| 10 | Tender client fixture builder 抽成共用 helper | `_mineru_fixtures.py`（新）| 🟡 结构 |
