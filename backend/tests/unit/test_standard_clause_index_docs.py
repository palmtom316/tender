from __future__ import annotations

from uuid import uuid4

from tender_backend.tools.reindex_standard_clauses import build_clause_index_docs


def test_build_clause_index_docs_includes_viewer_fields() -> None:
    docs = build_clause_index_docs(
        {
            "id": uuid4(),
            "standard_code": "GB 50010",
            "standard_name": "混凝土结构设计规范",
            "specialty": "结构",
        },
        [
            {
                "id": uuid4(),
                "clause_no": "3.2.1",
                "node_type": "item",
                "node_key": "3.2.1#1",
                "node_label": "1",
                "clause_title": "材料要求",
                "clause_text": "混凝土强度等级不应低于 C30。",
                "summary": "规定混凝土最低强度等级。",
                "tags": ["结构", "混凝土"],
                "page_start": 15,
                "page_end": 16,
            }
        ],
    )

    _, body = docs[0]
    assert body["standard_name"] == "混凝土结构设计规范"
    assert body["node_type"] == "item"
    assert body["node_key"] == "3.2.1#1"
    assert body["node_label"] == "1"
    assert body["page_start"] == 15
    assert body["page_end"] == 16
