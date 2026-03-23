# MinerU Structured Front-End Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current text-only `MinerU -> AI` standard pipeline with a MinerU-led structured parsing flow, add AST/grammar/phrase validation plus local VL repair, and retire the whole-document Qwen-VL pipeline.

**Architecture:** Keep MinerU as the only document-wide parser and promote its `markdown + page payload + table payload` output into explicit structured assets. Build an AST from structured scopes, run deterministic grammar and phrase validation, then send only table and numeric/symbol anomalies to a local VL repair service before projecting the validated AST into `standard_clause`.

**Tech Stack:** FastAPI, Psycopg, Pydantic settings, MinerU batch parsing, AI Gateway task profiles, pytest

---

## File Structure

### Existing files to modify

- `backend/tender_backend/services/norm_service/norm_processor.py`
  Current MinerU orchestration. Refactor to consume structured assets, call validators, invoke repair tasks, and persist AST-derived clauses.
- `backend/tender_backend/services/norm_service/prompt_builder.py`
  Replace plain-text-only prompts with prompts that serialize structured scope metadata and repair context.
- `backend/tender_backend/services/norm_service/tree_builder.py`
  Narrow responsibility to AST-to-clause projection or keep projection helpers only; remove assumptions that all hierarchy originates from raw LLM flat entries.
- `backend/tender_backend/services/parse_service/parser.py`
  Preserve and expose richer MinerU parse assets needed by the structured pipeline.
- `backend/tender_backend/workflows/standard_ingestion.py`
  Remove whole-document vision workflow, wire standard ingestion to the structured MinerU pipeline, and keep retry semantics stable.
- `backend/tender_backend/api/standards.py`
  Remove `/process-vision`, keep parse-asset endpoints useful for debugging structured assets, and preserve `/process`.
- `backend/tender_backend/db/repositories/standard_repo.py`
  Add helpers for structured parse assets and AST-backed persistence metadata if needed.
- `backend/tender_backend/core/config.py`
  Replace whole-page vision settings with local VL repair settings.
- `ai_gateway/tender_ai_gateway/task_profiles.py`
  Replace `vision_extract_clauses` with a local repair task profile.
- `ai_gateway/tests/smoke/test_task_profiles.py`
  Update task-profile assertions for repair usage.
- `backend/tests/integration/test_standard_mineru_batch_flow.py`
  Extend integration coverage from MinerU parse to structured scopes / validation / repair planning.
- `backend/tests/integration/test_standard_viewer_query_api.py`
  Keep parse-assets and viewer behavior aligned with new source metadata.
- `backend/tests/unit/test_standard_tree_builder.py`
  Retarget tests toward AST projection behavior and source metadata preservation.
- `backend/tests/unit/test_vision_settings.py`
  Replace with repair-setting coverage.

### Existing files to delete in the final retirement chunk

- `backend/tender_backend/services/vision_service/vision_processor.py`
- `backend/tender_backend/services/vision_service/vision_prompt.py`
- `backend/tender_backend/services/vision_service/page_merger.py`
- `backend/tests/unit/test_page_merger.py`

### Existing files to keep

- `backend/tender_backend/services/vision_service/pdf_renderer.py`
  Reuse for rendering page or cropped page images for repair requests.
- `backend/tests/unit/test_pdf_renderer.py`
  Keep as the renderer regression suite.

### New files to create

- `backend/tender_backend/services/norm_service/document_assets.py`
  Build `DocumentAsset`, page assets, and table assets from persisted MinerU results.
- `backend/tender_backend/services/norm_service/structural_nodes.py`
  Define `StructuralNode` and helpers that turn MinerU assets into structured nodes and scopes.
- `backend/tender_backend/services/norm_service/ast_models.py`
  Define AST node dataclasses and typed issue / repair-task models.
- `backend/tender_backend/services/norm_service/ast_builder.py`
  Build AST from structured scopes and AI extraction output while retaining `source_ref`.
- `backend/tender_backend/services/norm_service/validation.py`
  Implement grammar and phrase validators plus mandatory-clause detection.
- `backend/tender_backend/services/norm_service/repair_tasks.py`
  Convert validation issues into deduplicated `RepairTask` objects.
