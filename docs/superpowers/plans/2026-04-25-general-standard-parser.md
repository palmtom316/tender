# 通用规范解析 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前面向少数 GB 电气规范调优的 AI 条款抽取链路改造成通用、规则优先、AI 辅助的规范解析管线。

**Architecture:** 以 MinerU cleaned parse asset 为输入，先用 profile 驱动的确定性 block/outline/table 解析产出可验证 AST，再只让 AI 做低风险补全（摘要、标签、疑难表格/异常片段）。AI 层只允许使用 `deepseek-v4-flash` 作为 DeepSeek 主模型，不使用 `deepseek-v4-pro`。质量门禁在持久化前执行，失败时进入 review/repair queue，而不是直接覆盖旧库。

**Tech Stack:** Python 3.12, PyMuPDF/MinerU parse assets, PostgreSQL, OpenSearch, existing `norm_service` modules, pytest.

---

## Root Cause Findings

当前“AI 解析后质量不佳、难以形成可靠入库结果”的根因不是单个 prompt 或 DB insert 问题，而是管线职责错位：

- `process_standard_ai()` 仍把 LLM 作为正文条款抽取主路径。默认分支在构建 scopes 后逐 scope 调 `_process_scope_with_retries()`，AI 输出再进入 AST 和入库，见 `backend/tender_backend/services/norm_service/norm_processor.py:2304`、`:2350`、`:2403`。
- 规则优先 block path 只对 `_SINGLE_STANDARD_BLOCK_EXPERIMENT_IDS` / `_SINGLE_STANDARD_BLOCK_EXPERIMENT_CODES` 启用，目前代码特例包含 `GB50148-2010`，不是通用机制，见 `backend/tender_backend/services/norm_service/norm_processor.py:44`、`:2316`、`:2336`。
- 大纲重建只收集 1 到 2 级标题，`code.count(".") > 1` 会跳过 `3.1.1` 这类真实条款级编号，导致条款边界仍大量交给 AI 判断，见 `backend/tender_backend/services/norm_service/outline_rebuilder.py:26`、`:203`、`:208`。
- scope 拆分仍以 chapter/page/字符为主，`rebalance_scopes()` 只是按段落、行和字符预算拆分，不能保证 clause boundary 完整，见 `backend/tender_backend/services/norm_service/scope_splitter.py:229`、`:278`、`:388`。
- prompt 是“建筑工程规范条款提取助手”的泛化文本，但 schema、编号制度、表格策略、强制性用词、条文说明边界没有按标准 profile 注入，见 `backend/tender_backend/services/norm_service/prompt_builder.py:11`。
- `ParseProfile` 已存在，但只有 `cn_gb` 一个 profile，且阈值默认保守，无法覆盖行业规范、企业标准、英文/中英双语、表格式规范等场景，见 `backend/tender_backend/services/norm_service/parse_profiles.py:20`、`:77`、`:100`。
- 入库本身没有质量阻断。`quality_report` 即使 fail 也会继续 `delete_clauses()` + `bulk_create_clauses()`，见 `backend/tender_backend/services/norm_service/norm_processor.py:2466`、`:2476`；`bulk_create_clauses()` 只是批量插入字段，见 `backend/tender_backend/db/repositories/standard_repo.py:615`。
- 历史验收显示上游 cleaned bundle 已可达到 100% section anchor coverage，但 AI 入库验收曾被真实 key 阻断，说明当前缺少真实 AI 结果的稳定基线与 golden-set 回归，见 `docs/reports/2026-04-22-ai-clause-ingestion-acceptance.md:81`、`:109`。
- 当前 `skills` 只在质量报告中作为推荐项出现，不在上传/解析主链路中执行。`mineru-standard-bundle` 有实际 evaluate/clean/compare 脚本，能提高上游 parse asset 质量；`standard-parse-recovery` 是事故排查手册，能指导修复但不会自动修复。解析调度器仍只调用 `ensure_standard_ocr()` 和 `process_standard_ai()`，没有根据 skill 改变清洗、解析、prompt 或门禁策略。
- DeepSeek 已升级到 V4 Preview，`deepseek-v4-flash` 支持 1M context 和更高输出上限；当前系统仍有旧模型名和小输出限制：`ai_gateway/tender_ai_gateway/task_profiles.py` 默认 `deepseek-chat`，`tag_clauses` migration 默认 `deepseek-ai/DeepSeek-V3.2`，`norm_processor._call_ai_gateway()` 固定 `max_tokens=8192`，AI Gateway 默认 `max_tokens=4096`。

