from __future__ import annotations

import json
from pathlib import Path

from tender_backend.services.norm_service.general_standard_parser import (
    parse_general_standard_document,
)


ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = ROOT / "backend/tests/fixtures/general_standard_parser_expected.json"


def _load_bundle(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_general_standard_parser_builds_clause_blocks_without_ai_credentials() -> None:
    expected = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["GB50150-2016"]
    bundle = _load_bundle(expected["bundle_path"])

    result = parse_general_standard_document(
        standard={
            "standard_code": "GB50150-2016",
            "standard_name": "电气装置安装工程电气设备交接试验标准",
        },
        document=bundle.get("document"),
        sections=bundle["sections"],
        tables=bundle["tables"],
    )

    clause_like_blocks = [
        block
        for block in result.blocks
        if block["block_type"] in {"clause", "appendix_clause", "commentary_clause"}
    ]
    clause_blocks = [block for block in clause_like_blocks if block["block_type"] == "clause"]
    clause_nos = {block["clause_no"] for block in clause_blocks}

    assert result.profile.code == "cn_gb"
    assert result.ai_required is False
    assert len(clause_like_blocks) >= expected["min_clause_count"]
    assert set(expected["must_have_clause_nos"]).issubset(clause_nos)
    assert result.metrics["anchor_coverage"] >= expected["min_anchor_coverage"]
    assert result.metrics["validation_issue_count"] <= expected["max_validation_issues"]