- `backend/tender_backend/services/norm_service/ast_merger.py`
  Merge local VL repair results back into AST nodes and rerun local validation.
- `backend/tender_backend/services/vision_service/repair_prompt.py`
  Build local repair prompts for table and numeric/symbol repair.
- `backend/tender_backend/services/vision_service/repair_service.py`
  Call AI Gateway for repair tasks and return typed patch results.
- `backend/tests/unit/test_document_assets.py`
- `backend/tests/unit/test_structural_nodes.py`
- `backend/tests/unit/test_ast_builder.py`
- `backend/tests/unit/test_validation.py`
- `backend/tests/unit/test_repair_tasks.py`
- `backend/tests/unit/test_repair_service.py`

## Chunk 1: Structured Assets And Scope Construction

### Task 1: Preserve MinerU Parse Assets As First-Class Objects

**Files:**
- Create: `backend/tender_backend/services/norm_service/document_assets.py`
- Modify: `backend/tender_backend/services/parse_service/parser.py`
- Modify: `backend/tender_backend/db/repositories/standard_repo.py`
- Test: `backend/tests/unit/test_document_assets.py`
- Test: `backend/tests/integration/test_standard_viewer_query_api.py`

- [ ] **Step 1: Write the failing unit tests for document assets**

```python
from tender_backend.services.norm_service.document_assets import build_document_asset


def test_build_document_asset_prefers_document_raw_payload_pages_and_tables() -> None:
    asset = build_document_asset(
        document_id="doc-1",
        document={"raw_payload": {
            "full_markdown": "# 1 总则\n正文",
            "pages": [{"page_number": 3, "markdown": "1 总则\n正文"}],
            "tables": [{"page_start": 4, "table_title": "主要参数", "html": "<table></table>"}],
        }},
        sections=[],
        tables=[],
    )

    assert asset.full_markdown.startswith("# 1 总则")
    assert asset.pages[0].page_number == 3
    assert asset.tables[0].page_start == 4


def test_build_document_asset_falls_back_to_section_and_table_rows() -> None:
    asset = build_document_asset(
        document_id="doc-1",
        document={"raw_payload": None},
        sections=[{"id": "sec-1", "section_code": "1", "title": "总则", "text": "正文", "page_start": 5, "page_end": 5, "raw_json": {"page_number": 5}}],
        tables=[{"id": "tbl-1", "page_start": 6, "page_end": 7, "table_title": "参数", "table_html": "<table></table>", "raw_json": {"cells": []}}],
    )

    assert asset.pages[0].page_number == 5
    assert asset.tables[0].source_ref == "table:tbl-1"
```

- [ ] **Step 2: Run the new unit tests and verify they fail**

Run: `PYTHONPATH=backend .venv/bin/pytest backend/tests/unit/test_document_assets.py -q`
Expected: FAIL with `ModuleNotFoundError` or missing `build_document_asset`

- [ ] **Step 3: Implement document asset models and repository helpers**

```python
@dataclass(slots=True)
class PageAsset:
    page_number: int
    normalized_text: str
    raw_page: dict[str, Any]
    source_ref: str


@dataclass(slots=True)
class TableAsset:
    source_ref: str
    page_start: int | None
    page_end: int | None
    table_title: str | None
    table_html: str | None
    raw_json: dict[str, Any]


@dataclass(slots=True)
class DocumentAsset:
    document_id: str
    parser_name: str | None
    parser_version: str | None
    full_markdown: str
    pages: list[PageAsset]
    tables: list[TableAsset]


def build_document_asset(*, document_id: str, document: dict, sections: list[dict], tables: list[dict]) -> DocumentAsset:
    ...
```

- [ ] **Step 4: Add parse-asset API regression coverage**

Run: `PYTHONPATH=backend .venv/bin/pytest backend/tests/integration/test_standard_viewer_query_api.py -q -k "parse_assets"`
Expected: PASS and parse-assets response still returns `parser_name`, `raw_payload`, section rows, and table rows

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/services/norm_service/document_assets.py \
  backend/tender_backend/services/parse_service/parser.py \
  backend/tender_backend/db/repositories/standard_repo.py \
  backend/tests/unit/test_document_assets.py \
  backend/tests/integration/test_standard_viewer_query_api.py
