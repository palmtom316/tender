# MinerU New Output Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut the project over to a single canonical MinerU integration that treats modern structured outputs such as `pdf_info -> para_blocks` as the source of truth and removes legacy result-shape compatibility work.

**Architecture:** Replace the current mixed MinerU parsing logic with one canonical normalization layer and one canonical persisted parse-asset shape. Because the system is not yet in use, do not preserve old payload contracts or old client contracts; instead, rewrite the standards path, tender path, and parse-assets API to the new shape and migrate test fixtures accordingly.

**Tech Stack:** Python 3.12, FastAPI, psycopg/PostgreSQL JSONB, Alembic, pytest, httpx, MinerU hosted API, existing standard/tender ingestion workflows.

---

## File Map

**Create:**

- `backend/tender_backend/services/parse_service/mineru_normalizer.py`
  - Single canonical normalizer for modern MinerU payloads and zip assets.
- `backend/tests/unit/test_mineru_normalizer.py`
  - Unit coverage for `pdf_info/para_blocks`, page extraction, and table extraction.
- `backend/tender_backend/db/alembic/versions/0014_mineru_canonical_assets.py`
  - Schema update for the canonical parse asset model.

**Modify:**

- `backend/tender_backend/services/norm_service/norm_processor.py`
  - Replace ad hoc extraction with the canonical normalizer and canonical persisted payload.
- `backend/tender_backend/services/norm_service/document_assets.py`
  - Assume canonical normalized pages/tables/full markdown only.
- `backend/tender_backend/services/parse_service/parser.py`
  - Persist canonical parse assets into `document`.
- `backend/tender_backend/services/parse_service/mineru_client.py`
  - Replace legacy `/parse` assumptions with the current v4 batch flow and canonical parse result shape.
- `backend/tender_backend/workflows/tender_ingestion.py`
  - Accept canonical parse results and persist them directly.
- `backend/tender_backend/api/standards.py`
  - Return only the new canonical parse asset contract from `/parse-assets`.
- `backend/tender_backend/db/repositories/standard_repo.py`
  - Read the canonical parse asset shape only.
- `backend/tender_backend/core/config.py`
  - Add the MinerU option surface used by the new transport.
- `backend/tests/integration/test_standard_mineru_batch_flow.py`
  - Update standards-path regressions to the new canonical payload.
- `backend/tests/unit/test_document_assets.py`
  - Remove old-shape assumptions and lock canonical page/table behavior.
- `backend/tests/unit/test_vision_settings.py`
  - Cover the expanded MinerU options.
- `backend/tests/integration/test_standard_viewer_query_api.py`
  - Update parse-assets API expectations.
- `backend/tests/unit/test_mineru_client.py`
  - Lock the new tender MinerU client behavior.

**Reference:**

- `docs/reports/2026-04-18-mineru-compatibility-gap-checklist.md`
- `docs/superpowers/plans/2026-04-05-mineru-doc-alignment.md`

---

### Task 1: Define the Canonical MinerU Parse Asset Shape

**Files:**
- Create: `backend/tender_backend/services/parse_service/mineru_normalizer.py`
- Create: `backend/tests/unit/test_mineru_normalizer.py`

- [ ] **Step 1: Write the failing unit tests for the canonical shape**

Create `backend/tests/unit/test_mineru_normalizer.py` with these tests:

```python
from tender_backend.services.parse_service.mineru_normalizer import normalize_mineru_payload


def test_normalize_mineru_payload_converts_pdf_info_para_blocks_to_canonical_pages() -> None:
    payload = {
        "pdf_info": [
            {
                "page_idx": 0,
                "para_blocks": [
                    {"type": "title", "lines": [{"spans": [{"content": "1 总则"}]}]},
                    {"type": "text", "lines": [{"spans": [{"content": "正文内容"}]}]},
                ],
            }
        ],
        "_version_name": "2.7.6",
    }

    normalized = normalize_mineru_payload(payload)

    assert normalized == {
        "parser_version": "2.7.6",
        "pages": [{"page_number": 1, "markdown": "1 总则\n正文内容"}],
        "tables": [],
        "full_markdown": "1 总则\n正文内容",
    }


def test_normalize_mineru_payload_collects_table_blocks_into_canonical_tables() -> None:
    payload = {
        "pdf_info": [
            {
                "page_idx": 1,
                "para_blocks": [
                    {
                        "type": "table",
                        "table_caption": "表1 参数",
                        "table_body": "<table><tr><td>A</td></tr></table>",
                    }
                ],
            }
        ]
    }

    normalized = normalize_mineru_payload(payload)

    assert normalized["tables"] == [
        {
            "page_start": 2,
            "page_end": 2,
            "table_title": "表1 参数",
            "table_html": "<table><tr><td>A</td></tr></table>",
            "raw_json": {
                "type": "table",
                "table_caption": "表1 参数",
                "table_body": "<table><tr><td>A</td></tr></table>",
            },
        }
    ]
```