## Target Design

目标管线：

```text
PDF/MinerU cleaned bundle
  -> DocumentAsset
  -> SkillPlugin preflight hooks
  -> ProfileResolver
  -> DeterministicBlockParser
  -> ClauseBoundaryParser
  -> TableRequirementParser
  -> ClauseAST
  -> SkillPlugin enrichment/fallback hooks
  -> AI enrichment/fallback only
  -> Validation + coverage gates
  -> SkillPlugin recovery diagnostics
  -> persist when pass/review-approved
  -> index
```

核心原则：

- 条款边界、编号层级、页码锚点、source_ref 必须确定性生成。
- AI 不再负责“发现全部条款”，只负责摘要/标签/无法规则化的疑难片段。
- DeepSeek 主模型统一为 `deepseek-v4-flash`，明确禁止默认或自动选择 `deepseek-v4-pro`，避免成本失控。
- 1M context 只用于整本文档级审计、批量 enrich、跨 scope 一致性检查；不得把“整本 PDF 直接交给 AI 提取条款”作为主路径。
- profile 是解析行为的入口，不能靠 hard-coded standard id/code。
- skills 必须从“推荐文案”升级为可执行插件：preflight、cleanup、diagnostics、recovery、artifact review。
- 质量门禁必须在删旧数据和写新数据之前执行。
- 每次解析必须输出可复跑 artifact：normalized sections、blocks、raw AI responses、AST、validation、quality_report。

## File Structure

- Modify: `backend/tender_backend/services/norm_service/parse_profiles.py`
  - 扩展 `ParseProfile`，加入 numbering families、clause boundary regex、table strategies、commentary boundaries、quality thresholds。
- Create: `backend/tender_backend/services/norm_service/profile_resolver.py`
  - 根据 standard code/name、document language、section patterns 选择 profile。
- Create: `backend/tender_backend/services/norm_service/clause_boundary_parser.py`
  - 从 normalized sections/pages 生成 clause-level blocks，覆盖 `3.1.1`、`A.0.1`、`1.0.1`、列表项、条文说明。
