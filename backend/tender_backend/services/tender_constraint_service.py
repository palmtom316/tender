"""Versioned tender constraint set service."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from tender_backend.services.requirement_grouping_service import build_requirement_workbench


class TenderConstraintService:
    def build_from_requirements(self, conn: Connection, *, project_id: UUID) -> dict[str, Any]:
        with conn.cursor(row_factory=dict_row) as cur:
            version_row = cur.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS version FROM tender_constraint_set WHERE project_id = %s",
                (project_id,),
            ).fetchone()
            requirements = cur.execute(
                "SELECT * FROM project_requirement WHERE project_id = %s ORDER BY created_at",
                (project_id,),
            ).fetchall()
            version = int(version_row["version"] if version_row else 1)
            constraint_set = cur.execute(
                """
                INSERT INTO tender_constraint_set (id, project_id, version, status, metadata_json)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *
                """,
                (uuid4(), project_id, version, "draft", Jsonb({"source": "project_requirement"})),
            ).fetchone()
            if constraint_set is None:
                raise RuntimeError("failed to create constraint set")
            workbench = build_requirement_workbench(str(project_id), [dict(row) for row in requirements])
            packages_by_requirement = {
                requirement_id: package
                for package in workbench["packages"]
                for requirement_id in package["requirements"]
            }
            items: list[dict[str, Any]] = []
            for requirement in requirements:
                package = packages_by_requirement.get(str(requirement["id"]), {})
                status = "accepted" if package.get("confirmation_level") == "auto_accept" else "needs_review" if package.get("confirmation_level") == "review" else "draft"
                row = cur.execute(
                    """
                    INSERT INTO tender_constraint_item (
                      id, constraint_set_id, project_id, requirement_id, category, status, confirmation_level,
                      title, constraint_text, source_file, source_locator, metadata_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        uuid4(),
                        constraint_set["id"],
                        project_id,
                        requirement["id"],
                        requirement["category"],
                        status,
                        package.get("confirmation_level") or "auto_accept",
                        requirement["title"],
                        requirement.get("requirement_text") or requirement.get("source_text") or "",
                        requirement.get("source_file"),
                        requirement.get("source_locator"),
                        Jsonb({"package_id": package.get("id"), "has_conflict": package.get("has_conflict", False)}),
                    ),
                ).fetchone()
                if row:
                    items.append(dict(row))
        conn.commit()
        result = dict(constraint_set)
        result["items"] = items
        return result

    def latest(self, conn: Connection, *, project_id: UUID) -> dict[str, Any] | None:
        with conn.cursor(row_factory=dict_row) as cur:
            constraint_set = cur.execute(
                "SELECT * FROM tender_constraint_set WHERE project_id = %s ORDER BY version DESC LIMIT 1",
                (project_id,),
            ).fetchone()
            if constraint_set is None:
                return None
            items = cur.execute(
                "SELECT * FROM tender_constraint_item WHERE constraint_set_id = %s ORDER BY category, created_at",
                (constraint_set["id"],),
            ).fetchall()
        result = dict(constraint_set)
        result["items"] = [dict(row) for row in items]
        return result


__all__ = ["TenderConstraintService"]
