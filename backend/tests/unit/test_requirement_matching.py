from __future__ import annotations

from uuid import uuid4

from tender_backend.services.requirement_matching import _match_records
from tender_backend.services.requirement_matching import _match_standard_clauses


def test_match_records_satisfied_when_master_data_contains_requirement_terms() -> None:
    requirement = {
        "id": uuid4(),
        "title": "业绩要求",
        "requirement_text": "类似项目业绩 智能化 工程",
    }
    records = [
        {
            "id": uuid4(),
            "project_name": "智能化工程类似项目",
            "client_name": "业主单位",
            "service_scope": "智能化 工程 服务",
        }
    ]

    match = _match_records(
        requirement=requirement,
        records=records,
        source_type="project_performance",
        title_keys=("project_name",),
        missing_reason="未找到业绩资料",
    )

    assert match["match_status"] == "satisfied"
    assert match["matched_source_type"] == "project_performance"
    assert match["requires_human_confirm"] is False


def test_match_records_missing_when_no_master_data_exists() -> None:
    requirement = {
        "id": uuid4(),
        "title": "人员要求",
        "requirement_text": "项目经理须提供一级建造师证书",
    }

    match = _match_records(
        requirement=requirement,
        records=[],
        source_type="person_profile",
        title_keys=("full_name",),
        missing_reason="未找到人员资料",
    )

    assert match["match_status"] == "missing"
    assert match["missing_reason"] == "未找到人员资料"
    assert match["requires_human_confirm"] is True


def test_match_standard_clauses_for_technical_requirement() -> None:
    requirement = {
        "id": uuid4(),
        "title": "验收标准",
        "requirement_text": "工程质量 验收 标准",
    }
    clauses = [
        {
            "id": uuid4(),
            "standard_name": "施工质量验收规范",
            "clause_title": "工程质量验收",
            "clause_text": "工程质量 验收 应符合 标准",
        }
    ]

    match = _match_standard_clauses(requirement, clauses)

    assert match["match_status"] == "satisfied"
    assert match["matched_source_type"] == "standard_clause"
