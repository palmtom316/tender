from __future__ import annotations

import pytest

from tender_backend.services.bid_outline_templates import SGCC_DISTRIBUTION_TECHNICAL_CHAPTERS
from tender_backend.services.technical_chapter_strategies.registry import strategy_for_chapter


def test_technical_strategy_registry_covers_requested_top_level_chapters() -> None:
    top_level_codes = {
        chapter["chapter_code"]
        for chapter in SGCC_DISTRIBUTION_TECHNICAL_CHAPTERS
        if "." not in chapter["chapter_code"]
    }

    assert top_level_codes == {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"}
    assert {code for code in top_level_codes if strategy_for_chapter(code) is None} == set()


@pytest.mark.parametrize("chapter_code", ["0", "0.1", "0.2", "0.3", "2", "3", "7", "11", "12", "13"])
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


def test_chapter_8_4_strategy_slices_distribution_process_subsections() -> None:
    strategy = strategy_for_chapter("8.4")

    assert strategy is not None
    section_text = "\n".join(f"{heading}\n{body}" for heading, body in strategy.sections)
    for process_name in ("架空线", "电缆", "配电站房", "台区改造"):
        assert process_name in section_text

    for _heading, body in strategy.sections:
        if any(process_name in body for process_name in ("架空线", "电缆", "配电站房", "台区改造")):
            assert "SOP" in body
            assert "风险点" in body
            assert "质量控制点" in body
            assert "{{chart:" in body


def test_chapter_8_prompt_input_contains_distribution_process_guidance() -> None:
    strategy = strategy_for_chapter("8")

    assert strategy is not None
    prompt_input_text = "\n".join(f"{heading}\n{body}" for heading, body in strategy.sections)
    assert "8.4 主要施工方法及技术要求" in prompt_input_text
    for process_name in ("架空线", "电缆", "配电站房", "台区改造"):
        assert process_name in prompt_input_text
    assert "SOP" in prompt_input_text
    assert "质量控制点" in prompt_input_text
    assert "{{chart:construction_flow}}" in prompt_input_text
    assert "按测量、开挖、基础、电杆组立、架线、电缆敷设、设备安装、接地、恢复等工序形成SOP" not in prompt_input_text


def test_chapter_0_3_strategy_is_bid_directory_not_cover_page() -> None:
    strategy = strategy_for_chapter("0.3")

    assert strategy is not None
    assert strategy.key == "technical_bid_directory"
    assert any("目录" in heading for heading, _body in strategy.sections)
    assert any("不得生成章节封面" in rule for rule in strategy.self_check_rules)
