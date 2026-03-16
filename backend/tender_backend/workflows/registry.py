"""Workflow registry — register and look up workflow classes by name."""

from __future__ import annotations

from typing import Type

from tender_backend.workflows.base import BaseWorkflow


_registry: dict[str, Type[BaseWorkflow]] = {}


def register_workflow(cls: Type[BaseWorkflow]) -> Type[BaseWorkflow]:
    """Class decorator to register a workflow."""
    _registry[cls.workflow_name] = cls
    return cls


def get_workflow(name: str) -> Type[BaseWorkflow]:
    if name not in _registry:
        raise KeyError(f"Workflow '{name}' not registered. Available: {list(_registry.keys())}")
    return _registry[name]


def list_workflows() -> list[str]:
    return list(_registry.keys())