git commit -m "feat: preserve mineru parse assets as structured objects"
```

### Task 2: Build Structural Nodes And Structured Processing Scopes

**Files:**
- Create: `backend/tender_backend/services/norm_service/structural_nodes.py`
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py`
- Modify: `backend/tender_backend/services/norm_service/prompt_builder.py`
- Test: `backend/tests/unit/test_structural_nodes.py`
- Test: `backend/tests/integration/test_standard_mineru_batch_flow.py`

- [ ] **Step 1: Write failing tests for structural-node construction**

```python
from tender_backend.services.norm_service.structural_nodes import build_structural_nodes, build_processing_scopes


def test_build_structural_nodes_creates_table_nodes_with_source_refs(document_asset) -> None:
    nodes = build_structural_nodes(document_asset)
    table_nodes = [node for node in nodes if node.node_type == "table"]
    assert table_nodes[0].source_ref.startswith("table:")


def test_build_processing_scopes_serializes_markdown_and_layout_context(document_asset) -> None:
    scopes = build_processing_scopes(document_asset)
    assert scopes[0].scope_type == "normative"
    assert scopes[0].source_refs
    assert "full_markdown" not in scopes[0].text
    assert scopes[0].context["page_start"] == 3
```

- [ ] **Step 2: Run the new structural-node tests and verify they fail**

Run: `PYTHONPATH=backend .venv/bin/pytest backend/tests/unit/test_structural_nodes.py -q`
Expected: FAIL because `structural_nodes.py` does not exist yet

- [ ] **Step 3: Implement node and scope builders, then refactor the pipeline to use them**

```python
@dataclass(slots=True)
class StructuralNode:
    node_type: str
    node_key: str
    node_label: str | None
    title: str | None
    text: str
    page_start: int | None
    page_end: int | None
    source_ref: str
    children: list["StructuralNode"]


def build_processing_scopes(asset: DocumentAsset) -> list[ProcessingScope]:
    return [
        ProcessingScope(
            scope_type="table" if node.node_type == "table" else "normative",
            chapter_label=node.title or node.node_key,
            text=node.text,
            page_start=node.page_start or 0,
            page_end=node.page_end or node.page_start or 0,
            section_ids=[],
            context={"source_ref": node.source_ref, "node_type": node.node_type},
            source_refs=[node.source_ref],
        )
        for node in build_structural_nodes(asset)
    ]
```

- [ ] **Step 4: Update prompts to consume structured context and verify integration tests**

Run: `PYTHONPATH=backend .venv/bin/pytest backend/tests/integration/test_standard_mineru_batch_flow.py -q -k "parse_via_mineru or process_standard_ai_uses_existing_ocr_sections"`
Expected: PASS with scopes built from structured assets instead of pure text windows only

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/services/norm_service/structural_nodes.py \
  backend/tender_backend/services/norm_service/norm_processor.py \
  backend/tender_backend/services/norm_service/prompt_builder.py \
  backend/tests/unit/test_structural_nodes.py \
  backend/tests/integration/test_standard_mineru_batch_flow.py
git commit -m "feat: build structured scopes from mineru assets"
```

## Chunk 2: AST Construction, Grammar Rules, And Phrase Detection

### Task 3: Introduce AST Models And AST Builder

**Files:**
- Create: `backend/tender_backend/services/norm_service/ast_models.py`
- Create: `backend/tender_backend/services/norm_service/ast_builder.py`
- Modify: `backend/tender_backend/services/norm_service/tree_builder.py`
- Test: `backend/tests/unit/test_ast_builder.py`
- Test: `backend/tests/unit/test_standard_tree_builder.py`

- [ ] **Step 1: Write failing AST-builder tests**

```python
from tender_backend.services.norm_service.ast_builder import build_clause_ast


def test_build_clause_ast_keeps_source_ref_and_page_range() -> None:
    ast = build_clause_ast(
        standard_id=uuid4(),
        entries=[{
            "node_type": "clause",
            "clause_no": "3.2.1",
            "clause_text": "混凝土强度等级不应低于 C30。",
            "page_start": 12,
            "page_end": 12,
            "source_ref": "page:12",
        }],
    )

    assert ast.roots[0].source_ref == "page:12"
    assert ast.roots[0].page_start == 12


