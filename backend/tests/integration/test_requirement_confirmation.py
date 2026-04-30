"""Integration test for requirement extraction and confirmation flow.

Tests the extraction service and repository without live DB/AI connections.
"""

from __future__ import annotations

import asyncio

import pytest

from tender_backend.services.extract_service.requirements_extractor import (
    extract_requirements,
    extract_requirements_from_source_chunks,
    REQUIREMENT_CATEGORIES,
)
from tender_backend.services.extract_service.scoring_extractor import extract_scoring_criteria


def test_requirement_categories_defined():
    assert "veto" in REQUIREMENT_CATEGORIES
    assert "scoring" in REQUIREMENT_CATEGORIES
    assert "format" in REQUIREMENT_CATEGORIES
    assert "project_team" in REQUIREMENT_CATEGORIES
    assert "special" in REQUIREMENT_CATEGORIES


def test_extract_veto_requirement():
    sections = [
        {"title": "投标无效情形", "text": "以下情形将作废标处理：未提供营业执照", "page_start": 5},
    ]
    results = asyncio.run(extract_requirements(sections))
    veto = [r for r in results if r.category == "veto"]
    assert len(veto) >= 1
    assert "废标" in veto[0].source_text or "废标" in veto[0].title


def test_extract_qualification_requirement():
    sections = [
        {"title": "资质要求", "text": "投标人须具有建筑工程施工总承包资质", "page_start": 3},
    ]
    results = asyncio.run(extract_requirements(sections))
    quals = [r for r in results if r.category == "qualification"]
    assert len(quals) >= 1


def test_extract_core_constraints_from_source_chunks():
    chunks = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "chunk_type": "paragraph",
            "source_file": "招标文件.pdf",
            "source_locator": "page:5:block:1",
            "section_title": "专用资格要求",
            "text": "投标人须具有类似项目业绩，项目经理须提供证书和社保证明。",
            "page_start": 5,
            "page_end": 5,
        },
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "chunk_type": "paragraph",
            "source_file": "招标文件.pdf",
            "source_locator": "page:9:block:2",
            "section_title": "否决项",
            "text": "未按要求盖章的，按无效投标处理。",
            "page_start": 9,
            "page_end": 9,
        },
        {
            "id": "33333333-3333-3333-3333-333333333333",
            "chunk_type": "paragraph",
            "source_file": "报价说明.pdf",
            "source_locator": "page:2:block:1",
            "section_title": "最高限价",
            "text": "本项目最高限价为100万元，报价不得超过最高限价。",
            "page_start": 2,
            "page_end": 2,
        },
    ]

    results = extract_requirements_from_source_chunks(chunks)
    categories = {item.category for item in results}

    assert "performance" in categories
    assert "project_team" in categories
    assert "veto" in categories
    assert any(item.is_veto and item.requires_human_confirm for item in results)
    assert any(item.category == "veto" and item.is_hard_constraint for item in results)
    assert any(item.category == "performance" and item.is_hard_constraint for item in results)
    assert any(item.ignored_for_pricing for item in results)
    assert all(item.source_file and item.source_locator for item in results)


def test_extract_scoring_from_table():
    tables = [
        {
            "page": 12,
            "data": {
                "headers": ["评分项", "分值", "评分方法"],
                "rows": [
                    ["施工组织设计", "20", "根据方案合理性评分"],
                    ["人员配置", "15", "根据人员资历评分"],
                ],
            },
        }
    ]
    results = asyncio.run(extract_scoring_criteria(tables))
    assert len(results) == 2
    assert results[0].dimension == "施工组织设计"
    assert results[0].max_score == 20.0
    assert results[1].dimension == "人员配置"