- [ ] **Step 2: Run the unit test file to verify it fails**

Run: `PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/unit/test_mineru_normalizer.py -q`

Expected: FAIL because the normalizer module does not exist.

- [ ] **Step 3: Write the minimal normalizer**

Create `backend/tender_backend/services/parse_service/mineru_normalizer.py`:

```python
from __future__ import annotations

from typing import Any


def normalize_mineru_payload(payload: dict[str, Any]) -> dict[str, Any]:
    pages = _extract_pages_from_pdf_info(payload.get("pdf_info"))
    tables = _extract_tables_from_pdf_info(payload.get("pdf_info"))
    full_markdown = payload.get("full_markdown") if isinstance(payload.get("full_markdown"), str) else "\n\n".join(
        page["markdown"] for page in pages if page.get("markdown")
    )
    return {
        "parser_version": payload.get("_version_name"),
        "pages": pages,
        "tables": tables,
        "full_markdown": full_markdown,
    }
```

```python
def _extract_pages_from_pdf_info(pdf_info: object) -> list[dict[str, Any]]:
    if not isinstance(pdf_info, list):
        return []
    pages: list[dict[str, Any]] = []
    for page in pdf_info:
        if not isinstance(page, dict):
            continue
        page_idx = page.get("page_idx")
        if not isinstance(page_idx, int):
            continue
        para_blocks = page.get("para_blocks")
        if not isinstance(para_blocks, list):
            continue
        fragments: list[str] = []
        for block in para_blocks:
            fragments.extend(_collect_block_text(block))
        markdown = "\n".join(fragment for fragment in fragments if fragment)
        if markdown:
            pages.append({"page_number": page_idx + 1, "markdown": markdown})
    return pages
```

- [ ] **Step 4: Run the new unit tests to verify they pass**

Run: `PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/unit/test_mineru_normalizer.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/services/parse_service/mineru_normalizer.py \
  backend/tests/unit/test_mineru_normalizer.py
git commit -m "feat: add canonical MinerU normalizer"
```

### Task 2: Replace the Standards Pipeline With the Canonical Payload

**Files:**
- Modify: `backend/tender_backend/services/norm_service/norm_processor.py`
- Modify: `backend/tender_backend/services/parse_service/parser.py`
- Modify: `backend/tests/integration/test_standard_mineru_batch_flow.py`

- [ ] **Step 1: Write the failing standards regression for canonical payload persistence**

Add to `backend/tests/integration/test_standard_mineru_batch_flow.py`:

```python
def test_parse_via_mineru_persists_canonical_payload_from_pdf_info(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "spec.pdf"
    pdf_path.write_bytes(b"%PDF-1.7 fake pdf")

    captured: dict[str, object] = {}

    def fake_update_document_parse_assets(conn, **kwargs):
        captured.update(kwargs)

    # wire fake batch upload + result zip returning middle.json with pdf_info
    ...

    norm_processor._parse_via_mineru(object(), "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    assert captured["raw_payload"] == {
        "parser_version": "2.7.6",
        "pages": [{"page_number": 1, "markdown": "1 总则\n正文内容"}],
        "tables": [],
        "full_markdown": "1 总则\n正文内容",
    }
```

- [ ] **Step 2: Run the targeted regression to verify it fails**

Run: `PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/integration/test_standard_mineru_batch_flow.py -q -k "canonical_payload_from_pdf_info"`

Expected: FAIL because `_parse_via_mineru()` still persists the old mixed payload.

- [ ] **Step 3: Replace ad hoc extraction with the normalizer**

