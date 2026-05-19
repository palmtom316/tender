# Enterprise Prompt Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add enterprise-grade bid-generation prompt contracts and enforce tender-document layout/font requirements as the highest-priority formatting source.

**Architecture:** Do not install the industrial prompt as one global prompt. Split it into small prompt contracts used by business prose, technical prose, and chart-spec generation; normalize extracted tender format requirements into a shared format profile; apply that profile during DOCX rendering; record format-check evidence so export gates can show whether tender formatting was followed.

**Tech Stack:** Python, FastAPI service modules, python-docx, pytest, existing AI gateway message payloads, existing `project_requirement` extraction data.

---

## Non-Negotiable Rules

- Tender-file formatting and font requirements override all default templates, visual tokens, and prompt preferences.
- If the tender file specifies font family, font size, margins, line spacing, page size, headers/footers, table style, numbering, binding, file format, or signature/seal placement, the generated bid must follow the tender file first.
- If extracted tender formatting requirements conflict with each other, the system must mark the conflict for review instead of guessing.
- If no formatting requirement is extracted, the system uses the default enterprise print template and records `format_source=default_enterprise_template`.
- Compliance and evidence rules outrank visual polish. No prompt may ask the model to invent qualifications, people, equipment, certificates, dates, awards, financials, prices, or commitments.
- Blind-bid mode must continue to suppress sensitive company, person, project, phone, ID, certificate-number, and address fields.
- Prose prompts must produce bid content, not architecture designs, folder structures, sample code, or implementation advice.

## File Map

- Create `backend/tender_backend/services/prompt_contracts.py`
  - Owns reusable prompt-contract strings and `compose_prompt_contract(...)`.
  - Keeps bid-generation prompts separate from system-architecture prompt material.
- Modify `backend/tender_backend/services/business_text_generators.py`
  - Use business prompt contract instead of inline one-sentence system prompt.
  - Pass `tender_format_requirements` through sanitized context.
- Modify `backend/tender_backend/services/technical_bid_writer.py`
  - Use technical prompt contract in `_ai_gateway_messages(...)`.
  - Add `tender_format_requirements` and `tender_requirement_priority` to allowed context keys.
- Modify `backend/tender_backend/services/chart_generation_service.py`
  - Add chart-spec contract language: semantic spec only, print-first, grayscale-safe, no default Mermaid/SVG fragments, no invented dates.
- Modify `backend/tender_backend/services/chart_service/visual_template.py`
  - Align default chart visual tokens with State Grid / enterprise print palette.
- Modify `backend/tender_backend/services/tender_requirement_priority.py`
  - Normalize tender format requirements into a `TenderFormatProfile`.
  - Preserve traceability to extracted requirement rows.
- Modify `backend/tender_backend/services/export_service/docx_exporter.py`
  - Apply `TenderFormatProfile` to DOCX Normal style, section margins, page size, headers/footers, and generated requirement appendix.
- Modify `backend/tender_backend/services/export_service/format_checker.py`
  - Check exported DOCX against tender format profile when provided.
  - Emit structured evidence for prompt/export gates.
- Modify `backend/tender_backend/services/export_gate_service.py`
  - Surface tender-format compliance evidence more explicitly.
- Add or modify tests:
  - `backend/tests/unit/test_prompt_contracts.py`
  - `backend/tests/unit/test_business_text_generators.py`
  - `backend/tests/unit/test_technical_bid_writer.py`
  - `backend/tests/unit/test_chart_generation_service.py`
  - `backend/tests/unit/test_chart_visual_template.py`
  - `backend/tests/unit/test_tender_requirement_priority.py`
  - `backend/tests/unit/test_docx_exporter.py`
  - `backend/tests/unit/test_format_checker.py`

## Task 1: Prompt Contract Module

**Files:**
- Create: `backend/tender_backend/services/prompt_contracts.py`
- Test: `backend/tests/unit/test_prompt_contracts.py`

- [ ] **Step 1: Write failing tests**

Add `backend/tests/unit/test_prompt_contracts.py`:

