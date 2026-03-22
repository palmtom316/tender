"""Unit tests for vision_service.page_merger."""

from __future__ import annotations

from tender_backend.services.vision_service.page_merger import merge_page_results


def _clause(
    clause_no: str,
    text: str,
    page: int,
    *,
    is_continuation: bool = False,
    continuation_clause_no: str | None = None,
    clause_type: str = "normative",
    children: list | None = None,
) -> dict:
    entry: dict = {
        "node_type": "clause",
        "clause_no": clause_no,
        "clause_title": "",
        "clause_text": text,
        "summary": f"summary of {clause_no}",
        "tags": [],
        "page_start": page,
        "page_end": page,
        "clause_type": clause_type,
        "children": children or [],
    }
    if is_continuation:
        entry["is_continuation"] = True
        entry["continuation_clause_no"] = continuation_clause_no or clause_no
    return entry


class TestMergePageResults:
    def test_no_continuations(self):
        pages = [
            (1, [_clause("1.1", "text A", 1)]),
            (2, [_clause("1.2", "text B", 2)]),
        ]
        result = merge_page_results(pages)
        assert len(result) == 2
        assert result[0]["clause_no"] == "1.1"
        assert result[1]["clause_no"] == "1.2"

    def test_simple_continuation(self):
        pages = [
            (1, [_clause("3.1", "start of clause", 1)]),
            (2, [_clause("3.1", "end of clause", 2, is_continuation=True, continuation_clause_no="3.1")]),
        ]
        result = merge_page_results(pages)
        assert len(result) == 1
        assert "start of clause" in result[0]["clause_text"]
        assert "end of clause" in result[0]["clause_text"]
        assert result[0]["page_start"] == 1
        assert result[0]["page_end"] == 2

    def test_three_page_continuation(self):
        pages = [
            (1, [_clause("5.1", "part 1", 1)]),
            (2, [_clause("5.1", "part 2", 2, is_continuation=True, continuation_clause_no="5.1")]),
            (3, [_clause("5.1", "part 3", 3, is_continuation=True, continuation_clause_no="5.1")]),
        ]
        result = merge_page_results(pages)
        assert len(result) == 1
        assert "part 1" in result[0]["clause_text"]
        assert "part 2" in result[0]["clause_text"]
        assert "part 3" in result[0]["clause_text"]
        assert result[0]["page_end"] == 3

    def test_orphan_continuation_kept_as_standalone(self):
        pages = [
            (2, [_clause("X.1", "orphan text", 2, is_continuation=True, continuation_clause_no="X.1")]),
        ]
        result = merge_page_results(pages)
        assert len(result) == 1
        assert result[0]["clause_text"] == "orphan text"

    def test_empty_pages_skipped(self):
        pages = [
            (1, [_clause("1.1", "text", 1)]),
            (2, []),
            (3, [_clause("1.2", "more text", 3)]),
        ]
        result = merge_page_results(pages)
        assert len(result) == 2

    def test_mixed_continuation_and_new(self):
        pages = [
            (1, [_clause("2.1", "clause 2.1 start", 1)]),
            (2, [
                _clause("2.1", "clause 2.1 end", 2, is_continuation=True, continuation_clause_no="2.1"),
                _clause("2.2", "new clause 2.2", 2),
            ]),
        ]
        result = merge_page_results(pages)
        assert len(result) == 2
        assert result[0]["clause_no"] == "2.1"
        assert "clause 2.1 start" in result[0]["clause_text"]
        assert "clause 2.1 end" in result[0]["clause_text"]
        assert result[1]["clause_no"] == "2.2"

    def test_continuation_fields_stripped(self):
        pages = [
            (1, [_clause("1.1", "text", 1)]),
        ]
        result = merge_page_results(pages)
        assert "is_continuation" not in result[0]
        assert "continuation_clause_no" not in result[0]

    def test_children_merged_on_continuation(self):
        pages = [
            (1, [_clause("4.1", "base", 1, children=[{"node_type": "item", "clause_text": "item A"}])]),
            (2, [_clause("4.1", "cont", 2, is_continuation=True, continuation_clause_no="4.1",
                         children=[{"node_type": "item", "clause_text": "item B"}])]),
        ]
        result = merge_page_results(pages)
        assert len(result) == 1
        assert len(result[0]["children"]) == 2

    def test_unsorted_pages_handled(self):
        """Pages can arrive out of order (from concurrent processing)."""
        pages = [
            (3, [_clause("1.3", "page 3", 3)]),
            (1, [_clause("1.1", "page 1", 1)]),
            (2, [_clause("1.2", "page 2", 2)]),
        ]
        result = merge_page_results(pages)
        assert len(result) == 3
        # Should be in page order after sorting
        assert result[0]["page_start"] == 1
        assert result[1]["page_start"] == 2
        assert result[2]["page_start"] == 3