Modify `backend/tender_backend/services/norm_service/norm_processor.py`:

```python
from tender_backend.services.parse_service.mineru_normalizer import normalize_mineru_payload
```

Inside `_parse_via_mineru()`:

```python
normalized_payload = normalize_mineru_payload(
    {
        **(extracted_primary_json or {}),
        "full_markdown": raw_content,
    }
)

pages = normalized_payload["pages"]
tables = normalized_payload["tables"]
sections = _mineru_to_sections(normalized_payload["full_markdown"], pages)

update_document_parse_assets(
    conn,
    document_id=UUID(document_id),
    parser_name="mineru",
    parser_version=normalized_payload.get("parser_version"),
    raw_payload=normalized_payload,
)
```

Do not keep provider-shape fallback branches inside `_parse_via_mineru()`.

- [ ] **Step 4: Run the focused standards tests**

Run: `PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/integration/test_standard_mineru_batch_flow.py backend/tests/unit/test_mineru_normalizer.py -q -k "canonical or batch_upload_flow"`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/services/norm_service/norm_processor.py \
  backend/tender_backend/services/parse_service/parser.py \
  backend/tests/integration/test_standard_mineru_batch_flow.py
git commit -m "feat: cut standards pipeline to canonical MinerU payload"
```

### Task 3: Simplify Document Asset Reading to Canonical Pages Only

**Files:**
- Modify: `backend/tender_backend/services/norm_service/document_assets.py`
- Modify: `backend/tests/unit/test_document_assets.py`

- [ ] **Step 1: Write failing document-asset tests that remove legacy assumptions**

Update `backend/tests/unit/test_document_assets.py` with:

```python
def test_build_document_asset_reads_canonical_pages_from_raw_payload() -> None:
    document_id = uuid4()
    document = {
        "id": document_id,
        "raw_payload": {
            "pages": [{"page_number": 1, "markdown": "1 总则\n正文内容"}],
            "tables": [],
            "full_markdown": "1 总则\n正文内容",
        },
    }

    asset = build_document_asset(document_id=document_id, document=document, sections=[], tables=[])

    assert asset.pages[0].page_number == 1
    assert asset.pages[0].normalized_text == "1 总则\n正文内容"
```

```python
def test_build_document_asset_ignores_noncanonical_page_entries() -> None:
    document_id = uuid4()
    document = {
        "id": document_id,
        "raw_payload": {
            "pages": [{"type": "title", "content": "旧 shape"}],
            "tables": [],
            "full_markdown": "",
        },
    }

    asset = build_document_asset(document_id=document_id, document=document, sections=[], tables=[])

    assert asset.pages == []
```

- [ ] **Step 2: Run the document-asset tests to verify they fail**

Run: `PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/unit/test_document_assets.py -q`

Expected: FAIL because the current code still treats any `raw_payload.pages` list as usable input.

- [ ] **Step 3: Remove the old mixed-shape reconciliation logic**

Modify `backend/tender_backend/services/norm_service/document_assets.py`:

```python
def _pages_from_raw_payload(raw_payload: dict[str, Any]) -> list[PageAsset]:
    raw_pages = raw_payload.get("pages")
    if not isinstance(raw_pages, list):
        return []
    pages: list[PageAsset] = []
    for index, item in enumerate(raw_pages):
        if not isinstance(item, dict):
            continue
        page_number = item.get("page_number")
        markdown = item.get("markdown")
        if not isinstance(page_number, int) or not isinstance(markdown, str) or not markdown.strip():
            continue
        pages.append(
            PageAsset(
                page_number=page_number,
                normalized_text=markdown,
                raw_page=item,
                source_ref=f"document.raw_payload.pages[{index}]",
            )
        )
    return pages
```

In `build_document_asset()`, keep section fallback only for missing canonical pages. Remove the branch that treats old provider blocks as reconcilable raw page inputs.

- [ ] **Step 4: Run the unit tests to verify they pass**

Run: `PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/unit/test_document_assets.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/services/norm_service/document_assets.py \
  backend/tests/unit/test_document_assets.py