- Modify: `backend/tender_backend/services/norm_service/block_segments.py`
  - 将 GB50148 实验 block path 升级为 profile-driven 通用 block builder。
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py`
  - 默认走 deterministic parser；AI 仅 fallback/enrich；质量门禁前置到入库前；按任务传递 `max_tokens` / timeout。
- Modify: `ai_gateway/tender_ai_gateway/task_profiles.py`
  - 将 DeepSeek 主模型从旧 `deepseek-chat` 迁移到 `deepseek-v4-flash`，并为解析审计、批量 enrich、fallback repair 配置不同 token/timeout。
- Modify: `ai_gateway/tender_ai_gateway/api/chat.py`
  - 支持请求不传 `max_tokens` 时使用 task profile 默认值，而不是固定 4096。
- Modify: `ai_gateway/tender_ai_gateway/fallback.py`
  - 从 task profile 读取 `max_tokens` 默认值；增加禁止 `deepseek-v4-pro` 的保护。
- Modify: `ai_gateway/tender_ai_gateway/core/config.py`
  - 默认主模型改为 `deepseek-v4-flash`。
- Modify: `backend/tender_backend/db/alembic/versions/0009_tag_clauses_siliconflow_primary.py` 或新增迁移
  - 将 `tag_clauses` 默认主模型改为官方 DeepSeek `deepseek-v4-flash` 或网关可用的 Flash 等价模型名；不得设置 V4 Pro。
- Modify: `backend/tests/unit/test_tag_clauses_defaults.py`
  - 更新默认模型断言，新增禁止 V4 Pro 的配置回归测试。
- Create: `backend/tender_backend/services/norm_service/skill_plugins.py`
  - 定义解析链路可执行 skill plugin 接口和 hook 调度器。
- Modify: `backend/tender_backend/services/skill_catalog.py`
  - 区分 documentation skills、workflow skills、executable parse plugins，并暴露 hook metadata。
- Modify: `docs/skills/mineru-standard-bundle/scripts/run_mineru_standard_bundle.py`
  - 抽出可被后端 import 的 evaluate/clean library API，避免主链路只能 shell 调 CLI。
- Modify: `docs/skills/mineru-standard-bundle/SKILL.md`
  - 增加作为解析 preflight/cleanup plugin 的契约说明。
- Modify: `docs/skills/standard-parse-recovery/SKILL.md`
  - 增加自动诊断规则清单，明确哪些规则应沉淀为代码 hook。
- Modify: `backend/tender_backend/services/norm_service/prompt_builder.py`
  - prompt 接受 profile + task mode，只生成 enrichment/fallback prompt。
- Create: `backend/tender_backend/services/norm_service/parse_artifacts.py`
  - 统一保存/序列化 blocks、AST、AI response、validation artifact。
- Modify: `backend/tender_backend/services/norm_service/quality_report.py`
  - 新增 coverage gate：expected clause count、must-have clauses、AI fallback ratio、unparsed block count。
- Test: `backend/tests/unit/test_clause_boundary_parser.py`
  - 覆盖条款边界、列表项、附录、条文说明。
- Test: `backend/tests/integration/test_general_standard_parser.py`
  - 使用 147/148/150 cleaned bundle 和小型 synthetic standards 验证通用入口。
- Test: `backend/tests/unit/test_skill_plugins.py`
  - 覆盖 skill hook 选择、执行顺序、失败策略和 artifact 输出。
- Test: `ai_gateway/tests/smoke/test_task_profiles.py`
  - 覆盖 `tag_clauses` / 新解析任务默认使用 `deepseek-v4-flash`，且不会选择 `deepseek-v4-pro`。

## Task 1: Baseline And Golden Fixtures

- [x] **Step 1: Freeze current sample inputs**

Use existing cleaned bundles under `tmp/mineru_standard_bundle/50147`, `tmp/mineru_standard_bundle/50173`, and `tmp/mineru_converted/GB50150-2016.*` as read-only fixtures or copy minimal normalized snippets into tests.

- [x] **Step 2: Define expected coverage fixtures**

Create fixture JSON with:

```json
{
  "standard_code": "GB50148-2010",
  "must_have_clause_nos": ["1.0.1", "2.0.1", "3.1.1", "4.1.1", "5.1.1"],
  "min_clause_count": 250,
  "min_anchor_coverage": 0.95,
  "max_validation_issues": 5
}
```

- [x] **Step 3: Add a failing integration test**

The test should call the new planned deterministic entrypoint and fail until it returns clause blocks without requiring AI credentials.

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/integration/test_general_standard_parser.py -q
```

Expected now: fail because the entrypoint does not exist.

## Task 2: Profile-Driven Parsing

- [x] **Step 1: Extend `ParseProfile`**

Add fields for `clause_heading_patterns`, `appendix_heading_patterns`, `commentary_heading_patterns`, `list_item_patterns`, `table_requirement_strategy`, and gate thresholds.

- [x] **Step 2: Add `profile_resolver.py`**

Implement `resolve_standard_profile(standard: dict | None, document_asset: DocumentAsset) -> ParseProfile`.

- [x] **Step 3: Remove standard-id special casing**

