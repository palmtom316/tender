"""Base classes for the workflow engine.

A Workflow is a sequence of Steps. Each step receives a WorkflowContext
and returns an updated context. Steps can declare suspend points where
the workflow pauses for human input.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import structlog

from tender_backend.workflows.states import (
    StepState,
    WorkflowState,
    can_transition,
)

logger = structlog.stdlib.get_logger(__name__)


@dataclass
class WorkflowContext:
    """Mutable bag of data passed through workflow steps."""

    project_id: str
    workflow_run_id: str = ""
    trace_id: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.trace_id:
            self.trace_id = uuid.uuid4().hex[:16]


@dataclass
class StepResult:
    state: StepState
    message: str = ""
    suspend: bool = False


class WorkflowStep(ABC):
    """Single unit of work within a workflow."""

    name: str

    @abstractmethod
    async def execute(self, ctx: WorkflowContext) -> StepResult:
        ...


class BaseWorkflow(ABC):
    """Orchestrates a sequence of WorkflowStep instances."""

    workflow_name: str
    steps: list[WorkflowStep]

    def __init__(self) -> None:
        self.steps = self._define_steps()

    @abstractmethod
    def _define_steps(self) -> list[WorkflowStep]:
        ...

    async def run(
        self,
        ctx: WorkflowContext,
        *,
        repo: Any = None,
        start_from: str | None = None,
    ) -> WorkflowContext:
        """Execute the workflow, persisting state via repo if provided."""
        run_id = ctx.workflow_run_id or uuid.uuid4().hex
        ctx.workflow_run_id = run_id

        if repo:
            await repo.create_run(
                run_id=run_id,
                workflow_name=self.workflow_name,
                project_id=ctx.project_id,
                trace_id=ctx.trace_id,
            )
            await repo.update_run_state(run_id, WorkflowState.RUNNING)

        started = start_from is None
        for step in self.steps:
            if not started:
                if step.name == start_from:
                    started = True
                else:
                    continue

            step_log_id = uuid.uuid4().hex
            if repo:
                await repo.create_step_log(
                    step_log_id=step_log_id,
                    workflow_run_id=run_id,
                    step_name=step.name,
                    state=StepState.RUNNING,
                )
                await repo.update_run_current_step(run_id, step.name)

            log = logger.bind(
                workflow=self.workflow_name,
                step=step.name,
                run_id=run_id,
            )

            try:
                result = await step.execute(ctx)
            except Exception as exc:
                log.exception("step_failed", error=str(exc))
                if repo:
                    await repo.finish_step_log(step_log_id, StepState.FAILED, str(exc))
                    await repo.update_run_state(run_id, WorkflowState.FAILED, error=str(exc))
                raise

            if repo:
                await repo.finish_step_log(step_log_id, result.state, result.message)

            if result.suspend:
                log.info("workflow_suspended", step=step.name)
                if repo:
                    await repo.update_run_state(run_id, WorkflowState.SUSPENDED)
                    await repo.save_context(run_id, ctx.data)
                return ctx

            if result.state == StepState.FAILED:
                log.warning("step_failed_non_exception", message=result.message)
                if repo:
                    await repo.update_run_state(
                        run_id, WorkflowState.FAILED, error=result.message
                    )
                return ctx

            log.info("step_completed", message=result.message)

        if repo:
            await repo.update_run_state(run_id, WorkflowState.COMPLETED)
            await repo.save_context(run_id, ctx.data)

        return ctx

    async def resume(
        self,
        ctx: WorkflowContext,
        *,
        repo: Any = None,
    ) -> WorkflowContext:
        """Resume a suspended workflow from its current_step."""
        if not repo:
            raise ValueError("Cannot resume without a repository")
        run = await repo.get_run(ctx.workflow_run_id)
        if run["state"] != WorkflowState.SUSPENDED:
            raise ValueError(f"Cannot resume workflow in state: {run['state']}")
        ctx.data = run.get("context_json", {})
        # Find the step AFTER the suspended step
        current_step = run["current_step"]
        step_names = [s.name for s in self.steps]
        idx = step_names.index(current_step)
        next_step = step_names[idx + 1] if idx + 1 < len(step_names) else None
        if next_step is None:
            await repo.update_run_state(ctx.workflow_run_id, WorkflowState.COMPLETED)
            return ctx
        await repo.update_run_state(ctx.workflow_run_id, WorkflowState.RUNNING)
        return await self.run(ctx, repo=repo, start_from=next_step)
