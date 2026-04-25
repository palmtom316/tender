"""Serializable artifacts emitted by the standard parsing pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class AiResponseArtifact:
    task_type: str
    prompt_mode: str
    scope_label: str
    prompt: str
    raw_response: str
    parsed_count: int
    source_refs: list[str] = field(default_factory=list)


def serialize_ai_response_artifacts(
    artifacts: list[AiResponseArtifact],
) -> list[dict[str, Any]]:
    return [asdict(artifact) for artifact in artifacts]
