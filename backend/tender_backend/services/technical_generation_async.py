"""Async/pollable technical chapter generation backed by workflow_run."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any
from uuid import UUID, uuid4

from psycopg import connect

from tender_backend.core.config import get_settings
from tender_backend.db.pool import get_pool
from tender_backend.db.repositories.workflow_repo import WorkflowRepository
from tender_backend.services.technical_bid_writer import TechnicalBidWriter
from tender_backend.workflows.states import WorkflowState


def _build_repo(conn=None) -> WorkflowRepository:
    if conn is None:
        repo = WorkflowRepository(connect(get_settings().database_url))
        setattr(repo, "_owned_conn", True)
        return repo
    repo = WorkflowRepository(conn)
    setattr(repo, "_owned_conn", False)
    return repo


def enqueue_technical_generation(
    *,
    project_id: UUID | str,
    chapter_id: UUID | str,
    created_by: str | None,
    rewrite_note: str | None,
    target_pages: int | None,
) -> dict[str, Any]:
    run_id = str(uuid4())
    project_id_str = str(project_id)
    chapter_id_str = str(chapter_id)
    context = {
        "chapter_id": chapter_id_str,
        "created_by": created_by,
        "rewrite_note": rewrite_note,
        "target_pages": target_pages,
        "draft_id": None,
    }

    async def _create_pending_run() -> None:
        repo = _build_repo()
        try:
            await repo.create_run(
                run_id=run_id,
                workflow_name="generate_section_async",
                project_id=project_id_str,
                trace_id=run_id[:16],
            )
            await repo.save_context(run_id, context)
            _commit_if_possible(repo)
        finally:
            _close_if_owned(repo)

    asyncio.run(_create_pending_run())
    start_background_generation(run_id=run_id, project_id=project_id_str)
    return {"run_id": run_id, "state": WorkflowState.PENDING, "chapter_id": chapter_id_str}


def start_background_generation(*, run_id: str, project_id: UUID | str) -> None:
    worker = threading.Thread(
        target=_run_background_generation,
        kwargs={"run_id": run_id, "project_id": str(project_id)},
        daemon=True,
        name=f"technical-generation-{run_id[:8]}",
    )
    worker.start()


def _run_background_generation(*, run_id: str, project_id: str) -> None:
    async def _runner() -> None:
        pool = get_pool(database_url=get_settings().database_url)
        with pool.connection() as conn:
            repo = _build_repo(conn)
            run = await repo.get_run(run_id)
            context = _normalize_context(run.get("context_json"))
            await repo.update_run_state(run_id, WorkflowState.RUNNING)
            await repo.update_run_current_step(run_id, "generate_chapter")
            conn.commit()

            try:
                def _progress_callback(payload: dict[str, Any]) -> None:
                    context["completed_sections"] = int(payload.get("completed_sections") or 0)
                    context["total_sections"] = int(payload.get("total_sections") or 0)
                    context["percent"] = int(payload.get("percent") or 0)
                    context["last_section_code"] = payload.get("section_code")
                    if payload.get("round_index") is not None:
                        context["current_round"] = int(payload.get("round_index") or 0)
                    if payload.get("max_rounds") is not None:
                        context["max_rounds"] = int(payload.get("max_rounds") or 0)
                    context["last_event"] = payload.get("event")
                    if payload.get("draft_id"):
                        context["draft_id"] = str(payload["draft_id"])
                    _persist_progress_sync(repo, run_id, context)

                result = TechnicalBidWriter().generate_chapter(
                    conn,
                    project_id=UUID(project_id),
                    chapter_id=UUID(str(context["chapter_id"])),
                    created_by=context.get("created_by"),
                    rewrite_note=context.get("rewrite_note"),
                    target_pages=context.get("target_pages"),
                    progress_callback=_progress_callback,
                )
                draft = result.get("draft") or {}
                draft_id = draft.get("id")
                context["draft_id"] = str(draft_id) if draft_id else None
                await repo.save_context(run_id, context)
                await repo.update_run_current_step(run_id, "save_draft")
                await repo.update_run_state(run_id, WorkflowState.COMPLETED)
                conn.commit()
            except Exception as exc:
                await repo.update_run_state(run_id, WorkflowState.FAILED, error=str(exc))
                conn.commit()

    asyncio.run(_runner())


def get_technical_generation_run_status(*, project_id: UUID | str, run_id: str) -> dict[str, Any]:
    async def _load() -> dict[str, Any]:
        repo = _build_repo()
        try:
            run = await repo.get_run(run_id)
            if str(run.get("project_id")) != str(project_id):
                raise ValueError(f"Workflow run {run_id} not found")
            return run
        finally:
            _close_if_owned(repo)

    run = asyncio.run(_load())
    context = _normalize_context(run.get("context_json"))
    return {
        "run_id": str(run.get("id") or run_id),
        "state": str(run.get("state")),
        "chapter_id": context.get("chapter_id"),
        "draft_id": context.get("draft_id"),
        "error": run.get("error_message"),
        "current_step": run.get("current_step"),
        "progress": {
            "completed_sections": int(context.get("completed_sections") or 0),
            "total_sections": int(context.get("total_sections") or 0),
            "percent": int(context.get("percent") or 0),
            "last_section_code": context.get("last_section_code"),
            "current_round": int(context.get("current_round") or 0),
            "max_rounds": int(context.get("max_rounds") or 0),
            "last_event": context.get("last_event"),
        },
    }


def _normalize_context(context: Any) -> dict[str, Any]:
    if isinstance(context, dict):
        return context
    if isinstance(context, str):
        try:
            loaded = json.loads(context)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _commit_if_possible(repo: Any) -> None:
    conn = getattr(repo, "_conn", None)
    if conn is not None:
        conn.commit()


def _close_if_owned(repo: Any) -> None:
    if not getattr(repo, "_owned_conn", False):
        return
    conn = getattr(repo, "_conn", None)
    if conn is not None:
        conn.close()


async def _persist_progress(repo: WorkflowRepository, run_id: str, context: dict[str, Any]) -> None:
    await repo.save_context(run_id, context)
    _commit_if_possible(repo)


def _persist_progress_sync(repo: WorkflowRepository, run_id: str, context: dict[str, Any]) -> None:
    repo._conn.execute(
        "UPDATE workflow_run SET context_json = %s, updated_at = now() WHERE id = %s",
        (json.dumps(context), run_id),
    )
    _commit_if_possible(repo)
