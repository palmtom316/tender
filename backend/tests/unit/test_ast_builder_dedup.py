from __future__ import annotations

from uuid import uuid4

from tender_backend.services.norm_service.ast_builder import (
    build_clause_ast,
    deduplicate_entries,
)


def test_deduplicate_entries_keeps_entries_with_different_source_labels() -> None:
    """Two clauses sharing clause_no but from different sections must both survive."""
    entries = [
        {
            "clause_no": "1.0.1",
            "clause_text": "章节 1 的首条",
            "source_label": "1 总则",
        },
        {
            "clause_no": "1.0.1",
            "clause_text": "附录 A 的首条",
            "source_label": "附录A 不需干燥的条件",
        },
    ]

    deduped = deduplicate_entries(entries)

    assert len(deduped) == 2
    assert {e["clause_text"] for e in deduped} == {"章节 1 的首条", "附录 A 的首条"}


def test_deduplicate_entries_still_drops_true_duplicates_with_same_source_label() -> None:
    entries = [
        {
            "clause_no": "3.0.1",
            "clause_text": "第一遍",
            "source_label": "3 基本规定",
        },
        {
            "clause_no": "3.0.1",
            "clause_text": "第二遍",
            "source_label": "3 基本规定",
        },
    ]

    deduped = deduplicate_entries(entries)

    assert len(deduped) == 1
    assert deduped[0]["clause_text"] == "第一遍"


def test_deduplicate_entries_preserves_legacy_behavior_without_source_label() -> None:
    entries = [
        {"clause_no": "4.1.1", "clause_text": "A"},
        {"clause_no": "4.1.1", "clause_text": "B"},
    ]

    deduped = deduplicate_entries(entries)

    assert len(deduped) == 1
    assert deduped[0]["clause_text"] == "A"


def test_build_clause_ast_assigns_distinct_node_keys_when_source_labels_differ() -> None:
    standard_id = uuid4()

    roots = build_clause_ast(
        [
            {
                "clause_no": "A.0.1",
                "clause_text": "附录 A.0.1",
                "source_label": "附录A",
            },
            {
                "clause_no": "A.0.1",
                "clause_text": "另一处 A.0.1",
                "source_label": "附录B",
            },
        ],
        standard_id,
    )

    assert len(roots) == 2
    node_keys = {node.node_key for node in roots}
    assert len(node_keys) == 2, node_keys
    # Both keys must still start with the clause_no so downstream lookups work.
    assert all(key.startswith("A.0.1") for key in node_keys), node_keys


def test_build_clause_ast_keeps_bare_node_key_when_source_label_absent() -> None:
    """Backward-compat: entries without source_label still produce node_key == clause_no."""
    standard_id = uuid4()

    roots = build_clause_ast(
        [{"clause_no": "3.0.1", "clause_text": "总则一"}],
        standard_id,
    )

    assert len(roots) == 1
    assert roots[0].node_key == "3.0.1"