```python
from tender_backend.services.prompt_contracts import (
    BUSINESS_BID_CONTRACT,
    CHART_SPEC_CONTRACT,
    FORMAT_REQUIREMENT_PRIORITY_CONTRACT,
    TECHNICAL_BID_CONTRACT,
    compose_prompt_contract,
)


def test_format_priority_contract_makes_tender_file_format_authoritative() -> None:
    assert "招标文件" in FORMAT_REQUIREMENT_PRIORITY_CONTRACT
    assert "字体" in FORMAT_REQUIREMENT_PRIORITY_CONTRACT
    assert "排版" in FORMAT_REQUIREMENT_PRIORITY_CONTRACT
    assert "优先" in FORMAT_REQUIREMENT_PRIORITY_CONTRACT
    assert "不得猜测" in FORMAT_REQUIREMENT_PRIORITY_CONTRACT


def test_bid_contracts_forbid_fabrication_and_code_generation() -> None:
    combined = BUSINESS_BID_CONTRACT + TECHNICAL_BID_CONTRACT
    assert "不得编造" in combined
    assert "证据" in combined
    assert "不得输出架构设计" in combined
    assert "不得输出示例代码" in combined


def test_chart_contract_is_semantic_and_print_first() -> None:
    assert "只生成结构化 spec" in CHART_SPEC_CONTRACT
    assert "不得输出 SVG" in CHART_SPEC_CONTRACT
    assert "灰度打印" in CHART_SPEC_CONTRACT
    assert "不得依赖颜色" in CHART_SPEC_CONTRACT


def test_compose_prompt_contract_deduplicates_blank_parts() -> None:
    assert compose_prompt_contract("A", "", "B", "A") == "A\n\nB"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend && pytest tests/unit/test_prompt_contracts.py -q
```

Expected: FAIL because `tender_backend.services.prompt_contracts` does not exist.

- [ ] **Step 3: Implement prompt contracts**

Create `backend/tender_backend/services/prompt_contracts.py`:

```python
"""Reusable prompt contracts for bid-generation AI calls."""

from __future__ import annotations


FORMAT_REQUIREMENT_PRIORITY_CONTRACT = """
招标文件关于排版、字体和提交格式的要求是最高优先级格式来源。
如招标文件规定字体、字号、行距、页边距、纸张、页眉页脚、页码、目录、编号、表格样式、签章、装订、DOCX/PDF 格式或其他排版要求，必须服从招标文件。
如招标格式要求与默认模板、企业风格、图表视觉 token 或章节提示词冲突，以招标文件为准。
如格式要求来源不足或互相冲突，必须输出可复核的缺失/冲突问题，不得猜测。
""".strip()


COMPLIANCE_CONTRACT = """
只使用输入事实、已确认招标要求、标准条文、企业资料和证据引用。
不得编造日期、数量、金额、人员姓名、证书编号、设备型号、业绩、奖项、财务数据或承诺。
暗标模式下不得输出公司、人员、项目、电话、身份证号、证书编号、地址等敏感身份信息。
视觉表达和文字润色不得覆盖合规、证据、暗标和招标文件要求。
""".strip()


DOCUMENT_OUTPUT_CONTRACT = """
输出必须是正式、克制、工程化、适合评标专家阅读的中文投标文件正文。
不得输出架构设计、文件夹结构、数据流说明、AST schema、渲染管线、主题 token 说明、示例代码或实现建议。
不得使用营销化、互联网产品化、夸张宣传式表达。
""".strip()


BUSINESS_BID_CONTRACT = """
你是投标商务标正文生成器。
商务标内容必须围绕招标文件要求、商务响应、企业资质、业绩、财务、偏差和承诺边界组织。
只输出可放入商务标的 Markdown 正文。
""".strip()


TECHNICAL_BID_CONTRACT = """
你是投标文件技术标章节编写助手。
技术标内容必须围绕施工组织、技术措施、质量安全、进度、风险、运维、响应矩阵和图表占位符组织。
价格、报价、单价、总价等内容不得进入技术标，除非输入上下文明确要求该章节属于商务/报价卷。
输出 Markdown 正文，保留章节编号；需要图表的位置使用 {{chart:key}} 占位符。
""".strip()


CHART_SPEC_CONTRACT = """
你是投标文件图表规划助手，只生成结构化 spec，不生成代码。
只输出合法 JSON object，不要 Markdown。
不得输出 SVG、Mermaid 源码、坐标、颜色、尺寸或样式片段。
图表必须服务于 A4/A3 打印、灰度打印、复印和扫描后的可读性，不得依赖颜色表达唯一含义。
缺少来源的日期、工期、人员、设备、风险等级和量化指标不得生成。
""".strip()


def compose_prompt_contract(*parts: str) -> str:
    """Join prompt-contract parts while preserving first occurrence order."""

    seen: set[str] = set()
    output: list[str] = []
    for part in parts:
        text = str(part or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return "\n\n".join(output)
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
cd backend && pytest tests/unit/test_prompt_contracts.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/services/prompt_contracts.py backend/tests/unit/test_prompt_contracts.py
git commit -m "feat: add enterprise bid prompt contracts"
```

