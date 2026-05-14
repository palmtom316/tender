from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from tender_backend.db.repositories.project_template_instance_repo import ProjectTemplateInstanceRepository


class _RecordingCursor:
    def __init__(self, response_rows: list[dict]) -> None:
        self.executed: list[tuple[str, tuple | list | None]] = []
        self._responses = list(response_rows)

    def execute(self, sql: str, params: tuple | list | None = None) -> "_RecordingCursor":
        self.executed.append((sql, params))
        return self

    def fetchone(self) -> dict | None:
        return self._responses.pop(0) if self._responses else None

    def fetchall(self) -> list[dict]:
        return list(self._responses)

    def __enter__(self) -> "_RecordingCursor":
        return self

    def __exit__(self, *_: object) -> bool:
        return False


class _FakeConn:
    def __init__(self, cursor: _RecordingCursor) -> None:
        self._cursor = cursor
        self.commits = 0

    def cursor(self, **_: object) -> _RecordingCursor:
        return self._cursor

    def commit(self) -> None:
        self.commits += 1


def _now() -> datetime:
    return datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc)


def _instance_row(*, instance_id: UUID, project_id: UUID, package_id: UUID | None) -> dict:
    return {
        "id": instance_id,
        "project_id": project_id,
        "base_template_package_id": package_id,
        "category_code": "power-grid",
        "display_name": "国网配电项目模板实例",
        "status": "draft",
        "version": 1,
        "confirmed_at": None,
        "confirmed_by": None,
        "metadata_json": {"format_profile": {"font_family": "宋体"}, "seal_units": []},
        "created_at": _now(),
        "updated_at": _now(),
    }


def _chapter_row(*, chapter_id: UUID, instance_id: UUID, project_id: UUID, source_item_id: UUID | None = None) -> dict:
    return {
        "id": chapter_id,
        "template_instance_id": instance_id,
        "project_id": project_id,
        "parent_id": None,
        "source_template_item_id": source_item_id,
        "chapter_code": "5",
        "chapter_title": "施工组织设计",
        "volume_type": "technical",
        "sort_order": 5,
        "enabled": True,
        "chapter_status": "draft",
        "tender_requirement_status": "not_checked",
        "metadata_json": {"cloned_from": "bid_template_item"},
        "lock_owner": None,
        "locked_until": None,
        "lock_version": 1,
        "created_at": _now(),
        "updated_at": _now(),
    }


def _block_row(*, block_id: UUID, chapter_id: UUID, project_id: UUID, block_type: str = "fixed_text") -> dict:
    return {
        "id": block_id,
        "template_chapter_id": chapter_id,
        "project_id": project_id,
        "block_type": block_type,
        "sort_order": 10,
        "label": "章节固定文本",
        "content_text": "请按招标文件要求响应。",
        "prompt_text": "",
        "placeholder_key": None,
        "asset_type": None,
        "required": True,
        "render_options_json": {"visible_in_preview": True},
        "condition_json": {},
        "metadata_json": {"source": "template"},
        "created_at": _now(),
        "updated_at": _now(),
    }


def test_repository_creates_project_template_instance_with_cloned_chapter_and_block_rows() -> None:
    project_id = uuid4()
    package_id = uuid4()
    instance_id = uuid4()
    source_item_id = uuid4()
    chapter_id = uuid4()
    block_id = uuid4()
    cursor = _RecordingCursor(
        [
            _instance_row(instance_id=instance_id, project_id=project_id, package_id=package_id),
            _chapter_row(chapter_id=chapter_id, instance_id=instance_id, project_id=project_id, source_item_id=source_item_id),
            _block_row(block_id=block_id, chapter_id=chapter_id, project_id=project_id),
        ]
    )

    repo = ProjectTemplateInstanceRepository()
    conn = _FakeConn(cursor)

    instance = repo.create_instance(
        conn,
        project_id=project_id,
        base_template_package_id=package_id,
        category_code="power-grid",
        display_name="国网配电项目模板实例",
        metadata={"format_profile": {"font_family": "宋体"}, "seal_units": []},
    )
    chapter = repo.create_chapter(
        conn,
        instance_id=instance.id,
        project_id=project_id,
        source_template_item_id=source_item_id,
        chapter_code="5",
        chapter_title="施工组织设计",
        volume_type="technical",
        sort_order=5,
        metadata={"cloned_from": "bid_template_item"},
    )
    block = repo.create_block(
        conn,
        chapter.id,
        {
            "project_id": project_id,
            "block_type": "fixed_text",
            "sort_order": 10,
            "label": "章节固定文本",
            "content_text": "请按招标文件要求响应。",
            "required": True,
            "render_options_json": {"visible_in_preview": True},
            "metadata_json": {"source": "template"},
        },
    )

    assert instance.id == instance_id
    assert instance.base_template_package_id == package_id
    assert chapter.source_template_item_id == source_item_id
    assert chapter.template_instance_id == instance_id
    assert block.template_chapter_id == chapter_id
    assert block.render_options_json == {"visible_in_preview": True}

    sql_text = "\n".join(sql for sql, _ in cursor.executed)
    assert "INSERT INTO project_template_instance" in sql_text
    assert "INSERT INTO project_template_chapter" in sql_text
    assert "INSERT INTO project_template_block" in sql_text


