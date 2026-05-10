from tender_backend.services.extract_service.requirements_extractor import (
    extract_requirements_from_source_chunks,
)


def test_pricing_only_source_chunk_produces_no_active_requirement():
    requirements = extract_requirements_from_source_chunks(
        [
            {
                "id": "chunk-1",
                "source_file": "招标文件.docx",
                "source_locator": "p10",
                "text": "投标报价不得超过最高限价100万元，综合单价按工程量清单填报。",
            }
        ]
    )

    assert requirements == []


def test_mixed_pricing_and_qualification_keeps_only_non_pricing_requirement():
    requirements = extract_requirements_from_source_chunks(
        [
            {
                "id": "chunk-1",
                "source_file": "招标文件.docx",
                "source_locator": "p11",
                "text": "投标人须具备电力工程施工总承包二级及以上资质，投标报价不得超过最高限价。",
            }
        ]
    )

    assert [req.category for req in requirements] == ["qualification"]
    assert requirements[0].ignored_for_pricing is False
    assert requirements[0].source_metadata["scope_policy"] == "bid_writing_v1"


def test_quality_schedule_safety_and_personnel_chunks_are_active_constraints():
    requirements = extract_requirements_from_source_chunks(
        [
            {
                "id": "quality",
                "text": "质量目标：满足国家电网公司优质工程验收要求，工程质量合格率100%。",
            },
            {
                "id": "schedule",
                "text": "计划工期90日历天，投标人须编制进度保证措施。",
            },
            {
                "id": "safety",
                "text": "投标人须落实安全文明施工和绿色施工措施。",
            },
            {
                "id": "personnel",
                "text": "项目经理1名，须具备机电工程一级注册建造师资格。",
            },
        ]
    )

    assert [req.source_chunk_id for req in requirements] == ["quality", "schedule", "safety", "personnel"]
    assert [req.source_metadata["constraint_subtype"] for req in requirements] == [
        "quality_target",
        "schedule_target",
        "safety_civilized",
        "personnel_count",
    ]
