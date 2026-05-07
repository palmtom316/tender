"""Repository for bid outline planning tables."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class BidOutlineRepository:
    def replace_for_project(self, conn: Connection, *, project_id: UUID, outline: dict[str, Any]) -> dict[str, Any]:
        with conn.cursor(row_factory=dict_row) as cur:
            outline_row = cur.execute(
                """
                INSERT INTO bid_outline (id, project_id, outline_name, status, metadata_json)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    uuid4(),
                    project_id,
                    outline.get("outline_name") or "投标文件目录草案",
                    outline.get("status") or "draft",
                    Jsonb(outline.get("metadata_json") or {}),
                ),
            ).fetchone()
            if outline_row is None:
                raise RuntimeError("failed to create bid outline")

            volume_titles = {
                "qualification": "资格审查册",
                "business": "资格商务分册",
                "technical": "技术分册",
                "pricing": "报价分册（外部挂载）",
                "attachments": "附件分册",
            }
            volume_rows: dict[str, dict[str, Any]] = {}
            for sort_order, volume_type in enumerate(volume_titles, start=1):
                volume_row = cur.execute(
                    """
                    INSERT INTO bid_volume (id, project_id, bid_outline_id, volume_type, title, strategy, sort_order)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (bid_outline_id, volume_type)
                    DO UPDATE SET title = EXCLUDED.title, sort_order = EXCLUDED.sort_order, updated_at = now()
                    RETURNING *
                    """,
                    (
                        uuid4(),
                        project_id,
                        outline_row["id"],
                        volume_type,
                        volume_titles[volume_type],
                        "external_attached" if volume_type == "pricing" else "generated",
                        sort_order,
                    ),
                ).fetchone()
                if volume_row:
                    volume_rows[volume_type] = dict(volume_row)

            chapters: list[dict[str, Any]] = []
            for chapter in outline.get("chapters") or []:
                chapter_row = cur.execute(
                    """
                    INSERT INTO bid_chapter (
                      id, bid_outline_id, project_id, parent_id, chapter_code,
                      chapter_title, volume_type, volume_id, sort_order, outline_md, metadata_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        uuid4(),
                        outline_row["id"],
                        project_id,
                        chapter.get("parent_id"),
                        chapter["chapter_code"],
                        chapter["chapter_title"],
                        chapter["volume_type"],
                        volume_rows.get(chapter["volume_type"], {}).get("id"),
                        chapter.get("sort_order", 0),
                        chapter.get("outline_md") or "",
                        Jsonb(chapter.get("metadata_json") or {}),
                    ),
                ).fetchone()
                if chapter_row is None:
                    continue
                chapter_dict = dict(chapter_row)
                mappings: list[dict[str, Any]] = []
                for mapping in chapter.get("requirement_mappings") or []:
                    mapping_row = cur.execute(
                        """
                        INSERT INTO bid_chapter_requirement (
                          id, bid_chapter_id, requirement_id, mapping_reason, priority_level
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (bid_chapter_id, requirement_id)
                        DO UPDATE SET
                          mapping_reason = EXCLUDED.mapping_reason,
                          priority_level = EXCLUDED.priority_level
                        RETURNING *
                        """,
                        (
                            uuid4(),
                            chapter_row["id"],
                            mapping["requirement_id"],
                            mapping.get("mapping_reason"),
                            mapping.get("priority_level") or "normal",
                        ),
                    ).fetchone()
                    if mapping_row is not None:
                        mappings.append(dict(mapping_row))
                chapter_dict["requirement_mappings"] = mappings
                chapter_dict["requirement_ids"] = [row["requirement_id"] for row in mappings]
                chapters.append(chapter_dict)
        conn.commit()
        result = dict(outline_row)
        result["volumes"] = list(volume_rows.values())
        result["chapters"] = chapters
        return result

    def get_latest_by_project(self, conn: Connection, *, project_id: UUID) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            outline = cur.execute(
                """
                SELECT *
                FROM bid_outline
                WHERE project_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
            if outline is None:
                return None
            chapters = cur.execute(
                """
                SELECT *
                FROM bid_chapter
                WHERE bid_outline_id = %s
                ORDER BY sort_order, chapter_code
                """,
                (outline["id"],),
            ).fetchall()
            volumes = cur.execute(
                """
                SELECT *
                FROM bid_volume
                WHERE bid_outline_id = %s
                ORDER BY sort_order, volume_type
                """,
                (outline["id"],),
            ).fetchall()
            chapter_rows = [dict(row) for row in chapters]
            chapter_ids = [row["id"] for row in chapter_rows]
            mappings_by_chapter: dict[UUID, list[dict[str, Any]]] = {chapter_id: [] for chapter_id in chapter_ids}
            if chapter_ids:
                mappings = cur.execute(
                    """
                    SELECT bcr.*, pr.category, pr.title AS requirement_title, pr.is_veto, pr.is_hard_constraint
                    FROM bid_chapter_requirement bcr
                    JOIN project_requirement pr ON pr.id = bcr.requirement_id
                    WHERE bcr.bid_chapter_id = ANY(%s)
                    ORDER BY bcr.created_at
                    """,
                    (chapter_ids,),
                ).fetchall()
                for mapping in mappings:
                    mappings_by_chapter.setdefault(mapping["bid_chapter_id"], []).append(dict(mapping))
        for chapter in chapter_rows:
            mappings = mappings_by_chapter.get(chapter["id"], [])
            chapter["requirement_mappings"] = mappings
            chapter["requirement_ids"] = [row["requirement_id"] for row in mappings]
        result = dict(outline)
        result["volumes"] = [dict(row) for row in volumes]
        result["chapters"] = chapter_rows
        return result

    def update_chapter(self, conn: Connection, *, chapter_id: UUID, fields: dict[str, Any]) -> dict | None:
        allowed = {"chapter_code", "chapter_title", "volume_type", "sort_order", "outline_md", "metadata_json"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            with conn.cursor(row_factory=dict_row) as cur:
                row = cur.execute("SELECT * FROM bid_chapter WHERE id = %s", (chapter_id,)).fetchone()
            return dict(row) if row else None

        sets: list[str] = []
        values: list[Any] = []
        for key, value in updates.items():
            sets.append(f"{key} = %s")
            values.append(Jsonb(value) if key == "metadata_json" else value)
        sets.append("updated_at = now()")
        values.append(chapter_id)
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                UPDATE bid_chapter
                SET {', '.join(sets)}
                WHERE id = %s
                RETURNING *
                """,
                values,
            ).fetchone()
        conn.commit()
        return dict(row) if row else None

    def replace_chapter_requirements(
        self,
        conn: Connection,
        *,
        chapter_id: UUID,
        requirement_ids: list[UUID],
        mapping_reason: str = "人工调整章节约束映射",
        priority_level: str = "normal",
    ) -> dict | None:
        with conn.cursor(row_factory=dict_row) as cur:
            chapter = cur.execute("SELECT * FROM bid_chapter WHERE id = %s", (chapter_id,)).fetchone()
            if chapter is None:
                return None
            cur.execute("DELETE FROM bid_chapter_requirement WHERE bid_chapter_id = %s", (chapter_id,))
            mappings: list[dict[str, Any]] = []
            for requirement_id in requirement_ids:
                row = cur.execute(
                    """
                    INSERT INTO bid_chapter_requirement (
                      id, bid_chapter_id, requirement_id, mapping_reason, priority_level
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (uuid4(), chapter_id, requirement_id, mapping_reason, priority_level),
                ).fetchone()
                if row is not None:
                    mappings.append(dict(row))
        conn.commit()
        result = dict(chapter)
        result["requirement_mappings"] = mappings
        result["requirement_ids"] = [row["requirement_id"] for row in mappings]
        return result
