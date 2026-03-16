"""Tool base class with pydantic input validation and unified output."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


@dataclass
class ToolResult:
    """Unified output from any tool execution."""
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class BaseTool(ABC):
    """Base class for all tools used by the workflow agent."""

    name: str
    description: str

    @abstractmethod
    def get_input_schema(self) -> type[BaseModel]:
        """Return the Pydantic model for validating input."""
        ...

    @abstractmethod
    async def execute(self, params: BaseModel) -> ToolResult:
        """Execute the tool with validated parameters."""
        ...

    def to_schema(self) -> dict[str, Any]:
        """Export tool definition as a JSON-serializable schema."""
        schema_cls = self.get_input_schema()
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": schema_cls.model_json_schema(),
        }