def test_repository_reorders_and_moves_chapters_with_revision_safe_lock_version() -> None:
    instance_id = uuid4()
    actor = "alice@example.com"
    chapter_ids = [uuid4(), uuid4(), uuid4()]
    moved = _chapter_row(chapter_id=chapter_ids[0], instance_id=instance_id, project_id=uuid4())
    moved["parent_id"] = chapter_ids[2]
    moved["sort_order"] = 7
    moved["lock_owner"] = actor
    moved["lock_version"] = 2
    cursor = _RecordingCursor([moved])
    repo = ProjectTemplateInstanceRepository()

    repo.replace_chapter_order(_FakeConn(cursor), instance_id=instance_id, ordered_chapter_ids=chapter_ids)
    chapter = repo.move_chapter(
        _FakeConn(cursor),
        chapter_id=chapter_ids[0],
        new_parent_id=chapter_ids[2],
        new_sort_order=7,
        actor=actor,
    )

    assert chapter.parent_id == chapter_ids[2]
    assert chapter.sort_order == 7
    assert chapter.lock_version == 2
    update_sql = "\n".join(sql for sql, _ in cursor.executed if sql.lstrip().upper().startswith("UPDATE"))
    assert "lock_version = lock_version + 1" in update_sql
    assert "locked_until" in update_sql


def test_repository_upserts_requirement_response_and_confirms_seal_item() -> None:
    instance_id = uuid4()
    project_id = uuid4()
    requirement_id = uuid4()
    response_id = uuid4()
    seal_block_id = uuid4()
    seal_confirmation_id = uuid4()
    now = _now()
    cursor = _RecordingCursor(
        [
            {
                "id": response_id,
                "project_id": project_id,
                "template_instance_id": instance_id,
                "requirement_id": requirement_id,
                "template_chapter_id": None,
                "template_block_id": None,
                "response_status": "full_response",
                "response_text": "完全响应",
                "deviation_note": "",
                "source_type": "tender_requirement",
                "source_clarification_id": None,
                "metadata_json": {},
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": seal_confirmation_id,
                "project_id": project_id,
                "template_instance_id": instance_id,
                "seal_block_id": seal_block_id,
                "confirmation_status": "confirmed",
                "confirmed_by": "alice@example.com",
                "confirmed_at": now,
                "note": "已核对",
                "created_at": now,
                "updated_at": now,
            },
        ]
    )
    repo = ProjectTemplateInstanceRepository()
    conn = _FakeConn(cursor)

    response = repo.upsert_requirement_response(
        conn,
        instance_id=instance_id,
        requirement_id=requirement_id,
        template_chapter_id=None,
        template_block_id=None,
        fields={"project_id": project_id, "response_status": "full_response", "response_text": "完全响应"},
    )
    seal = repo.confirm_seal_item(conn, instance_id=instance_id, seal_block_id=seal_block_id, actor="alice@example.com", note="已核对")

    assert response.response_status == "full_response"
    assert response.response_text == "完全响应"
    assert seal.confirmation_status == "confirmed"
    assert seal.confirmed_by == "alice@example.com"
    sql_text = "\n".join(sql for sql, _ in cursor.executed)
    assert "ON CONFLICT (template_instance_id, requirement_id)" in sql_text
    assert "ON CONFLICT (template_instance_id, seal_block_id)" in sql_text


def test_move_chapter_rejects_moving_chapter_under_itself_before_database_write() -> None:
    chapter_id = uuid4()
    cursor = _RecordingCursor([])
    repo = ProjectTemplateInstanceRepository()

    with pytest.raises(ValueError, match="itself"):
        repo.move_chapter(_FakeConn(cursor), chapter_id=chapter_id, new_parent_id=chapter_id, new_sort_order=1, actor="alice")

    assert cursor.executed == []


