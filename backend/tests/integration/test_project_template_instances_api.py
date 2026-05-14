from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

import tender_backend.core.security as security
from tender_backend.db.deps import get_db_conn
from tender_backend.main import app
from tender_backend.test_support.asgi_client import SyncASGIClient


@dataclass(frozen=True)
class _Instance:
    id: UUID
    project_id: UUID
    base_template_package_id: UUID | None
    category_code: str
    display_name: str
    status: str = "draft"
    version: int = 1
    confirmed_at: datetime | None = None
    confirmed_by: str | None = None
    metadata_json: dict | None = None
    created_at: datetime = datetime(2026, 5, 14, tzinfo=timezone.utc)
    updated_at: datetime = datetime(2026, 5, 14, tzinfo=timezone.utc)


@dataclass(frozen=True)
class _Chapter:
    id: UUID
    template_instance_id: UUID
    project_id: UUID
    parent_id: UUID | None
    source_template_item_id: UUID | None
    chapter_code: str
    chapter_title: str
    volume_type: str
    sort_order: int
    enabled: bool = True
    chapter_status: str = "draft"
    tender_requirement_status: str = "not_checked"
    metadata_json: dict | None = None
    lock_owner: str | None = None
    locked_until: datetime | None = None
    lock_version: int = 1
    created_at: datetime = datetime(2026, 5, 14, tzinfo=timezone.utc)
    updated_at: datetime = datetime(2026, 5, 14, tzinfo=timezone.utc)


@dataclass(frozen=True)
class _Block:
    id: UUID
    template_chapter_id: UUID
    project_id: UUID
    block_type: str
    sort_order: int
    label: str
    content_text: str = ""
    prompt_text: str = ""
    placeholder_key: str | None = None
    asset_type: str | None = None
    required: bool = False
    render_options_json: dict | None = None
    condition_json: dict | None = None
    metadata_json: dict | None = None
    created_at: datetime = datetime(2026, 5, 14, tzinfo=timezone.utc)
    updated_at: datetime = datetime(2026, 5, 14, tzinfo=timezone.utc)


@dataclass(frozen=True)
class _Response:
    id: UUID
    project_id: UUID
    template_instance_id: UUID
    requirement_id: UUID
    template_chapter_id: UUID | None
    template_block_id: UUID | None
    response_status: str
    response_text: str = ""
    deviation_note: str = ""
    source_type: str = "tender_requirement"
    source_clarification_id: UUID | None = None
    metadata_json: dict | None = None
    created_at: datetime = datetime(2026, 5, 14, tzinfo=timezone.utc)
    updated_at: datetime = datetime(2026, 5, 14, tzinfo=timezone.utc)


@dataclass(frozen=True)
class _Seal:
    id: UUID
    project_id: UUID
    template_instance_id: UUID
    seal_block_id: UUID
    confirmation_status: str = "pending"
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    note: str = ""
    created_at: datetime = datetime(2026, 5, 14, tzinfo=timezone.utc)
    updated_at: datetime = datetime(2026, 5, 14, tzinfo=timezone.utc)



@dataclass(frozen=True)
class _Proposal:
    id: UUID
    template_instance_id: UUID
    base_template_package_id: UUID | None
    project_id: UUID
    proposal_status: str
    diff_json: dict
    created_by: str | None = None
    reviewed_by: str | None = None
    created_at: datetime = datetime(2026, 5, 14, tzinfo=timezone.utc)
    reviewed_at: datetime | None = None


@dataclass(frozen=True)
class _Revision:
    id: UUID
    template_instance_id: UUID
    project_id: UUID
    revision_no: int
    change_type: str
    change_summary: str
    snapshot_json: dict
    created_by: str | None = None
    created_at: datetime = datetime(2026, 5, 14, tzinfo=timezone.utc)


class _FakeConn:
    def transaction(self):
        class _Tx:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        return _Tx()


class _FakeService:
    def __init__(self, instance: _Instance) -> None:
        self.instance = instance

    def ensure_for_project(self, _conn, *, project_id: UUID, actor: str | None = None):
        assert project_id == self.instance.project_id
        return self.instance


