from __future__ import annotations

from tender_backend.services.deepseek_api import (
    DEEPSEEK_V4_MAX_REASONING_EFFORT,
    DEEPSEEK_V4_PRO_MODEL,
    apply_deepseek_v4_thinking_options,
    deepseek_v4_thinking_options,
    normalize_deepseek_v4_reasoning_effort,
)


def test_deepseek_v4_thinking_options_do_not_default_to_max_reasoning_effort() -> None:
    assert deepseek_v4_thinking_options() == {}
    assert deepseek_v4_thinking_options(reasoning_effort=DEEPSEEK_V4_MAX_REASONING_EFFORT) == {
        "reasoning_effort": "max",
    }


def test_apply_deepseek_v4_thinking_options_only_for_v4_models() -> None:
    payload = {"model": DEEPSEEK_V4_PRO_MODEL}

    apply_deepseek_v4_thinking_options(
        payload,
        model=DEEPSEEK_V4_PRO_MODEL,
        reasoning_effort=DEEPSEEK_V4_MAX_REASONING_EFFORT,
    )

    assert payload["reasoning_effort"] == "max"

    other_payload = {"model": "qwen-plus"}
    apply_deepseek_v4_thinking_options(
        other_payload,
        model="qwen-plus",
        reasoning_effort=DEEPSEEK_V4_MAX_REASONING_EFFORT,
    )
    assert "thinking" not in other_payload
    assert "reasoning_effort" not in other_payload


def test_normalize_deepseek_v4_reasoning_effort_rejects_unknown_values() -> None:
    assert normalize_deepseek_v4_reasoning_effort(None) is None
    assert normalize_deepseek_v4_reasoning_effort("high") == "high"

    try:
        normalize_deepseek_v4_reasoning_effort("medium")
    except ValueError as exc:
        assert "unsupported DeepSeek V4 reasoning_effort" in str(exc)
    else:
        raise AssertionError("unsupported reasoning effort should fail fast")
