"""Structured clause validation for post-AST deterministic checks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from uuid import UUID

PHRASE_SPECS: tuple[tuple[str, str], ...] = (
    ("不应小于", "numeric_constraint"),
    ("不应大于", "numeric_constraint"),
    ("不得超过", "numeric_constraint"),
    ("应符合表", "table_reference"),
    ("应符合", "numeric_constraint"),
    ("见表", "table_reference"),
    ("按表", "table_reference"),
    ("见图", "figure_reference"),
    ("按图", "figure_reference"),
    ("可以", "permissive"),
    ("不宜", "advisory"),
    ("必须", "mandatory"),
    ("不得", "prohibitive"),
    ("严禁", "prohibitive"),
    ("禁止", "prohibitive"),
    ("宜", "advisory"),
    ("可", "permissive"),
    ("应", "mandatory"),
)

_CLAUSE_NO_RE = re.compile(r"^\d+(?:\.\d+)*$")
_DOUBLE_DOT_NUMBER_RE = re.compile(r"\d+\.\.\d+")
_INCOMPLETE_MPA_RE = re.compile(r"(?<!\d)\d+(?:\.\d+)?\s*MP\b")
_REPEATED_PUNCT_RE = re.compile(r"[?？!！~～。]{2,}")
_PHRASE_CATEGORY_MAP = {phrase: category for phrase, category in PHRASE_SPECS}
_PHRASE_PATTERN = re.compile(
    "|".join(
        re.escape(phrase)
        for phrase, _category in sorted(
            PHRASE_SPECS,
            key=lambda item: (-len(item[0]), item[0]),
        )
    )
)


@dataclass(slots=True)
class ValidationIssue:
    code: str
    severity: str
    message: str
    clause_id: UUID | None = None
    clause_no: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    source_ref: str | None = None
    snippet: str | None = None
    details: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "clause_id": str(self.clause_id) if self.clause_id else None,
            "clause_no": self.clause_no,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "source_ref": self.source_ref,
            "snippet": self.snippet,
            "details": self.details,
        }


@dataclass(slots=True)
class PhraseFlag:
    phrase: str
    category: str
    clause_id: UUID | None = None
    clause_no: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "phrase": self.phrase,
            "category": self.category,
            "clause_id": str(self.clause_id) if self.clause_id else None,
            "clause_no": self.clause_no,
        }


@dataclass(slots=True)
class ValidationResult:
    issues: list[ValidationIssue] = field(default_factory=list)
    phrase_flags: list[PhraseFlag] = field(default_factory=list)

    def warning_messages(self, limit: int | None = None) -> list[str]:
        items = self.issues[:limit] if limit is not None else self.issues
        return [issue.message for issue in items]

    def to_dict(self) -> dict[str, object]:
        return {
            "issue_count": len(self.issues),
            "phrase_flag_count": len(self.phrase_flags),
            "issues": [issue.to_dict() for issue in self.issues],
            "phrase_flags": [flag.to_dict() for flag in self.phrase_flags],
        }


def _parse_clause_no(clause_no: str | None) -> tuple[int, ...] | None:
    if not clause_no:
        return None
    candidate = clause_no.strip()
    if not _CLAUSE_NO_RE.match(candidate):
        return None
    return tuple(int(part) for part in candidate.split("."))


def _clause_identity(clause: dict) -> tuple[UUID | None, str | None]:
    return clause.get("id"), clause.get("clause_no")


def _add_issue(
    result: ValidationResult,
    clause: dict,
    *,
    code: str,
    message: str,
    severity: str = "warning",
    details: dict[str, object] | None = None,
) -> None:
    clause_id, clause_no = _clause_identity(clause)
    source_ref = _iter_source_refs(clause)
    result.issues.append(
        ValidationIssue(
            code=code,
            severity=severity,
            message=message,
            clause_id=clause_id,
            clause_no=clause_no,
            page_start=clause.get("page_start"),
            page_end=clause.get("page_end"),
            source_ref=source_ref[0] if source_ref else None,
            snippet=_build_snippet(clause.get("clause_text")),
            details=details or {},
        )
    )


def _build_snippet(raw: object, *, limit: int = 160) -> str | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _iter_source_refs(clause: dict) -> list[str]:
    refs: list[str] = []
    source_ref = clause.get("source_ref")
    if isinstance(source_ref, str) and source_ref.strip():
        refs.append(source_ref.strip())
    source_refs = clause.get("source_refs")
    if isinstance(source_refs, list):
        for source in source_refs:
            if isinstance(source, str) and source.strip():
                refs.append(source.strip())
    return refs


def _validate_numbering(clauses: list[dict], result: ValidationResult) -> None:
    clause_numbers: set[str] = set()
    parsed_sequence: list[tuple[dict, tuple[int, ...]]] = []
    for clause in clauses:
        if clause.get("node_type", "clause") != "clause":
            continue
        clause_no = clause.get("clause_no")
        parsed = _parse_clause_no(clause_no)
        if not parsed:
            continue
        clause_numbers.add(clause_no)
        parsed_sequence.append((clause, parsed))

    for clause, parsed in parsed_sequence:
        if len(parsed) <= 1:
            continue
        parent_no = ".".join(str(part) for part in parsed[:-1])
        if parent_no not in clause_numbers:
            _add_issue(
                result,
                clause,
                code="numbering.missing_parent",
                message=f"Clause {clause.get('clause_no')}: missing parent clause {parent_no}",
                details={"expected_parent": parent_no},
            )

    last_segment_by_parent: dict[tuple[int, ...], int] = {}
    for clause, parsed in parsed_sequence:
        parent_key = parsed[:-1]
        segment = parsed[-1]
        if parent_key not in last_segment_by_parent:
            if segment > 1:
                _add_issue(
                    result,
                    clause,
                    code="numbering.gap",
                    message=f"Clause {clause.get('clause_no')}: numbering starts at {segment}, expected 1",
                    details={"previous_segment": 0, "current_segment": segment},
                )
            last_segment_by_parent[parent_key] = segment
            continue

        previous = last_segment_by_parent[parent_key]
        if segment <= previous:
            _add_issue(
                result,
                clause,
                code="numbering.non_monotonic",
                message=f"Clause {clause.get('clause_no')}: numbering is not increasing",
                details={"previous_segment": previous, "current_segment": segment},
            )
        elif segment - previous > 1:
            _add_issue(
                result,
                clause,
                code="numbering.gap",
                message=f"Clause {clause.get('clause_no')}: numbering gap from {previous} to {segment}",
                details={"previous_segment": previous, "current_segment": segment},
            )

        last_segment_by_parent[parent_key] = segment


def _validate_page_anchors(clauses: list[dict], result: ValidationResult) -> None:
    for clause in clauses:
        start = clause.get("page_start")
        end = clause.get("page_end")

        if start is None and end is None:
            _add_issue(
                result,
                clause,
                code="page.missing_anchor",
                message=f"Clause {clause.get('clause_no')}: missing page anchors",
            )
            continue

        if isinstance(start, int) and start <= 0:
            _add_issue(
                result,
                clause,
                code="page.invalid_start",
                message=f"Clause {clause.get('clause_no')}: page_start must be > 0",
                details={"page_start": start},
            )
        if isinstance(end, int) and end <= 0:
            _add_issue(
                result,
                clause,
                code="page.invalid_end",
                message=f"Clause {clause.get('clause_no')}: page_end must be > 0",
                details={"page_end": end},
            )
        if isinstance(start, int) and isinstance(end, int) and start > end:
            _add_issue(
                result,
                clause,
                code="page.reversed_range",
                message=f"Clause {clause.get('clause_no')}: page_start cannot exceed page_end",
                details={"page_start": start, "page_end": end},
            )


def _validate_table_attachments(clauses: list[dict], result: ValidationResult) -> None:
    for clause in clauses:
        if clause.get("source_type") != "table":
            continue
        source_refs = _iter_source_refs(clause)
        has_table_ref = any(source.startswith("table:") for source in source_refs)
        if not has_table_ref:
            _add_issue(
                result,
                clause,
                code="table.missing_source_ref",
                message=f"Clause {clause.get('clause_no')}: table clause is missing table source_ref",
                details={"source_refs": source_refs},
            )


def _validate_numeric_and_symbol_anomalies(clauses: list[dict], result: ValidationResult) -> None:
    for clause in clauses:
        text = str(clause.get("clause_text") or "")
        if not text:
            continue
        if _DOUBLE_DOT_NUMBER_RE.search(text):
            _add_issue(
                result,
                clause,
                code="numeric.double_dot",
                message=f"Clause {clause.get('clause_no')}: numeric token appears malformed (double dot)",
            )
        if _INCOMPLETE_MPA_RE.search(text):
            _add_issue(
                result,
                clause,
                code="unit.incomplete_token",
                message=f"Clause {clause.get('clause_no')}: unit token appears truncated",
                details={"pattern": "MP"},
            )
        if _REPEATED_PUNCT_RE.search(text):
            _add_issue(
                result,
                clause,
                code="symbol.repeated_punctuation",
                message=f"Clause {clause.get('clause_no')}: repeated punctuation detected",
            )
        if "�" in text:
            _add_issue(
                result,
                clause,
                code="symbol.replacement_character",
                message=f"Clause {clause.get('clause_no')}: replacement character detected",
            )


def _append_phrase_flags(result: ValidationResult, clause: dict) -> None:
    text = str(clause.get("clause_text") or "")
    if not text:
        return
    clause_id, clause_no = _clause_identity(clause)
    seen: set[tuple[str, str]] = set()
    for match in _PHRASE_PATTERN.finditer(text):
        phrase = match.group(0)
        category = _PHRASE_CATEGORY_MAP[phrase]
        marker = (phrase, category)
        if marker in seen:
            continue
        seen.add(marker)
        result.phrase_flags.append(
            PhraseFlag(
                phrase=phrase,
                category=category,
                clause_id=clause_id,
                clause_no=clause_no,
            )
        )


def _detect_phrase_flags(clauses: list[dict], result: ValidationResult) -> None:
    for clause in clauses:
        if clause.get("clause_type") == "commentary":
            continue
        _append_phrase_flags(result, clause)


def validate_clauses(clauses: list[dict]) -> ValidationResult:
    """Run deterministic post-AST validators and phrase extraction."""
    result = ValidationResult()
    if not clauses:
        return result

    _validate_numbering(clauses, result)
    _validate_page_anchors(clauses, result)
    _validate_table_attachments(clauses, result)
    _validate_numeric_and_symbol_anomalies(clauses, result)
    _detect_phrase_flags(clauses, result)
    return result