## Task 2: Business and Technical Prompt Integration

**Files:**
- Modify: `backend/tender_backend/services/business_text_generators.py`
- Modify: `backend/tender_backend/services/technical_bid_writer.py`
- Test: `backend/tests/unit/test_business_text_generators.py`
- Test: `backend/tests/unit/test_technical_bid_writer.py`

- [ ] **Step 1: Write failing business prompt test**

Append to `backend/tests/unit/test_business_text_generators.py`:

```python
def test_business_prompt_includes_tender_format_priority_contract() -> None:
    calls: list[dict[str, Any]] = []

    def fake_gateway(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(payload)
        return {"content": "## 绿色发展\n\n按招标文件格式要求响应。"}

    generate_business_text(
        "11",
        {
            "green_plans": [{"title": "绿色施工制度", "evidence_asset_id": "asset-green-1"}],
            "tender_format_requirements": [
                {"category": "format", "requirement_text": "正文采用宋体小四，1.5倍行距。"}
            ],
        },
        completion_fn=fake_gateway,
    )

    prompt_blob = str(calls[0]["messages"])
    assert "招标文件关于排版、字体" in prompt_blob
    assert "正文采用宋体小四" in prompt_blob
    assert "不得输出架构设计" in prompt_blob
```

- [ ] **Step 2: Write failing technical prompt test**

Append to `backend/tests/unit/test_technical_bid_writer.py`:

```python
def test_technical_prompt_contract_allows_tender_format_requirements() -> None:
    messages = technical_bid_writer_module._ai_gateway_messages(
        {
            "chapter": {"chapter_code": "8", "chapter_title": "施工方案与技术措施"},
            "constraints": [],
            "standard_clauses": [],
            "strategy": {"key": "construction_plan"},
            "tender_format_requirements": [
                {"category": "format", "requirement_text": "技术标正文仿宋小四。"}
            ],
            "tender_requirement_priority": {
                "policy": "tender_extracted_requirements_override_template",
                "format_requirement_count": 1,
            },
        }
    )

    prompt_blob = str(messages)
    assert "招标文件关于排版、字体" in prompt_blob
    assert "技术标正文仿宋小四" in prompt_blob
    assert "tender_format_requirements" in prompt_blob
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
cd backend && pytest tests/unit/test_business_text_generators.py::test_business_prompt_includes_tender_format_priority_contract tests/unit/test_technical_bid_writer.py::test_technical_prompt_contract_allows_tender_format_requirements -q
```

Expected: FAIL because current prompts do not include the shared contracts and technical allowed context omits tender format keys.

- [ ] **Step 4: Integrate contracts in business generator**

Modify imports in `backend/tender_backend/services/business_text_generators.py`:

```python
from tender_backend.services.prompt_contracts import (
    BUSINESS_BID_CONTRACT,
    COMPLIANCE_CONTRACT,
    DOCUMENT_OUTPUT_CONTRACT,
    FORMAT_REQUIREMENT_PRIORITY_CONTRACT,
    compose_prompt_contract,
)
```

Replace the `_messages(...)` system message content with:

```python
compose_prompt_contract(
    BUSINESS_BID_CONTRACT,
    FORMAT_REQUIREMENT_PRIORITY_CONTRACT,
    COMPLIANCE_CONTRACT,
    DOCUMENT_OUTPUT_CONTRACT,
)
```

- [ ] **Step 5: Integrate contracts in technical writer**

Modify imports in `backend/tender_backend/services/technical_bid_writer.py`:

```python
from tender_backend.services.prompt_contracts import (
    COMPLIANCE_CONTRACT,
    DOCUMENT_OUTPUT_CONTRACT,
    FORMAT_REQUIREMENT_PRIORITY_CONTRACT,
    TECHNICAL_BID_CONTRACT,
    compose_prompt_contract,
)
```

Replace `_ai_gateway_messages(...)` system message content with:

