from __future__ import annotations

from tender_backend.services.deepseek_api import (
    DEEPSEEK_V4_MAX_REASONING_EFFORT,
    DEEPSEEK_V4_PRO_MODEL,
    apply_deepseek_v4_thinking_options,
    deepseek_v4_openai_sdk_options,
    deepseek_v4_thinking_options,
    normalize_deepseek_v4_reasoning_effort,
)


def test_deepseek_v4_thinking_options_do_not_default_to_max_reasoning_effort() -> None:
    assert deepseek_v4_thinking_options() == {}
    assert deepseek_v4_thinking_options(reasoning_effort=DEEPSEEK_V4_MAX_REASONING_EFFORT) == {
        "reasoning_effort": "max",
    }
    assert deepseek_v4_thinking_options(thinking_enabled=False) == {
        "thinking": {"type": "disabled"},
    }


def test_apply_deepseek_v4_thinking_options_only_for_v4_models() -> None:
    payload = {"model": DEEPSEEK_V4_PRO_MODEL}

    apply_deepseek_v4_thinking_options(
        payload,
        model=DEEPSEEK_V4_PRO_MODEL,
        thinking_enabled=True,
        reasoning_effort=DEEPSEEK_V4_MAX_REASONING_EFFORT,
    )

    assert payload["thinking"] == {"type": "enabled"}
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
    assert normalize_deepseek_v4_reasoning_effort("low") == "high"
    assert normalize_deepseek_v4_reasoning_effort("medium") == "high"
    assert normalize_deepseek_v4_reasoning_effort("xhigh") == "max"

    try:
        normalize_deepseek_v4_reasoning_effort("ultra")
    except ValueError as exc:
        assert "unsupported DeepSeek V4 reasoning_effort" in str(exc)
    else:
        raise AssertionError("unsupported reasoning effort should fail fast")


def test_deepseek_v4_openai_sdk_options_puts_thinking_in_extra_body() -> None:
    assert deepseek_v4_openai_sdk_options(thinking_enabled=True, reasoning_effort="xhigh") == {
        "extra_body": {"thinking": {"type": "enabled"}},
        "reasoning_effort": "max",
    }
