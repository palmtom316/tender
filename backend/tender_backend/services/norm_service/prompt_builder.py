"""LLM prompt templates for clause extraction from standard documents."""

from __future__ import annotations

import json

from tender_backend.services.norm_service.scope_splitter import ProcessingScope

# ── Clause extraction prompt (normative body) ──

CLAUSE_EXTRACTION_PROMPT = """\
你是一个建筑工程规范条款提取助手。请从以下规范文本中提取所有条款，以 JSON 数组格式输出。

要求：
1. 每个主条款对象包含: node_type（固定为"clause"）、clause_no（条款编号如"3.2.1"）、clause_title（标题，可为空）、clause_text（完整条文）、summary（一句话摘要）、tags（关键词数组）、page_start（页码，如已知）、children（下级项数组）
2. 严格按照原文提取，不要修改条文内容
3. 条款编号格式保持原文一致（如"3.2.1"、"第3.2.1条"等均保留原始格式）
4. 如果条文下存在“1、2、3”这类项，必须放入 children，并将节点写为：node_type="item"、node_label="1"（保留原编号文本）、clause_text、summary、tags、page_start、children
5. 如果项下还存在“1)”“2）”这类子项，必须继续放入 children，并将节点写为：node_type="subitem"、node_label="1)"（保留原编号文本）、clause_text、summary、tags、page_start
6. tags 应包含：专业领域（如"结构"、"给排水"）、条款类型（如"强制性条文"、"推荐性条文"）、关键技术词
7. 如果条文包含"必须"、"应"、"不得"、"严禁"等强制性用词，在tags中标注"强制性条文"

仅输出 JSON 数组，不要输出其他文字。格式示例：
[
  {{
    "node_type": "clause",
    "clause_no": "3.2.1",
    "clause_title": "一般规定",
    "clause_text": "混凝土强度等级不应低于C25...",
    "summary": "规定了混凝土最低强度等级要求",
    "tags": ["结构", "混凝土", "强制性条文"],
    "page_start": 15,
    "children": [
      {{
        "node_type": "item",
        "node_label": "1",
        "clause_text": "第一项内容...",
        "summary": "第一项摘要",
        "tags": ["结构"],
        "page_start": 15,
        "children": [
          {{
            "node_type": "subitem",
            "node_label": "1)",
            "clause_text": "子项内容...",
            "summary": "子项摘要",
            "tags": ["结构"],
            "page_start": 15
          }}
        ]
      }}
    ]
  }}
]

--- 规范文本开始 ---
{text}
--- 规范文本结束 ---
"""

# ── Commentary extraction prompt (条文说明) ──

COMMENTARY_EXTRACTION_PROMPT = """\
你是一个建筑工程规范条文说明提取助手。请从以下条文说明文本中提取所有说明条款，以 JSON 数组格式输出。

要求：
1. 每条包含: clause_no（对应的正文条款编号）、clause_title（标题，可为空）、clause_text（说明全文）、summary（一句话摘要）、tags（关键词数组）、page_start
2. clause_no 必须与正文条款编号对应（如正文"3.2.1"的说明也用"3.2.1"）
3. 这些是条文说明（解释性、非强制性），用于辅助理解正文条款

仅输出 JSON 数组，格式同上。

--- 条文说明开始 ---
{text}
--- 条文说明结束 ---
"""

# ── Table extraction prompt (规范表格) ──

TABLE_EXTRACTION_PROMPT = """\
你是一个建筑工程规范表格条款提取助手。请从以下规范表格中提取能形成规范要求的条款，以 JSON 数组格式输出。

要求：
1. 仅提取表格中明确表达的规范要求、参数要求、限值、条件、检测项、技术指标
2. 每条仍输出为与正文兼容的结构：node_type、clause_no（如无明确编号可为空）、clause_title、clause_text、summary、tags、page_start、children
3. 如果表格只是标题或说明，不能形成独立规范要求时，返回空数组
4. `clause_text` 必须保留关键数字、单位、符号和条件，不要改写
5. 仅输出 JSON 数组，不要输出其他文字

--- 规范表格开始 ---
{text}
--- 规范表格结束 ---
"""

# ── Tag summary prompt ──

TAG_SUMMARY_PROMPT = """\
请为以下规范条款生成精确的标签和摘要。

条款编号: {clause_no}
条款内容: {clause_text}

请输出 JSON 对象:
{{
  "summary": "一句话摘要（不超过50字）",
  "tags": ["标签1", "标签2", ...]
}}

标签应包含：专业领域、技术关键词、条款性质（强制性/推荐性）。
仅输出 JSON，不要输出其他文字。
"""

# ── Long-context Flash prompts (audit/enrichment/repair) ──

STANDARD_PARSE_AUDIT_PROMPT = """\
You are auditing a deterministic standard parser output.
Do not extract the document from scratch.

Given document outline, deterministic blocks, AST summary, validation issues,
and source references:
1. report missing clause numbers
2. report duplicated or merged clauses
3. report commentary mismatches
4. report table requirement gaps
5. return JSON patches keyed by block_id/node_key/source_ref

If evidence is insufficient, return needs_review instead of guessing.
Only output JSON.

Document outline JSON:
{document_outline}

Deterministic blocks JSON:
{deterministic_blocks}

AST summary JSON:
{ast_summary}

Validation issues JSON:
{validation_issues}
"""

