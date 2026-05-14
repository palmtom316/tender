from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


@dataclass(frozen=True)
class ProjectTemplateInstanceRow:
    id: UUID
    project_id: UUID
    base_template_package_id: UUID | None
    category_code: str
    display_name: str
    status: str
    version: int
    confirmed_at: datetime | None
    confirmed_by: str | None
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ProjectTemplateChapterRow:
    id: UUID
    template_instance_id: UUID
    project_id: UUID
    parent_id: UUID | None
    source_template_item_id: UUID | None
    chapter_code: str
    chapter_title: str
    volume_type: str
    sort_order: int
    enabled: bool
    chapter_status: str
    tender_requirement_status: str
    metadata_json: dict[str, Any]
    lock_owner: str | None
    locked_until: datetime | None
    lock_version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ProjectTemplateBlockRow:
    id: UUID
    template_chapter_id: UUID
    project_id: UUID
    block_type: str
    sort_order: int
    label: str
    content_text: str
    prompt_text: str
    placeholder_key: str | None
    asset_type: str | None
    required: bool
    render_options_json: dict[str, Any]
    condition_json: dict[str, Any]
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ProjectRequirementResponseRow:
    id: UUID
    project_id: UUID
    template_instance_id: UUID
    requirement_id: UUID
    template_chapter_id: UUID | None
    template_block_id: UUID | None
    response_status: str
    response_text: str
    deviation_note: str
    source_type: str
    source_clarification_id: UUID | None
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ProjectTemplateSealConfirmationRow:
    id: UUID
    project_id: UUID
    template_instance_id: UUID
    seal_block_id: UUID
    confirmation_status: str
    confirmed_by: str | None
    confirmed_at: datetime | None
    note: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ProjectTemplateRevisionRow:
    id: UUID
    template_instance_id: UUID
    project_id: UUID
    revision_no: int
    change_type: str
    change_summary: str
    snapshot_json: dict[str, Any]
    created_by: str | None
    created_at: datetime


@dataclass(frozen=True)
class TemplatePromotionProposalRow:
    id: UUID
    template_instance_id: UUID
    base_template_package_id: UUID | None
    project_id: UUID
    proposal_status: str
    diff_json: dict[str, Any]
    created_by: str | None
    reviewed_by: str | None
    created_at: datetime
    reviewed_at: datetime | None


_INSTANCE_COLUMNS = (
    "id, project_id, base_template_package_id, category_code, display_name, status, version, "
    "confirmed_at, confirmed_by, metadata_json, created_at, updated_at"
)
_CHAPTER_COLUMNS = (
    "id, template_instance_id, project_id, parent_id, source_template_item_id, chapter_code, "
    "chapter_title, volume_type, sort_order, enabled, chapter_status, tender_requirement_status, "
    "metadata_json, lock_owner, locked_until, lock_version, created_at, updated_at"
)
_BLOCK_COLUMNS = (
    "id, template_chapter_id, project_id, block_type, sort_order, label, content_text, prompt_text, "
    "placeholder_key, asset_type, required, render_options_json, condition_json, metadata_json, created_at, updated_at"
)
_RESPONSE_COLUMNS = (
    "id, project_id, template_instance_id, requirement_id, template_chapter_id, template_block_id, "
    "response_status, response_text, deviation_note, source_type, source_clarification_id, metadata_json, "
    "created_at, updated_at"
)
_SEAL_COLUMNS = (
    "id, project_id, template_instance_id, seal_block_id, confirmation_status, confirmed_by, confirmed_at, "
    "note, created_at, updated_at"
)
_REVISION_COLUMNS = (
    "id, template_instance_id, project_id, revision_no, change_type, change_summary, snapshot_json, created_by, created_at"
)
_PROPOSAL_COLUMNS = (
    "id, template_instance_id, base_template_package_id, project_id, proposal_status, diff_json, created_by, "
    "reviewed_by, created_at, reviewed_at"
)


