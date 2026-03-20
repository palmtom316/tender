"""Integration test for search service and synonym loading.

Tests synonym loading, index configuration, and workflow registration
without requiring a live OpenSearch instance.
"""

from __future__ import annotations

import pytest

from tender_backend.services.search_service.synonym_loader import load_synonyms, count_synonyms
from tender_backend.services.search_service.index_manager import (
    INDEX_SETTINGS,
    SECTION_INDEX_MAPPINGS,
    CLAUSE_INDEX_MAPPINGS,
)

# Import to trigger registration
import tender_backend.workflows.standard_ingestion  # noqa: F401
from tender_backend.workflows.registry import get_workflow, list_workflows


_SYNONYM_FIXTURE = """\
基坑开挖,土方开挖
管道安装,管线安装
路基施工,路基工程
涂料施工,油漆施工
安全文明施工,文明施工
"""

def _write_synonym_fixture(tmp_path) -> str:
    path = tmp_path / "synonyms.txt"
    path.write_text(_SYNONYM_FIXTURE, encoding="utf-8")
    return str(path)

def test_synonyms_file_counts_groups(tmp_path) -> None:
    count = count_synonyms(_write_synonym_fixture(tmp_path))
    assert count == 5


def test_synonyms_cover_key_categories(tmp_path) -> None:
    groups = load_synonyms(_write_synonym_fixture(tmp_path))
    all_terms = [term for group in groups for term in group]
    joined = " ".join(all_terms)
    assert "基坑开挖" in joined, "Missing civil engineering terms"
    assert "管道安装" in joined, "Missing MEP terms"
    assert "路基施工" in joined, "Missing municipal terms"
    assert "涂料施工" in joined, "Missing decoration terms"
    assert "安全文明施工" in joined, "Missing management terms"


def test_index_settings_use_ik_max_word():
    analyzer = INDEX_SETTINGS["settings"]["analysis"]["analyzer"]["cn_with_synonym"]
    assert analyzer["tokenizer"] == "ik_max_word"


def test_clause_index_has_synonym_analyzer():
    props = CLAUSE_INDEX_MAPPINGS["mappings"]["properties"]
    assert props["clause_text"]["analyzer"] == "cn_with_synonym"
    assert props["clause_title"]["analyzer"] == "cn_with_synonym"


def test_standard_ingestion_workflow_registered():
    assert "standard_ingestion" in list_workflows()
    wf_cls = get_workflow("standard_ingestion")
    wf = wf_cls()
    step_names = [s.name for s in wf.steps]
    assert step_names == [
        "parse_standard_pdf",
        "build_clause_tree",
        "tag_clauses",
        "index_to_opensearch",
    ]