Replace `_SINGLE_STANDARD_BLOCK_EXPERIMENT_IDS` and `_SINGLE_STANDARD_BLOCK_EXPERIMENT_CODES` decisions with profile capability checks.

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/unit/test_block_segments.py backend/tests/unit/test_structural_nodes.py -q
```

Expected: existing behavior remains green.

## Task 3: Skill Plugin Integration

- [x] **Step 1: Define parse skill hook contract**

Create `backend/tender_backend/services/norm_service/skill_plugins.py` with hook names:

```python
from dataclasses import dataclass, field
from typing import Any, Protocol

@dataclass(frozen=True)
class ParseSkillContext:
    standard: dict | None
    document_id: str
    document_asset: Any
    raw_sections: list[dict]
    tables: list[dict]
    artifacts_dir: str | None = None

@dataclass
class ParseSkillResult:
    status: str
    messages: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    raw_sections: list[dict] | None = None
    tables: list[dict] | None = None
    document_asset: Any | None = None

class ParseSkillPlugin(Protocol):
    name: str
    hooks: tuple[str, ...]

    def run(self, hook: str, context: ParseSkillContext) -> ParseSkillResult:
        ...
```

- [x] **Step 2: Add hook phases to the parser**

Support these phases in `process_standard_ai()`:

```text
preflight_parse_asset
cleanup_parse_asset
before_profile_resolve
after_block_parse
after_validation
recovery_diagnostics
```

Failure policy:

```text
preflight_parse_asset fail -> stop before AI and return needs_review
cleanup_parse_asset fail -> continue only if original asset passes minimum quality
after_validation fail -> do not persist unless force flag is set
recovery_diagnostics fail -> attach warnings, do not mutate clauses
```

- [x] **Step 3: Register built-in plugins**

Implement two built-in plugins:

```text
mineru-standard-bundle-plugin
  hooks: preflight_parse_asset, cleanup_parse_asset
  behavior: evaluate/clean MinerU-derived assets and emit bundle metrics

standard-parse-recovery-plugin
  hooks: after_validation, recovery_diagnostics
  behavior: classify validation failures and recommend deterministic repair tasks
```

- [x] **Step 4: Connect `skill_definition.active`**

Only active configured skills should run automatically. Missing `skill_definition` rows should not block parsing; defaults from `default_skill_specs()` may be used as available-but-disabled execution candidates unless explicitly synced/active.

- [x] **Step 5: Write plugin tests**

Create `backend/tests/unit/test_skill_plugins.py` with tests for:

```python
def test_active_mineru_skill_runs_preflight_cleanup():
    ...

def test_inactive_skill_is_recommended_but_not_executed():
    ...

def test_preflight_failure_returns_needs_review_before_ai():
    ...

def test_recovery_diagnostics_adds_report_without_mutating_clauses():
    ...
```

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/unit/test_skill_plugins.py -q
```

Expected: plugin dispatch, skip, and failure behavior are deterministic.

## Task 4: DeepSeek V4 Flash Migration

- [x] **Step 1: Update AI Gateway task profile defaults**

Modify `ai_gateway/tender_ai_gateway/task_profiles.py`:

```python
TASK_PROFILES = {
    "generate_section": {
        "primary_model": "deepseek-v4-flash",
        "fallback_model": "qwen-max",
        "max_tokens": 8192,
    },
    "review_section": {
        "primary_model": "deepseek-v4-flash",
        "fallback_model": "qwen-max",
        "max_tokens": 8192,
    },
    "tag_clauses": {
        "primary_model": "deepseek-v4-flash",
        "fallback_model": "qwen-plus",
        "timeout": 600,
        "max_tokens": 32768,
        "max_retries": 0,
    },
    "standard_parse_audit": {
        "primary_model": "deepseek-v4-flash",
        "fallback_model": "qwen-plus",
        "timeout": 900,
        "max_tokens": 65536,
        "max_retries": 0,
    },
    "clause_enrichment_batch": {
        "primary_model": "deepseek-v4-flash",
        "fallback_model": "qwen-plus",
        "timeout": 600,
        "max_tokens": 32768,
        "max_retries": 0,
    },
    "unparsed_block_repair": {
        "primary_model": "deepseek-v4-flash",
        "fallback_model": "qwen-plus",
        "timeout": 600,
        "max_tokens": 16384,
        "max_retries": 0,
    },
    "vision_repair": {
        "primary_model": "Qwen/Qwen3-VL-8B-Instruct",
        "fallback_model": "Qwen/Qwen3-VL-8B-Instruct",
        "timeout": 300,
        "max_tokens": 4096,
        "max_retries": 1,
    },
}
```

