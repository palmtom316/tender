from __future__ import annotations

import pytest


_MUST_HAVE_CLAUSE_NOS = {
    "4.1.2",
    "4.2.4",
    "4.12.1",
    "5.3.6",
    "A.0.2",
}
_MIN_TOTAL_CLAUSES = 370

_CURRENT_BASELINE_SNAPSHOT = {
    "status": "completed",
    "total_clauses": 140,
    "normative": 12,
    "commentary": 128,
    "incomplete_page_anchor_count": 140,
    "table_clause_count": 4,
    "clause_nos": {"4.8.1", "5.2.1"},
}


def assert_gb50148_persisted_acceptance(snapshot: dict) -> None:
    assert snapshot["status"] == "completed", snapshot
    assert snapshot["total_clauses"] >= _MIN_TOTAL_CLAUSES, snapshot
    assert snapshot["normative"] > 0, snapshot
    assert snapshot["commentary"] > 0, snapshot
    assert snapshot["table_clause_count"] > 0, snapshot
    assert snapshot["incomplete_page_anchor_count"] == 0, snapshot

    clause_nos = {str(value).strip() for value in snapshot.get("clause_nos", set()) if value}
    missing_clause_nos = sorted(_MUST_HAVE_CLAUSE_NOS - clause_nos)
    assert not missing_clause_nos, missing_clause_nos


def test_gb50148_persisted_baseline_snapshot_fails_acceptance_threshold() -> None:
    with pytest.raises(AssertionError):
        assert_gb50148_persisted_acceptance(_CURRENT_BASELINE_SNAPSHOT)


def test_gb50148_persisted_acceptance_passes_for_target_shape() -> None:
    assert_gb50148_persisted_acceptance(
        {
            "status": "completed",
            "total_clauses": 373,
            "normative": 317,
            "commentary": 56,
            "incomplete_page_anchor_count": 0,
            "table_clause_count": 4,
            "clause_nos": _MUST_HAVE_CLAUSE_NOS,
        }
    )