def test_service_ensure_for_project_is_idempotent_and_clones_selected_package_items() -> None:
    from tender_backend.db.repositories.bid_template_package_repo import BidTemplateItemRow, BidTemplatePackageRow
    from tender_backend.services.project_template_instance_service import ProjectTemplateInstanceService

    project_id = uuid4()
    package_id = uuid4()
    item_a = uuid4()
    item_b = uuid4()
    instance_id = uuid4()
    project = type(
        "Project",
        (),
        {
            "id": project_id,
            "name": "配网施工项目",
            "category_code": "sgcc_distribution",
            "selected_template_package_id": package_id,
            "tender_no": "T-2026-001",
            "employer_name": "国网某公司",
            "metadata_json": {},
        },
    )()
    package = BidTemplatePackageRow(
        id=package_id,
        package_key="sgcc-distribution-technical",
        display_name="配网技术标模板",
        package_type="technical",
        category_code="sgcc_distribution",
        source_root="/templates",
        source_manifest={"metadata": {"format_profile": {"font_family": "宋体"}, "seal_units": ["正本"]}},
        created_at=_now(),
        updated_at=_now(),
    )
    items = [
        BidTemplateItemRow(
            id=item_a,
            package_id=package_id,
            item_code="5",
            item_name="施工组织设计",
            filename="5.docx",
            relative_path="5.docx",
            source_kind="docx",
            item_type="chapter",
            render_mode="ai_written",
            is_required=True,
            sort_order=5,
            created_at=_now(),
        ),
        BidTemplateItemRow(
            id=item_b,
            package_id=package_id,
            item_code="8",
            item_name="法定代表人签字盖章",
            filename="8.docx",
            relative_path="8.docx",
            source_kind="docx",
            item_type="chapter",
            render_mode="templated",
            is_required=True,
            sort_order=8,
            created_at=_now(),
        ),
    ]

    class ProjectRepo:
        def get(self, conn, *, project_id):
            return project

    class TemplateRepo:
        def __init__(self) -> None:
            self.writes = 0

        def get_by_id(self, conn, *, package_id):
            return package

        def list_items(self, conn, *, package_id):
            return items

        def replace_items(self, *args, **kwargs):
            self.writes += 1
            raise AssertionError("project instance cloning must not mutate global template items")

    class InstanceRepo:
        def __init__(self) -> None:
            self.current_calls = 0
            self.created_instances = []
            self.created_chapters = []
            self.created_blocks = []
            self.responses = []
            self.revisions = []

        def get_current_for_project(self, conn, project_id):
            self.current_calls += 1
            if self.current_calls > 1:
                return type("Instance", (), {"id": instance_id, "project_id": project_id})()
            return None

        def create_instance(self, conn, project_id, base_template_package_id, category_code, display_name, metadata=None):
            instance = type(
                "Instance",
                (),
                {
                    "id": instance_id,
                    "project_id": project_id,
                    "base_template_package_id": base_template_package_id,
                    "category_code": category_code,
                    "display_name": display_name,
                    "metadata_json": metadata or {},
                },
            )()
            self.created_instances.append(instance)
            return instance

        def create_chapter(self, conn, **kwargs):
            chapter = type("Chapter", (), {"id": uuid4(), **kwargs})()
            self.created_chapters.append(chapter)
            return chapter

        def create_block(self, conn, chapter_id, fields):
            block = type("Block", (), {"id": uuid4(), "template_chapter_id": chapter_id, **fields})()
            self.created_blocks.append(block)
            return block

        def upsert_requirement_response(self, conn, instance_id, requirement_id, template_chapter_id, template_block_id, fields):
            self.responses.append((instance_id, requirement_id, template_chapter_id, template_block_id, fields))

        def record_revision(self, conn, instance_id, change_type, change_summary, snapshot_json, created_by):
            self.revisions.append((instance_id, change_type, change_summary, snapshot_json, created_by))

    class RequirementRepo:
        def list_by_project(self, conn, *, project_id, include_stale=False, **kwargs):
            return [
                {"id": uuid4(), "review_status": "confirmed", "is_stale": False},
                {"id": uuid4(), "review_status": "pending", "is_stale": False},
                {"id": uuid4(), "review_status": "confirmed", "is_stale": True},
            ]

    template_repo = TemplateRepo()
    instance_repo = InstanceRepo()
    service = ProjectTemplateInstanceService(
        project_repo=ProjectRepo(),
        template_repo=template_repo,
        instance_repo=instance_repo,
        requirement_repo=RequirementRepo(),
    )

    first = service.ensure_for_project(None, project_id=project_id, actor="tester")
    second = service.ensure_for_project(None, project_id=project_id, actor="tester")

    assert first.id == instance_id
    assert second.id == instance_id
    assert len(instance_repo.created_instances) == 1
    assert instance_repo.created_instances[0].base_template_package_id == package_id
    assert instance_repo.created_instances[0].metadata_json["format_profile"] == {"font_family": "宋体"}
    assert instance_repo.created_instances[0].metadata_json["standard_variables"]["project.name"] == "配网施工项目"
    assert [chapter.source_template_item_id for chapter in instance_repo.created_chapters] == [item_a, item_b]
    block_types = [block.block_type for block in instance_repo.created_blocks]
    assert "fixed_text" in block_types
    assert "page_break" in block_types
    assert "header_footer" in block_types
    assert "ai_prompt" in block_types
    assert "seal_mark" in block_types
    assert len(instance_repo.responses) == 1, "only confirmed non-stale project requirements become response rows"
    assert instance_repo.revisions[0][1] == "create_instance"
    assert template_repo.writes == 0


def test_service_raises_when_project_has_no_selected_template_package() -> None:
    from tender_backend.services.project_template_instance_service import ProjectTemplateInstanceService

    project = type(
        "Project",
        (),
        {"id": uuid4(), "name": "无模板项目", "category_code": "sgcc_distribution", "selected_template_package_id": None},
    )()

    class ProjectRepo:
        def get(self, conn, *, project_id):
            return project

    class InstanceRepo:
        def get_current_for_project(self, conn, project_id):
            return None

    service = ProjectTemplateInstanceService(project_repo=ProjectRepo(), instance_repo=InstanceRepo())

    with pytest.raises(ValueError, match="selected template package"):
        service.ensure_for_project(None, project_id=project.id)
