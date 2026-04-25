from __future__ import annotations

from uuid import uuid4

from tender_backend.services.norm_service.document_assets import DocumentAsset, PageAsset
from tender_backend.services.norm_service import norm_processor
from tender_backend.services.norm_service.parse_profiles import CN_GB_PROFILE
from tender_backend.services.norm_service.profile_resolver import (
    resolve_standard_profile,
)


def _asset_with_text(text: str) -> DocumentAsset:
    return DocumentAsset(
        document_id=uuid4(),
        parser_name="mineru",
        parser_version="test",
        raw_payload={},
        pages=[
            PageAsset(
                page_number=1,
                normalized_text=text,
                raw_page=None,
                source_ref="document.raw_payload.pages[0]",
            )
        ],
        tables=[],
        full_markdown=text,
    )


def test_resolve_standard_profile_uses_cn_gb_for_gb_codes() -> None:
    profile = resolve_standard_profile(
        {"standard_code": "GB 50150-2016"},
        _asset_with_text("1.0.1 为适应电气装置安装工程电气设备交接试验的需要，制定本标准。"),
    )

    assert profile.code == "cn_gb"
    assert profile.table_requirement_strategy == "parameter_limit_table"
    assert any(pattern.match("1.0.1") for pattern in profile.clause_heading_patterns)
    assert any(pattern.match("A.0.1") for pattern in profile.appendix_heading_patterns)
    assert any(pattern.match("1") for pattern in profile.list_item_patterns)
    assert profile.quality_thresholds["min_anchor_coverage"] >= 0.95


def test_resolve_standard_profile_detects_synthetic_enterprise_profile() -> None:
    profile = resolve_standard_profile(
        {"standard_code": "Q/ACME-001"},
        _asset_with_text("REQ-001 Equipment shall pass factory acceptance testing."),
    )

    assert profile.code == "generic_enterprise"
    assert any(pattern.match("REQ-001") for pattern in profile.clause_heading_patterns)
    assert profile.table_requirement_strategy == "generic_table"


def test_block_path_decision_uses_profile_capability_not_specific_standard_id() -> None:
    assert norm_processor._should_use_single_standard_block_path(CN_GB_PROFILE) is True
