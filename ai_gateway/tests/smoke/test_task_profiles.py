from __future__ import annotations

from tender_ai_gateway.task_profiles import TASK_PROFILES


def test_vision_repair_profile_uses_extended_timeout() -> None:
    profile = TASK_PROFILES["vision_repair"]

    assert profile["timeout"] == 300
    assert profile["max_retries"] == 1
