"""Integration test for the parse pipeline workflow structure.

Tests the workflow definition and step registration without
requiring MinerU or database connections.
"""

from __future__ import annotations

import asyncio
import pytest
from types import SimpleNamespace

from tender_backend.workflows.registry import get_workflow, list_workflows
from tender_backend.workflows.states import WorkflowState, can_transition


# Ensure the workflow module is imported so registration runs
import tender_backend.workflows.tender_ingestion  # noqa: F401
import tender_backend.workflows.standard_ingestion  # noqa: F401


def test_standard_ingestion_build_clause_tree_uses_table_aware_scopes(monkeypatch):
    from tender_backend.workflows.standard_ingestion import BuildClauseTree
    from tender_backend.workflows import standard_ingestion as standard_ingestion_module

    sections = [
        {
            "id": "s1",
            "section_code": "1",
            "title": "总则",
            "level": 1,
            "text": "1.0.1 正文",
            "page_start": 1,
            "page_end": 1,
        }
    ]
    tables = [
        {
            "id": "t1",
            "table_title": "主要参数",
            "table_html": "<table><tr><td>额定电压</td><td>10kV</td></tr></table>",
            "page_start": 2,
            "page_end": 2,
        }
    ]

    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, query, params):
            self.query = str(query)
            return self

        def fetchall(self):
            if "FROM document_table" in self.query:
                return tables
            return sections

    class _Conn:
        def cursor(self, **kwargs):
            return _Cursor()

    class _ConnCtx:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(standard_ingestion_module, "_get_conn", lambda: _ConnCtx())

    step = BuildClauseTree()
    ctx = SimpleNamespace(data={"standard_id": "11111111-1111-1111-1111-111111111111", "document_id": "doc-1"})

    result = asyncio.run(step.execute(ctx))

    assert result.state.value == "completed"
    assert [scope["scope_type"] for scope in ctx.data["scopes"]] == ["normative", "table"]
    assert ctx.data["scopes"][1]["chapter_label"] == "表格: 主要参数"


def test_tender_ingestion_registered():
    assert "tender_ingestion" in list_workflows()


def test_tender_ingestion_has_expected_steps():
    wf_cls = get_workflow("tender_ingestion")
    wf = wf_cls()
    step_names = [s.name for s in wf.steps]
    assert step_names == [
        "upload_to_minio",
        "request_parse",
        "poll_result",
        "persist_sections",
        "persist_tables",
        "extract_outline",
    ]


def test_workflow_state_transitions():
    assert can_transition(WorkflowState.PENDING, WorkflowState.RUNNING)
    assert can_transition(WorkflowState.RUNNING, WorkflowState.SUSPENDED)
    assert can_transition(WorkflowState.SUSPENDED, WorkflowState.RUNNING)
    assert can_transition(WorkflowState.RUNNING, WorkflowState.COMPLETED)
    assert can_transition(WorkflowState.RUNNING, WorkflowState.FAILED)
    assert not can_transition(WorkflowState.COMPLETED, WorkflowState.RUNNING)
    assert not can_transition(WorkflowState.FAILED, WorkflowState.RUNNING)