```python
compose_prompt_contract(
    TECHNICAL_BID_CONTRACT,
    FORMAT_REQUIREMENT_PRIORITY_CONTRACT,
    COMPLIANCE_CONTRACT,
    DOCUMENT_OUTPUT_CONTRACT,
)
```

Add these keys to `_technical_prompt_contract(...)[ "allowed_context_keys" ]`:

```python
"tender_requirements",
"tender_content_requirements",
"tender_format_requirements",
"tender_requirement_priority",
```

- [ ] **Step 6: Run prompt integration tests**

Run:

```bash
cd backend && pytest tests/unit/test_business_text_generators.py::test_business_prompt_includes_tender_format_priority_contract tests/unit/test_technical_bid_writer.py::test_technical_prompt_contract_allows_tender_format_requirements -q
```

Expected: PASS.

- [ ] **Step 7: Run affected unit suites**

Run:

```bash
cd backend && pytest tests/unit/test_business_text_generators.py tests/unit/test_technical_bid_writer.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/tender_backend/services/business_text_generators.py backend/tender_backend/services/technical_bid_writer.py backend/tests/unit/test_business_text_generators.py backend/tests/unit/test_technical_bid_writer.py
git commit -m "feat: apply bid prompt contracts to prose generation"
```

## Task 3: Chart Prompt and Visual Token Alignment

**Files:**
- Modify: `backend/tender_backend/services/chart_generation_service.py`
- Modify: `backend/tender_backend/services/chart_service/visual_template.py`
- Test: `backend/tests/unit/test_chart_generation_service.py`
- Test: `backend/tests/unit/test_chart_visual_template.py`

- [ ] **Step 1: Write failing chart prompt test**

Append to `backend/tests/unit/test_chart_generation_service.py`:

```python
def test_chart_spec_prompt_uses_enterprise_print_contract() -> None:
    prompt = chart_generation_service._chart_spec_system_prompt("construction_flow")

    assert "只生成结构化 spec" in prompt
    assert "不得输出 SVG" in prompt
    assert "灰度打印" in prompt
    assert "不得依赖颜色" in prompt
```

- [ ] **Step 2: Write failing visual token test**

Append to `backend/tests/unit/test_chart_visual_template.py`:

```python
def test_chart_visual_template_uses_state_grid_print_palette() -> None:
    from tender_backend.services.chart_service.visual_template import FONT, PALETTE

    assert PALETTE.primary == "#0B3A82"
    assert PALETTE.primary_dark == "#062B61"
    assert PALETTE.surface_alt == "#EAF2FD"
    assert PALETTE.text == "#1A1A1A"
    assert PALETTE.border == "#4A4A4A"
    assert FONT.min_px >= 11
    assert "Microsoft YaHei" in FONT.family
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
cd backend && pytest tests/unit/test_chart_generation_service.py::test_chart_spec_prompt_uses_enterprise_print_contract tests/unit/test_chart_visual_template.py::test_chart_visual_template_uses_state_grid_print_palette -q
```

Expected: FAIL because chart prompt and visual tokens are not yet aligned.

- [ ] **Step 4: Add chart contract to chart prompt**

Modify `backend/tender_backend/services/chart_generation_service.py` imports:

```python
from tender_backend.services.prompt_contracts import CHART_SPEC_CONTRACT, compose_prompt_contract
```

In `_chart_spec_system_prompt(...)`, wrap the existing prompt body:

```python
return compose_prompt_contract(
    CHART_SPEC_CONTRACT,
    (
        "你是投标文件图表规划助手。只输出 JSON，不要 Markdown。"
        "输出必须是合法 json object，并符合 tender chart spec。"
        "AI 只生成结构化 spec，不生成代码。"
        "Never output coordinates, colors, dimensions, or SVG fragments. Only output semantic chart structure. "
        "不得编造日期、天数、人员姓名、证书编号、设备型号、风险等级、量化指标或许可结果。"
        "schedule_gantt/critical_path/outage_timeline 的每个任务日期必须来自 context 中已确认的工期、里程碑或约束，"
        "并在任务 source_refs 中写入 constraint_id/source_chunk_id/user_confirmed_by 等来源；缺少来源时不要输出甘特图任务。"
        "risk_matrix 的 cells[].level 只能使用 low/medium/high/critical。"
        "示例 JSON："
        + json.dumps(example, ensure_ascii=False)
    ),
)
```

