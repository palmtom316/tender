"""Project setup metadata and guarded workflow transitions."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from tender_backend.db.repositories.project_repository import Project, ProjectRepository


WORKFLOW_TRANSITIONS: dict[str, set[str]] = {
    "created": {"source_uploaded", "constraints_pending_confirmation", "abandoned"},
    "source_uploaded": {"analysis_running", "constraints_pending_confirmation", "abandoned"},
    "analysis_running": {"constraints_pending_confirmation", "abandoned"},
    "constraints_pending_confirmation": {"outline_pending_confirmation", "abandoned"},
    "outline_pending_confirmation": {"drafting", "abandoned"},
    "drafting": {"draft_reviewing", "revision_pending_confirmation", "abandoned"},
    "draft_reviewing": {"revision_pending_confirmation", "compliance_check", "abandoned"},
    "revision_pending_confirmation": {"drafting", "compliance_check", "abandoned"},
    "compliance_check": {"final_layout", "revision_pending_confirmation", "abandoned"},
    "final_layout": {"external_pricing_merge", "final_packaged", "abandoned"},
    "external_pricing_merge": {"final_packaged", "abandoned"},
    "final_packaged": {"bid_sealed", "bid_submitted", "archived", "abandoned"},
    "bid_sealed": {"bid_submitted", "abandoned"},
    "bid_submitted": {"bid_opened", "archived", "abandoned"},
    "bid_opened": {"bid_evaluating", "bid_clarification", "awarded", "not_awarded", "archived"},
    "bid_evaluating": {"bid_clarification", "awarded", "not_awarded", "archived"},
    "bid_clarification": {"bid_evaluating", "awarded", "not_awarded", "archived"},
    "awarded": {"contract_signed", "archived"},
    "not_awarded": {"archived"},
    "contract_signed": {"archived"},
    "abandoned": {"archived"},
    "archived": set(),
}


class ProjectSetupService:
    def __init__(self, repo: ProjectRepository | None = None) -> None:
        self.repo = repo or ProjectRepository()

    def create_project(
        self,
        conn: Connection,
        *,
        name: str,
        user_id: UUID | None,
        metadata: dict[str, Any] | None = None,
        actor: str | None = None,
    ) -> Project:
        project = self.repo.create_for_user(conn, name=name, user_id=user_id, metadata=metadata)
        self.record_event(
            conn,
            project_id=project.id,
            previous_status=None,
            next_status=project.workflow_status or "created",
            actor=actor,
            reason="project created",
        )
        return project

    def transition(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        next_status: str,
        actor: str | None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Project:
        project = self.repo.get(conn, project_id=project_id)
        if project is None:
            raise ValueError("project not found")
        previous_status = project.workflow_status or project.status or "created"
        allowed = WORKFLOW_TRANSITIONS.get(previous_status, set())
        if next_status != previous_status and next_status not in allowed:
            raise ValueError(f"invalid workflow transition: {previous_status} -> {next_status}")
        updated = self.repo.update(conn, project_id=project_id, fields={"workflow_status": next_status, "status": next_status})
        if updated is None:
            raise ValueError("project not found")
        self.record_event(
            conn,
            project_id=project_id,
            previous_status=previous_status,
            next_status=next_status,
            actor=actor,
            reason=reason,
            metadata=metadata,
        )
        return updated

    def record_event(
        self,
        conn: Connection,
        *,
        project_id: UUID,
        previous_status: str | None,
        next_status: str,
        actor: str | None,
        reason: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO bid_workflow_event (id, project_id, previous_status, next_status, actor, reason, metadata_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (uuid4(), project_id, previous_status, next_status, actor, reason, Jsonb(metadata or {})),
            ).fetchone()
        conn.commit()
        return dict(row) if row else {}

    def list_events(self, conn: Connection, *, project_id: UUID) -> list[dict[str, Any]]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT *
                FROM bid_workflow_event
                WHERE project_id = %s
                ORDER BY created_at DESC
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]


__all__ = ["ProjectSetupService", "WORKFLOW_TRANSITIONS"]
