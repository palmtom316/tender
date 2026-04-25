from __future__ import annotations

import json

from tender_ai_gateway.task_profiles import TASK_PROFILES


def test_vision_repair_profile_uses_extended_timeout() -> None:
    profile = TASK_PROFILES["vision_repair"]

    assert profile["timeout"] == 300
    assert profile["max_retries"] == 1


def test_parse_profiles_use_deepseek_v4_flash_only() -> None:
    for task_name in (
        "generate_section",
        "review_section",
        "tag_clauses",
        "standard_parse_audit",
        "clause_enrichment_batch",
        "unparsed_block_repair",
    ):
        assert TASK_PROFILES[task_name]["primary_model"] == "deepseek-v4-flash"

    assert "deepseek-v4-pro" not in json.dumps(TASK_PROFILES).lower()


def test_tag_clause_profile_has_large_output_budget() -> None:
    profile = TASK_PROFILES["tag_clauses"]

    assert profile["timeout"] == 600
    assert profile["max_tokens"] == 32768
    assert profile["max_retries"] == 0
