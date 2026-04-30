from __future__ import annotations

from tender_backend.services.deepseek_api import (
    DEEPSEEK_V4_PRO_MODEL,
    apply_deepseek_v4_thinking_options,
    deepseek_v4_thinking_options,
)


def test_deepseek_v4_thinking_options_use_max_reasoning_effort() -> None:
    assert deepseek_v4_thinking_options() == {
        "thinking": {"type": "enabled"},
        "reasoning_effort": "max",
    }


def test_apply_deepseek_v4_thinking_options_only_for_v4_models() -> None:
    payload = {"model": DEEPSEEK_V4_PRO_MODEL}

    apply_deepseek_v4_thinking_options(payload, model=DEEPSEEK_V4_PRO_MODEL)

    assert payload["thinking"] == {"type": "enabled"}
    assert payload["reasoning_effort"] == "max"

    other_payload = {"model": "qwen-plus"}
    apply_deepseek_v4_thinking_options(other_payload, model="qwen-plus")
    assert "thinking" not in other_payload
    assert "reasoning_effort" not in other_payload
