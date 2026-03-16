"""Tool registry — register, find, and export tool schemas."""

from __future__ import annotations

from typing import Type

from tender_backend.tools.base import BaseTool


_registry: dict[str, BaseTool] = {}


def register_tool(tool: BaseTool) -> BaseTool:
    """Register a tool instance."""
    _registry[tool.name] = tool
    return tool


def get_tool(name: str) -> BaseTool:
    if name not in _registry:
        raise KeyError(f"Tool '{name}' not registered. Available: {list(_registry.keys())}")
    return _registry[name]


def list_tools() -> list[str]:
    return list(_registry.keys())


def export_all_schemas() -> list[dict]:
    """Export all registered tool schemas for LLM function calling."""
    return [tool.to_schema() for tool in _registry.values()]