def _json(value: Any) -> dict[str, Any]:
    return dict(value or {})


def _to_instance(row: dict[str, Any]) -> ProjectTemplateInstanceRow:
    return ProjectTemplateInstanceRow(
        id=row["id"],
        project_id=row["project_id"],
        base_template_package_id=row.get("base_template_package_id"),
        category_code=row["category_code"],
        display_name=row["display_name"],
        status=row["status"],
        version=row["version"],
        confirmed_at=row.get("confirmed_at"),
        confirmed_by=row.get("confirmed_by"),
        metadata_json=_json(row.get("metadata_json")),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_chapter(row: dict[str, Any]) -> ProjectTemplateChapterRow:
    return ProjectTemplateChapterRow(
        id=row["id"],
        template_instance_id=row["template_instance_id"],
        project_id=row["project_id"],
        parent_id=row.get("parent_id"),
        source_template_item_id=row.get("source_template_item_id"),
        chapter_code=row["chapter_code"],
        chapter_title=row["chapter_title"],
        volume_type=row["volume_type"],
        sort_order=row["sort_order"],
        enabled=row["enabled"],
        chapter_status=row["chapter_status"],
        tender_requirement_status=row["tender_requirement_status"],
        metadata_json=_json(row.get("metadata_json")),
        lock_owner=row.get("lock_owner"),
        locked_until=row.get("locked_until"),
        lock_version=row["lock_version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_block(row: dict[str, Any]) -> ProjectTemplateBlockRow:
    return ProjectTemplateBlockRow(
        id=row["id"],
        template_chapter_id=row["template_chapter_id"],
        project_id=row["project_id"],
        block_type=row["block_type"],
        sort_order=row["sort_order"],
        label=row["label"],
        content_text=row["content_text"],
        prompt_text=row["prompt_text"],
        placeholder_key=row.get("placeholder_key"),
        asset_type=row.get("asset_type"),
        required=row["required"],
        render_options_json=_json(row.get("render_options_json")),
        condition_json=_json(row.get("condition_json")),
        metadata_json=_json(row.get("metadata_json")),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_response(row: dict[str, Any]) -> ProjectRequirementResponseRow:
    return ProjectRequirementResponseRow(
        id=row["id"],
        project_id=row["project_id"],
        template_instance_id=row["template_instance_id"],
        requirement_id=row["requirement_id"],
        template_chapter_id=row.get("template_chapter_id"),
        template_block_id=row.get("template_block_id"),
        response_status=row["response_status"],
        response_text=row["response_text"],
        deviation_note=row["deviation_note"],
        source_type=row["source_type"],
        source_clarification_id=row.get("source_clarification_id"),
        metadata_json=_json(row.get("metadata_json")),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_seal(row: dict[str, Any]) -> ProjectTemplateSealConfirmationRow:
    return ProjectTemplateSealConfirmationRow(
        id=row["id"],
        project_id=row["project_id"],
        template_instance_id=row["template_instance_id"],
        seal_block_id=row["seal_block_id"],
        confirmation_status=row["confirmation_status"],
        confirmed_by=row.get("confirmed_by"),
        confirmed_at=row.get("confirmed_at"),
        note=row["note"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_revision(row: dict[str, Any]) -> ProjectTemplateRevisionRow:
    return ProjectTemplateRevisionRow(
        id=row["id"],
        template_instance_id=row["template_instance_id"],
        project_id=row["project_id"],
        revision_no=row["revision_no"],
        change_type=row["change_type"],
        change_summary=row["change_summary"],
        snapshot_json=_json(row.get("snapshot_json")),
        created_by=row.get("created_by"),
        created_at=row["created_at"],
    )


def _to_proposal(row: dict[str, Any]) -> TemplatePromotionProposalRow:
    return TemplatePromotionProposalRow(
        id=row["id"],
        template_instance_id=row["template_instance_id"],
        base_template_package_id=row.get("base_template_package_id"),
        project_id=row["project_id"],
        proposal_status=row["proposal_status"],
        diff_json=_json(row.get("diff_json")),
        created_by=row.get("created_by"),
        reviewed_by=row.get("reviewed_by"),
        created_at=row["created_at"],
        reviewed_at=row.get("reviewed_at"),
    )


def _jsonb(value: dict[str, Any] | None) -> Jsonb:
    return Jsonb(value or {})


class ProjectTemplateInstanceRepository:
    def create_instance(
        self,
        conn: Connection,
        project_id: UUID,
        base_template_package_id: UUID | None,
        category_code: str,
        display_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> ProjectTemplateInstanceRow:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                INSERT INTO project_template_instance (
                  id, project_id, base_template_package_id, category_code, display_name, metadata_json
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING {_INSTANCE_COLUMNS}
                """,
                (uuid4(), project_id, base_template_package_id, category_code, display_name, _jsonb(metadata)),
            ).fetchone()
        assert row is not None
        return _to_instance(dict(row))

    def get_current_for_project(self, conn: Connection, project_id: UUID) -> ProjectTemplateInstanceRow | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                SELECT {_INSTANCE_COLUMNS}
                FROM project_template_instance
                WHERE project_id = %s AND status <> 'superseded'
                ORDER BY version DESC, created_at DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
        return _to_instance(dict(row)) if row else None


    def get_by_id(self, conn: Connection, instance_id: UUID) -> ProjectTemplateInstanceRow | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"SELECT {_INSTANCE_COLUMNS} FROM project_template_instance WHERE id = %s",
                (instance_id,),
            ).fetchone()
        return _to_instance(dict(row)) if row else None

    def update_instance(self, conn: Connection, instance_id: UUID, fields: dict[str, Any]) -> ProjectTemplateInstanceRow | None:
        allowed = {"display_name", "status", "version", "confirmed_at", "confirmed_by", "metadata_json"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return self.get_by_id(conn, instance_id)
        sets: list[str] = []
        params: list[Any] = []
        for key, value in updates.items():
            sets.append(f"{key} = %s")
            params.append(_jsonb(value) if key == "metadata_json" else value)
        sets.append("updated_at = now()")
        params.append(instance_id)
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"UPDATE project_template_instance SET {', '.join(sets)} WHERE id = %s RETURNING {_INSTANCE_COLUMNS}",
                params,
            ).fetchone()
        return _to_instance(dict(row)) if row else None

    def confirm_instance(self, conn: Connection, instance_id: UUID, actor: str | None) -> ProjectTemplateInstanceRow:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                UPDATE project_template_instance
                SET status = 'ready_for_authoring',
                    confirmed_at = now(),
                    confirmed_by = %s,
                    updated_at = now()
                WHERE id = %s
                RETURNING {_INSTANCE_COLUMNS}
                """,
                (actor, instance_id),
            ).fetchone()
        if row is None:
            raise ValueError("template instance not found")
        return _to_instance(dict(row))

    def list_chapters(self, conn: Connection, instance_id: UUID) -> list[ProjectTemplateChapterRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"""
                SELECT {_CHAPTER_COLUMNS}
                FROM project_template_chapter
                WHERE template_instance_id = %s
                ORDER BY parent_id NULLS FIRST, sort_order, chapter_code
                """,
                (instance_id,),
            ).fetchall()
        return [_to_chapter(dict(row)) for row in rows]

    def create_chapter(
        self,
        conn: Connection,
        *,
        instance_id: UUID,
        project_id: UUID,
        source_template_item_id: UUID | None = None,
        parent_id: UUID | None = None,
        chapter_code: str,
        chapter_title: str,
        volume_type: str,
        sort_order: int = 0,
        enabled: bool = True,
        chapter_status: str = "draft",
        tender_requirement_status: str = "not_checked",
        metadata: dict[str, Any] | None = None,
    ) -> ProjectTemplateChapterRow:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                INSERT INTO project_template_chapter (
                  id, template_instance_id, project_id, parent_id, source_template_item_id, chapter_code,
                  chapter_title, volume_type, sort_order, enabled, chapter_status, tender_requirement_status,
                  metadata_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING {_CHAPTER_COLUMNS}
                """,
                (
                    uuid4(),
                    instance_id,
                    project_id,
                    parent_id,
                    source_template_item_id,
                    chapter_code,
                    chapter_title,
                    volume_type,
                    sort_order,
                    enabled,
                    chapter_status,
                    tender_requirement_status,
                    _jsonb(metadata),
                ),
            ).fetchone()
        assert row is not None
        return _to_chapter(dict(row))

    def list_blocks(self, conn: Connection, chapter_id: UUID) -> list[ProjectTemplateBlockRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"""
                SELECT {_BLOCK_COLUMNS}
                FROM project_template_block
                WHERE template_chapter_id = %s
                ORDER BY sort_order, created_at
                """,
                (chapter_id,),
            ).fetchall()
        return [_to_block(dict(row)) for row in rows]

    def replace_chapter_order(self, conn: Connection, instance_id: UUID, ordered_chapter_ids: list[UUID]) -> None:
        if not ordered_chapter_ids:
            return
        with conn.cursor() as cur:
            for sort_order, chapter_id in enumerate(ordered_chapter_ids):
                cur.execute(
                    """
                    UPDATE project_template_chapter
                    SET sort_order = %s,
                        lock_version = lock_version + 1,
                        updated_at = now()
                    WHERE template_instance_id = %s AND id = %s
                    """,
                    (sort_order, instance_id, chapter_id),
                )


    def replace_chapter_tree_order(
        self,
        conn: Connection,
        instance_id: UUID,
        ordered_tree: list[dict[str, Any]],
        actor: str | None = None,
    ) -> list[ProjectTemplateChapterRow]:
        seen: set[UUID] = set()
        with conn.cursor(row_factory=dict_row) as cur:
            for row in ordered_tree:
                chapter_id = row["chapter_id"]
                parent_id = row.get("parent_id")
                if chapter_id == parent_id:
                    raise ValueError("chapter cannot be moved under itself")
                if chapter_id in seen:
                    raise ValueError("duplicate chapter in ordered_tree")
                seen.add(chapter_id)
                cur.execute(
                    """
                    UPDATE project_template_chapter
                    SET parent_id = %s,
                        sort_order = %s,
                        lock_version = lock_version + 1,
                        updated_at = now()
                    WHERE template_instance_id = %s
                      AND id = %s
                      AND (locked_until IS NULL OR locked_until < now() OR lock_owner = %s OR %s IS NULL)
                    """,
                    (parent_id, row["sort_order"], instance_id, chapter_id, actor, actor),
                )
            rows = cur.execute(
                f"""
                SELECT {_CHAPTER_COLUMNS}
                FROM project_template_chapter
                WHERE template_instance_id = %s
                ORDER BY parent_id NULLS FIRST, sort_order, chapter_code
                """,
                (instance_id,),
            ).fetchall()
        return [_to_chapter(dict(row)) for row in rows]

    def move_chapter(
        self,
        conn: Connection,
        chapter_id: UUID,
        new_parent_id: UUID | None,
        new_sort_order: int,
        actor: str,
    ) -> ProjectTemplateChapterRow:
        if new_parent_id == chapter_id:
            raise ValueError("chapter cannot be moved under itself")
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                UPDATE project_template_chapter
                SET parent_id = %s,
                    sort_order = %s,
                    lock_owner = %s,
                    locked_until = now() + interval '5 minutes',
                    lock_version = lock_version + 1,
                    updated_at = now()
                WHERE id = %s
                  AND (locked_until IS NULL OR locked_until < now() OR lock_owner = %s)
                RETURNING {_CHAPTER_COLUMNS}
                """,
                (new_parent_id, new_sort_order, actor, chapter_id, actor),
            ).fetchone()
        if row is None:
            raise ValueError("chapter is locked by another actor or does not exist")
        return _to_chapter(dict(row))

    def update_chapter(self, conn: Connection, chapter_id: UUID, fields: dict[str, Any]) -> ProjectTemplateChapterRow | None:
        allowed = {
            "parent_id",
            "source_template_item_id",
            "chapter_code",
            "chapter_title",
            "volume_type",
            "sort_order",
            "enabled",
            "chapter_status",
            "tender_requirement_status",
            "metadata_json",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            with conn.cursor(row_factory=dict_row) as cur:
                row = cur.execute(f"SELECT {_CHAPTER_COLUMNS} FROM project_template_chapter WHERE id = %s", (chapter_id,)).fetchone()
            return _to_chapter(dict(row)) if row else None
        sets: list[str] = []
        params: list[Any] = []
        for key, value in updates.items():
            sets.append(f"{key} = %s")
            params.append(_jsonb(value) if key == "metadata_json" else value)
        sets.append("lock_version = lock_version + 1")
        sets.append("updated_at = now()")
        params.append(chapter_id)
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"UPDATE project_template_chapter SET {', '.join(sets)} WHERE id = %s RETURNING {_CHAPTER_COLUMNS}",
                params,
            ).fetchone()
        return _to_chapter(dict(row)) if row else None

    def create_block(self, conn: Connection, chapter_id: UUID, fields: dict[str, Any]) -> ProjectTemplateBlockRow:
        project_id = fields["project_id"]
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                INSERT INTO project_template_block (
                  id, template_chapter_id, project_id, block_type, sort_order, label, content_text, prompt_text,
                  placeholder_key, asset_type, required, render_options_json, condition_json, metadata_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING {_BLOCK_COLUMNS}
                """,
                (
                    uuid4(),
                    chapter_id,
                    project_id,
                    fields["block_type"],
                    fields.get("sort_order", 0),
                    fields.get("label", fields["block_type"]),
                    fields.get("content_text", ""),
                    fields.get("prompt_text", ""),
                    fields.get("placeholder_key"),
                    fields.get("asset_type"),
                    fields.get("required", False),
                    _jsonb(fields.get("render_options_json")),
                    _jsonb(fields.get("condition_json")),
                    _jsonb(fields.get("metadata_json")),
                ),
            ).fetchone()
        assert row is not None
        return _to_block(dict(row))

    def update_block(self, conn: Connection, block_id: UUID, fields: dict[str, Any]) -> ProjectTemplateBlockRow | None:
        allowed = {
            "block_type",
            "sort_order",
            "label",
            "content_text",
            "prompt_text",
            "placeholder_key",
            "asset_type",
            "required",
            "render_options_json",
            "condition_json",
            "metadata_json",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            with conn.cursor(row_factory=dict_row) as cur:
                row = cur.execute(f"SELECT {_BLOCK_COLUMNS} FROM project_template_block WHERE id = %s", (block_id,)).fetchone()
            return _to_block(dict(row)) if row else None
        sets: list[str] = []
        params: list[Any] = []
        for key, value in updates.items():
            sets.append(f"{key} = %s")
            params.append(_jsonb(value) if key in {"render_options_json", "condition_json", "metadata_json"} else value)
        sets.append("updated_at = now()")
        params.append(block_id)
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"UPDATE project_template_block SET {', '.join(sets)} WHERE id = %s RETURNING {_BLOCK_COLUMNS}",
                params,
            ).fetchone()
        return _to_block(dict(row)) if row else None

    def delete_block(self, conn: Connection, block_id: UUID) -> bool:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute("DELETE FROM project_template_block WHERE id = %s RETURNING id", (block_id,)).fetchone()
        return row is not None

    def list_requirement_responses(self, conn: Connection, instance_id: UUID) -> list[ProjectRequirementResponseRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"""
                SELECT {_RESPONSE_COLUMNS}
                FROM project_requirement_response
                WHERE template_instance_id = %s
                ORDER BY created_at, id
                """,
                (instance_id,),
            ).fetchall()
        return [_to_response(dict(row)) for row in rows]

    def upsert_requirement_response(
        self,
        conn: Connection,
        instance_id: UUID,
        requirement_id: UUID,
        template_chapter_id: UUID | None,
        template_block_id: UUID | None,
        fields: dict[str, Any],
    ) -> ProjectRequirementResponseRow:
        project_id = fields["project_id"]
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                INSERT INTO project_requirement_response (
                  id, project_id, template_instance_id, requirement_id, template_chapter_id, template_block_id,
                  response_status, response_text, deviation_note, source_type, source_clarification_id, metadata_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (template_instance_id, requirement_id)
                DO UPDATE SET
                  template_chapter_id = EXCLUDED.template_chapter_id,
                  template_block_id = EXCLUDED.template_block_id,
                  response_status = EXCLUDED.response_status,
                  response_text = EXCLUDED.response_text,
                  deviation_note = EXCLUDED.deviation_note,
                  source_type = EXCLUDED.source_type,
                  source_clarification_id = EXCLUDED.source_clarification_id,
                  metadata_json = EXCLUDED.metadata_json,
                  updated_at = now()
                RETURNING {_RESPONSE_COLUMNS}
                """,
                (
                    uuid4(),
                    project_id,
                    instance_id,
                    requirement_id,
                    template_chapter_id,
                    template_block_id,
                    fields.get("response_status", "unanswered"),
                    fields.get("response_text", ""),
                    fields.get("deviation_note", ""),
                    fields.get("source_type", "tender_requirement"),
                    fields.get("source_clarification_id"),
                    _jsonb(fields.get("metadata_json")),
                ),
            ).fetchone()
        assert row is not None
        return _to_response(dict(row))


    def update_requirement_response(
        self,
        conn: Connection,
        response_id: UUID,
        fields: dict[str, Any],
    ) -> ProjectRequirementResponseRow | None:
        allowed = {
            "template_chapter_id",
            "template_block_id",
            "response_status",
            "response_text",
            "deviation_note",
            "source_type",
            "source_clarification_id",
            "metadata_json",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            with conn.cursor(row_factory=dict_row) as cur:
                row = cur.execute(f"SELECT {_RESPONSE_COLUMNS} FROM project_requirement_response WHERE id = %s", (response_id,)).fetchone()
            return _to_response(dict(row)) if row else None
        sets: list[str] = []
        params: list[Any] = []
        for key, value in updates.items():
            sets.append(f"{key} = %s")
            params.append(_jsonb(value) if key == "metadata_json" else value)
        sets.append("updated_at = now()")
        params.append(response_id)
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"UPDATE project_requirement_response SET {', '.join(sets)} WHERE id = %s RETURNING {_RESPONSE_COLUMNS}",
                params,
            ).fetchone()
        return _to_response(dict(row)) if row else None

    def list_seal_checklist(self, conn: Connection, instance_id: UUID) -> list[ProjectTemplateSealConfirmationRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"""
                SELECT {_SEAL_COLUMNS}
                FROM project_template_seal_confirmation
                WHERE template_instance_id = %s
                ORDER BY created_at, id
                """,
                (instance_id,),
            ).fetchall()
        return [_to_seal(dict(row)) for row in rows]

    def confirm_seal_item(
        self,
        conn: Connection,
        instance_id: UUID,
        seal_block_id: UUID,
        actor: str,
        note: str = "",
    ) -> ProjectTemplateSealConfirmationRow:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                INSERT INTO project_template_seal_confirmation (
                  id, project_id, template_instance_id, seal_block_id, confirmation_status, confirmed_by, confirmed_at, note
                )
                SELECT %s, project_id, %s, %s, 'confirmed', %s, now(), %s
                FROM project_template_block
                WHERE id = %s
                ON CONFLICT (template_instance_id, seal_block_id)
                DO UPDATE SET
                  confirmation_status = 'confirmed',
                  confirmed_by = EXCLUDED.confirmed_by,
                  confirmed_at = now(),
                  note = EXCLUDED.note,
                  updated_at = now()
                RETURNING {_SEAL_COLUMNS}
                """,
                (uuid4(), instance_id, seal_block_id, actor, note, seal_block_id),
            ).fetchone()
        assert row is not None
        return _to_seal(dict(row))

    def try_lock_chapter(self, conn: Connection, chapter_id: UUID, actor: str, ttl_seconds: int) -> ProjectTemplateChapterRow | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                UPDATE project_template_chapter
                SET lock_owner = %s,
                    locked_until = now() + (%s || ' seconds')::interval,
                    lock_version = lock_version + 1,
                    updated_at = now()
                WHERE id = %s
                  AND (locked_until IS NULL OR locked_until < now() OR lock_owner = %s)
                RETURNING {_CHAPTER_COLUMNS}
                """,
                (actor, ttl_seconds, chapter_id, actor),
            ).fetchone()
        return _to_chapter(dict(row)) if row else None

    def release_chapter_lock(self, conn: Connection, chapter_id: UUID, actor: str) -> bool:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                UPDATE project_template_chapter
                SET lock_owner = NULL,
                    locked_until = NULL,
                    lock_version = lock_version + 1,
                    updated_at = now()
                WHERE id = %s AND lock_owner = %s
                RETURNING id
                """,
                (chapter_id, actor),
            ).fetchone()
        return row is not None

    def record_revision(
        self,
        conn: Connection,
        instance_id: UUID,
        change_type: str,
        change_summary: str,
        snapshot_json: dict[str, Any],
        created_by: str | None,
    ) -> ProjectTemplateRevisionRow:
        with conn.cursor(row_factory=dict_row) as cur:
            project_row = cur.execute(
                "SELECT project_id FROM project_template_instance WHERE id = %s",
                (instance_id,),
            ).fetchone()
            if project_row is None:
                raise ValueError("template instance does not exist")
            row = cur.execute(
                f"""
                INSERT INTO project_template_revision (
                  id, template_instance_id, project_id, revision_no, change_type, change_summary, snapshot_json, created_by
                ) VALUES (
                  %s, %s, %s,
                  COALESCE((SELECT MAX(revision_no) + 1 FROM project_template_revision WHERE template_instance_id = %s), 1),
                  %s, %s, %s, %s
                )
                RETURNING {_REVISION_COLUMNS}
                """,
                (
                    uuid4(),
                    instance_id,
                    project_row["project_id"] if isinstance(project_row, dict) else project_row[0],
                    instance_id,
                    change_type,
                    change_summary,
                    _jsonb(snapshot_json),
                    created_by,
                ),
            ).fetchone()
        assert row is not None
        return _to_revision(dict(row))

    def create_promotion_proposal(
        self,
        conn: Connection,
        *,
        instance_id: UUID,
        base_template_package_id: UUID | None,
        project_id: UUID,
        diff_json: dict[str, Any],
        created_by: str | None,
    ) -> TemplatePromotionProposalRow:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                INSERT INTO template_promotion_proposal (
                  id, template_instance_id, base_template_package_id, project_id, diff_json, created_by
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING {_PROPOSAL_COLUMNS}
                """,
                (uuid4(), instance_id, base_template_package_id, project_id, _jsonb(diff_json), created_by),
            ).fetchone()
        assert row is not None
        return _to_proposal(dict(row))

    def list_promotion_proposals(self, conn: Connection, instance_id: UUID) -> list[TemplatePromotionProposalRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"""
                SELECT {_PROPOSAL_COLUMNS}
                FROM template_promotion_proposal
                WHERE template_instance_id = %s
                ORDER BY created_at DESC, id
                """,
                (instance_id,),
            ).fetchall()
        return [_to_proposal(dict(row)) for row in rows]
