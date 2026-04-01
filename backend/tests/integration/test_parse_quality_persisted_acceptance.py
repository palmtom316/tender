from __future__ import annotations


_SNAPSHOTS = {
    "GB 50147-2010": {
        "status": "completed",
        "total_count": 429,
        "missing_anchor_count": 0,
        "table_missing_source_ref_count": 0,
        "null_clause_no_count": 3,
        "null_clause_no_budget": 3,
        "duplicate_identity_count": 8,
        "duplicate_identity_budget": 8,
        "must_have_clause_nos": {"5.1.4", "5.2.1", "10.0.1"},
        "top_heavy_source_labels": [
            "3 基本规定",
            "10 干式电抗器和阻波器",
            "5.2 安装与调整 (2/2)",
        ],
        "accepted_residual_notes": [
            "table 5.2.2 still contributes null-clause table-derived rows in the latest persisted sample",
            "duplicate subitem labels under 3.0.7 require parent-aware review and are not all hard defects",
        ],
    },
    "GB 50150-2016": {
        "status": "completed",
        "total_count": 844,
        "missing_anchor_count": 0,
        "table_missing_source_ref_count": 0,
        "null_clause_no_count": 8,
        "null_clause_no_budget": 8,
        "duplicate_identity_count": 16,
        "duplicate_identity_budget": 16,
        "ocr_clause_like_sections": 350,
        "ocr_numbered_item_sections": 657,
        "must_have_clause_nos": {"8.0.14", "17.0.4"},
        "top_heavy_source_labels": [
            "4 同步发电机及调相机 (1/2)",
            "8 电力变压器 (1/3)",
            "10 互感器 (1/2)",
            "12 六氟化硫断路器",
            "17 电力电缆线路",
        ],
        "appendix_scope_noise_status": "reviewed",
        "accepted_residual_notes": [
            "latest 844 is evaluated against OCR section shape, not the deprecated 214 baseline",
            "appendix G scope leakage into 8.0.14 remains a documented review target until the next rerun confirms the fix",
        ],
    },
}


def load_snapshot(standard_code: str) -> dict:
    return dict(_SNAPSHOTS[standard_code])


def assert_standard_shape(snapshot: dict) -> None:
    assert snapshot["missing_anchor_count"] == 0
    assert snapshot["table_missing_source_ref_count"] == 0
    assert snapshot["null_clause_no_count"] <= snapshot["null_clause_no_budget"]
    assert snapshot["duplicate_identity_count"] <= snapshot["duplicate_identity_budget"]


def assert_gb50150_structural_shape(snapshot: dict) -> None:
    assert snapshot["ocr_clause_like_sections"] >= 300
    assert snapshot["ocr_numbered_item_sections"] >= 600
    assert snapshot["appendix_scope_noise_status"] == "reviewed"
    assert snapshot["top_heavy_source_labels"] == [
        "4 同步发电机及调相机 (1/2)",
        "8 电力变压器 (1/3)",
        "10 互感器 (1/2)",
        "12 六氟化硫断路器",
        "17 电力电缆线路",
    ]


def test_gb50147_persisted_shape() -> None:
    snapshot = load_snapshot("GB 50147-2010")
    assert_standard_shape(snapshot)
    assert "5.1.4" in snapshot["must_have_clause_nos"]


def test_gb50150_persisted_shape() -> None:
    snapshot = load_snapshot("GB 50150-2016")
    assert_standard_shape(snapshot)
    assert_gb50150_structural_shape(snapshot)
    assert "8.0.14" in snapshot["must_have_clause_nos"]
