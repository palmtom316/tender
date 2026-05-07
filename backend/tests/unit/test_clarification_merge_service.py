from tender_backend.services.clarification_merge_service import ClarificationMergeService


def test_extract_clauses_classifies_later_clarification_items() -> None:
    service = ClarificationMergeService()

    clauses = service.extract_clauses("递交截止时间调整为2026年5月20日。\n\n项目经理须提供近6个月社保。")

    assert [clause.category for clause in clauses] == ["schedule", "project_team"]
    assert clauses[0].source_locator == "clarification-clause-1"
    assert "2026年5月20日" in clauses[0].text


def test_match_existing_requirement_uses_category_topic_and_similarity() -> None:
    service = ClarificationMergeService()
    clause = service.extract_clauses("投标文件递交截止时间调整为2026年5月20日。")[-1]
    requirements = [
        {
            "id": "old-deadline",
            "category": "schedule",
            "title": "递交截止时间",
            "requirement_text": "投标文件递交截止时间为2026年5月10日。",
        },
        {
            "id": "technical",
            "category": "technical",
            "title": "施工方案",
            "requirement_text": "投标人应编制施工组织设计。",
        },
    ]

    matched = service._match_existing_requirement(clause, requirements)

    assert matched is not None
    assert matched["id"] == "old-deadline"
    assert matched["_similarity"] > 0.52


def test_unrelated_clarification_does_not_force_override() -> None:
    service = ClarificationMergeService()
    clause = service.extract_clauses("新增绿色施工与低碳管理章节。")[-1]

    matched = service._match_existing_requirement(
        clause,
        [
            {
                "id": "old-bond",
                "category": "business",
                "title": "保证金",
                "requirement_text": "投标保证金金额为10万元。",
            }
        ],
    )

    assert matched is None
