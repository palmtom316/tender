"""Prompt templates and message builders for Qwen3-VL vision extraction."""

from __future__ import annotations

from typing import Any

from tender_backend.services.vision_service.pdf_renderer import (
    PageImage,
    encode_page_base64,
)

SYSTEM_PROMPT = (
    "你是一个专业的建筑工程规范条款提取助手。"
    "你将接收规范文档的页面图像，从中提取所有条款信息。"
    "仅输出 JSON 数组，不要输出其他内容。"
)

PAGE_EXTRACTION_PROMPT = """\
请仔细查看这张规范文档的第 {page_number} 页图像，提取该页中所有可见的条款。

输出要求：
1. 以 JSON 数组格式输出该页中每一条可见的条款。
2. 每个条款对象包含:
   - node_type: "clause"（条款）、"item"（条款下的项）、"subitem"（子项）
   - clause_no: 条款编号（如 "3.2.1"），item/subitem 继承父条款编号
   - clause_title: 条款标题（可为空字符串）
   - clause_text: 完整条文内容（严格按原文抄录，包括所有数字、单位、符号）
   - summary: 一句话中文摘要（不超过 50 字）
   - tags: 关键词数组（包含专业领域、技术关键词）
   - page_start: {page_number}
   - page_end: {page_number}
   - children: 下级项数组（item 或 subitem），无则为空数组
   - is_continuation: 此条款是否从上一页延续的内容（true/false）
   - continuation_clause_no: 若 is_continuation 为 true，填写所延续的条款编号
3. 如果条文下存在 "1、2、3" 这类项，放入 children，node_type="item"，node_label 保留原编号文本。
4. 如果项下还有 "1)""2）" 子项，继续放入 children，node_type="subitem"。
5. 页面包含表格时，将表格中的规范要求提取为条款，clause_text 中保留完整的数值和单位。
6. 如果条文包含"必须"、"应"、"不得"、"严禁"等强制性用词，在 tags 中加入 "强制性条文"。
7. 如果该页属于"条文说明"部分，在每个条款中额外设置 clause_type 为 "commentary"。
8. 如果该页是目录、封面、前言等非条款内容，返回空数组 []。

仅输出 JSON 数组，不要输出任何其他文字。"""


def build_vision_messages(
    page: PageImage,
) -> list[dict[str, Any]]:
    """Build OpenAI-format multimodal messages for one page.

    Returns a ``messages`` list suitable for ``client.chat.completions.create``.
    """
    image_uri = encode_page_base64(page)
    user_prompt = PAGE_EXTRACTION_PROMPT.format(page_number=page.page_number)

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": image_uri, "detail": "high"},
                },
                {"type": "text", "text": user_prompt},
            ],
        },
    ]