Do not add `deepseek-v4-pro` to any default or fallback profile.

- [x] **Step 2: Use task profile max_tokens by default**

Modify `ai_gateway/tender_ai_gateway/api/chat.py` so `ChatRequest.max_tokens` can be `None`:

```python
class ChatRequest(BaseModel):
    ...
    max_tokens: int | None = None
```

Modify `ai_gateway/tender_ai_gateway/fallback.py`:

```python
profile_max_tokens = profile.get("max_tokens")
effective_max_tokens = max_tokens if max_tokens is not None else profile_max_tokens or 4096
```

Then pass `effective_max_tokens` to `client.chat.completions.create()`.

- [x] **Step 3: Add V4 Pro cost guard**

Add a guard in `fallback.py`:

```python
def _reject_disallowed_model(model: str) -> None:
    if model.strip().lower() in {"deepseek-v4-pro", "deepseek/deepseek-v4-pro"}:
        raise ValueError("deepseek-v4-pro is disabled for cost control; use deepseek-v4-flash")
```

Call it before each provider request, including override models.

- [x] **Step 4: Update backend `tag_clauses` payload**

Modify `_call_ai_gateway()` in `backend/tender_backend/services/norm_service/norm_processor.py` to avoid hard-coded 8192 for all extraction work:

```python
payload = {
    "task_type": "tag_clauses",
    "messages": [...],
    "temperature": 0.0,
    "max_tokens": None,
}
```

When the caller is an enrichment/audit task, use `task_type` values from Step 1 instead of overloading `tag_clauses`.

- [x] **Step 5: Add model migration**

Add a new Alembic migration after `0014`:

```sql
UPDATE agent_config
SET base_url = 'https://api.deepseek.com/v1',
    primary_model = 'deepseek-v4-flash',
    updated_at = now()
WHERE agent_key IN ('tag_clauses', 'generate_section', 'review_section')
  AND primary_model IN ('deepseek-chat', 'deepseek-reasoner', 'deepseek-ai/DeepSeek-V3.2');
```

If production must keep SiliconFlow as provider, use its Flash-equivalent model name only after verifying the exact provider model id. Do not set V4 Pro.

- [x] **Step 6: Update tests**

Update or add:

```text
backend/tests/unit/test_tag_clauses_defaults.py
ai_gateway/tests/smoke/test_task_profiles.py
ai_gateway/tests/smoke/test_fallback.py
```

Required assertions:

```python
assert profile["primary_model"] == "deepseek-v4-flash"
assert "deepseek-v4-pro" not in json.dumps(TASK_PROFILES).lower()
```

Run:

```bash
PYTHONPATH=ai_gateway ./.venv/bin/python -m pytest ai_gateway/tests/smoke/test_task_profiles.py ai_gateway/tests/smoke/test_fallback.py -q
PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/unit/test_tag_clauses_defaults.py -q
```

Expected: model defaults use Flash only; Pro is rejected.

## Task 5: Prompt Redesign For Long Context Flash

- [x] **Step 1: Add audit prompt mode**

Create `STANDARD_PARSE_AUDIT_PROMPT` in `backend/tender_backend/services/norm_service/prompt_builder.py`.

Prompt contract:

```text
You are auditing a deterministic standard parser output.
Do not extract the document from scratch.
Given document outline, deterministic blocks, AST summary, validation issues, and source refs:
1. report missing clause numbers
2. report duplicated or merged clauses
3. report commentary mismatches
4. report table requirement gaps
5. return JSON patches keyed by block_id/node_key/source_ref
If evidence is insufficient, return needs_review instead of guessing.
```