- [ ] **Step 5: Update visual tokens**

Modify `backend/tender_backend/services/chart_service/visual_template.py`:

```python
PALETTE = PaletteSpec(
    primary="#0B3A82",
    primary_dark="#062B61",
    surface="#FFFFFF",
    surface_alt="#EAF2FD",
    border="#4A4A4A",
    text="#1A1A1A",
    text_muted="#4A4A4A",
    risk_low="#E7F5E8",
    risk_medium="#FFF4CE",
    risk_high="#FFE0CC",
    risk_critical="#FFD6D6",
    risk_default="#FFFFFF",
)


FONT = FontSpec(
    family="HarmonyOS Sans SC, Source Han Sans SC, Microsoft YaHei, SimSun, sans-serif",
    title_px=20,
    subtitle_px=16,
    axis_label_px=13,
    cell_text_px=12,
    legend_px=11,
    min_px=11,
)
```

- [ ] **Step 6: Run chart tests**

Run:

```bash
cd backend && pytest tests/unit/test_chart_generation_service.py::test_chart_spec_prompt_uses_enterprise_print_contract tests/unit/test_chart_visual_template.py::test_chart_visual_template_uses_state_grid_print_palette tests/unit/test_chart_quality_gate.py tests/unit/test_chart_vega_mapper.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/tender_backend/services/chart_generation_service.py backend/tender_backend/services/chart_service/visual_template.py backend/tests/unit/test_chart_generation_service.py backend/tests/unit/test_chart_visual_template.py
git commit -m "feat: align chart contracts with enterprise print style"
```

## Task 4: Tender Format Profile Normalization

**Files:**
- Modify: `backend/tender_backend/services/tender_requirement_priority.py`
- Test: `backend/tests/unit/test_tender_requirement_priority.py`

- [ ] **Step 1: Write failing normalization tests**

Append to `backend/tests/unit/test_tender_requirement_priority.py`:

```python
from tender_backend.services.tender_requirement_priority import build_tender_format_profile


def test_build_tender_format_profile_extracts_common_chinese_format_rules() -> None:
    profile = build_tender_format_profile(
        [
            {"id": "fmt-1", "category": "format", "requirement_text": "正文采用宋体小四，1.5倍行距，A4纸。"},
            {"id": "fmt-2", "category": "format", "requirement_text": "页边距上下左右均为25mm。"},
        ]
    )

    assert profile["source"] == "tender_extracted_requirements"
    assert profile["font_name"] == "宋体"
    assert profile["font_size_pt"] == 12
    assert profile["line_spacing"] == 1.5
    assert profile["page_size"] == "A4"
    assert profile["margins_mm"] == {"top": 25.0, "bottom": 25.0, "left": 25.0, "right": 25.0}
    assert profile["source_requirement_ids"] == ["fmt-1", "fmt-2"]
    assert profile["conflicts"] == []


def test_build_tender_format_profile_marks_conflicting_font_rules() -> None:
    profile = build_tender_format_profile(
        [
            {"id": "fmt-1", "category": "format", "requirement_text": "正文采用宋体小四。"},
            {"id": "fmt-2", "category": "format", "requirement_text": "正文采用仿宋四号。"},
        ]
    )

    assert profile["font_name"] == "宋体"
    assert profile["conflicts"]
    assert profile["conflicts"][0]["field"] == "font_name"


def test_build_tender_format_profile_uses_default_when_no_requirements() -> None:
    profile = build_tender_format_profile([])

    assert profile["source"] == "default_enterprise_template"
    assert profile["font_name"] == "宋体"
    assert profile["font_size_pt"] == 10.5
    assert profile["page_size"] == "A4"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend && pytest tests/unit/test_tender_requirement_priority.py -q
```

Expected: FAIL because `build_tender_format_profile` does not exist.

- [ ] **Step 3: Implement format profile builder**

In `backend/tender_backend/services/tender_requirement_priority.py`, add:

```python
import re
```

Add constants and helper functions:

