"""LLM prompt templates for clause extraction from standard documents."""

from __future__ import annotations

from tender_backend.services.norm_service.scope_splitter import ProcessingScope

# ── Clause extraction prompt (normative body) ──

CLAUSE_EXTRACTION_PROMPT = """\
你是一个建筑工程规范条款提取助手。请从以下规范文本中提取所有条款，以 JSON 数组格式输出。

要求：
1. 每条包含: clause_no（条款编号如"3.2.1"）、clause_title（标题，可为空）、clause_text（完整条文）、summary（一句话摘要）、tags（关键词数组）、page_start（页码，如已知）
2. 严格按照原文提取，不要修改条文内容
3. 条款编号格式保持原文一致（如"3.2.1"、"第3.2.1条"等均保留原始格式）
4. tags 应包含：专业领域（如"结构"、"给排水"）、条款类型（如"强制性条文"、"推荐性条文"）、关键技术词
5. 如果条文包含"必须"、"应"、"不得"、"严禁"等强制性用词，在tags中标注"强制性条文"

仅输出 JSON 数组，不要输出其他文字。格式示例：
[
  {{
    "clause_no": "3.2.1",
    "clause_title": "一般规定",
    "clause_text": "混凝土强度等级不应低于C25...",
    "summary": "规定了混凝土最低强度等级要求",
    "tags": ["结构", "混凝土", "强制性条文"],
    "page_start": 15
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


def build_prompt(scope: ProcessingScope) -> str:
    """Build the appropriate LLM prompt based on scope type."""
    if scope.scope_type == "commentary":
        return COMMENTARY_EXTRACTION_PROMPT.format(text=scope.text)
    return CLAUSE_EXTRACTION_PROMPT.format(text=scope.text)


def build_tag_prompt(clause_no: str, clause_text: str) -> str:
    """Build a tag/summary enrichment prompt for a single clause."""
    return TAG_SUMMARY_PROMPT.format(clause_no=clause_no, clause_text=clause_text)