def test_project_ast_to_clauses_normalizes_blank_page_numbers() -> None:
    ...
```

- [ ] **Step 2: Run AST-builder tests and verify they fail**

Run: `PYTHONPATH=backend .venv/bin/pytest backend/tests/unit/test_ast_builder.py backend/tests/unit/test_standard_tree_builder.py -q`
Expected: FAIL because `build_clause_ast` and AST projection helpers do not exist yet

- [ ] **Step 3: Implement AST models and move persistence-facing projection into `tree_builder.py`**

```python
@dataclass(slots=True)
class ClauseAstNode:
    node_type: str
    node_key: str
    node_label: str | None
    clause_no: str | None
    clause_title: str | None
    clause_text: str
    summary: str | None
    tags: list[str]
    page_start: int | None
    page_end: int | None
    source_ref: str | None
    source_type: str
    source_label: str | None
    children: list["ClauseAstNode"]


def build_clause_ast(*, standard_id: UUID, entries: list[dict]) -> ClauseAst:
    ...
```

- [ ] **Step 4: Verify AST projection tests**

Run: `PYTHONPATH=backend .venv/bin/pytest backend/tests/unit/test_ast_builder.py backend/tests/unit/test_standard_tree_builder.py -q`
Expected: PASS with source metadata, hierarchy, and page normalization preserved

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/services/norm_service/ast_models.py \
  backend/tender_backend/services/norm_service/ast_builder.py \
  backend/tender_backend/services/norm_service/tree_builder.py \
  backend/tests/unit/test_ast_builder.py \
  backend/tests/unit/test_standard_tree_builder.py
git commit -m "feat: add clause ast builder and projection helpers"
```

### Task 4: Implement Grammar Validation And Phrase-Based Detection

**Files:**
- Create: `backend/tender_backend/services/norm_service/validation.py`
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py`
- Test: `backend/tests/unit/test_validation.py`
- Test: `backend/tests/integration/test_standard_mineru_batch_flow.py`

- [ ] **Step 1: Write failing validation tests**

```python
from tender_backend.services.norm_service.validation import validate_ast, detect_phrase_flags


def test_validate_ast_flags_clause_number_jump() -> None:
    issues = validate_ast(ast_with_clause_numbers(["3", "3.2.1"]))
    assert issues[0].issue_type == "clause_number_jump"


def test_detect_phrase_flags_marks_mandatory_clauses() -> None:
    flags = detect_phrase_flags("混凝土强度等级不得低于 C30。")
    assert flags.is_mandatory is True


def test_validate_ast_flags_symbol_numeric_anomaly_for_broken_unit() -> None:
    issues = validate_ast(ast_with_text("抗压强度不应小于 30 MP"))
    assert any(issue.issue_type == "symbol_numeric_anomaly" for issue in issues)
```

- [ ] **Step 2: Run validation tests and verify they fail**

Run: `PYTHONPATH=backend .venv/bin/pytest backend/tests/unit/test_validation.py -q`
Expected: FAIL because `validation.py` does not exist yet

- [ ] **Step 3: Implement deterministic validators and integrate them after AST build**

```python
MANDATORY_PHRASES = ("必须", "应", "不得", "严禁", "禁止")
RECOMMENDED_PHRASES = ("宜", "可", "不宜")
NUMERIC_SYMBOL_PATTERNS = (
    re.compile(r"\\b\\d+(?:\\.\\d+)?\\s*(?:MPa|mm|m³|kN/m²)\\b"),
    re.compile(r"[≥≤><=~]"),
)


def validate_ast(ast: ClauseAst) -> list[ValidationIssue]:
    issues = []
    issues.extend(_validate_numbering(ast))
    issues.extend(_validate_page_anchors(ast))
    issues.extend(_validate_table_attachments(ast))
    issues.extend(_validate_numeric_symbols(ast))
    return issues
