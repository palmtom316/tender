"""DeepSeek API defaults and request helpers."""

from __future__ import annotations

from typing import Any


DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_V4_PRO_MODEL = "deepseek-v4-pro"
DEEPSEEK_V4_FLASH_MODEL = "deepseek-v4-flash"
DEEPSEEK_THINKING_ENABLED = "enabled"
DEEPSEEK_THINKING_DISABLED = "disabled"
DEEPSEEK_V4_HIGH_REASONING_EFFORT = "high"
DEEPSEEK_V4_MAX_REASONING_EFFORT = "max"
DEEPSEEK_V4_REASONING_EFFORTS = {
    DEEPSEEK_V4_HIGH_REASONING_EFFORT,
    DEEPSEEK_V4_MAX_REASONING_EFFORT,
}
_DEEPSEEK_V4_COMPAT_REASONING_EFFORTS = {
    "low": DEEPSEEK_V4_HIGH_REASONING_EFFORT,
    "medium": DEEPSEEK_V4_HIGH_REASONING_EFFORT,
    "xhigh": DEEPSEEK_V4_MAX_REASONING_EFFORT,
}


def is_deepseek_v4_model(model: str | None) -> bool:
    return (model or "").strip() in {DEEPSEEK_V4_PRO_MODEL, DEEPSEEK_V4_FLASH_MODEL}


def normalize_deepseek_v4_reasoning_effort(reasoning_effort: str | None) -> str | None:
    value = (reasoning_effort or "").strip()
    if not value:
        return None
    value = _DEEPSEEK_V4_COMPAT_REASONING_EFFORTS.get(value, value)
    if value not in DEEPSEEK_V4_REASONING_EFFORTS:
        raise ValueError(f"unsupported DeepSeek V4 reasoning_effort: {value}")
    return value


def deepseek_v4_thinking_options(
    *,
    thinking_enabled: bool | None = None,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    normalized = normalize_deepseek_v4_reasoning_effort(reasoning_effort)
    if thinking_enabled is None and normalized is None:
        return {}
    payload: dict[str, Any] = {}
    if thinking_enabled is not None:
        payload["thinking"] = {
            "type": DEEPSEEK_THINKING_ENABLED if thinking_enabled else DEEPSEEK_THINKING_DISABLED
        }
    if normalized is not None:
        payload["reasoning_effort"] = normalized
    return payload


def deepseek_v4_openai_sdk_options(
    *,
    thinking_enabled: bool | None = None,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    """Return DeepSeek V4 thinking options in OpenAI Python SDK shape."""
    options = deepseek_v4_thinking_options(
        thinking_enabled=thinking_enabled,
        reasoning_effort=reasoning_effort,
    )
    sdk_options: dict[str, Any] = {}
    thinking = options.get("thinking")
    if thinking is not None:
        sdk_options["extra_body"] = {"thinking": thinking}
    if options.get("reasoning_effort") is not None:
        sdk_options["reasoning_effort"] = options["reasoning_effort"]
    return sdk_options


def apply_deepseek_v4_thinking_options(
    payload: dict[str, Any],
    *,
    model: str | None,
    thinking_enabled: bool | None = None,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    if is_deepseek_v4_model(model):
        payload.update(
            deepseek_v4_thinking_options(
                thinking_enabled=thinking_enabled,
                reasoning_effort=reasoning_effort,
            )
        )
    return payload