git commit -m "refactor: require canonical MinerU page assets"
```

### Task 4: Cut the Tender Ingestion Path to the New MinerU Client Contract

**Files:**
- Modify: `backend/tender_backend/services/parse_service/mineru_client.py`
- Modify: `backend/tender_backend/workflows/tender_ingestion.py`
- Create: `backend/tests/unit/test_mineru_client.py`

- [ ] **Step 1: Write the failing tender-client tests for the v4 batch flow**

Create `backend/tests/unit/test_mineru_client.py`:

```python
from tender_backend.services.parse_service.mineru_client import MineruClient


async def test_request_upload_url_uses_file_urls_batch(httpx_mock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://mineru.net/api/v4/file-urls/batch",
        json={"data": {"batch_id": "batch-123", "file_urls": ["https://upload.example.com/file-1"]}},
    )

    client = MineruClient(base_url="https://mineru.net/api/v4/extract/task", api_key="token")
    upload = await client.request_upload_url("spec.pdf", data_id="doc-1")

    assert upload.batch_id == "batch-123"
    assert upload.upload_url == "https://upload.example.com/file-1"
```

```python
async def test_get_parse_status_returns_canonical_pages(httpx_mock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://mineru.net/api/v4/extract-results/batch/batch-123",
        json={"data": {"extract_result": [{"state": "done", "full_zip_url": "https://download.example.com/result.zip"}]}},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://download.example.com/result.zip",
        content=_zip_bytes("1 总则\n正文内容", {"middle.json": '{"pdf_info":[{"page_idx":0,"para_blocks":[{"type":"text","lines":[{"spans":[{"content":"正文内容"}]}]}]}]}'})
    )

    client = MineruClient(base_url="https://mineru.net/api/v4/extract/task", api_key="token")
    result = await client.get_parse_status("batch-123")

    assert result.pages == [{"page_number": 1, "markdown": "正文内容"}]
```

- [ ] **Step 2: Run the client tests to verify they fail**

Run: `PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/unit/test_mineru_client.py -q`

Expected: FAIL because the client still assumes `/parse` and `/parse/{job_id}`.

- [ ] **Step 3: Rewrite the client to the current batch contract**

Modify `backend/tender_backend/services/parse_service/mineru_client.py` so it:

- normalizes `base_url` to the v4 root
- posts to `/file-urls/batch`
- uploads to the returned signed URL
- polls `/extract-results/batch/{batch_id}`
- downloads `full_zip_url`
- normalizes the zip payload with `normalize_mineru_payload()`

Use dataclasses like:

```python
@dataclass(frozen=True)
class MineruUploadInfo:
    batch_id: str
    upload_url: str
    data_id: str
```

```python
@dataclass(frozen=True)
class MineruParseResult:
    job_id: str
    status: str
    pages: list[dict[str, Any]]
    tables: list[dict[str, Any]]
    sections: list[dict[str, Any]]
    raw_payload: dict[str, Any]
```

- [ ] **Step 4: Update the tender workflow to consume the canonical result**

Modify `backend/tender_backend/workflows/tender_ingestion.py`:

```python
ctx.data["parsed_sections"] = result.sections
ctx.data["parsed_tables"] = result.tables
ctx.data["parsed_pages"] = result.pages
ctx.data["parsed_raw_payload"] = result.raw_payload
```

Before persisting sections/tables, call:

```python
update_document_parse_assets(
    conn,
    document_id=document_id,
    parser_name="mineru",
    parser_version=result.raw_payload.get("parser_version"),
    raw_payload=result.raw_payload,
)
```

- [ ] **Step 5: Run the client tests and a focused workflow regression**

Run: `PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/unit/test_mineru_client.py backend/tests/integration/test_standard_mineru_batch_flow.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/tender_backend/services/parse_service/mineru_client.py \
  backend/tender_backend/workflows/tender_ingestion.py \
  backend/tests/unit/test_mineru_client.py
git commit -m "feat: cut tender ingestion to modern MinerU contract"
```

### Task 5: Update Schema, Config, and API to the New Canonical Contract

**Files:**
- Create: `backend/tender_backend/db/alembic/versions/0014_mineru_canonical_assets.py`
- Modify: `backend/tender_backend/core/config.py`
- Modify: `backend/tender_backend/api/standards.py`
- Modify: `backend/tender_backend/db/repositories/standard_repo.py`
- Modify: `backend/tests/unit/test_vision_settings.py`
- Modify: `backend/tests/integration/test_standard_viewer_query_api.py`

- [ ] **Step 1: Write failing config and API tests**

Update `backend/tests/unit/test_vision_settings.py`:

```python
def test_mineru_defaults_cover_current_provider_options() -> None:
    settings = Settings()

    assert settings.standard_mineru_model_version == "vlm"
    assert settings.standard_mineru_language == "ch"
    assert settings.standard_mineru_enable_table is True
    assert settings.standard_mineru_enable_formula is False
    assert settings.standard_mineru_is_ocr is True
