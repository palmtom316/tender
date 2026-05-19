from __future__ import annotations

import pytest

from tender_backend.services.bid_outline_templates import SGCC_DISTRIBUTION_TECHNICAL_CHAPTERS
from tender_backend.services.technical_chapter_strategies.registry import strategy_for_chapter


def test_technical_strategy_registry_covers_16_top_level_chapters() -> None:
    top_level_codes = {
        chapter["chapter_code"]
        for chapter in SGCC_DISTRIBUTION_TECHNICAL_CHAPTERS
        if "." not in chapter["chapter_code"]
    }

    assert top_level_codes == {str(index) for index in range(1, 17)}
    assert {code for code in top_level_codes if strategy_for_chapter(code) is None} == set()


@pytest.mark.parametrize("chapter_code", ["2", "3", "7", "11", "14", "15", "16"])
def test_non_longform_delivery_chapters_have_specific_semantics(chapter_code: str) -> None:
    strategy = strategy_for_chapter(chapter_code)

    assert strategy is not None
    assert strategy.required_facts
    assert strategy.required_assets
    assert strategy.self_check_rules
    assert "fallback" not in strategy.key


def test_chapter_6_strategy_requires_team_certificates_appointment_and_commitments() -> None:
    strategy = strategy_for_chapter("6")

    assert strategy is not None
    assert {"project_team_roster", "personnel_certificates", "appointment_letter", "team_commitment"} <= set(
        strategy.required_assets
    )
    assert any("人证岗" in rule for rule in strategy.self_check_rules)
    assert any("任命" in rule for rule in strategy.self_check_rules)
