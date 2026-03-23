"""Prompt builders for local VL repair tasks."""

from __future__ import annotations

from typing import Any

from tender_backend.services.norm_service.repair_tasks import RepairTask
from tender_backend.services.vision_service.pdf_renderer import PageImage, encode_page_base64

SYSTEM_PROMPT = (
    "你是一个建筑工程规范文档局部修复助手。"
    "你将收到规范页面图像和局部修复任务。"
    "只能修复指定 source_ref 对应的表格或数字符号片段，不得改写其他内容。"
    "仅输出 JSON 对象，不要输出其他内容。"
)

_TASK_INSTRUCTIONS = {
    "table_repair": (
        "请根据图像修复指定表格块，重点检查跨页延续、表头、空单元格、数字单位。"
        "输出 patched_table_html；如果无需修复，status 返回 noop。"
    ),
    "symbol_numeric_repair": (
        "请根据图像修复指定片段中的数字、单位、符号问题。"
        "输出 patched_text；如果无需修复，status 返回 noop。"
    ),
}


def build_repair_messages(task: RepairTask, pages: list[PageImage]) -> list[dict[str, Any]]:
    """Build multimodal AI Gateway messages for a local repair task."""
    if not pages:
        raise ValueError("Repair tasks require at least one rendered page image")

    user_prompt = (
        f"任务类型: {task.task_type}\n"
        f"来源引用: {task.source_ref}\n"
        f"页码范围: {task.page_start} - {task.page_end}\n"
        f"触发原因: {', '.join(task.trigger_reasons) or 'none'}\n"
        f"输入载荷: {task.input_payload}\n\n"
        f"{_TASK_INSTRUCTIONS.get(task.task_type, '请对指定片段做精确修复。')}\n\n"
        "输出 JSON 对象，字段至少包含:\n"
        "- task_type\n"
        "- source_ref\n"
        "- status: patched 或 noop\n"
        "- patched_text: 文本修复结果，没有则为 null\n"
        "- patched_table_html: 表格修复结果，没有则为 null\n"
        "- notes: 简短说明\n"
    )

    content: list[dict[str, Any]] = [
        {
            "type": "image_url",
            "image_url": {"url": encode_page_base64(page), "detail": "high"},
        }
        for page in pages
    ]
    content.append({"type": "text", "text": user_prompt})

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]
