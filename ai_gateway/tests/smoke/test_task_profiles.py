from __future__ import annotations

from tender_ai_gateway.task_profiles import TASK_PROFILES


def test_vision_repair_profile_uses_extended_timeout() -> None:
    profile = TASK_PROFILES["vision_repair"]

    assert profile["timeout"] == 300
    assert profile["max_retries"] == 1


def test_parse_profiles_use_deepseek_v4_flash_only() -> None:
    """Non-tender parse profiles stay on flash for cost control.

    Tender extraction tasks (extract_tender_*, extract_scoring_criteria) are
    explicitly whitelisted to use v4-pro elsewhere — see _V4_PRO_ALLOWED_TASKS
    in fallback.py.
    """
    for task_name in (
        "generate_section",
        "review_section",
        "tag_clauses",
        "standard_parse_audit",
        "clause_enrichment_batch",
        "unparsed_block_repair",
    ):
        assert TASK_PROFILES[task_name]["primary_model"] == "deepseek-v4-flash"


def test_tender_requirement_profile_uses_flash_first_for_throughput() -> None:
    profile = TASK_PROFILES["extract_tender_requirements"]

    assert profile["primary_model"] == "deepseek-v4-flash"
    assert profile["fallback_model"] == "deepseek-v4-pro"
    assert profile["max_tokens"] == 16384
    assert profile["max_retries"] == 0


def test_high_value_tender_profiles_allow_v4_pro() -> None:
    for task_name in ("extract_tender_facts", "extract_scoring_criteria"):
        profile = TASK_PROFILES[task_name]
        assert profile["primary_model"] == "deepseek-v4-pro"
        assert profile["fallback_model"] == "deepseek-v4-flash"
        assert profile["max_retries"] == 0


def test_tag_clause_profile_has_large_output_budget() -> None:
    profile = TASK_PROFILES["tag_clauses"]

    assert profile["timeout"] == 600
    assert profile["max_tokens"] == 32768
    assert profile["max_retries"] == 0