```

- [ ] **Step 4: Run validation unit tests and focused integration tests**

Run: `PYTHONPATH=backend .venv/bin/pytest backend/tests/unit/test_validation.py backend/tests/integration/test_standard_mineru_batch_flow.py -q -k "process_standard_ai_processes_text_and_table_scopes or validation"`
Expected: PASS with validation issues generated before persistence

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/services/norm_service/validation.py \
  backend/tender_backend/services/norm_service/norm_processor.py \
  backend/tests/unit/test_validation.py \
  backend/tests/integration/test_standard_mineru_batch_flow.py
git commit -m "feat: add ast grammar and phrase validation"
```

## Chunk 3: Local VL Repair For Tables And Numeric/Symbol Anomalies

### Task 5: Generate Deduplicated Repair Tasks

**Files:**
- Create: `backend/tender_backend/services/norm_service/repair_tasks.py`
- Modify: `backend/tender_backend/services/norm_service/validation.py`
- Test: `backend/tests/unit/test_repair_tasks.py`

- [ ] **Step 1: Write failing tests for repair-task generation**

```python
from tender_backend.services.norm_service.repair_tasks import build_repair_tasks


def test_build_repair_tasks_promotes_all_tables_to_candidates() -> None:
    tasks = build_repair_tasks(ast_with_table_node(), issues=[])
    assert tasks[0].task_type == "table_repair"


def test_build_repair_tasks_deduplicates_symbol_numeric_issues_by_source_ref() -> None:
    tasks = build_repair_tasks(
        ast_with_text("抗压强度不应小于 30 MP"),
        issues=[issue("symbol_numeric_anomaly", source_ref="page:12"), issue("symbol_numeric_anomaly", source_ref="page:12")],
    )
    assert len(tasks) == 1
```

- [ ] **Step 2: Run repair-task tests and verify they fail**

Run: `PYTHONPATH=backend .venv/bin/pytest backend/tests/unit/test_repair_tasks.py -q`
Expected: FAIL because `build_repair_tasks` does not exist yet

- [ ] **Step 3: Implement task generation with high-recall defaults**

```python
def build_repair_tasks(ast: ClauseAst, issues: list[ValidationIssue]) -> list[RepairTask]:
    tasks = []
    tasks.extend(_table_tasks_from_ast(ast))
    tasks.extend(_symbol_tasks_from_issues(issues))
    return _deduplicate_tasks(tasks)
```

- [ ] **Step 4: Verify repair-task tests**

Run: `PYTHONPATH=backend .venv/bin/pytest backend/tests/unit/test_repair_tasks.py -q`
Expected: PASS with all table nodes becoming candidates and numeric issues deduplicated by `source_ref`

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/services/norm_service/repair_tasks.py \
  backend/tender_backend/services/norm_service/validation.py \
  backend/tests/unit/test_repair_tasks.py
git commit -m "feat: plan local vl repair tasks from validation issues"
```

### Task 6: Replace Whole-Document Vision Processing With Local Repair Service

**Files:**
- Create: `backend/tender_backend/services/vision_service/repair_prompt.py`
- Create: `backend/tender_backend/services/vision_service/repair_service.py`
- Create: `backend/tender_backend/services/norm_service/ast_merger.py`
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py`
- Modify: `backend/tender_backend/core/config.py`
- Modify: `ai_gateway/tender_ai_gateway/task_profiles.py`
- Test: `backend/tests/unit/test_repair_service.py`
- Test: `backend/tests/unit/test_pdf_renderer.py`
- Test: `backend/tests/unit/test_vision_settings.py`
- Test: `ai_gateway/tests/smoke/test_task_profiles.py`

- [ ] **Step 1: Write failing repair-service and settings tests**

```python
from tender_backend.services.vision_service.repair_service import run_repair_tasks
from tender_backend.core.config import Settings


def test_run_repair_tasks_uses_local_repair_task_type(monkeypatch) -> None:
    result = run_repair_tasks(conn=object(), tasks=[repair_task("table_repair")], document_id="doc-1")
    assert result[0].task_type == "table_repair"


def test_repair_settings_defaults_are_local_and_serial() -> None:
    settings = Settings()
    assert settings.vl_repair_max_concurrent_tasks == 1
    assert settings.vl_repair_ai_gateway_timeout_seconds == 300.0
```

