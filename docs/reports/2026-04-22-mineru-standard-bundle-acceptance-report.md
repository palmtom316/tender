# MinerU Standard Bundle 技能验收结论

- **日期：** `2026-04-22`
- **范围：** `GB 50147-2010`、`GB 50148-2010`、`GB 50150-2016`
- **目标：** 验证 repo-local `mineru-standard-bundle` skill 是否已按计划完成实现，并确认三本规范在本轮真实样本下的 bundle 生成、确定性清洗、页锚点回填、对比输出是否达到可入库的上游资产质量。

## 1. 验收对象

本次验收对象包括：

- repo-local skill 文档：
  - [docs/skills/mineru-standard-bundle/SKILL.md](/home/palmtom/projects/tender/docs/skills/mineru-standard-bundle/SKILL.md)
- CLI 入口：
  - [docs/skills/mineru-standard-bundle/scripts/run_mineru_standard_bundle.py](/home/palmtom/projects/tender/docs/skills/mineru-standard-bundle/scripts/run_mineru_standard_bundle.py)
- 后端 helper：
  - [backend/tender_backend/services/norm_service/mineru_standard_bundle.py](/home/palmtom/projects/tender/backend/tender_backend/services/norm_service/mineru_standard_bundle.py)
- 测试：
  - [backend/tests/unit/test_mineru_standard_bundle.py](/home/palmtom/projects/tender/backend/tests/unit/test_mineru_standard_bundle.py)
  - [backend/tests/smoke/test_mineru_standard_bundle_cli.py](/home/palmtom/projects/tender/backend/tests/smoke/test_mineru_standard_bundle_cli.py)

## 2. 计划完成情况

对照 `2026-04-21` 计划与设计文档，本轮已完成以下功能性工作：

- 已实现 `evaluate`、`clean`、`compare` 三个命令面。
- 已实现标准 bundle 生成、质量评估、确定性清洗、比较汇总与输出落盘。
- 已补齐 unit test 与 CLI smoke test。
- 已使用真实样本完成 `147 / 148 / 150` 三本规范的本地验证。
- 已针对真实样本暴露的问题，补充以下确定性清洗与回填规则：
  - TOC 噪声去除
  - front-matter / cover heading 噪声去除
  - suspicious year-like section code 去除
  - 标题规范化唯一命中页回填
  - 紧凑章节标题回填，例如 `5互感器 -> 5 互感器`
  - appendix heading 回填到最早非 TOC 正文页
  - 末尾书名空 heading 与“本规范/本标准用词说明”清理

未执行的仅有计划中的 `git commit` 步骤。该部分不影响功能验收。

## 3. 真实样本输入

本轮真实样本目录：

- `/mnt/d/147148150`

样本文件组：

- `GB 50147 2010 电气装置安装工程 高压电器施工及验收规范.pdf/.md/.json`
- `GB 50148 2010 电气装置安装工程电力变压器、油浸电抗器、互感器施工及验收规范.pdf/.md/.json`
- `GB 50150 2016 电气装置安装工程电气设备交接试验标准.pdf/.md/.json`

三本书的 `json` 均确认满足本 skill 输入前提：

- `_backend = hybrid`
- `_version_name = 2.7.6`

## 4. 验证命令

测试验证：

```bash
PYTHONPATH=backend ./.venv/bin/python -m pytest \
  backend/tests/unit/test_mineru_standard_bundle.py \
  backend/tests/smoke/test_mineru_standard_bundle_cli.py -q
```

本轮最终结果对应：

- unit：`18 passed`
- smoke：`3 passed`

真实样本输出目录：

