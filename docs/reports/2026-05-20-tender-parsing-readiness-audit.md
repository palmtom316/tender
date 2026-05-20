# tender 招标文件解析能力审计报告

- 日期：2026-05-20
- 分支：develop
- 配套讨论：`docs/reports/2026-05-20-direction-and-decisions.md`
- 触发问题：tender 下一步要走"通用 11 章策略 + 自行迭代"路线，当前解析能力能不能撑住？

---

## 1. tender 解析能力地图

```
ZIP/PDF 上传 → 文件名分类（12 类） → MinerU 2.7.x 解析（hybrid/vlm 后端）
  → 归一化 pages/tables/full_markdown → document_section + document_table + outline_node
  → 规则抽取（关键词 12 类） + AI 抽取（deepseek-v4-flash/pro 双档）
  → project_requirement / scoring_criteria / tender_summary
```

### 四层服务清单

| 层 | 文件 | 规模 | 评估 |
|---|---|---|---|
| 上传摄取 | `tender_document_ingestion.py` | 303 行 | ✅ 健壮（zip 防炸、安全路径、深度限制） |
| 解析 | `parse_service/`（`mineru_normalizer.py` + `parser.py`） | 197 + 158 行 | ✅ 已升级到 MinerU 2.7 新 backend |
| 规则抽取 | `requirements_extractor.py` + `scoring_extractor.py` + `facts_extractor.py` | 356 + 142 + 55 行 | ⚠️ 召回为主、精度弱 |
| AI 抽取 | `ai_requirements_extractor.py` + `ai_extraction_planner.py` + `tender_facts_extractor.py` | 1046 + 347 + 236 行 | ✅ 工程做得很重 |

---

## 2. 七类抽取产物 vs 下一步方向需求

| # | 抽取需求 | 当前实现 | 评估 | 用于下一步 |
|---|---|---|---|---|
| 1 | 强制响应点 + 页码 locator | `ExtractedRequirement` schema 已含 `source_file/source_locator/page_start/page_end/paragraph_index/source_chunk_id` | ✅ 结构完整，链路通 | Requirement Ledger 直接可用 |
| 2 | 评分标准 + 维度 + 分值 | `scoring_extractor.py` 解析评分表，输出 `dimension/max_score/scoring_method/sub_items_json` | ⚠️ 只解析表头是"评分项/分值"这类规整表；嵌套子项、跨页表、文字叙述夹表抽不出来 | "按权重选章节深度档"的输入不够 |
| 3 | 投标文件格式要求（目录骨架天然来源） | `category=format`，关键词包含"投标文件组成/目录/资格审查文件/商务文件目录/技术文件目录" | ⚠️ 抽出来后被丢进通用 requirement 集合，没有专门解析"投标文件目录"这一段的结构 | "目录骨架"方案的核心入口缺失 |
| 4 | 技术规范条款（含层级 + 编号） | `category=technical` 关键词匹配，无层级；MinerU outline_node 有层级但没和 requirement 关联 | ⚠️ 层级丢了，每条技术规范只有 page 没有"第 5.2.3 条"路径 | 影响"逐条响应" |
| 5 | 必填承诺书 / 附件清单 | `category=format` + `business`（混入），靠"承诺函/签章/盖章/装订"等关键词捞 | ❌ 没有结构化承诺书清单 | 11 章方案的"固定附件集合"无数据源 |
| 6 | 表格结构化（评分表、需求一览、工程量清单） | MinerU 已输出 table_html + raw_json + page_start/end，存到 document_table | ⚠️ 存了 HTML，但下游只在评分表里挖；需求一览/参数响应表/资质表没结构化 | "技术应答=参数应答表"子策略缺数据 |
| 7 | 页码 / source 反查 | 全链路保留 page_start/page_end/source_file/source_chunk_id；`tender_ai_extraction_runs` 留有 model/prompt/token 全审计 | ✅ 是整个系统最扎实的部分 | Evidence Citation 反查可直接接 |

---

## 3. 关键质量观察

### 好消息（基础设施层面）
- MinerU 2.7 + hybrid backend 已经落地（2026-04 升级，有专门 plan 和兼容性 checklist）。
- 抽取全链路保留 `source_chunk_id` 和 page 定位，**反查链完全打通**。
- AI 抽取有 `ai_extraction_planner` 做模型分档（flash → pro → pro_review）、batch 切分、quality_policy（fast_prefilter / table_or_critical / pro_review）—— **工程相当成熟**。
- AI prompt 明确禁止编造 source_chunk_id（"严禁虚构"），约束方向完全正确。

### 真正的问题（结构性短板）