```

Update `backend/tests/integration/test_standard_viewer_query_api.py`:

```python
assert payload["document"]["raw_payload"]["pages"] == [
    {"page_number": 1, "markdown": "1 总则\n正文内容"}
]
assert payload["document"]["raw_payload"]["tables"] == []
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `PYTHONPATH=backend ./.venv/bin/python -m pytest backend/tests/unit/test_vision_settings.py backend/tests/integration/test_standard_viewer_query_api.py -q`

Expected: FAIL because config and fixture expectations still reflect the old mixed contract.

- [ ] **Step 3: Add the config surface and schema migration**

Modify `backend/tender_backend/core/config.py`:

```python
class Settings(BaseSettings):
    ...
    standard_mineru_model_version: str = "vlm"
    standard_mineru_language: str = "ch"
    standard_mineru_enable_table: bool = True
    standard_mineru_enable_formula: bool = False
    standard_mineru_is_ocr: bool = True
    standard_mineru_page_ranges: str | None = None
```

Create `backend/tender_backend/db/alembic/versions/0014_mineru_canonical_assets.py`:

```python
from alembic import op


revision = "0014_mineru_canonical_assets"
down_revision = "0013_standard_parse_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE document
        SET raw_payload = jsonb_build_object(
            'parser_version', parser_version,
            'pages', COALESCE(raw_payload->'pages', '[]'::jsonb),
            'tables', COALESCE(raw_payload->'tables', '[]'::jsonb),
            'full_markdown', COALESCE(raw_payload->>'full_markdown', '')
        )
        WHERE raw_payload IS NOT NULL;
        """
    )


def downgrade() -> None:
    pass
```

- [ ] **Step 4: Update repository/API code to expose only the canonical parse asset**

Modify `backend/tender_backend/db/repositories/standard_repo.py` and `backend/tender_backend/api/standards.py` so all parse-asset reads and serialized responses assume:

```python
{
    "id": str(document["id"]),
    "parser_name": document.get("parser_name"),
    "parser_version": document.get("parser_version"),
    "raw_payload": document.get("raw_payload"),
}
```

where `raw_payload.pages` always contains canonical page objects, not provider blocks.

- [ ] **Step 5: Run the end-to-end verification set**

Run:

```bash
PYTHONPATH=backend ./.venv/bin/python -m pytest \
  backend/tests/unit/test_mineru_normalizer.py \
  backend/tests/unit/test_document_assets.py \
  backend/tests/unit/test_mineru_client.py \
  backend/tests/unit/test_vision_settings.py \
  backend/tests/integration/test_standard_mineru_batch_flow.py \
  backend/tests/integration/test_standard_viewer_query_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/tender_backend/db/alembic/versions/0014_mineru_canonical_assets.py \
  backend/tender_backend/core/config.py \
  backend/tender_backend/api/standards.py \
  backend/tender_backend/db/repositories/standard_repo.py \
  backend/tests/unit/test_vision_settings.py \
  backend/tests/integration/test_standard_viewer_query_api.py
git commit -m "feat: cut parse assets to canonical MinerU contract"
```

## Self-Review

- Spec coverage:
  - canonical modern MinerU normalization: covered in Task 1
  - standards pipeline cutover: covered in Task 2
  - document asset cleanup: covered in Task 3
  - tender pipeline cutover: covered in Task 4
  - schema/config/API closure: covered in Task 5
- Placeholder scan:
  - no `TODO` / `TBD`
  - every task names exact files, commands, and expected outcomes
- Type consistency:
  - canonical persisted contract is consistently `parser_version`, `pages`, `tables`, `full_markdown`

Plan complete and saved to `docs/superpowers/plans/2026-04-18-mineru-new-output-compatibility-plan.md`.
