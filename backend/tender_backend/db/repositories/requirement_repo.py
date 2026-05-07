"""Repository for project_requirement table."""

from __future__ import annotations

from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class RequirementRepository:
    def create(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        category: str,
        title: str,
        requirement_text: str | None = None,
        source_text: str | None = None,
        source_file: str | None = None,
        source_locator: str | None = None,
        confidence: float | None = None,
        is_veto: bool | None = None,
        requires_human_confirm: bool | None = None,
        ignored_for_pricing: bool | None = None,
        source_chunk_id: UUID | None = None,
        source_metadata: dict | None = None,
        is_hard_constraint: bool | None = None,
    ) -> dict:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO project_requirement
                    (id, project_id, category, title, requirement_text, source_text,
                     source_file, source_locator, confidence, is_veto,
                     requires_human_confirm, ignored_for_pricing, source_chunk_id,
                     source_metadata, is_hard_constraint)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    uuid4(),
                    project_id,
                    category,
                    title,
                    requirement_text,
                    source_text,
                    source_file,
                    source_locator,
                    confidence,
                    is_veto if is_veto is not None else category == "veto",
                    requires_human_confirm if requires_human_confirm is not None else category == "veto",
                    ignored_for_pricing if ignored_for_pricing is not None else False,
                    source_chunk_id,
                    Jsonb(source_metadata or {}),
                    is_hard_constraint if is_hard_constraint is not None else False,
                ),
            ).fetchone()
        conn.commit()
        return row  # type: ignore[return-value]

    def create_many(self, conn: Connection, *, project_id: UUID, requirements: list[dict]) -> list[dict]:
        rows: list[dict] = []
        with conn.cursor(row_factory=dict_row) as cur:
            for requirement in requirements:
                source_chunk_id = requirement.get("source_chunk_id")
                row = cur.execute(
                    """
                    INSERT INTO project_requirement
                        (id, project_id, category, title, requirement_text, source_text,
                         source_file, source_locator, confidence, is_veto,
                         requires_human_confirm, ignored_for_pricing, source_chunk_id,
                         source_metadata, is_hard_constraint, extraction_method)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (project_id, category, source_chunk_id, source_locator)
                    WHERE source_chunk_id IS NOT NULL
                    DO UPDATE SET
                      title = EXCLUDED.title,
                      requirement_text = EXCLUDED.requirement_text,
                      source_text = EXCLUDED.source_text,
                      source_file = EXCLUDED.source_file,
                      confidence = EXCLUDED.confidence,
                      is_veto = EXCLUDED.is_veto,
                      requires_human_confirm = EXCLUDED.requires_human_confirm,
                      ignored_for_pricing = EXCLUDED.ignored_for_pricing,
                      source_metadata = EXCLUDED.source_metadata,
                      is_hard_constraint = EXCLUDED.is_hard_constraint,
                      extraction_method = CASE
                          WHEN project_requirement.extraction_method = EXCLUDED.extraction_method
                              THEN project_requirement.extraction_method
                          ELSE 'merged'
                      END,
                      updated_at = now()
                    RETURNING *
                    """,
                    (
                        uuid4(),
                        project_id,
                        requirement["category"],
                        requirement["title"],
                        requirement.get("requirement_text"),
                        requirement.get("source_text"),
                        requirement.get("source_file"),
                        requirement.get("source_locator"),
                        requirement.get("confidence"),
                        requirement.get("is_veto", requirement["category"] == "veto"),
                        requirement.get("requires_human_confirm", requirement["category"] == "veto"),
                        requirement.get("ignored_for_pricing", False),
                        UUID(source_chunk_id) if source_chunk_id else None,
                        Jsonb(requirement.get("source_metadata") or {}),
                        requirement.get("is_hard_constraint", False),
                        requirement.get("extraction_method", "keyword"),
                    ),
                ).fetchone()
                if row is not None:
                    rows.append(dict(row))
        conn.commit()
        return rows

    def list_by_project(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        category: str | None = None,
        review_status: str | None = None,
        human_confirmed: bool | None = None,
        requires_human_confirm: bool | None = None,
        is_veto: bool | None = None,
        is_hard_constraint: bool | None = None,
    ) -> list[dict]:
        query = "SELECT * FROM project_requirement WHERE project_id = %s"
        params: list = [project_id]
        if category:
            query += " AND category = %s"
            params.append(category)
        if review_status:
            query += " AND review_status = %s"
            params.append(review_status)
        if human_confirmed is not None:
            query += " AND human_confirmed = %s"
            params.append(human_confirmed)
        if requires_human_confirm is not None:
            query += " AND requires_human_confirm = %s"
            params.append(requires_human_confirm)
        if is_veto is not None:
            query += " AND is_veto = %s"
            params.append(is_veto)
        if is_hard_constraint is not None:
            query += " AND is_hard_constraint = %s"
            params.append(is_hard_constraint)
        query += " ORDER BY created_at"
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def update(
        self,
        conn: Connection,
        *,
        requirement_id: UUID,
        fields: dict,
    ) -> dict | None:
        allowed = {
            "category",
            "title",
            "requirement_text",
            "source_text",
            "source_file",
            "source_locator",
            "confidence",
            "is_veto",
            "requires_human_confirm",
            "human_confirmed",
            "ignored_for_pricing",
            "applies_to_chapter",
            "review_status",
            "review_note",
            "source_metadata",
            "is_hard_constraint",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            with conn.cursor(row_factory=dict_row) as cur:
                row = cur.execute("SELECT * FROM project_requirement WHERE id = %s", (requirement_id,)).fetchone()
            return dict(row) if row else None

        sets: list[str] = []
        values: list = []
        for key, value in updates.items():
            sets.append(f"{key} = %s")
            values.append(Jsonb(value) if key == "source_metadata" else value)
        sets.append("updated_at = now()")
        values.append(requirement_id)

        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                UPDATE project_requirement
                SET {', '.join(sets)}
                WHERE id = %s
                RETURNING *
                """,
                values,
            ).fetchone()
        conn.commit()
        return dict(row) if row else None

    def merge(
        self,
        conn: Connection,
        *,
        target_requirement_id: UUID,
        source_requirement_ids: list[UUID],
    ) -> dict | None:
        if not source_requirement_ids:
            return self.update(conn, requirement_id=target_requirement_id, fields={})
        with conn.cursor(row_factory=dict_row) as cur:
            target = cur.execute(
                "SELECT * FROM project_requirement WHERE id = %s",
                (target_requirement_id,),
            ).fetchone()
            if target is None:
                return None
            sources = cur.execute(
                """
                SELECT *
                FROM project_requirement
                WHERE id = ANY(%s)
                  AND project_id = %s
                ORDER BY created_at
                """,
                (source_requirement_ids, target["project_id"]),
            ).fetchall()
            if len(sources) != len(source_requirement_ids):
                return None

            merged_texts = [
                str(row.get("requirement_text") or row.get("source_text") or row.get("title") or "").strip()
                for row in [target, *sources]
            ]
            merged_text = "\n".join(text for text in merged_texts if text)
            source_files = [
                str(row.get("source_file") or "")
                for row in [target, *sources]
                if row.get("source_file")
            ]
            source_locators = [
                str(row.get("source_locator") or "")
                for row in [target, *sources]
                if row.get("source_locator")
            ]
            metadata = dict(target.get("source_metadata") or {})
            metadata["merged_from_requirement_ids"] = [str(row["id"]) for row in sources]

            row = cur.execute(
                """
                UPDATE project_requirement
                SET requirement_text = %s,
                    source_text = %s,
                    source_file = %s,
                    source_locator = %s,
                    confidence = LEAST(1.0, COALESCE(confidence, 0.0) + 0.05),
                    is_veto = is_veto OR %s,
                    requires_human_confirm = TRUE,
                    is_hard_constraint = is_hard_constraint OR %s,
                    source_metadata = %s,
                    updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (
                    merged_text,
                    merged_text,
                    "；".join(dict.fromkeys(source_files)) or target.get("source_file"),
                    "；".join(dict.fromkeys(source_locators)) or target.get("source_locator"),
                    any(bool(row.get("is_veto")) for row in sources),
                    any(bool(row.get("is_hard_constraint")) for row in sources),
                    Jsonb(metadata),
                    target_requirement_id,
                ),
            ).fetchone()
            cur.execute(
                """
                UPDATE project_requirement
                SET review_status = 'merged',
                    review_note = %s,
                    updated_at = now()
                WHERE id = ANY(%s)
                """,
                (f"merged into {target_requirement_id}", source_requirement_ids),
            )
        conn.commit()
        return dict(row) if row else None

    def confirm(
        self,
        conn: Connection,
        *,
        requirement_id: UUID,
        confirmed_by: str,
    ) -> dict | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                UPDATE project_requirement
                SET human_confirmed = TRUE, confirmed_by = %s, confirmed_at = now(), updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (confirmed_by, requirement_id),
            ).fetchone()
        conn.commit()
        return dict(row) if row else None

    def confirm_if_in_project(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        requirement_id: UUID,
        confirmed_by: str,
    ) -> dict | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                UPDATE project_requirement
                SET human_confirmed = TRUE, confirmed_by = %s, confirmed_at = now(), updated_at = now()
                WHERE id = %s
                  AND project_id = %s
                RETURNING *
                """,
                (confirmed_by, requirement_id, project_id),
            ).fetchone()
        conn.commit()
        return dict(row) if row else None

    def reject(
        self,
        conn: Connection,
        *,
        requirement_id: UUID,
        review_note: str | None = None,
    ) -> dict | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                UPDATE project_requirement
                SET review_status = 'rejected',
                    review_note = %s,
                    human_confirmed = FALSE,
                    updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (review_note, requirement_id),
            ).fetchone()
        conn.commit()
        return dict(row) if row else None

    def unconfirmed_veto_count(self, conn: Connection, *, project_id: UUID) -> int:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                SELECT COUNT(*) AS c FROM project_requirement
                WHERE project_id = %s
                  AND (category = 'veto' OR is_veto = TRUE)
                  AND human_confirmed = FALSE
                """,
                (project_id,),
            ).fetchone()
        return row["c"] if row else 0  # type: ignore[index]