| 问题 | 体现 | 对下一步的影响 |
|---|---|---|
| A. 整套抽取是为"国网配网施工标"专门训出来的 | `KEYWORDS_BY_CATEGORY` 的 `technical` 类直接出现"国网/国家电网/施工组织/安全文明施工"；`tender_facts_extractor` 把空主体兜底为"国网重庆市电力公司" | 离"通用商务标+技术标系统"很远 |
| B. 评分表抽取只覆盖最简单的形式 | `scoring_extractor.py` 只识别 `["评分项/评分内容/评审因素/评分标准/分值/得分"]` 这种规整表头 + dim/score/method 三列 | "按评分权重决定章节深度"输入不够 |
| C. 投标文件格式 / 投标文件目录没有专项解析器 | 当成普通 `format` 类 requirement 处理，目录层级和附件清单丢了 | "目录骨架从招标文件出"——入口缺失 |
| D. 没有 fingerprint 表 | `tender_document_ingestion` 只做分类和落盘，不抽取格式特征 | 自行迭代 L1 / 业主偏好积累 —— 底盘没有 |
| E. 没有"招标文件抽取质量"维度的回归 | 测试都是 unit 级别（test_ai_requirements_extractor 是 mock AI Gateway） | 无法量化"够不够用支撑下一步" |
| F. 没看到"投标文件目录"专项 ad-hoc 章节模板 | `ad_hoc_chapter_task_card.py` 是兜底未匹配模板的，不是"从招标文件抽取目录生成章节"的入口 | 11 章方案落地时目录裁剪逻辑无挂载点 |

---

## 4. 下一步能力对账

| 下一步方向 | 当前抽取能力够不够？ | 缺什么 |
|---|---|---|
| Requirement Ledger 状态机 | ✅ 够 | 状态字段（plan 已写） |
| 段落级 Evidence Citation | ✅ 够 | chapter_draft 反查列（plan 已写） |
| 规则化 Gap Engine（编造检测、scoring 覆盖） | ⚠️ 部分够 | scoring 子项级抽取的命中率要先验证 |
| 11 核心章节策略 + 招标文件抽取适配 | ⚠️ 关键入口缺失 | 需新加 `submission_outline_extractor` |
| 业主偏好 ledger + 招标文件 fingerprint | ❌ 基础没有 | 需新加 `tender_document_fingerprint` 表和提取器 |
| 自行迭代 L1 信号收集 | ⚠️ 审计层有，反馈层无 | 需新加 `chapter_draft_revision` |
| 去"配网"化、通用化 | ❌ 抽取本身是国网配网定制的 | 需要从关键词改成"模式 + 行业 tag"的配置化 |

---

## 5. 结论

**当前 tender 解析的"硬件基础"非常扎实，但"软件能力"被深度绑定到了国网配网施工标这一个垂直场景上。**

- **Ledger / Evidence / Gap Engine 主线（plan 中那 5 步）—— 解析侧基本够用，不需要先动解析**。
- **通用 11 章方案会立即被三个抽取短板卡住**：评分子项抽取不够细 / 投标文件目录没专项解析器 / 业主偏好 fingerprint 完全没采。

---

## 6. 建议的下一步顺序

### A 组：不动解析也能推进的（先做）
1. Requirement-Evidence Ledger plan 落地（`docs/plans/2026-05-20-requirement-evidence-ledger-plan.md`）。
2. 编造检测 + scoring_point_uncovered 规则上线。
3. `tender_document_fingerprint` 表先建（属于 ingestion 层加字段，不动解析）。

### B 组：要先升级解析才能推进的（后做）
1. 投标文件目录专项解析器（通用 11 章方案的真正入口）。
2. 评分子项级抽取（按权重选章节深度档的前提）。
3. 去配网化关键词重构（让通用化成立）。

### 先做的验证性实验
拿 3-5 份**非电力行业**的招标文件，跑现有解析链路，看：
- `project_requirement` 命中率
- `scoring_criteria` 抽取的子项粒度
- `format` 类 requirement 里"投标文件目录"那段长什么样

用真实数据告诉我们 B 组的工作量是"加 200 行 prompt"还是"重写一个 service"。

---

## 7. References

- 上传摄取：`backend/tender_backend/services/tender_document_ingestion.py:54-81`（分类）、`:124-303`（zip 解压）
- MinerU 归一化：`backend/tender_backend/services/parse_service/mineru_normalizer.py:28-57`（normalize_mineru_payload）
- 规则抽取：`backend/tender_backend/services/extract_service/requirements_extractor.py:69-116`（KEYWORDS_BY_CATEGORY）、`:232-324`（extract_requirements_from_source_chunks）
- AI 抽取：`backend/tender_backend/services/extract_service/ai_requirements_extractor.py:52-119`（prompt 设计）、`:1046` 全文
- 抽取调度：`backend/tender_backend/services/extract_service/ai_extraction_planner.py:14-68`（模型/批次策略常量）
- 评分抽取：`backend/tender_backend/services/extract_service/scoring_extractor.py:42-112`（extract_scoring_criteria）
- 招标摘要：`backend/tender_backend/services/extract_service/tender_facts_extractor.py:33-100`（_FIELD_KEYWORDS / _rule_extract）
- 之前的兼容性 plan：`docs/reports/2026-04-18-mineru-compatibility-gap-checklist.md`
- 之前的配网 gap 报告：`docs/reports/2026-05-18-distribution-tender-full-coverage-gap.md`
