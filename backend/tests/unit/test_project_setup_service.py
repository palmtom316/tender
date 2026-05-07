from uuid import uuid4

import pytest

from tender_backend.services.project_setup_service import WORKFLOW_TRANSITIONS, ProjectSetupService


def test_workflow_rejects_invalid_jump_policy():
    assert "final_packaged" not in WORKFLOW_TRANSITIONS["outline_pending_confirmation"]
    assert "drafting" in WORKFLOW_TRANSITIONS["outline_pending_confirmation"]


class FakeRepo:
    def __init__(self):
        self.project = type("Project", (), {"id": uuid4(), "workflow_status": "outline_pending_confirmation", "status": "outline_pending_confirmation"})()

    def get(self, conn, *, project_id):
        return self.project

    def update(self, conn, *, project_id, fields):
        self.project.workflow_status = fields["workflow_status"]
        self.project.status = fields["status"]
        return self.project


def test_transition_raises_on_invalid_jump(monkeypatch):
    service = ProjectSetupService(repo=FakeRepo())
    monkeypatch.setattr(service, "record_event", lambda *args, **kwargs: {})

    with pytest.raises(ValueError, match="invalid workflow transition"):
        service.transition(None, project_id=uuid4(), next_status="final_packaged", actor="tester")


def test_transition_allows_next_step(monkeypatch):
    service = ProjectSetupService(repo=FakeRepo())
    monkeypatch.setattr(service, "record_event", lambda *args, **kwargs: {})

    project = service.transition(None, project_id=uuid4(), next_status="drafting", actor="tester")

    assert project.workflow_status == "drafting"
