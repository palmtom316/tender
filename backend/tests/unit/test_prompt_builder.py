from __future__ import annotations

from tender_backend.services.norm_service.prompt_builder import (
    build_clause_enrichment_batch_prompt,
    build_standard_parse_audit_prompt,
    build_unparsed_block_repair_prompt,
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
