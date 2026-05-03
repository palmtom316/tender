from __future__ import annotations

from uuid import uuid4

from tender_backend.services.extract_service.ai_extraction_planner import build_extraction_batch_plan


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
    assert plan.model == "deepseek-v4-pro"
    assert plan.reasoning_effort == "max"
    assert set(plan.chunk_ids) == {str(chunk["id"]) for chunk in chunks}
    assert plan.metadata_json["high_value"] is True


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
