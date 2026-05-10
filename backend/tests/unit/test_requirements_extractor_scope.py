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


def test_pricing_only_source_chunk_records_ignored_reason_in_chunk_metadata():
    chunk = {
        "id": "chunk-1",
        "source_file": "招标文件.docx",
        "source_locator": "p10",
        "text": "投标报价不得超过最高限价100万元，综合单价按工程量清单填报。",
    }

    requirements = extract_requirements_from_source_chunks([chunk])

    assert requirements == []
    assert chunk["extraction_metadata"]["ignored_reason"] == "pricing_only"
    assert chunk["extraction_metadata"]["pricing_keywords"] == ["报价", "投标报价", "最高限价", "单价", "工程量清单"]


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
    assert requirements[0].source_metadata["extraction_mode_marker"] == "scoped_v1"


def test_rule_fallback_active_decisions_are_subset_of_scoped_policy_topics():
    chunks = [
        {"id": "pricing", "text": "投标报价不得超过最高限价100万元，综合单价按工程量清单填报。"},
        {"id": "qualification", "text": "投标人须具备电力工程施工总承包二级及以上资质。"},
        {"id": "personnel", "text": "项目经理1名，须具备机电工程一级注册建造师资格。"},
        {"id": "format", "text": "投标文件须按格式签字盖章后上传。"},
        {"id": "background", "text": "本项目背景介绍用于说明建设必要性，不构成投标文件编写要求。"},
    ]

    requirements = extract_requirements_from_source_chunks(chunks)

    active_topics = {
        req.source_metadata.get("constraint_subtype")
        for req in requirements
        if not req.ignored_for_pricing
    }
    assert active_topics <= {"qualification_certificate", "personnel_count", "signature_seal"}
    assert {req.source_chunk_id for req in requirements} == {"qualification", "personnel", "format"}
    assert chunks[0]["extraction_metadata"]["ignored_reason"] == "pricing_only"
    assert chunks[-1]["extraction_metadata"]["ignored_reason"] == "background_only"


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


def test_legacy_extraction_scope_policy_sets_rollback_marker(monkeypatch):
    monkeypatch.setenv("EXTRACTION_SCOPE_POLICY", "legacy")

    requirements = extract_requirements_from_source_chunks(
        [
            {
                "id": "chunk-1",
                "source_file": "招标文件.docx",
                "source_locator": "p11",
                "text": "投标人须具备电力工程施工总承包二级及以上资质。",
            }
        ]
    )

    assert requirements[0].source_metadata["extraction_mode_marker"] == "legacy_v0"