class _FakeRepo:
    def __init__(self) -> None:
        self.project_id = uuid4()
        self.instance_id = uuid4()
        self.chapter_id = uuid4()
        self.block_id = uuid4()
        self.requirement_response_id = uuid4()
        self.requirement_id = uuid4()
        self.seal_block_id = uuid4()
        self.instance = _Instance(
            id=self.instance_id,
            project_id=self.project_id,
            base_template_package_id=uuid4(),
            category_code="sgcc_distribution",
            display_name="项目模板实例",
            metadata_json={"reconciliation": {"critical": 0}},
        )
        self.chapter = _Chapter(
            id=self.chapter_id,
            template_instance_id=self.instance_id,
            project_id=self.project_id,
            parent_id=None,
            source_template_item_id=None,
            chapter_code="5",
            chapter_title="施工组织设计",
            volume_type="technical",
            sort_order=5,
            metadata_json={},
        )
        self.block = _Block(
            id=self.block_id,
            template_chapter_id=self.chapter_id,
            project_id=self.project_id,
            block_type="fixed_text",
            sort_order=10,
            label="固定文本",
            content_text="响应内容",
            render_options_json={},
            condition_json={},
            metadata_json={},
        )
        self.response = _Response(
            id=self.requirement_response_id,
            project_id=self.project_id,
            template_instance_id=self.instance_id,
            requirement_id=self.requirement_id,
            template_chapter_id=self.chapter_id,
            template_block_id=self.block_id,
            response_status="full_response",
            metadata_json={},
        )
        self.seal = _Seal(id=uuid4(), project_id=self.project_id, template_instance_id=self.instance_id, seal_block_id=self.seal_block_id)
        self.reorder_payload = None
        self.proposals: list[_Proposal] = []
        self.revisions: list[_Revision] = []

    def get_current_for_project(self, _conn, project_id):
        return self.instance if project_id == self.project_id else None

    def get_by_id(self, _conn, instance_id):
        return self.instance if instance_id == self.instance_id else None

    def list_chapters(self, _conn, instance_id):
        return [self.chapter] if instance_id == self.instance_id else []

    def list_blocks(self, _conn, chapter_id):
        return [self.block] if chapter_id == self.chapter_id else []

    def get_block_by_id(self, _conn, block_id):
        return self.block if block_id == self.block_id else None

    def update_instance(self, _conn, instance_id, fields):
        self.instance = _Instance(**{**self.instance.__dict__, **fields, "metadata_json": fields.get("metadata_json", self.instance.metadata_json)})
        return self.instance

    def update_chapter(self, _conn, chapter_id, fields):
        self.chapter = _Chapter(**{**self.chapter.__dict__, **fields})
        return self.chapter

    def replace_chapter_tree_order(self, _conn, instance_id, ordered_tree, actor=None):
        self.reorder_payload = ordered_tree
        return [self.chapter]

    def create_block(self, _conn, chapter_id, fields):
        self.block = _Block(id=uuid4(), template_chapter_id=chapter_id, **fields)
        return self.block

    def update_block(self, _conn, block_id, fields):
        self.block = _Block(**{**self.block.__dict__, **fields})
        return self.block

    def list_requirement_responses(self, _conn, instance_id):
        return [self.response]

    def update_requirement_response(self, _conn, response_id, fields):
        self.response = _Response(**{**self.response.__dict__, **fields})
        return self.response

    def list_seal_checklist(self, _conn, instance_id):
        return [self.seal]

    def try_lock_chapter(self, _conn, chapter_id, actor, ttl_seconds):
        self.chapter = _Chapter(**{**self.chapter.__dict__, "lock_owner": actor, "lock_version": 2})
        return self.chapter

    def record_revision(self, _conn, instance_id, change_type, change_summary, snapshot_json, created_by):
        revision = _Revision(
            id=uuid4(),
            template_instance_id=instance_id,
            project_id=self.project_id,
            revision_no=len(self.revisions) + 1,
            change_type=change_type,
            change_summary=change_summary,
            snapshot_json=snapshot_json,
            created_by=created_by,
        )
        self.revisions.append(revision)
        return revision

    def create_promotion_proposal(self, _conn, *, instance_id, base_template_package_id, project_id, diff_json, created_by):
        proposal = _Proposal(
            id=uuid4(),
            template_instance_id=instance_id,
            base_template_package_id=base_template_package_id,
            project_id=project_id,
            proposal_status="draft",
            diff_json=diff_json,
            created_by=created_by,
        )
        self.proposals.append(proposal)
        return proposal

    def list_promotion_proposals(self, _conn, instance_id):
        return [proposal for proposal in self.proposals if proposal.template_instance_id == instance_id]


class _FakeRequirements:
    def list_by_project(self, _conn, *, project_id, include_stale=False, **_kwargs):
        return [
            {"id": uuid4(), "category": "directory", "directory_code": "6", "title": "进度计划"},
            {"id": uuid4(), "category": "directory", "directory_code": "5", "title": "施工组织设计"},
        ]


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    import tender_backend.api.project_template_instances as api

    fake_repo = _FakeRepo()
    app.dependency_overrides[get_db_conn] = lambda: _FakeConn()
    monkeypatch.setenv("AUTH_TOKENS", "dev-token:editor:Dev User")
    monkeypatch.setattr(security, "_token_map", None)
    monkeypatch.setattr(api, "_repo", fake_repo)
    monkeypatch.setattr(api, "_service", api.ProjectTemplateInstanceService(instance_repo=fake_repo))
    monkeypatch.setattr(api, "_requirements", _FakeRequirements())
    monkeypatch.setattr(api, "require_project_access", lambda *args, **kwargs: None)
    sync_client = SyncASGIClient(app)
    sync_client.headers.update({"Authorization": "Bearer dev-token"})
    yield sync_client, fake_repo
    sync_client.close()
    app.dependency_overrides.clear()
    monkeypatch.setattr(security, "_token_map", None)


