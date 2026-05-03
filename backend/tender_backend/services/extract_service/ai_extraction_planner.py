"""Build trackable AI extraction batch plans for tender source chunks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


DEFAULT_MODEL_POLICY = "v4_flash_then_pro"
FLASH_MODEL = "deepseek-v4-flash"
PRO_MODEL = "deepseek-v4-pro"
HIGH_VALUE_CLASSIFICATIONS = {
    "tender_document",
    "tender_notice",
    "technical_specification",
    "qualification_requirement",
    "technical_scoring",
    "business_scoring",
    "scoring",
    "bid_submission_requirement",
}
SKIPPABLE_CLASSIFICATIONS = {"signature"}
SKIPPABLE_EMPTY_FILENAMES = {"合同条款（空白）.doc", "合同条款（空白）.docx"}
TARGET_TOKENS_NORMAL = 50_000
TARGET_TOKENS_HIGH_VALUE = 120_000
MAX_CHUNKS_PER_BATCH = 350


@dataclass(frozen=True)
class ExtractionBatchPlan:
    source_file: str
    batch_index: int
    chunk_ids: list[str]
    tender_document_file_id: UUID | None
    status: str
    chunk_count: int
    input_char_count: int
    estimated_input_tokens: int
    model: str
    reasoning_effort: str | None
    response_format: str = "json_object"
    max_retries: int = 2
    skip_reason: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_repository_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "batch_index": self.batch_index,
            "chunk_ids": self.chunk_ids,
            "tender_document_file_id": self.tender_document_file_id,
            "status": self.status,
            "chunk_count": self.chunk_count,
            "input_char_count": self.input_char_count,
            "estimated_input_tokens": self.estimated_input_tokens,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "response_format": self.response_format,
            "max_retries": self.max_retries,
            "skip_reason": self.skip_reason,
            "metadata_json": self.metadata_json,
        }


def estimate_tokens(text: str) -> int:
    # Conservative mixed Chinese/English approximation. Planning only needs a stable upper bound.
    return max(1, (len(text or "") + 1) // 2)


def _chunk_text_for_budget(chunk: dict[str, Any]) -> str:
    parts = [str(chunk.get("title") or ""), str(chunk.get("text") or "")]
    table = chunk.get("table_json") or {}
    if table.get("rows"):
        parts.append(str(table["rows"]))
    return "\n".join(part for part in parts if part)


def _has_extractable_content(chunk: dict[str, Any]) -> bool:
    table = chunk.get("table_json") or {}
    return bool((chunk.get("text") or "").strip() or table.get("rows"))


def _group_chunks(chunks: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for chunk in chunks:
        source_file = str(chunk.get("source_file") or "unknown")
        groups.setdefault(source_file, []).append(chunk)
    grouped = []
    for source_file, items in groups.items():
        items.sort(key=lambda c: (c.get("sort_order") or 0, str(c.get("id") or "")))
        grouped.append((source_file, items))
    grouped.sort(key=lambda item: item[0])
    return grouped


def _file_classification(chunks: list[dict[str, Any]]) -> str:
    for chunk in chunks:
        value = chunk.get("document_type")
        if value:
            return str(value)
    return "unclassified"


def _is_high_value(source_file: str, classification: str) -> bool:
    if classification in HIGH_VALUE_CLASSIFICATIONS:
        return True
    return any(keyword in source_file for keyword in ("采购文件", "招标文件", "评分", "资格", "递交要求", "技术规范"))


def _skip_reason(source_file: str, chunks: list[dict[str, Any]], classification: str) -> str | None:
    filename = source_file.rsplit("/", 1)[-1]
    if classification in SKIPPABLE_CLASSIFICATIONS:
        return f"classification:{classification}"
    if filename in SKIPPABLE_EMPTY_FILENAMES:
        return "known_blank_contract_template"
    if not any(_has_extractable_content(chunk) for chunk in chunks):
        return "no_extractable_text_or_table_rows"
    return None


def _model_for(*, high_value: bool, model_policy: str) -> tuple[str, str | None]:
    if model_policy == "v4_pro_only":
        return PRO_MODEL, "max"
    if model_policy == "v4_flash_only":
        return FLASH_MODEL, None
    if high_value:
        return PRO_MODEL, "max"
    return FLASH_MODEL, None


def build_extraction_batch_plan(
    chunks: list[dict[str, Any]],
    *,
    model_policy: str = DEFAULT_MODEL_POLICY,
) -> list[ExtractionBatchPlan]:
    plans: list[ExtractionBatchPlan] = []
    for source_file, file_chunks in _group_chunks(chunks):
        classification = _file_classification(file_chunks)
        skip_reason = _skip_reason(source_file, file_chunks, classification)
        tender_document_file_id = next(
            (chunk.get("tender_document_file_id") for chunk in file_chunks if chunk.get("tender_document_file_id")),
            None,
        )
        if skip_reason:
            plans.append(
                ExtractionBatchPlan(
                    source_file=source_file,
                    batch_index=0,
                    chunk_ids=[str(chunk["id"]) for chunk in file_chunks if chunk.get("id")],
                    tender_document_file_id=tender_document_file_id,
                    status="skipped",
                    chunk_count=len(file_chunks),
                    input_char_count=0,
                    estimated_input_tokens=0,
                    model=FLASH_MODEL,
                    reasoning_effort=None,
                    skip_reason=skip_reason,
                    metadata_json={"classification": classification},
                )
            )
            continue

        usable = [chunk for chunk in file_chunks if _has_extractable_content(chunk)]
        high_value = _is_high_value(source_file, classification)
        target_tokens = TARGET_TOKENS_HIGH_VALUE if high_value else TARGET_TOKENS_NORMAL
        model, reasoning_effort = _model_for(high_value=high_value, model_policy=model_policy)

        current: list[dict[str, Any]] = []
        current_chars = 0
        current_tokens = 0
        batch_index = 0

        def flush() -> None:
            nonlocal current, current_chars, current_tokens, batch_index
            if not current:
                return
            plans.append(
                ExtractionBatchPlan(
                    source_file=source_file,
                    batch_index=batch_index,
                    chunk_ids=[str(chunk["id"]) for chunk in current if chunk.get("id")],
                    tender_document_file_id=tender_document_file_id,
                    status="pending",
                    chunk_count=len(current),
                    input_char_count=current_chars,
                    estimated_input_tokens=current_tokens,
                    model=model,
                    reasoning_effort=reasoning_effort,
                    metadata_json={
                        "classification": classification,
                        "high_value": high_value,
                        "model_policy": model_policy,
                    },
                )
            )
            batch_index += 1
            current = []
            current_chars = 0
            current_tokens = 0

        for chunk in usable:
            text = _chunk_text_for_budget(chunk)
            token_count = estimate_tokens(text)
            would_exceed_tokens = current and current_tokens + token_count > target_tokens
            would_exceed_count = current and len(current) >= MAX_CHUNKS_PER_BATCH
            if would_exceed_tokens or would_exceed_count:
                flush()
            current.append(chunk)
            current_chars += len(text)
            current_tokens += token_count
        flush()

    return plans


__all__ = [
    "DEFAULT_MODEL_POLICY",
    "ExtractionBatchPlan",
    "build_extraction_batch_plan",
    "estimate_tokens",
]
