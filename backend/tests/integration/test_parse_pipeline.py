"""Integration test for the parse pipeline workflow structure.

Tests the workflow definition and step registration without
requiring MinerU or database connections.
"""

from __future__ import annotations

import pytest

from tender_backend.workflows.registry import get_workflow, list_workflows
from tender_backend.workflows.states import WorkflowState, can_transition


# Ensure the workflow module is imported so registration runs
import tender_backend.workflows.tender_ingestion  # noqa: F401


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
