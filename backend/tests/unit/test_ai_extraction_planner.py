from __future__ import annotations

from uuid import uuid4

from tender_backend.services.extract_service.ai_extraction_planner import (
    STRATEGY_VERSION,
    TASK_TYPE,
    build_extraction_batch_plan,
)


def _chunk(*, source_file: str, text: str, document_type: str = "unclassified", sort_order: int = 0):
    return {
        "id": uuid4(),
        "source_file": source_file,
        "tender_document_file_id": uuid4(),
        "document_type": document_type,
        "text": text,
        "sort_order": sort_order,
    }


def test_planner_assigns_every_extractable_chunk_to_pending_batch() -> None:
    chunks = [
        _chunk(source_file="采购文件（服务）.docx", text="投标人应满足资格要求", document_type="tender_document", sort_order=1),
        _chunk(source_file="采购文件（服务）.docx", text="技术响应要求", document_type="tender_document", sort_order=2),
    ]

    plans = build_extraction_batch_plan(chunks)

    assert len(plans) == 1
    plan = plans[0]
    assert plan.status == "pending"
    assert plan.model == "deepseek-v4-flash"
    assert plan.reasoning_effort is None
    assert plan.quality_policy == "table_or_critical_extract"
    assert set(plan.chunk_ids) == {str(chunk["id"]) for chunk in chunks}
    assert plan.metadata_json["high_value"] is True
    assert plan.metadata_json["direct_pro"] is False
    assert plan.metadata_json["strategy_version"] == STRATEGY_VERSION
    assert plan.metadata_json["task_type"] == TASK_TYPE
    assert plan.metadata_json["thinking_enabled"] is False
    assert plan.metadata_json["stage"] == "primary"


def test_planner_skips_known_blank_contract_template_with_reason() -> None:
    chunks = [_chunk(source_file="合同条款（空白）.docx", text=" ", document_type="contract")]

    plans = build_extraction_batch_plan(chunks)

    assert len(plans) == 1
    assert plans[0].status == "skipped"
    assert plans[0].skip_reason == "known_blank_contract_template"


def test_planner_uses_flash_for_low_value_files() -> None:
    chunks = [_chunk(source_file="附件8：价格公式、参数及权重.xlsx", text="公式参数", document_type="unclassified")]

    plans = build_extraction_batch_plan(chunks)

    assert len(plans) == 1
    assert plans[0].status == "pending"
    assert plans[0].model == "deepseek-v4-flash"
    assert plans[0].reasoning_effort is None
    assert plans[0].quality_policy == "fast_prefilter"
    assert plans[0].metadata_json["task_type"] == TASK_TYPE
    assert plans[0].metadata_json["next_quality_policy"] == "flash_extract"


def test_planner_uses_pro_high_for_small_scoring_file() -> None:
    chunks = [
        _chunk(source_file="附件6：商务评分细则.xlsx", text="评分项 满分 投标报价", document_type="scoring_sheet", sort_order=0),
        _chunk(source_file="附件6：商务评分细则.xlsx", text="业绩 资质 人员", document_type="spreadsheet", sort_order=1),
    ]

    plans = build_extraction_batch_plan(chunks)

    assert len(plans) == 1
    assert plans[0].status == "pending"
    assert plans[0].model == "deepseek-v4-pro"
    assert plans[0].reasoning_effort == "high"
    assert plans[0].quality_policy == "pro_review"
    assert plans[0].metadata_json["high_value"] is True
    assert plans[0].metadata_json["direct_pro"] is True
    assert plans[0].metadata_json["task_type"] == TASK_TYPE
    assert plans[0].metadata_json["thinking_enabled"] is True


def test_planner_keeps_delivery_instruction_sheet_on_flash() -> None:
    chunks = [
        _chunk(
            source_file="附件10：技术投标文件制作及递交要求.xlsx",
            text="技术文件制作要求详见分类说明，按分类递交。",
            document_type="spreadsheet",
            sort_order=0,
        )
    ]

    plans = build_extraction_batch_plan(chunks)

    assert len(plans) == 1
    assert plans[0].model == "deepseek-v4-flash"
    assert plans[0].reasoning_effort is None
    assert plans[0].quality_policy == "table_or_critical_extract"
    assert plans[0].metadata_json["direct_pro"] is False


def test_planner_keeps_large_tender_document_on_flash() -> None:
    chunks = [
        _chunk(
            source_file="国网重庆采购文件（施工）.docx",
            text="技术要求和投标文件组成 " * 200,
            document_type="tender_document",
            sort_order=index,
        )
        for index in range(30)
    ]

    plans = build_extraction_batch_plan(chunks)

    assert plans
    assert all(plan.model == "deepseek-v4-flash" for plan in plans)
    assert all(plan.reasoning_effort is None for plan in plans)
    assert all(plan.quality_policy == "table_or_critical_extract" for plan in plans)
    assert all(plan.metadata_json["high_value"] is True for plan in plans)
    assert all(plan.metadata_json["direct_pro"] is False for plan in plans)


def test_planner_splits_large_flash_file_by_flash_chunk_cap() -> None:
    chunks = [
        _chunk(
            source_file="大型采购文件.docx",
            text="通用条款 " * 10,
            document_type="tender_document",
            sort_order=index,
        )
        for index in range(250)
    ]

    plans = build_extraction_batch_plan(chunks)

    assert len(plans) == 11
    assert [plan.chunk_count for plan in plans] == [24, 24, 24, 24, 24, 24, 24, 24, 24, 24, 10]
    assert all(plan.model == "deepseek-v4-flash" for plan in plans)
    assert all(plan.quality_policy == "table_or_critical_extract" for plan in plans)
