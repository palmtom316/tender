from uuid import uuid4

from fastapi.testclient import TestClient

from tender_backend.main import app


def test_async_generate_technical_chapter_returns_202_with_run_id(monkeypatch) -> None:
    project_id = uuid4()
    chapter_id = uuid4()

    monkeypatch.setattr("tender_backend.api.bid_generation.require_resource_project_access", lambda *a, **k: project_id)
    monkeypatch.setattr("tender_backend.api.bid_generation.require_project_access", lambda *a, **k: None)
    monkeypatch.setattr("tender_backend.api.bid_generation._project_repo.get", lambda *a, **k: None)
    monkeypatch.setattr("tender_backend.api.bid_generation._template_instances.build_generation_inputs", lambda *a, **k: {"metadata": {}})
    monkeypatch.setattr(
        "tender_backend.api.bid_generation.enqueue_technical_generation",
        lambda **kwargs: {"run_id": "run-123", "state": "pending", "chapter_id": str(chapter_id)},
        raising=False,
    )

    client = TestClient(app)
    res = client.post(
        f"/api/projects/{project_id}/technical-bid/chapters/{chapter_id}/generate-async",
        headers={"Authorization": "Bearer dev-token"},
        json={"target_pages": 100},
    )

    assert res.status_code == 202
    assert res.json()["run_id"] == "run-123"
    assert res.json()["state"] == "pending"


def test_get_technical_generation_run_status_returns_draft_link(monkeypatch) -> None:
    project_id = uuid4()
    chapter_id = uuid4()

    monkeypatch.setattr("tender_backend.api.bid_generation.require_project_access", lambda *a, **k: None)
    monkeypatch.setattr(
        "tender_backend.api.bid_generation.get_technical_generation_run_status",
        lambda **kwargs: {
            "run_id": "run-123",
            "state": "completed",
            "chapter_id": str(chapter_id),
            "draft_id": "draft-456",
            "error": None,
        },
        raising=False,
    )

    client = TestClient(app)
    res = client.get(
        f"/api/projects/{project_id}/technical-bid/generation-runs/run-123",
        headers={"Authorization": "Bearer dev-token"},
    )

    assert res.status_code == 200
    assert res.json()["state"] == "completed"
    assert res.json()["draft_id"] == "draft-456"