CLAUSE_ENRICHMENT_BATCH_PROMPT = """\
You are enriching existing standard clause nodes.
You must not add, remove, split, merge, or renumber clauses.
Return one JSON array item per input node, keyed by node_key.

Allowed output fields:
- node_key
- summary
- tags
- requirement_type: mandatory|advisory|permissive|informative
- mandatory_terms

Only output JSON.

Clause nodes JSON:
{clause_nodes}
"""

UNPARSED_BLOCK_REPAIR_PROMPT = """\
You are repairing one low-confidence parser block.
Do not rewrite the whole document. Return a patch contract only.

Allowed status values: patch|needs_review|no_change
Allowed operations: split_clause|attach_item|normalize_table

Output JSON shape:
{{
  "status": "patch|needs_review|no_change",
  "patches": [
    {{
      "source_ref": "...",
      "operation": "split_clause|attach_item|normalize_table",
      "evidence": "...",
      "candidate": {{}}
    }}
  ]
}}

Low-confidence block JSON:
{block}
"""


def build_prompt(scope: ProcessingScope) -> str:
    """Build the appropriate LLM prompt based on scope type."""
    context_parts: list[str] = []
    if scope.source_refs:
        context_parts.append(f"来源引用: {', '.join(scope.source_refs)}")
    if scope.context:
        context_parts.append(f"结构化上下文(JSON): {json.dumps(scope.context, ensure_ascii=False)}")

    content = scope.text
    if context_parts:
        content = "\n".join(context_parts) + "\n\n" + content

    if scope.scope_type == "commentary":
        return COMMENTARY_EXTRACTION_PROMPT.format(text=content)
    if scope.scope_type == "table":
        return TABLE_EXTRACTION_PROMPT.format(text=content)
    return CLAUSE_EXTRACTION_PROMPT.format(text=content)


def build_tag_prompt(clause_no: str, clause_text: str) -> str:
    """Build a tag/summary enrichment prompt for a single clause."""
    return TAG_SUMMARY_PROMPT.format(clause_no=clause_no, clause_text=clause_text)


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def build_standard_parse_audit_prompt(
    *,
    document_outline: list[dict],
    deterministic_blocks: list[dict],
    ast_summary: list[dict],
    validation_issues: list[dict],
) -> str:
    """Build a whole-document parser audit prompt for long-context models."""
    return STANDARD_PARSE_AUDIT_PROMPT.format(
        document_outline=_json_dumps(document_outline),
        deterministic_blocks=_json_dumps(deterministic_blocks),
        ast_summary=_json_dumps(ast_summary),
        validation_issues=_json_dumps(validation_issues),
    )


def build_clause_enrichment_batch_prompt(clause_nodes: list[dict]) -> str:
    """Build a batch enrichment prompt that cannot mutate AST structure."""
    return CLAUSE_ENRICHMENT_BATCH_PROMPT.format(clause_nodes=_json_dumps(clause_nodes))


def build_unparsed_block_repair_prompt(block: dict) -> str:
    """Build a patch-oriented prompt for a low-confidence parser block."""
    return UNPARSED_BLOCK_REPAIR_PROMPT.format(block=_json_dumps(block))


PROMPT_MODE_TASK_TYPES = {
    "summarize_tags": "clause_enrichment_batch",
    "classify_requirement": "clause_enrichment_batch",
    "repair_unparsed_block": "unparsed_block_repair",
    "normalize_table_requirement": "unparsed_block_repair",
    "whole_document_consistency": "standard_parse_audit",
}


def prompt_mode_task_type(prompt_mode: str) -> str:
    try:
        return PROMPT_MODE_TASK_TYPES[prompt_mode]
    except KeyError as exc:
        raise ValueError(f"Unsupported prompt mode: {prompt_mode}") from exc


def build_task_mode_prompt(prompt_mode: str, **payload: object) -> str:
    """Build enrichment/fallback prompts by task mode, never legacy extraction."""
    prompt_mode_task_type(prompt_mode)
    if prompt_mode in {"summarize_tags", "classify_requirement"}:
        clause_nodes = payload.get("clause_nodes")
        if not isinstance(clause_nodes, list):
            raise ValueError(f"{prompt_mode} requires clause_nodes")
        return build_clause_enrichment_batch_prompt(clause_nodes)
    if prompt_mode in {"repair_unparsed_block", "normalize_table_requirement"}:
        block = payload.get("block")
        if not isinstance(block, dict):
            raise ValueError(f"{prompt_mode} requires block")
        return build_unparsed_block_repair_prompt(block)
    if prompt_mode == "whole_document_consistency":
        return build_standard_parse_audit_prompt(
            document_outline=list(payload.get("document_outline") or []),
            deterministic_blocks=list(payload.get("deterministic_blocks") or []),
            ast_summary=list(payload.get("ast_summary") or []),
            validation_issues=list(payload.get("validation_issues") or []),
        )
    raise ValueError(f"Unsupported prompt mode: {prompt_mode}")
