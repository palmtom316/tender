"""Integration test for requirement extraction and confirmation flow.

Tests the extraction service and repository without live DB/AI connections.
"""

from __future__ import annotations

import asyncio

import pytest

from tender_backend.services.extract_service.requirements_extractor import (
    extract_requirements,
    REQUIREMENT_CATEGORIES,
)
from tender_backend.services.extract_service.scoring_extractor import extract_scoring_criteria


def test_requirement_categories_defined():
    assert "veto" in REQUIREMENT_CATEGORIES
    assert "scoring" in REQUIREMENT_CATEGORIES
    assert "format" in REQUIREMENT_CATEGORIES


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
