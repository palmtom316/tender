from __future__ import annotations

from tender_backend.services.norm_service.prompt_builder import (
    build_task_mode_prompt,
    build_clause_enrichment_batch_prompt,
    build_standard_parse_audit_prompt,
    build_unparsed_block_repair_prompt,
    prompt_mode_task_type,
)


def test_build_standard_parse_audit_prompt_is_patch_oriented() -> None:
    prompt = build_standard_parse_audit_prompt(
        document_outline=[{"clause_no": "3", "title": "变压器"}],
        deterministic_blocks=[{"block_id": "b1", "source_ref": "document_section:1"}],
        ast_summary=[{"node_key": "3.1.1", "clause_no": "3.1.1"}],
        validation_issues=[{"code": "numbering.gap", "clause_no": "3.1.2"}],
    )

    assert "Do not extract the document from scratch" in prompt
    assert "node_key" in prompt
    assert "source_ref" in prompt
    assert "needs_review" in prompt
    assert "numbering.gap" in prompt


def test_build_clause_enrichment_batch_prompt_forbids_structural_changes() -> None:
    prompt = build_clause_enrichment_batch_prompt([
        {
            "node_key": "3.1.1",
            "clause_no": "3.1.1",
            "clause_text": "变压器安装应符合设计要求。",
            "source_refs": ["document_section:1"],
        }
    ])

    assert "must not add, remove, split, merge, or renumber clauses" in prompt
    assert "requirement_type" in prompt
    assert "mandatory_terms" in prompt
    assert "3.1.1" in prompt


def test_build_unparsed_block_repair_prompt_returns_patch_contract() -> None:
    prompt = build_unparsed_block_repair_prompt({
        "source_ref": "document_section:2",
        "text": "3.1.1 设备安装应牢固。",
        "confidence": "low",
    })

    assert "patch|needs_review|no_change" in prompt
    assert "split_clause|attach_item|normalize_table" in prompt
    assert "document_section:2" in prompt


def test_prompt_modes_map_to_flash_only_task_profiles() -> None:
    assert prompt_mode_task_type("summarize_tags") == "clause_enrichment_batch"
    assert prompt_mode_task_type("classify_requirement") == "clause_enrichment_batch"
    assert prompt_mode_task_type("repair_unparsed_block") == "unparsed_block_repair"
    assert prompt_mode_task_type("normalize_table_requirement") == "unparsed_block_repair"
    assert prompt_mode_task_type("whole_document_consistency") == "standard_parse_audit"


def test_task_mode_prompt_builders_do_not_use_legacy_extraction_contract() -> None:
    prompt = build_task_mode_prompt(
        "summarize_tags",
        clause_nodes=[{"node_key": "3.1.1", "clause_no": "3.1.1", "clause_text": "应符合要求。"}],
    )

    assert "must not add, remove, split, merge, or renumber" in prompt
    assert "建筑工程规范条款提取助手" not in prompt