```python
_FONT_SIZE_PT = {
    "初号": 42.0,
    "小初": 36.0,
    "一号": 26.0,
    "小一": 24.0,
    "二号": 22.0,
    "小二": 18.0,
    "三号": 16.0,
    "小三": 15.0,
    "四号": 14.0,
    "小四": 12.0,
    "五号": 10.5,
    "小五": 9.0,
}
_KNOWN_FONTS = ("宋体", "仿宋", "黑体", "楷体", "微软雅黑", "方正仿宋", "方正小标宋")


def build_tender_format_profile(format_requirements: list[dict[str, Any]]) -> dict[str, Any]:
    profile: dict[str, Any] = {
        "source": "tender_extracted_requirements" if format_requirements else "default_enterprise_template",
        "font_name": "宋体",
        "font_size_pt": 10.5,
        "line_spacing": None,
        "page_size": "A4",
        "margins_mm": {"top": 25.4, "bottom": 25.4, "left": 25.4, "right": 25.4},
        "source_requirement_ids": [],
        "conflicts": [],
        "raw_requirements": format_requirements,
    }
    seen: dict[str, Any] = {}
    for requirement in format_requirements:
        text = str(requirement.get("requirement_text") or requirement.get("source_text") or requirement.get("title") or "")
        req_id = str(requirement.get("id") or requirement.get("requirement_id") or "")
        if req_id:
            profile["source_requirement_ids"].append(req_id)
        _set_profile_value(profile, seen, "font_name", _extract_font_name(text), req_id)
        _set_profile_value(profile, seen, "font_size_pt", _extract_font_size_pt(text), req_id)
        _set_profile_value(profile, seen, "line_spacing", _extract_line_spacing(text), req_id)
        _set_profile_value(profile, seen, "page_size", "A4" if "A4" in text.upper() else None, req_id)
        margins = _extract_margins_mm(text)
        if margins:
            _set_profile_value(profile, seen, "margins_mm", margins, req_id)
    return profile


def _set_profile_value(profile: dict[str, Any], seen: dict[str, Any], field: str, value: Any, req_id: str) -> None:
    if value in (None, "", {}):
        return
    if field in seen and seen[field] != value:
        profile["conflicts"].append(
            {"field": field, "kept": seen[field], "conflicting": value, "requirement_id": req_id}
        )
        return
    seen[field] = value
    profile[field] = value


def _extract_font_name(text: str) -> str | None:
    return next((font for font in _KNOWN_FONTS if font in text), None)


def _extract_font_size_pt(text: str) -> float | None:
    for label, pt in _FONT_SIZE_PT.items():
        if label in text:
            return pt
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:pt|磅)", text, re.IGNORECASE)
    return float(match.group(1)) if match else None


def _extract_line_spacing(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*倍行距", text)
    return float(match.group(1)) if match else None


def _extract_margins_mm(text: str) -> dict[str, float] | None:
    uniform = re.search(r"页边距(?:上?下?左?右?)*均为\s*(\d+(?:\.\d+)?)\s*mm", text, re.IGNORECASE)
    if uniform:
        value = float(uniform.group(1))
        return {"top": value, "bottom": value, "left": value, "right": value}
    return None
```

Modify `apply_tender_requirement_context(...)` to add:

```python
merged["tender_format_profile"] = build_tender_format_profile(overrides["format_requirements"])
```

- [ ] **Step 4: Run normalization tests**

Run:

```bash
cd backend && pytest tests/unit/test_tender_requirement_priority.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/services/tender_requirement_priority.py backend/tests/unit/test_tender_requirement_priority.py
git commit -m "feat: normalize tender format requirements"
```

## Task 5: Apply Tender Format Profile in DOCX Export

**Files:**
- Modify: `backend/tender_backend/services/export_service/docx_exporter.py`
- Test: `backend/tests/unit/test_docx_exporter.py`

- [ ] **Step 1: Write failing style application tests**

Append to `backend/tests/unit/test_docx_exporter.py`:

```python
from docx import Document

from tender_backend.services.export_service import docx_exporter


def test_apply_basic_style_uses_tender_format_profile() -> None:
    document = Document()
    profile = {
        "font_name": "仿宋",
        "font_size_pt": 12.0,
        "line_spacing": 1.5,
        "page_size": "A4",
        "margins_mm": {"top": 25.0, "bottom": 25.0, "left": 25.0, "right": 25.0},
    }

    docx_exporter._apply_basic_style(
        document,
        company_name="投标人",
        project_name="测试项目",
        volume_label="技术标",
        format_profile=profile,
    )

    normal = document.styles["Normal"]
    assert normal.font.name == "仿宋"
    assert normal.font.size.pt == 12
    assert round(document.sections[0].top_margin.mm) == 25
    assert round(document.sections[0].left_margin.mm) == 25
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend && pytest tests/unit/test_docx_exporter.py::test_apply_basic_style_uses_tender_format_profile -q
```