- [x] **Step 2: Add batch enrichment prompt mode**

Create `CLAUSE_ENRICHMENT_BATCH_PROMPT`.

Input is a list of existing clause nodes:

```json
[
  {
    "node_key": "3.1.1",
    "clause_no": "3.1.1",
    "clause_text": "...",
    "source_refs": ["document_section:..."]
  }
]
```

Output must only include:

```json
[
  {
    "node_key": "3.1.1",
    "summary": "...",
    "tags": ["..."],
    "requirement_type": "mandatory|advisory|permissive|informative",
    "mandatory_terms": ["应", "不得"]
  }
]
```

The model must not add, remove, split, merge, or renumber clauses.

- [x] **Step 3: Add repair prompt mode**

Create `UNPARSED_BLOCK_REPAIR_PROMPT` for low-confidence blocks only.

Output must be patch-oriented:

```json
{
  "status": "patch|needs_review|no_change",
  "patches": [
    {
      "source_ref": "document_section:...",
      "operation": "split_clause|attach_item|normalize_table",
      "evidence": "...",
      "candidate": {}
    }
  ]
}
```

- [x] **Step 4: Keep extraction prompt only as legacy fallback**

Keep existing `CLAUSE_EXTRACTION_PROMPT` temporarily for compatibility, but mark it as legacy and do not call it from the new deterministic path except behind an explicit feature flag.

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/unit/test_ast_builder.py backend/tests/unit/test_validation.py -q
```

Expected: prompt additions do not affect existing AST/validation behavior.

## Task 6: Deterministic Clause Boundary Parser

- [x] **Step 1: Create `clause_boundary_parser.py`**

Implement a parser that emits block objects with stable fields:

```python
{
    "block_type": "clause",
    "clause_no": "3.1.1",
    "clause_text": "...",
    "page_start": 12,
    "page_end": 12,
    "source_refs": ["document_section:..."],
    "confidence": "high"
}
```

- [x] **Step 2: Support nested list carry-forward**

When a clause ends with `：` or contains `下列/如下`, attach subsequent `1` / `1、` / `(1)` / `1)` sections as item/subitem nodes under the host clause.

- [x] **Step 3: Support commentary pairing**

Parse commentary blocks independently, then link by `clause_no` only after normative clause map exists.

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/unit/test_clause_boundary_parser.py -q
```

Expected: all parser boundary tests pass without AI.

## Task 7: Table Requirement Normalization

- [x] **Step 1: Extract current table parser**

Move `_TableHTMLParser`, `_expand_table_rows()`, and deterministic table entry logic from `norm_processor.py` into a focused module.

- [x] **Step 2: Add profile table strategies**

Support at least:

```text
quality_inspection_table
parameter_limit_table
form_template_table
non_requirement_table
```

- [x] **Step 3: Gate form-only tables**

Tables that are forms/check records should be preserved as source assets but not inflated into navigable clauses unless they contain explicit quality requirements.

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/unit/test_mineru_standard_bundle.py backend/tests/unit/test_standard_quality_report.py -q
```

Expected: table capture metrics remain stable or improve.

## Task 8: AI As Enrichment/Fallback

- [x] **Step 1: Split prompt modes**

Replace the current all-in-one extraction prompt with:

```text
summarize_tags
classify_requirement
repair_unparsed_block
normalize_table_requirement
```

Map these to Flash-only task types:

```text
summarize_tags -> clause_enrichment_batch
classify_requirement -> clause_enrichment_batch
repair_unparsed_block -> unparsed_block_repair
normalize_table_requirement -> unparsed_block_repair or table_requirement_normalize
whole-document consistency -> standard_parse_audit
```

- [x] **Step 2: Add raw response artifacts**

Persist AI input/output per block so every model decision can be audited and replayed.

- [x] **Step 3: Enforce fallback ratio**

If more than a configured percentage of blocks require AI fallback, quality status should be fail/review before DB replacement.

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/unit/test_ast_builder.py backend/tests/unit/test_validation.py -q
```

