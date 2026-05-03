from __future__ import annotations

import asyncio
from uuid import uuid4

from tender_backend.services.extract_service.scoring_extractor import extract_scoring_criteria_from_source_chunks


def test_extract_scoring_criteria_from_source_chunks_preserves_source_refs() -> None:
    chunk_id = uuid4()
    chunks = [
        {
            "id": chunk_id,
            "chunk_type": "table",
            "source_file": "附件7：技术评分细则.xlsx",
            "source_locator": "sheet:技术评分",
            "page_start": None,
            "table_json": {
                "headers": ["评分项", "分值", "评分方法"],
                "rows": [["施工组织", "20", "按方案合理性评分"]],
            },
        }
    ]

    results = asyncio.run(extract_scoring_criteria_from_source_chunks(chunks))

    assert len(results) == 1
    assert results[0].dimension == "施工组织"
    assert results[0].max_score == 20.0
    assert results[0].source_chunk_id == str(chunk_id)
    assert results[0].source_file == "附件7：技术评分细则.xlsx"
    assert results[0].source_locator == "sheet:技术评分"
    assert results[0].to_repository_dict()["extraction_method"] == "rule"