Expected: FAIL because `_apply_basic_style` does not accept `format_profile`.

- [ ] **Step 3: Update DOCX style function**

Modify imports in `backend/tender_backend/services/export_service/docx_exporter.py`:

```python
from docx.shared import Mm, Pt
from tender_backend.services.tender_requirement_priority import build_tender_format_profile, load_tender_requirement_overrides
```

Change `_apply_basic_style(...)` signature:

```python
def _apply_basic_style(
    document: Document,
    *,
    company_name: str = "投标人",
    project_name: str = "",
    volume_label: str = "投标文件",
    format_profile: dict | None = None,
) -> None:
```

At the top of `_apply_basic_style(...)`:

```python
profile = format_profile or {}
font_name = str(profile.get("font_name") or "宋体")
font_size_pt = float(profile.get("font_size_pt") or 10.5)
style = document.styles["Normal"]
style.font.name = font_name
style.font.size = Pt(font_size_pt)
```

Replace hardcoded margins:

```python
margins = profile.get("margins_mm") if isinstance(profile.get("margins_mm"), dict) else {}
section.top_margin = Mm(float(margins.get("top", 25.4)))
section.bottom_margin = Mm(float(margins.get("bottom", 25.4)))
section.left_margin = Mm(float(margins.get("left", 25.4)))
section.right_margin = Mm(float(margins.get("right", 25.4)))
```

Replace header/footer run font assignments from hardcoded `"宋体"` with `font_name`.

Where export calls `_apply_basic_style(...)`, load overrides before applying style:

```python
overrides = load_tender_requirement_overrides(conn, project_id=project_id)
format_profile = build_tender_format_profile(overrides["format_requirements"])
_apply_basic_style(
    document,
    project_name=project_name,
    volume_label=_volume_label(draft.get("volume_type")),
    format_profile=format_profile,
)
```

Keep the existing appendix, but include format profile evidence:

```python
document.add_paragraph(f"格式来源：{format_profile.get('source')}")
```

- [ ] **Step 4: Run DOCX exporter tests**

Run:

```bash
cd backend && pytest tests/unit/test_docx_exporter.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/services/export_service/docx_exporter.py backend/tests/unit/test_docx_exporter.py
git commit -m "feat: apply tender format profile to docx export"
```

## Task 6: Format Checker Evidence Against Tender Profile

**Files:**
- Modify: `backend/tender_backend/services/export_service/format_checker.py`
- Modify: `backend/tender_backend/services/export_gate_service.py`
- Test: `backend/tests/unit/test_format_checker.py`
- Test: `backend/tests/unit/test_export_gates.py`

- [ ] **Step 1: Write failing checker test**

Append to `backend/tests/unit/test_format_checker.py`:

```python
def test_check_docx_format_checks_tender_profile_font_and_margin(tmp_path: Path):
    path = tmp_path / "profile.docx"
    document = Document()
    document.styles["Normal"].font.name = "宋体"
    document.add_paragraph("正文内容")
    document.save(path)

    result = check_docx_format(
        path,
        tender_format_profile={
            "source": "tender_extracted_requirements",
            "font_name": "仿宋",
            "font_size_pt": 12.0,
            "margins_mm": {"top": 25.0, "bottom": 25.0, "left": 25.0, "right": 25.0},
        },
    )

    assert result["format_status"] == "failed"
    assert result["format_source"] == "tender_extracted_requirements"
    assert any(issue["code"] == "font_name_mismatch" for issue in result["issues"])
```

- [ ] **Step 2: Run checker test to verify it fails**

Run:

```bash
cd backend && pytest tests/unit/test_format_checker.py::test_check_docx_format_checks_tender_profile_font_and_margin -q
```

Expected: FAIL because `check_docx_format` does not accept `tender_format_profile`.

- [ ] **Step 3: Implement profile-aware checks**

Change signature in `backend/tender_backend/services/export_service/format_checker.py`:

```python
def check_docx_format(docx_path: Path | str, tender_format_profile: dict[str, Any] | None = None) -> dict[str, Any]:
```

After loading `document = Document(path)`, add:

