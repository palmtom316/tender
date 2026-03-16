"""Workflow state definitions and transition rules."""

from __future__ import annotations

from enum import StrEnum


class WorkflowState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# Valid state transitions for workflow_run.state
WORKFLOW_TRANSITIONS: dict[WorkflowState, set[WorkflowState]] = {
    WorkflowState.PENDING: {WorkflowState.RUNNING, WorkflowState.CANCELLED},
    WorkflowState.RUNNING: {
        WorkflowState.SUSPENDED,
        WorkflowState.COMPLETED,
        WorkflowState.FAILED,
        WorkflowState.CANCELLED,
    },
    WorkflowState.SUSPENDED: {WorkflowState.RUNNING, WorkflowState.CANCELLED},
    WorkflowState.COMPLETED: set(),
    WorkflowState.FAILED: set(),
    WorkflowState.CANCELLED: set(),
}


def can_transition(current: WorkflowState, target: WorkflowState) -> bool:
    return target in WORKFLOW_TRANSITIONS.get(current, set())