def test_project_template_instance_routes_cover_read_edit_confirm_and_locks(client) -> None:
    sync_client, repo = client

    created = sync_client.post(f"/api/projects/{repo.project_id}/template-instance")
    assert created.status_code == 200
    assert created.json()["id"] == str(repo.instance_id)

    current = sync_client.get(f"/api/projects/{repo.project_id}/template-instance")
    assert current.status_code == 200
    assert current.json()["chapters"][0]["blocks"][0]["block_type"] == "fixed_text"

    patched_chapter = sync_client.request("PATCH", 
        f"/api/project-template-chapters/{repo.chapter_id}",
        json={"chapter_title": "施工组织设计（调整后）", "enabled": True},
    )
    assert patched_chapter.status_code == 200
    assert patched_chapter.json()["chapter_title"] == "施工组织设计（调整后）"

    reordered = sync_client.post(
        f"/api/project-template-instances/{repo.instance_id}/chapters/reorder",
        json={"ordered_tree": [{"chapter_id": str(repo.chapter_id), "parent_id": None, "sort_order": 7}]},
    )
    assert reordered.status_code == 200
    assert repo.reorder_payload[0]["sort_order"] == 7

    patched_block = sync_client.request("PATCH",
        f"/api/project-template-blocks/{repo.block.id}",
        json={"content_text": "更新后的固定文本"},
    )
    assert patched_block.status_code == 200
    assert patched_block.json()["block"]["content_text"] == "更新后的固定文本"
    assert patched_block.json()["revision_no"] == 2
    assert patched_block.json()["impact"] == {
        "stale_drafts": 0,
        "stale_charts": 0,
        "stale_docx": 1,
        "stale_draft_count": 0,
        "stale_chart_count": 0,
        "stale_export_artifact_count": 1,
    }
    assert repo.revisions[-1].change_type == "template_block_update"

    added_block = sync_client.post(
        f"/api/project-template-chapters/{repo.chapter_id}/blocks",
        json={"project_id": str(repo.project_id), "block_type": "seal_mark", "label": "盖章", "required": True},
    )
    assert added_block.status_code == 200
    assert added_block.json()["block_type"] == "seal_mark"

    responses = sync_client.get(f"/api/project-template-instances/{repo.instance_id}/requirement-responses")
    assert responses.status_code == 200
    assert responses.json()[0]["response_status"] == "full_response"

    patched_response = sync_client.request("PATCH", 
        f"/api/project-requirement-responses/{repo.requirement_response_id}",
        json={"response_status": "deviation", "deviation_note": "有偏离"},
    )
    assert patched_response.status_code == 200
    assert patched_response.json()["response_status"] == "deviation"

    checklist = sync_client.get(f"/api/project-template-instances/{repo.instance_id}/seal-checklist")
    assert checklist.status_code == 200
    assert checklist.json()[0]["confirmation_status"] == "pending"

    locked = sync_client.post(f"/api/project-template-chapters/{repo.chapter_id}/lock", json={"ttl_seconds": 60})
    assert locked.status_code == 200
    assert locked.json()["lock_owner"] == "Dev User"

    confirm = sync_client.post(f"/api/project-template-instances/{repo.instance_id}/confirm")
    assert confirm.status_code == 200
    assert confirm.json()["status"] == "ready_for_authoring"


def test_reconcile_and_apply_directory_updates_instance_metadata(client) -> None:
    sync_client, repo = client

    reconciled = sync_client.post(f"/api/projects/{repo.project_id}/template-instance/reconcile-directory", json={})
    assert reconciled.status_code == 200
    body = reconciled.json()
    assert body["summary"]["counts_by_type"]["add_chapter"] >= 1
    suggestion_id = body["suggestions"][0]["id"]

    applied = sync_client.post(
        f"/api/projects/{repo.project_id}/template-instance/apply-reconciliation",
        json={"selected_suggestion_ids": [suggestion_id], "skipped_suggestion_ids": [], "not_applicable_reasons": {}},
    )
    assert applied.status_code == 200
    assert applied.json()["applied_suggestion_ids"] == [suggestion_id]
    assert "reconciliation" in repo.instance.metadata_json


def test_create_promotion_proposal_returns_diff_and_keeps_global_template_read_only(client) -> None:
    sync_client, repo = client

    response = sync_client.post(f"/api/project-template-instances/{repo.instance_id}/promotion-proposals")

    assert response.status_code == 200
    body = response.json()
    assert body["proposal_status"] == "draft"
    assert body["template_instance_id"] == str(repo.instance_id)
    assert body["base_template_package_id"] == str(repo.instance.base_template_package_id)
    assert body["diff_json"]["summary"]["chapter_count"] == 1
    assert body["diff_json"]["chapters"][0]["project"]["chapter_title"] == "施工组织设计"
    assert len(repo.proposals) == 1

    current = sync_client.get(f"/api/projects/{repo.project_id}/template-instance")
    assert current.status_code == 200
    proposals = current.json()["promotion_proposals"]
    assert proposals[0]["proposal_status"] == "draft"
