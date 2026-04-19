# MinerU 新旧输出兼容性差异清单

- **日期：** `2026-04-18`
- **目标：** 对比旧库中 `GB 50148-2010` 历史 MinerU 资产与本次提供的 `GB 50147-2010` 新 MinerU 输出，判断当前项目是否会受新模型 / 新输出结构影响。
- **范围：** 只做本地静态分析和数据库只读核查；**不修改业务代码**。

## 1. 样本来源

### 旧样本：库中历史 `GB 50148-2010`

- 标准：`GB 50148-2010`
- `standard_id`：`dae12cd4-d8d7-417b-b436-1b7e54a11b49`
- `document_id`：`bb1c0345-7969-4d3b-8274-169655b53a0d`
- `raw_payload` 键：`batch_id, full_markdown, pages, result_item, tables`
- `pages_count=12`
- `tables_count=1`
- `full_markdown_len=42848`
- 持久化结果：`document_section=488`，`document_table=1`

### 新样本：本次提供的 `GB 50147-2010`

- 文件：
  - `/Users/palmtom/Downloads/MinerU_GB50147 2010 电气装置安装工程 高压电器施工及验收规范__20260418120949.json`
  - `/Users/palmtom/Downloads/MinerU_markdown_GB50147_2010_电气装置安装工程_高压电器施工及验收规范_2045474865843142656.md`
- 顶层字段：`pdf_info, _backend, _ocr_enable, _vlm_ocr_enable, _version_name`
- `_backend=hybrid`
- `_version_name=2.7.6`
- `pdf_info_len=107`
- `markdown_chars=64283`
- `markdown_lines=2701`
- `heading_count=131`
- `clause_like_lines=405`
- `clause_like_unique=239`

## 2. 样本差异

### A. 旧 `GB50148` 的 `raw_payload.pages` 不是页级对象

旧库里 `GB50148` 的 `raw_payload.pages` 只有 `12` 项，实际是零散 layout blocks，不是带 `page_number + markdown` 的页对象：

- `page_items=12`
- `distinct_page_idx=0`
- `page_like_items=0`
- block 类型只看到：`header`、`title`、`text`

抽样内容：

```json
{
  "type": "header",
  "content": "UDC"
}
```

```json
{
  "type": "title",
  "content": "电气装置安装工程 电力变压器、油浸电抗器、互感器施工及验收规范"
}
```

这正是项目先前报告里提到的故障模式：`raw_payload.pages` 存在，但并不是真正可消费的页文本。

### B. 新 `GB50147` 已经接近“完整页级结构”

新样本的 `json` 顶层转为 `pdf_info`，每页下有 `para_blocks / discarded_blocks / page_size / page_idx`：

- `pdf_info_len=107`
- `nonempty_pages=102`
- block 统计：
  - `text=337`
  - `list=183`
  - `title=131`
  - `page_number=102`
  - `footer=54`
  - `table=7`

这说明新样本不再只是“少量 layout block + full markdown”，而是已经有较完整的页级 block 结构。

### C. 新样本的 markdown 覆盖也明显更强

旧 `GB50148`：

- `full_markdown_len=42848`
- `heading_count=75`
- `clause_like=178`
- `chapter_headings=9`

新 `GB50147`：

- `markdown_chars=64283`
- `heading_count=131`
- `clause_like_lines=405`
- `clause_like_unique=239`

结论：如果只看 MinerU 原始输出质量，新样本明显优于旧库里的 `GB50148` 历史结果。

## 3. 当前项目的兼容性命中点

### A. 规范库主链路：有兼容层，但对 `pdf_info/para_blocks` 仍不直接兼容

当前规范链路核心入口在：

