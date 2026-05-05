"""DeepSeek API defaults and request helpers."""

from __future__ import annotations

from typing import Any


DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_V4_PRO_MODEL = "deepseek-v4-pro"
DEEPSEEK_V4_FLASH_MODEL = "deepseek-v4-flash"
DEEPSEEK_V4_HIGH_REASONING_EFFORT = "high"
DEEPSEEK_V4_MAX_REASONING_EFFORT = "max"
DEEPSEEK_V4_REASONING_EFFORTS = {
    DEEPSEEK_V4_HIGH_REASONING_EFFORT,
    DEEPSEEK_V4_MAX_REASONING_EFFORT,
}


def is_deepseek_v4_model(model: str | None) -> bool:
    return (model or "").strip() in {DEEPSEEK_V4_PRO_MODEL, DEEPSEEK_V4_FLASH_MODEL}


def normalize_deepseek_v4_reasoning_effort(reasoning_effort: str | None) -> str | None:
    value = (reasoning_effort or "").strip()
    if not value:
        return None
    if value not in DEEPSEEK_V4_REASONING_EFFORTS:
        raise ValueError(f"unsupported DeepSeek V4 reasoning_effort: {value}")
    return value


def deepseek_v4_thinking_options(*, reasoning_effort: str | None = None) -> dict[str, Any]:
    normalized = normalize_deepseek_v4_reasoning_effort(reasoning_effort)
    if normalized is None:
        return {}
    return {
        "reasoning_effort": normalized,
    }


def apply_deepseek_v4_thinking_options(
    payload: dict[str, Any],
    *,
    model: str | None,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    if is_deepseek_v4_model(model) and reasoning_effort:
        payload.update(deepseek_v4_thinking_options(reasoning_effort=reasoning_effort))
    return payload
