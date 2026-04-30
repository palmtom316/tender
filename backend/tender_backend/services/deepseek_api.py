"""DeepSeek API defaults and request helpers."""

from __future__ import annotations

from typing import Any


DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_V4_PRO_MODEL = "deepseek-v4-pro"
DEEPSEEK_V4_FLASH_MODEL = "deepseek-v4-flash"
DEEPSEEK_V4_MAX_REASONING_EFFORT = "max"


def is_deepseek_v4_model(model: str | None) -> bool:
    return (model or "").strip() in {DEEPSEEK_V4_PRO_MODEL, DEEPSEEK_V4_FLASH_MODEL}


def deepseek_v4_thinking_options(*, reasoning_effort: str = DEEPSEEK_V4_MAX_REASONING_EFFORT) -> dict[str, Any]:
    return {
        "thinking": {"type": "enabled"},
        "reasoning_effort": reasoning_effort,
    }


def apply_deepseek_v4_thinking_options(payload: dict[str, Any], *, model: str | None) -> dict[str, Any]:
    if is_deepseek_v4_model(model):
        payload.update(deepseek_v4_thinking_options())
    return payload