- [backend/tender_backend/services/norm_service/norm_processor.py](/Users/palmtom/Projects/tender/backend/tender_backend/services/norm_service/norm_processor.py#L144)

`_extract_pages_from_payload()` 目前只兼容三类输入：

1. 已经是页对象：带 `page_number/markdown`
2. 扁平 layout block 列表：每项自己带 `page_idx + type + content`
3. 二维页块列表：`list[list[dict]]`

但新样本是：

- 顶层 `dict`
- `pdf_info` 是页对象数组
- 每页内部是 `para_blocks`
- 文字藏在 `lines/spans/content`

当前 `_extract_pages_from_payload()` 不会把 `pdf_info` 识别成“页对象”，也不会把每页 `para_blocks` 递归聚合成 `page_number + markdown`。按同等逻辑复现，这种新 `json` 会抽出 `0` 页。

影响判断：

- **规范链路有风险，但不是必然全挂。**
- 如果 MinerU 结果 zip 里继续提供 `full.md`，项目还能靠 markdown 主链路和 section fallback 勉强运行。
- 但页锚点、页文本对齐、结构化 scope 构建会继续受影响。

### B. `document_assets` 对旧故障有补丁，但补的是“旧 shape”

页资产组装逻辑在：

- [backend/tender_backend/services/norm_service/document_assets.py](/Users/palmtom/Projects/tender/backend/tender_backend/services/norm_service/document_assets.py#L49)
- [backend/tender_backend/services/norm_service/document_assets.py](/Users/palmtom/Projects/tender/backend/tender_backend/services/norm_service/document_assets.py#L381)

当前逻辑假设 `raw_payload.pages` 里的有效页至少长这样：

```json
{"page_number": 1, "markdown": "..."}
```

如果没有文本，再回退到 `document_section` 拼页。

这能修旧 `GB50148` 那种“pages 是 layout block”的问题，但它的前提仍然是：

- 上游最终要么给出可消费的 `pages`
- 要么能稳定从 `full_markdown + sections` 回补

对新样本 `pdf_info/para_blocks`，当前这里**没有原生读取能力**。

### C. 招标文件链路更脆弱

旧商业 client 还在假设简单接口和简单返回：

- [backend/tender_backend/services/parse_service/mineru_client.py](/Users/palmtom/Projects/tender/backend/tender_backend/services/parse_service/mineru_client.py#L49)
- [backend/tender_backend/services/parse_service/mineru_client.py](/Users/palmtom/Projects/tender/backend/tender_backend/services/parse_service/mineru_client.py#L74)
- [backend/tender_backend/services/parse_service/mineru_client.py](/Users/palmtom/Projects/tender/backend/tender_backend/services/parse_service/mineru_client.py#L86)

它假定：

- 上传：`/files/upload-url`
- 提交：`/parse`
- 查询：`/parse/{job_id}`
- 返回：`pages/sections/tables`

而规范链路已经转成了另一套 `v4 batch` 方式，并且项目里也已经有一份对齐 MinerU 文档的计划：

- [docs/superpowers/plans/2026-04-05-mineru-doc-alignment.md](/Users/palmtom/Projects/tender/docs/superpowers/plans/2026-04-05-mineru-doc-alignment.md#L5)

影响判断：

- **如果后续把招标文件链路也接到新 MinerU 契约，当前 client 不能直接复用。**
- 这部分受影响程度高于规范链路。

## 4. 影响等级

### 规范库链路

- **影响等级：中**
- 原因：
  - 已有 `full_markdown` 主链路
  - 已有 `document_assets` fallback
  - 但新 `pdf_info/para_blocks` 不能被当前页提取器直接消费

### 招标文件链路

- **影响等级：高**
- 原因：
  - 仍绑定旧商业 API 契约
  - 假设返回 `pages/sections/tables`
  - 没有当前规范链路这种兼容层和 fallback

### “skills / API / 新模型发布”本身

- **影响等级：低到中**
- 原因：
  - 当前仓库没有接 `MCP / SDK / router / tasks` 之类新配套工具
  - 真正有影响的是“HTTP 契约 + 输出 shape 漂移”

## 5. 结论

1. **新 MinerU 输出质量确实比旧库里的 `GB50148` 历史结果高不少。**
2. **这种提升目前还不能自动转化为本项目解析质量提升。**
3. **当前项目真正的风险点是兼容层，而不是 OCR 能力本身。**
4. **规范库链路短期可继续运行，但页级结构消费会落后于新输出。**
5. **招标文件链路如果迁到新契约，当前实现需要重做 client 层。**

## 6. 当前不改代码时的实用判断

- 如果目标只是继续用当前规范库链路跑旧式 MinerU / 当前线上契约：
  - **短期可用**
- 如果目标是充分利用新 `2.7.x / 3.x` 风格的 `pdf_info/para_blocks`：
  - **当前项目不能算已兼容**
- 如果目标是判断“新模型是否值得关注”：
  - **值得**
- 如果目标是判断“现在是否必须立刻改项目”：
  - **还不是必须立刻改**
  - 但应优先补 page extraction / payload normalization，而不是继续只盯 OCR 更换

## 7. 后续最小动作建议

按优先级排序：

1. 在规范链路里补 `pdf_info -> para_blocks -> page_number + markdown` 的归一化。
2. 给 `_extract_pages_from_payload()` 增加针对 `pdf_info` 页对象数组的测试。
3. 在招标文件链路决定是否继续沿用旧商业 API；若迁移，单独替换 `mineru_client.py`，不要和规范链路混改。
4. 保留 `full_markdown` fallback，但不要再把它当作“新 MinerU 页结构已兼容”的证据。
