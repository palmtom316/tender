from __future__ import annotations

import pytest


_MUST_HAVE_CLAUSE_NOS = {
    "4.1.2",
    "4.2.4",
    "4.12.1",
    "5.3.6",
    "A.0.2",
}
_MUST_HAVE_TABLE_TITLE = "表 4.2.4 变压器内油样性能"
_MIN_TOTAL_CLAUSES = 370

_CURRENT_BASELINE_SUMMARY = {
    "status": "completed",
    "total_clauses": 360,
    "normative": 311,
    "commentary": 49,
}

_CURRENT_BASELINE_CLAUSES = [
    {"clause_no": "4.1.2", "clause_type": "normative", "source_type": "text"},
    {"clause_no": "4.2.4", "clause_type": "normative", "source_type": "text"},
    {"clause_no": "4.12.1", "clause_type": "normative", "source_type": "text"},
    {"clause_no": "5.3.6", "clause_type": "normative", "source_type": "text"},
    {"clause_no": "A.0.2", "clause_type": "normative", "source_type": "text"},
    {"clause_no": None, "clause_type": "commentary", "source_type": "text"},
    {"clause_no": None, "clause_type": "normative", "source_type": "table"},
]

_CURRENT_BASELINE_TABLES = [
    {"table_title": "表 4.2.4 变压器内油样性能", "page_start": 18, "page_end": 18},
]


def assert_gb50148_acceptance(summary: dict, clauses: list[dict], tables: list[dict]) -> None:
    assert summary["status"] == "completed", summary
    assert summary["total_clauses"] >= _MIN_TOTAL_CLAUSES, summary

    clause_nos = {str(clause["clause_no"]).strip() for clause in clauses if clause["clause_no"]}
    missing_clause_nos = sorted(_MUST_HAVE_CLAUSE_NOS - clause_nos)
    assert not missing_clause_nos, missing_clause_nos

    assert summary["normative"] > 0, summary
    assert summary["commentary"] > 0, summary

    table_titles = {
        str(table["table_title"]).strip()
        for table in tables
        if table["table_title"]
    }
    assert _MUST_HAVE_TABLE_TITLE in table_titles, sorted(table_titles)

    table_clauses = [clause for clause in clauses if clause["source_type"] == "table"]
    assert table_clauses, "expected at least one table-derived clause"


def test_gb50148_baseline_snapshot_fails_acceptance_threshold() -> None:
    with pytest.raises(AssertionError):
        assert_gb50148_acceptance(
            _CURRENT_BASELINE_SUMMARY,
            _CURRENT_BASELINE_CLAUSES,
            _CURRENT_BASELINE_TABLES,
        )


def test_gb50148_acceptance_passes_for_target_shape() -> None:
    assert_gb50148_acceptance(
        {
            "status": "completed",
            "total_clauses": 373,
            "normative": 317,
            "commentary": 56,
        },
        _CURRENT_BASELINE_CLAUSES,
        _CURRENT_BASELINE_TABLES,
    )