```python
profile = tender_format_profile or {}
expected_font = profile.get("font_name")
if expected_font:
    actual_font = document.styles["Normal"].font.name
    if actual_font != expected_font:
        issues.append(
            {
                "code": "font_name_mismatch",
                "severity": "P1",
                "expected": expected_font,
                "actual": actual_font,
                "message": "正文默认字体与招标文件格式要求不一致。",
            }
        )

margins = profile.get("margins_mm") if isinstance(profile.get("margins_mm"), dict) else {}
for section_index, section in enumerate(document.sections, start=1):
    for field, attr in (("top", "top_margin"), ("bottom", "bottom_margin"), ("left", "left_margin"), ("right", "right_margin")):
        if field not in margins:
            continue
        actual = getattr(section, attr)
        actual_mm = actual.mm if actual is not None else 0
        expected_mm = float(margins[field])
        if abs(actual_mm - expected_mm) > 1.0:
            issues.append(
                {
                    "code": f"margin_{field}_mismatch",
                    "severity": "P1",
                    "section_index": section_index,
                    "expected_mm": expected_mm,
                    "actual_mm": round(actual_mm, 2),
                    "message": "页边距与招标文件格式要求不一致。",
                }
            )
```

In the returned dict add:

```python
"format_source": str(profile.get("source") or "unchecked"),
"tender_format_profile": profile,
```

- [ ] **Step 4: Surface evidence in export gate**

In `backend/tender_backend/services/export_gate_service.py`, keep existing non-blocking behavior but ensure `_format_gate_state(...)` includes:

```python
"format_source": str(format_check.get("format_source") or "unchecked"),
"tender_format_profile": format_check.get("tender_format_profile") or {},
```

- [ ] **Step 5: Run format checker and gate tests**

Run:

```bash
cd backend && pytest tests/unit/test_format_checker.py tests/unit/test_export_gates.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/tender_backend/services/export_service/format_checker.py backend/tender_backend/services/export_gate_service.py backend/tests/unit/test_format_checker.py backend/tests/unit/test_export_gates.py
git commit -m "feat: check docx export against tender format profile"
```

## Task 7: Regression Suite

**Files:**
- No code changes expected.

- [ ] **Step 1: Run focused regression**

Run:

```bash
cd backend && pytest tests/unit/test_prompt_contracts.py tests/unit/test_business_text_generators.py tests/unit/test_technical_bid_writer.py tests/unit/test_chart_generation_service.py tests/unit/test_chart_visual_template.py tests/unit/test_tender_requirement_priority.py tests/unit/test_docx_exporter.py tests/unit/test_format_checker.py tests/unit/test_export_gates.py -q
```

Expected: PASS.

- [ ] **Step 2: Run integration smoke for export**

Run:

```bash
cd backend && pytest tests/integration/test_export_gate_and_render.py tests/integration/test_business_bid_assembler_docx.py -q
```

Expected: PASS.

- [ ] **Step 3: Inspect working tree**

Run:

```bash
git status --short
```

Expected: only intended files changed. Do not revert unrelated pre-existing generated/deleted sample files.

- [ ] **Step 4: Commit any final fixes**

If Task 7 required fixes:

```bash
git add backend/tender_backend/services backend/tests/unit backend/tests/integration
git commit -m "test: cover enterprise prompt and format contracts"
```

Expected: commit created only if there were final fixes.

## Recommended Future Work

- Extract format requirements more structurally during tender parsing, not only by keyword matching in post-processing.
- Add source locators for each format rule: file id, page number, source chunk id, original text.
- Add UI review state for conflicting format rules before final export.
- Extend profile application to PDF conversion validation after LibreOffice export.
- Add separate price-volume guardrails so technical text cannot leak quotation terms.
- Add Mermaid/SVG post-processing in a later plan. Current chart generation intentionally remains semantic spec first.

## Self-Review

- Spec coverage: The plan covers prompt contracts, tender format priority, prose generation, chart generation, visual tokens, DOCX application, and export evidence.
- Placeholder scan: No `TBD`, `TODO`, or unspecified implementation steps remain.
- Scope check: This is one coherent first slice. It does not attempt a full AST document renderer or full PPT/PDF pipeline rewrite.
- Ambiguity decision: If tender formatting conflicts with defaults, tender wins. If tender rules conflict with each other, the system records conflicts and avoids guessing.
