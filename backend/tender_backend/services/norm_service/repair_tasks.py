"""Repair task planning for local VL compensation."""

from __future__ import annotations

from dataclasses import dataclass, field

from tender_backend.services.norm_service.validation import ValidationIssue

_SYMBOL_NUMERIC_PREFIXES = ("numeric.", "symbol.", "unit.")


@dataclass(slots=True)
class RepairTask:
    task_type: str
    source_ref: str
    page_start: int | None
    page_end: int | None
    input_payload: dict[str, object] = field(default_factory=dict)
    trigger_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "task_type": self.task_type,
            "source_ref": self.source_ref,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "input_payload": self.input_payload,
            "trigger_reasons": self.trigger_reasons,
        }


def _iter_source_refs(clause: dict) -> list[str]:
    refs: list[str] = []
    source_ref = clause.get("source_ref")
    if isinstance(source_ref, str) and source_ref.strip():
        refs.append(source_ref.strip())
    source_refs = clause.get("source_refs")
    if isinstance(source_refs, list):
        for value in source_refs:
            if isinstance(value, str) and value.strip():
                refs.append(value.strip())
    return refs


def _merge_unique(values: list[str], additions: list[str]) -> list[str]:
    merged = list(values)
    seen = set(values)
    for item in additions:
        if item not in seen:
            seen.add(item)
            merged.append(item)
    return merged


def _merge_page_start(current: int | None, incoming: int | None) -> int | None:
    if current is None:
        return incoming
    if incoming is None:
        return current
    return min(current, incoming)


def _merge_page_end(current: int | None, incoming: int | None) -> int | None:
    if current is None:
        return incoming
    if incoming is None:
        return current
    return max(current, incoming)


def _merge_input_payload(current: dict[str, object], incoming: dict[str, object]) -> dict[str, object]:
    merged = dict(current)
    for key, value in incoming.items():
        if value in (None, "", [], {}):
            continue
        existing = merged.get(key)
        if isinstance(existing, list) and isinstance(value, list):
            merged[key] = _merge_unique([str(item) for item in existing], [str(item) for item in value])
            continue
        if existing in (None, "", [], {}):
            merged[key] = value
    return merged


def _deduplicate_tasks(tasks: list[RepairTask]) -> list[RepairTask]:
    deduplicated: dict[tuple[str, str], RepairTask] = {}
    for task in tasks:
        key = (task.task_type, task.source_ref)
        existing = deduplicated.get(key)
        if existing is None:
            deduplicated[key] = task
            continue
        existing.page_start = _merge_page_start(existing.page_start, task.page_start)
        existing.page_end = _merge_page_end(existing.page_end, task.page_end)
        existing.trigger_reasons = _merge_unique(existing.trigger_reasons, task.trigger_reasons)
        existing.input_payload = _merge_input_payload(existing.input_payload, task.input_payload)
    return list(deduplicated.values())


def _table_tasks_from_clauses(clauses: list[dict]) -> list[RepairTask]:
    tasks: list[RepairTask] = []
    for clause in clauses:
        if clause.get("source_type") != "table":
            continue
        table_ref = next((ref for ref in _iter_source_refs(clause) if ref.startswith("table:")), None)
        if not table_ref:
            continue
        tasks.append(
            RepairTask(
                task_type="table_repair",
                source_ref=table_ref,
                page_start=clause.get("page_start"),
                page_end=clause.get("page_end"),
                input_payload={
                    "clause_no": clause.get("clause_no"),
                    "clause_text": clause.get("clause_text"),
                    "source_type": clause.get("source_type"),
                    "source_refs": _iter_source_refs(clause),
                },
                trigger_reasons=["table.high_recall"],
            )
        )
    return tasks


def _is_symbol_numeric_issue(issue: ValidationIssue) -> bool:
    return issue.code.startswith(_SYMBOL_NUMERIC_PREFIXES)


def _symbol_numeric_tasks_from_issues(issues: list[ValidationIssue]) -> list[RepairTask]:
    tasks: list[RepairTask] = []
    for issue in issues:
        if not _is_symbol_numeric_issue(issue):
            continue
        if not issue.source_ref or issue.source_ref.startswith("table:"):
            continue
        tasks.append(
            RepairTask(
                task_type="symbol_numeric_repair",
                source_ref=issue.source_ref,
                page_start=issue.page_start,
                page_end=issue.page_end,
                input_payload={
                    "issue_codes": [issue.code],
                    "snippets": [issue.snippet] if issue.snippet else [],
                },
                trigger_reasons=[issue.code],
            )
        )
    return tasks


def build_repair_tasks(clauses: list[dict], issues: list[ValidationIssue]) -> list[RepairTask]:
    """Plan high-recall local VL repair tasks from projected clauses and validation issues."""
    tasks: list[RepairTask] = []
    tasks.extend(_table_tasks_from_clauses(clauses))
    tasks.extend(_symbol_numeric_tasks_from_issues(issues))
    return _deduplicate_tasks(tasks)