- [tmp/mineru_standard_bundle/GB50147-2010](/home/palmtom/projects/tender/tmp/mineru_standard_bundle/GB50147-2010)
- [tmp/mineru_standard_bundle/GB50148-2010](/home/palmtom/projects/tender/tmp/mineru_standard_bundle/GB50148-2010)
- [tmp/mineru_standard_bundle/GB50150-2016](/home/palmtom/projects/tender/tmp/mineru_standard_bundle/GB50150-2016)
- [tmp/mineru_standard_bundle/compare-147-148-150/compare-summary.json](/home/palmtom/projects/tender/tmp/mineru_standard_bundle/compare-147-148-150/compare-summary.json)
- [tmp/mineru_standard_bundle/compare-147-148-150/compare-report.md](/home/palmtom/projects/tender/tmp/mineru_standard_bundle/compare-147-148-150/compare-report.md)

## 5. 最终真实样本结果

### GB 50147-2010

- raw：
  - `sections = 985`
  - `toc_noise_count = 120`
  - `front_matter_noise_count = 63`
  - `section_page_coverage_ratio = 0.871066`
- cleaned final：
  - `sections = 781`
  - `sections_with_page = 781`
  - `section_page_coverage_ratio = 1.0`
  - `remaining_no_anchor = 0`

### GB 50148-2010

- raw：
  - `sections = 487`
  - `toc_noise_count = 52`
  - `front_matter_noise_count = 63`
  - `section_page_coverage_ratio = 0.848049`
- cleaned final：
  - `sections = 413`
  - `sections_with_page = 413`
  - `section_page_coverage_ratio = 1.0`
  - `remaining_no_anchor = 0`

### GB 50150-2016

- raw：
  - `pdf_pages = 177`
  - `canonical_pages = 170`
  - `sections = 1102`
  - `toc_noise_count = 75`
  - `front_matter_noise_count = 76`
  - `section_page_coverage_ratio = 0.861162`
- cleaned final：
  - `sections = 1002`
  - `sections_with_page = 1002`
  - `section_page_coverage_ratio = 1.0`
  - `remaining_no_anchor = 0`

## 6. 验收结论

### A. skill 是否已按计划生成

结论：**是。**

repo-local skill、CLI、helper、单测、烟测均已落地，且命令面与计划一致：

- `evaluate`
- `clean`
- `compare`

### B. 计划的功能性工作是否已完成

结论：**是。**

从“实现技能、提供稳定 CLI、完成真实样本验证并收敛主要确定性噪声”的目标看，本轮功能性工作已完成。

说明：

- 计划中 `commit` 类步骤未执行，因为本轮未要求提交 git commit。
- 这不影响实现和验收结论。

### C. 三本规范是否达到可入库的上游资产质量

结论：**是。**

本轮 skill 产出的 cleaned bundle 已满足以下条件：

- `remaining_no_anchor = 0`
- `toc_noise_count = 0`
- `front_matter_noise_count = 0`
- `suspicious_section_code_count = 0`
- `section_page_coverage_ratio = 1.0`

因此，对 `147 / 148 / 150` 三本规范，可以认定当前 cleaned bundle 已达到**可入库的上游 parse asset 质量**。

### D. 是否等同于“完整生产 AI 入库验收”

结论：**否，不能直接等同。**

本 skill 验收覆盖的是：

- MinerU 资产归一化
- parse-asset-like bundle 生成
- 确定性噪声清理
- 页锚点回填
- 多书对比验证

它**不等于**以下全链路验收已经完成：

- 下游 AI scope 抽取
- `standard_clause` 持久化结果验收
- `normative/commentary` 分类质量验收
- 关键条号完整率验收
- 生产环境 DB import / reindex / viewer 联调验收

因此，本报告的正式结论应表述为：

- `147 / 148 / 150` 三本规范的 **MinerU cleaned bundle 上游资产质量已验收通过**
- 是否进入生产正式库，仍需单独完成下游 AI 解析与 DB 验收

## 7. 当前建议

建议将本轮产出作为上游基线固定下来，并在后续单独开展“AI 条款抽取入库验收”。

优先顺序：

1. 以当前 cleaned bundle 作为三本书的上游基线。
2. 对接现有 `norm_service` 全链路，做一次真实 AI 解析入库 rerun。
3. 以 `standard_clause` 结果补齐生产侧验收结论，而不是再回头修改当前 bundle 清洗规则。
