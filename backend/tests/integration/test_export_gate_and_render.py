"""Integration test for export gate logic and workflow registration."""

from __future__ import annotations

import pytest

import tender_backend.workflows.export_bid  # noqa: F401
from tender_backend.workflows.registry import get_workflow, list_workflows


def test_export_bid_workflow_registered():
    assert "export_bid" in list_workflows()


def test_export_bid_has_expected_steps():
    wf_cls = get_workflow("export_bid")
    wf = wf_cls()
    step_names = [s.name for s in wf.steps]
    assert step_names == [
        "check_veto_gate",
        "check_review_gate",
        "check_format_gate",
        "render_docx",
        "convert_to_pdf",
        "save_export_record",
    ]


def test_all_workflows_registered():
    """Verify all expected workflows are in the registry."""
    # Import all workflow modules to ensure registration
    import tender_backend.workflows.tender_ingestion  # noqa: F401
    import tender_backend.workflows.standard_ingestion  # noqa: F401
    import tender_backend.workflows.generate_section  # noqa: F401
    import tender_backend.workflows.review_section  # noqa: F401
    import tender_backend.workflows.export_bid  # noqa: F401

    workflows = list_workflows()
    assert "tender_ingestion" in workflows
    assert "standard_ingestion" in workflows
    assert "generate_section" in workflows
    assert "review_section" in workflows
    assert "export_bid" in workflows