- [ ] **Step 2: Run repair-service and settings tests and verify they fail**

Run: `PYTHONPATH=backend .venv/bin/pytest backend/tests/unit/test_repair_service.py backend/tests/unit/test_vision_settings.py -q`
Expected: FAIL because repair service and repair settings do not exist yet

- [ ] **Step 3: Implement local repair prompt/service and AST merge**

```python
TASK_PROFILES["vision_repair"] = {
    "primary_model": "Qwen/Qwen3-VL-8B-Instruct",
    "fallback_model": "Qwen/Qwen3-VL-8B-Instruct",
    "timeout": 300,
    "max_retries": 1,
}


def run_repair_tasks(*, conn: Connection, document_id: str, tasks: list[RepairTask]) -> list[RepairPatch]:
    for task in tasks:
        image_payload = render_source_ref_to_image(document_id=document_id, source_ref=task.source_ref)
        prompt = build_repair_messages(task, image_payload=image_payload)
        ...


def merge_repair_patches(ast: ClauseAst, patches: list[RepairPatch]) -> ClauseAst:
    ...
```

- [ ] **Step 4: Integrate repair after validation, then verify tests**

Run: `PYTHONPATH=backend .venv/bin/pytest backend/tests/unit/test_repair_service.py backend/tests/unit/test_pdf_renderer.py backend/tests/unit/test_vision_settings.py -q`
Expected: PASS with renderer reused for repair requests and config renamed to repair semantics

Run: `cd ai_gateway && ../.venv/bin/pytest tests/smoke/test_task_profiles.py -q`
Expected: PASS with `vision_repair` timeout assertions

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/services/vision_service/repair_prompt.py \
  backend/tender_backend/services/vision_service/repair_service.py \
  backend/tender_backend/services/norm_service/ast_merger.py \
  backend/tender_backend/services/norm_service/norm_processor.py \
  backend/tender_backend/core/config.py \
  ai_gateway/tender_ai_gateway/task_profiles.py \
  backend/tests/unit/test_repair_service.py \
  backend/tests/unit/test_pdf_renderer.py \
  backend/tests/unit/test_vision_settings.py \
  ai_gateway/tests/smoke/test_task_profiles.py
git commit -m "feat: add local vl repair for tables and symbol anomalies"
```

## Chunk 4: Retire Whole-Document Qwen-VL Pipeline

### Task 7: Remove Vision API Entry Points And Workflow Registration

**Files:**
- Modify: `backend/tender_backend/api/standards.py`
- Modify: `backend/tender_backend/workflows/standard_ingestion.py`
- Test: `backend/tests/integration/test_standard_processing_queue_api.py`

- [ ] **Step 1: Write failing API/workflow retirement tests**

```python
def test_process_vision_endpoint_is_not_registered(client) -> None:
    response = client.post("/api/standards/11111111-1111-1111-1111-111111111111/process-vision")
    assert response.status_code == 404


def test_retry_process_endpoint_still_requeues_failed_stage(client, seeded_standard) -> None:
    response = client.post(f"/api/standards/{seeded_standard}/process", headers={"Authorization": "Bearer dev-token"})
    assert response.status_code == 200
```

- [ ] **Step 2: Run retirement tests and verify they fail**

Run: `PYTHONPATH=backend .venv/bin/pytest backend/tests/integration/test_standard_processing_queue_api.py -q -k "process_vision or retry"`
Expected: FAIL because `/process-vision` still exists

- [ ] **Step 3: Remove the route and workflow classes**

```python
# Delete trigger_vision_processing from standards.py
# Delete VisionExtractClauses and StandardVisionIngestionWorkflow from standard_ingestion.py
# Keep only the standard_ingestion workflow and reuse local repair inside norm_processor
```

- [ ] **Step 4: Verify queue and retry behavior**

Run: `PYTHONPATH=backend .venv/bin/pytest backend/tests/integration/test_standard_processing_queue_api.py -q`
Expected: PASS with retry semantics unchanged and no public vision endpoint remaining

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/api/standards.py \
  backend/tender_backend/workflows/standard_ingestion.py \
  backend/tests/integration/test_standard_processing_queue_api.py
git commit -m "refactor: remove whole-document vision processing entrypoints"
```

