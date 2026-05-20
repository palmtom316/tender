from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tender_backend.db.deps import get_db_conn
from tender_backend.main import app


@pytest.fixture(autouse=True)
def _override_db_conn():
    app.dependency_overrides[get_db_conn] = lambda: object()
    yield
    app.dependency_overrides.pop(get_db_conn, None)


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


def test_get_ad_hoc_task_card_creates_only_for_marked_chapter(monkeypatch) -> None:
    project_id = uuid4()
    chapter_id = uuid4()
    chapter = {
        "id": chapter_id,
        "project_id": project_id,
        "chapter_code": "99",
        "chapter_title": "施工现场总平面布置及临电临水方案",
        "volume_type": "technical",
        "metadata_json": {"ad_hoc_required": True, "template_key": "keep"},
    }
    requirements = [
        {
            "id": "r1",
            "title": "临电临水方案",
            "requirement_text": "应提供临电临水方案",
            "source_file": "招标文件.pdf",
            "source_locator": "P32",
        }
    ]

    monkeypatch.setattr("tender_backend.api.bid_outline.require_resource_project_access", lambda *a, **k: project_id)
    monkeypatch.setattr("tender_backend.api.bid_outline._load_bid_chapter", lambda *a, **k: chapter)
    monkeypatch.setattr("tender_backend.api.bid_outline._load_chapter_requirements", lambda *a, **k: requirements)
    saved = {}

    def _save(_conn, *, project_id, chapter_id, card):
        saved["card"] = card
        return card

    monkeypatch.setattr("tender_backend.api.bid_outline._save_ad_hoc_task_card", _save)

    client = TestClient(app)
    res = client.get(
        f"/api/projects/{project_id}/bid-chapters/{chapter_id}/ad-hoc-task-card",
        headers={"Authorization": "Bearer dev-token"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["chapter_id"] == str(chapter_id)
    assert body["card"]["status"] == "needs_input"
    assert body["card"]["chapter_type"] == "technical_special_plan"
    assert saved["card"]["status"] == "needs_input"


def test_get_ad_hoc_task_card_rejects_unmarked_baseline_chapter(monkeypatch) -> None:
    project_id = uuid4()
    chapter_id = uuid4()
    chapter = {
        "id": chapter_id,
        "project_id": project_id,
        "chapter_code": "8",
        "chapter_title": "施工方案与技术措施",
        "volume_type": "technical",
        "metadata_json": {"template_key": "sgcc_distribution_technical_v1"},
    }

    monkeypatch.setattr("tender_backend.api.bid_outline.require_resource_project_access", lambda *a, **k: project_id)
    monkeypatch.setattr("tender_backend.api.bid_outline._load_bid_chapter", lambda *a, **k: chapter)

    client = TestClient(app)
    res = client.get(
        f"/api/projects/{project_id}/bid-chapters/{chapter_id}/ad-hoc-task-card",
        headers={"Authorization": "Bearer dev-token"},
    )

    assert res.status_code == 409


def test_patch_ad_hoc_task_card_rejects_unknown_answer(monkeypatch) -> None:
    project_id = uuid4()
    chapter_id = uuid4()
    chapter = {
        "id": chapter_id,
        "project_id": project_id,
        "chapter_code": "99",
        "chapter_title": "临电临水方案",
        "volume_type": "technical",
        "metadata_json": {
            "ad_hoc_required": True,
            "ad_hoc_task_card": {
                "status": "needs_input",
                "chapter_type": "technical_special_plan",
                "source_anchors": [],
                "must_respond": ["临电临水方案"],
                "missing_inputs": [
                    {"key": "site_type", "input_type": "choice", "options": ["城区道路"], "required": True, "answer": None}
                ],
                "outline": [],
            },
        },
    }

    monkeypatch.setattr("tender_backend.api.bid_outline.require_resource_project_access", lambda *a, **k: project_id)
    monkeypatch.setattr("tender_backend.api.bid_outline._load_bid_chapter", lambda *a, **k: chapter)

    client = TestClient(app)
    res = client.patch(
        f"/api/projects/{project_id}/bid-chapters/{chapter_id}/ad-hoc-task-card",
        headers={"Authorization": "Bearer dev-token"},
        json={"answers": {"unknown": "x"}},
    )

    assert res.status_code == 422


def test_confirm_ad_hoc_outline_sets_status(monkeypatch) -> None:
    project_id = uuid4()
    chapter_id = uuid4()
    card = {
        "status": "outline_ready",
        "chapter_type": "technical_special_plan",
        "source_anchors": [],
        "must_respond": ["临电临水方案"],
        "missing_inputs": [],
        "outline": [],
    }
    chapter = {
        "id": chapter_id,
        "project_id": project_id,
        "chapter_code": "99",
        "chapter_title": "临电临水方案",
        "volume_type": "technical",
        "metadata_json": {"ad_hoc_required": True, "ad_hoc_task_card": card},
    }
    monkeypatch.setattr("tender_backend.api.bid_outline.require_resource_project_access", lambda *a, **k: project_id)
    monkeypatch.setattr("tender_backend.api.bid_outline._load_bid_chapter", lambda *a, **k: chapter)
    monkeypatch.setattr("tender_backend.api.bid_outline._save_ad_hoc_task_card", lambda _conn, *, project_id, chapter_id, card: card)

    client = TestClient(app)
    res = client.post(
        f"/api/projects/{project_id}/bid-chapters/{chapter_id}/ad-hoc-task-card/confirm-outline",
        headers={"Authorization": "Bearer dev-token"},
        json={"outline": [{"heading": "编制依据", "purpose": "说明来源", "must_cover": ["招标要求"]}]},
    )

    assert res.status_code == 200
    assert res.json()["card"]["status"] == "outline_confirmed"



def test_confirm_ad_hoc_outline_rejects_before_outline_ready(monkeypatch) -> None:
    project_id = uuid4()
    chapter_id = uuid4()
    card = {
        "status": "needs_input",
        "chapter_type": "technical_special_plan",
        "source_anchors": [],
        "must_respond": ["临电临水方案"],
        "missing_inputs": [
            {"key": "site_type", "input_type": "choice", "options": ["城区道路"], "required": True, "answer": None}
        ],
        "outline": [],
    }
    chapter = {
        "id": chapter_id,
        "project_id": project_id,
        "chapter_code": "99",
        "chapter_title": "临电临水方案",
        "volume_type": "technical",
        "metadata_json": {"ad_hoc_required": True, "ad_hoc_task_card": card},
    }
    monkeypatch.setattr("tender_backend.api.bid_outline.require_resource_project_access", lambda *a, **k: project_id)
    monkeypatch.setattr("tender_backend.api.bid_outline._load_bid_chapter", lambda *a, **k: chapter)

    client = TestClient(app)
    res = client.post(
        f"/api/projects/{project_id}/bid-chapters/{chapter_id}/ad-hoc-task-card/confirm-outline",
        headers={"Authorization": "Bearer dev-token"},
        json={"outline": [{"heading": "编制依据", "purpose": "说明来源", "must_cover": ["招标要求"]}]},
    )

    assert res.status_code == 409


def test_generate_ad_hoc_outline_rejects_after_outline_confirmed(monkeypatch) -> None:
    project_id = uuid4()
    chapter_id = uuid4()
    card = {
        "status": "outline_confirmed",
        "chapter_type": "technical_special_plan",
        "source_anchors": [],
        "must_respond": ["临电临水方案"],
        "missing_inputs": [],
        "outline": [{"heading": "编制依据", "purpose": "说明来源", "must_cover": ["招标要求"]}],
    }
    chapter = {
        "id": chapter_id,
        "project_id": project_id,
        "chapter_code": "99",
        "chapter_title": "临电临水方案",
        "volume_type": "technical",
        "metadata_json": {"ad_hoc_required": True, "ad_hoc_task_card": card},
    }
    monkeypatch.setattr("tender_backend.api.bid_outline.require_resource_project_access", lambda *a, **k: project_id)
    monkeypatch.setattr("tender_backend.api.bid_outline._load_bid_chapter", lambda *a, **k: chapter)

    client = TestClient(app)
    res = client.post(
        f"/api/projects/{project_id}/bid-chapters/{chapter_id}/ad-hoc-task-card/outline",
        headers={"Authorization": "Bearer dev-token"},
    )

    assert res.status_code == 409
