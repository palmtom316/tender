"""Unit tests for the canonical MinerU payload normalizer.

These fixtures mirror the REAL MinerU 2.7.6 (VLM/hybrid backend) output
shape as observed in `MinerU_GB50147_2010__20260418120949.json`.

Reference doc: `docs/superpowers/plans/2026-04-18-mineru-new-output-compatibility-plan-revision.md`
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tender_backend.services.parse_service.mineru_normalizer import (
    normalize_mineru_payload,
)


# ── § 2.1 / Task 1 base fixtures ──

def test_converts_pdf_info_para_blocks_to_canonical_pages() -> None:
    payload = {
        "_backend": "hybrid",
        "_version_name": "2.7.6",
        "pdf_info": [
            {
                "page_idx": 0,
                "para_blocks": [
                    {
                        "type": "title",
                        "lines": [{"spans": [{"content": "1 总则", "type": "text"}]}],
                    },
                    {
                        "type": "text",
                        "lines": [{"spans": [{"content": "正文内容", "type": "text"}]}],
                    },
                ],
            }
        ],
    }

    normalized = normalize_mineru_payload(payload)

    assert normalized["parser_version"] == "2.7.6"
    assert normalized["pages"] == [{"page_number": 1, "markdown": "1 总则\n正文内容"}]
    assert normalized["tables"] == []
    assert normalized["full_markdown"] == "1 总则\n正文内容"


def test_collects_table_blocks_into_canonical_tables_with_nested_shape() -> None:
    """Real MinerU table blocks nest table_caption + table_body as sub-blocks,
    with the HTML living on a `type=table` span inside table_body.lines[0].spans[0].html.
    """
    table_block = {
        "type": "table",
        "bbox": [44, 442, 342, 517],
        "index": 15,
        "blocks": [
            {
                "type": "table_caption",
                "lines": [
                    {"spans": [{"content": "表1 参数", "type": "text"}]}
                ],
            },
            {
                "type": "table_body",
                "lines": [
                    {
                        "spans": [
                            {
                                "type": "table",
                                "html": "<table><tr><td>A</td></tr></table>",
                                "image_path": "https://cdn-mineru.openxlab.org.cn/x.jpg",
                            }
                        ]
                    }
                ],
            },
        ],
    }
    payload = {
        "_backend": "vlm",
        "pdf_info": [{"page_idx": 1, "para_blocks": [table_block]}],
    }

    normalized = normalize_mineru_payload(payload)

    assert normalized["tables"] == [
        {
            "page_start": 2,
            "page_end": 2,
            "table_title": "表1 参数",
            "table_html": "<table><tr><td>A</td></tr></table>",
            "table_image_path": "https://cdn-mineru.openxlab.org.cn/x.jpg",
            "raw_json": table_block,
        }
    ]
    # table 内容不应泄入 markdown
    assert normalized["pages"] == []


# ── § 2.2 new coverage ──

def test_recurses_into_list_block_children() -> None:
    payload = {
        "pdf_info": [
            {
                "page_idx": 2,
                "para_blocks": [
                    {
                        "type": "list",
                        "sub_type": "text",
                        "blocks": [
                            {
                                "type": "text",
                                "lines": [
                                    {"spans": [{"content": "1. 第一项", "type": "text"}]}
                                ],
                            },
                            {
                                "type": "text",
                                "lines": [
                                    {"spans": [{"content": "2. 第二项", "type": "text"}]}
                                ],
                            },
                            {
                                "type": "ref_text",
                                "lines": [
                                    {"spans": [{"content": "见 GB 50147", "type": "text"}]}
                                ],
                            },
                        ],
                    }
                ],
            }
        ]
    }

    normalized = normalize_mineru_payload(payload)

    assert normalized["pages"] == [
        {"page_number": 3, "markdown": "1. 第一项\n2. 第二项\n见 GB 50147"}
    ]


def test_preserves_inline_equation_as_dollar_wrapped_latex() -> None:
    payload = {
        "pdf_info": [
            {
                "page_idx": 0,
                "para_blocks": [
                    {
                        "type": "text",
                        "lines": [
                            {
                                "spans": [
                                    {"content": "压力达到 ", "type": "text"},
                                    {"content": "500\\mathrm{kV}", "type": "inline_equation"},
                                    {"content": " 时", "type": "text"},
                                ]
                            }
                        ],
                    }
                ],
            }
        ]
    }

    normalized = normalize_mineru_payload(payload)

    assert normalized["pages"] == [
        {"page_number": 1, "markdown": "压力达到 $500\\mathrm{kV}$ 时"}
    ]


def test_preserves_interline_equation_as_block_dollar_wrap() -> None:
    payload = {
        "pdf_info": [
            {
                "page_idx": 0,
                "para_blocks": [
                    {
                        "type": "interline_equation",
                        "lines": [
                            {
                                "spans": [
                                    {"content": "E = mc^2", "type": "interline_equation"}
                                ]
                            }
                        ],
                    }
                ],
            }
        ]
    }

    normalized = normalize_mineru_payload(payload)

    # 块级公式独占段落
    assert normalized["pages"][0]["markdown"].strip() == "$$E = mc^2$$"


def test_skips_discarded_blocks_like_page_numbers_and_footers() -> None:
    payload = {
        "pdf_info": [
            {
                "page_idx": 0,
                "discarded_blocks": [
                    {
                        "type": "page_number",
                        "lines": [{"spans": [{"content": "1", "type": "text"}]}],
                    },
                    {
                        "type": "footer",
                        "lines": [
                            {"spans": [{"content": "版权所有", "type": "text"}]}
                        ],
                    },
                ],
                "para_blocks": [
                    {
                        "type": "text",
                        "lines": [{"spans": [{"content": "正文内容", "type": "text"}]}],
                    }
                ],
            }
        ]
    }

    normalized = normalize_mineru_payload(payload)

    assert normalized["pages"] == [{"page_number": 1, "markdown": "正文内容"}]
    assert "1" not in normalized["full_markdown"]
    assert "版权所有" not in normalized["full_markdown"]


def test_handles_empty_pages_without_emitting_empty_page_objects() -> None:
    payload = {
        "pdf_info": [
            {"page_idx": 0, "para_blocks": []},
            {
                "page_idx": 1,
                "para_blocks": [
                    {
                        "type": "text",
                        "lines": [{"spans": [{"content": "仅此一页", "type": "text"}]}],
                    }
                ],
            },
        ]
    }

    normalized = normalize_mineru_payload(payload)

    assert normalized["pages"] == [{"page_number": 2, "markdown": "仅此一页"}]


def test_rejects_unknown_backend() -> None:
    payload = {"_backend": "pipeline", "pdf_info": []}

    with pytest.raises(ValueError, match="Unsupported MinerU backend"):
        normalize_mineru_payload(payload)


def test_allows_hybrid_and_vlm_backend() -> None:
    for backend in ("hybrid", "vlm", None):
        payload = {"pdf_info": []} if backend is None else {"_backend": backend, "pdf_info": []}
        normalize_mineru_payload(payload)  # should not raise


# ── § 5 end-to-end acceptance against real local sample (opt-in) ──

_REAL_SAMPLE = Path(
    "/Users/palmtom/Downloads/MinerU_GB50147 2010 电气装置安装工程 高压电器施工及验收规范__20260418120949.json"
)


@pytest.mark.skipif(
    not _REAL_SAMPLE.exists() or os.environ.get("SKIP_MINERU_SAMPLE") == "1",
    reason="real MinerU 2.7.6 sample unavailable in this environment",
)
def test_normalize_against_real_gb50147_sample() -> None:
    with _REAL_SAMPLE.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    normalized = normalize_mineru_payload(payload)

    assert normalized["parser_version"] == "2.7.6"
    # 107 页中有若干为纯空白/页码/页脚，规范化后应至少保留 95 页
    assert len(normalized["pages"]) >= 95, len(normalized["pages"])
    assert len(normalized["tables"]) == 7, len(normalized["tables"])
    for table in normalized["tables"]:
        assert table["table_html"].startswith("<table"), table
        assert isinstance(table["page_start"], int) and table["page_start"] >= 1
    # Threshold sits below the revision §5 target of 60_000 because here we
    # only feed `middle.json` to the normalizer, so `full_markdown` is
    # reassembled from `para_blocks` (discarded blocks like page numbers and
    # footers are dropped). In the standards pipeline `_parse_via_mineru`
    # injects the zip's `full.md` (~64k chars) into `middle_json["full_markdown"]`,
    # which preserves the original content end-to-end.
    assert len(normalized["full_markdown"]) > 50_000
