from __future__ import annotations

from tender_backend.services.norm_service.parse_artifacts import (
    AiResponseArtifact,
    serialize_ai_response_artifacts,
)


def test_ai_response_artifact_serializes_replayable_input_and_output() -> None:
    artifact = AiResponseArtifact(
        task_type="clause_enrichment_batch",
        prompt_mode="summarize_tags",
        scope_label="3.1 一般规定",
        prompt="prompt text",
        raw_response='[{"node_key":"3.1.1"}]',
        parsed_count=1,
        source_refs=["document_section:s1"],
    )

    assert serialize_ai_response_artifacts([artifact]) == [
        {
            "task_type": "clause_enrichment_batch",
            "prompt_mode": "summarize_tags",
            "scope_label": "3.1 一般规定",
            "prompt": "prompt text",
            "raw_response": '[{"node_key":"3.1.1"}]',
            "parsed_count": 1,
            "source_refs": ["document_section:s1"],
        }
    ]