### Task 8: Delete Obsolete Whole-Page Vision Modules And Finalize Regression Coverage

**Files:**
- Delete: `backend/tender_backend/services/vision_service/vision_processor.py`
- Delete: `backend/tender_backend/services/vision_service/vision_prompt.py`
- Delete: `backend/tender_backend/services/vision_service/page_merger.py`
- Delete: `backend/tests/unit/test_page_merger.py`
- Modify: `backend/tests/integration/test_standard_mineru_batch_flow.py`
- Modify: `backend/tests/unit/test_pdf_renderer.py`

- [ ] **Step 1: Write the final failing regression test for the structured pipeline**

```python
def test_process_standard_ai_repairs_table_and_symbol_anomalies_before_persist(monkeypatch) -> None:
    summary = process_standard_ai(...)
    assert summary["repair_task_count"] >= 2
    assert summary["issues_before_repair"] >= summary["issues_after_repair"]
```

- [ ] **Step 2: Run the focused regression test and verify it fails**

Run: `PYTHONPATH=backend .venv/bin/pytest backend/tests/integration/test_standard_mineru_batch_flow.py -q -k "repairs_table_and_symbol_anomalies"`
Expected: FAIL because structured repair summary is not fully wired yet

- [ ] **Step 3: Delete obsolete modules and finish the structured summary wiring**

```python
return {
    "pipeline": "mineru_structured",
    "scopes_processed": len(scopes),
    "repair_task_count": len(repair_tasks),
    "issues_before_repair": len(issues),
    "issues_after_repair": len(revalidated_issues),
    "total_clauses": inserted,
}
```

- [ ] **Step 4: Run the final regression suite**

Run: `PYTHONPATH=backend .venv/bin/pytest backend/tests/unit/test_document_assets.py backend/tests/unit/test_structural_nodes.py backend/tests/unit/test_ast_builder.py backend/tests/unit/test_validation.py backend/tests/unit/test_repair_tasks.py backend/tests/unit/test_repair_service.py backend/tests/unit/test_standard_tree_builder.py backend/tests/unit/test_pdf_renderer.py -q`
Expected: PASS

Run: `PYTHONPATH=backend .venv/bin/pytest backend/tests/integration/test_standard_mineru_batch_flow.py backend/tests/integration/test_standard_viewer_query_api.py backend/tests/integration/test_standard_processing_queue_api.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/integration/test_standard_mineru_batch_flow.py \
  backend/tests/unit/test_pdf_renderer.py \
  backend/tests/unit/test_document_assets.py \
  backend/tests/unit/test_structural_nodes.py \
  backend/tests/unit/test_ast_builder.py \
  backend/tests/unit/test_validation.py \
  backend/tests/unit/test_repair_tasks.py \
  backend/tests/unit/test_repair_service.py \
  backend/tests/unit/test_standard_tree_builder.py
git rm backend/tender_backend/services/vision_service/vision_processor.py \
  backend/tender_backend/services/vision_service/vision_prompt.py \
  backend/tender_backend/services/vision_service/page_merger.py \
  backend/tests/unit/test_page_merger.py
git commit -m "refactor: retire whole-page qwen vl pipeline"
```

## Verification Checklist

- `MinerU` parse assets remain queryable from `/api/standards/{id}/parse-assets`
- Standard processing still retries through `/api/standards/{id}/process`
- `process-vision` is removed
- AST nodes preserve `page_start/page_end`, `source_type`, `source_label`, and `source_ref`
- Grammar validation catches numbering jumps, page anchor regressions, and table attachment gaps
- Phrase detection tags mandatory clauses
- Local VL repair runs only for table and numeric/symbol tasks
- Final persistence writes validated AST output into `standard_clause`

## Notes For The Implementer

- Do not expand repair scope beyond `table_repair` and `symbol_numeric_repair` in this plan.
- Do not keep both the old whole-page vision route and the new local repair flow alive at the same time.
- Keep `pdf_renderer.py` if it cleanly serves repair rendering needs; avoid replacing it unless tests prove it is a blocker.
- Favor additive refactors in early chunks and push destructive deletion into Chunk 4 only after the replacement path is passing.