Expected: AST and validation tests remain green.

## Task 9: Pre-Persist Quality Gate

- [x] **Step 1: Move quality gate before delete/insert**

In `process_standard_ai()`, compute `quality_report` before `_std_repo.delete_clauses()`.

- [x] **Step 2: Add status behavior**

If quality is `fail`, do not delete existing clauses. Store artifacts and mark processing as `needs_review` or return `status="needs_review"`.

- [x] **Step 3: Add explicit force flag**

Allow a controlled `force_persist_failed_quality=True` path only for diagnostics.

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/integration/test_standard_processing_scheduler.py backend/tests/integration/test_standard_viewer_query_api.py -q
```

Expected: failed quality no longer wipes existing usable clauses.

## Task 10: Skill-Aware Quality Report And API

- [x] **Step 1: Record executed skill hooks**

Add `executed_skills` to `quality_report`:

```json
[
  {
    "skill_name": "mineru-standard-bundle",
    "hook": "cleanup_parse_asset",
    "status": "pass",
    "metrics": {
      "section_page_coverage_ratio": 1.0,
      "toc_noise_count": 0
    }
  }
]
```

- [x] **Step 2: Separate executed skills from recommended skills**

Keep `recommended_skills` for human follow-up, but add:

```json
{
  "executed_skills": [],
  "available_skills": [],
  "disabled_parse_plugins": []
}
```

- [x] **Step 3: Add API regression test**

Update `backend/tests/integration/test_standard_viewer_query_api.py` so `/quality-report` proves:

```text
recommended_skills remains available for review
executed_skills shows plugins actually run in the pipeline
inactive skills are not silently executed
```

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/integration/test_standard_viewer_query_api.py -q
```

Expected: API payload distinguishes recommendation from execution.

## Acceptance Criteria

- `process_standard_ai()` can produce deterministic clause AST for 147/148/150 without requiring real AI credentials for boundary extraction.
- Active parse skills run through explicit hooks in the parsing chain; inactive skills remain recommendations only.
- `mineru-standard-bundle` cleanup can be invoked automatically as a preflight/cleanup plugin for MinerU parse assets.
- `standard-parse-recovery` diagnostics can classify validation issues without mutating clauses unless a specific repair task is approved.
- DeepSeek defaults and `tag_clauses` migration use `deepseek-v4-flash` only; `deepseek-v4-pro` is rejected by test and runtime guard.
- AI Gateway task profiles provide task-specific `max_tokens` and timeout defaults instead of fixed 4096/8192 limits.
- Long-context Flash is used for whole-document audit and batch enrichment, not as the primary clause-boundary parser.
- `standard_clause` replacement only happens when quality gates pass or an explicit force flag is used.
- `quality_report.metrics` includes clause coverage, anchor coverage, table capture, unparsed block count, AI fallback ratio, must-have clause coverage, and executed skill hook summaries.
- `ParseProfile` supports at least `cn_gb` plus one synthetic non-GB profile in tests.
- The parser preserves `source_refs` and page anchors for at least 95% of persisted clauses on cleaned bundles.
- Reindexing uses persisted clauses only after successful parse quality gate.

## Open Questions

- Whether `needs_review` should be a new `standard.processing_status` value or only a returned process status.
- Whether parse artifacts should live in `document.raw_payload`, a new table, or filesystem under `tmp/parse_artifacts`.
- Which real provider/model should be the enrichment baseline after boundary extraction is deterministic.
- Whether parse skill plugins should be enabled by default after `/settings/skills/sync-defaults`, or require an explicit `auto_execute` flag separate from `active`.
- Whether `docs/skills/*` should remain the source of truth for human instructions only, while executable plugin metadata lives in Python registry code.
- Whether production should call DeepSeek official API directly for `deepseek-v4-flash`, or keep SiliconFlow if and only if it exposes an equivalent Flash model id with the same context and pricing assumptions.
