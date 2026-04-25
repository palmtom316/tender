from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from uuid import UUID

from tender_backend.services.norm_service import norm_processor
from tender_backend.services.norm_service.block_segments import BlockSegment
from tender_backend.services.norm_service.skill_plugins import (
    ParseSkillContext,
    ParseSkillResult,
    run_parse_skill_hooks,
)


@dataclass
class _Plugin:
    name: str
    hooks: tuple[str, ...]
    result: ParseSkillResult
    calls: list[str]

    def run(self, hook: str, context: ParseSkillContext) -> ParseSkillResult:
        self.calls.append(hook)
        return self.result


def _context() -> ParseSkillContext:
    return ParseSkillContext(
        standard={"standard_code": "GB50148-2010"},
        document_id="document-1",
        document_asset=SimpleNamespace(),
        raw_sections=[],
        tables=[],
    )


def test_active_mineru_skill_runs_preflight_cleanup() -> None:
    plugin = _Plugin(
        name="mineru-standard-bundle",
        hooks=("preflight_parse_asset", "cleanup_parse_asset"),
        result=ParseSkillResult(status="pass", metrics={"section_page_coverage_ratio": 1.0}),
        calls=[],
    )

    results = run_parse_skill_hooks(
        hook="preflight_parse_asset",
        context=_context(),
        plugins=[plugin],
        active_skill_names={"mineru-standard-bundle"},
    )

    assert [result.skill_name for result in results] == ["mineru-standard-bundle"]
    assert results[0].status == "pass"
    assert plugin.calls == ["preflight_parse_asset"]


def test_inactive_skill_is_not_executed() -> None:
    plugin = _Plugin(
        name="mineru-standard-bundle",
        hooks=("preflight_parse_asset",),
        result=ParseSkillResult(status="pass"),
        calls=[],
    )

    results = run_parse_skill_hooks(
        hook="preflight_parse_asset",
        context=_context(),
        plugins=[plugin],
        active_skill_names=set(),
    )

    assert results == []
    assert plugin.calls == []


def test_preflight_failure_is_reported_before_ai() -> None:
    plugin = _Plugin(
        name="mineru-standard-bundle",
        hooks=("preflight_parse_asset",),
        result=ParseSkillResult(status="fail", messages=["low section coverage"]),
        calls=[],
    )

    results = run_parse_skill_hooks(
        hook="preflight_parse_asset",
        context=_context(),
        plugins=[plugin],
        active_skill_names={"mineru-standard-bundle"},
    )

    assert results[0].status == "fail"
    assert results[0].blocking is True
    assert results[0].messages == ["low section coverage"]


def test_recovery_diagnostics_does_not_mutate_clauses() -> None:
    clauses = [{"clause_no": "3.1.1", "clause_text": "原文"}]
    plugin = _Plugin(
        name="standard-parse-recovery",
        hooks=("recovery_diagnostics",),
        result=ParseSkillResult(status="pass", metrics={"issue_classification_count": 1}),
        calls=[],
    )
    context = _context()
    context.clauses = clauses

    results = run_parse_skill_hooks(
        hook="recovery_diagnostics",
        context=context,
        plugins=[plugin],
        active_skill_names={"standard-parse-recovery"},
    )

    assert results[0].metrics == {"issue_classification_count": 1}
    assert clauses == [{"clause_no": "3.1.1", "clause_text": "原文"}]


def test_process_standard_ai_stops_before_ai_when_active_preflight_fails(monkeypatch) -> None:
    document_id = "dddddddd-dddd-dddd-dddd-dddddddddddd"
    standard_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    plugin = _Plugin(
        name="mineru-standard-bundle",
        hooks=("preflight_parse_asset",),
        result=ParseSkillResult(
            status="fail",
            messages=["low section coverage"],
            metrics={"section_page_coverage_ratio": 0.2},
        ),
        calls=[],
    )

    monkeypatch.setattr(norm_processor._std_repo, "get_standard", lambda conn, current_standard_id: {
        "id": standard_id,
        "standard_code": "GB 50150-2016",
    })
    monkeypatch.setattr(norm_processor, "_fetch_sections", lambda conn, current_document_id: [
        {
            "id": "s1",
            "section_code": "1.0.1",
            "title": "制定本标准。",
            "text": "",
            "level": 1,
            "page_start": 1,
            "page_end": 1,
        }
    ])
    monkeypatch.setattr(norm_processor, "_fetch_tables", lambda conn, current_document_id: [])
    monkeypatch.setattr(norm_processor, "_fetch_document", lambda conn, current_document_id: None)
    monkeypatch.setattr(norm_processor, "_parse_skill_plugins", lambda: [plugin])
    monkeypatch.setattr(
        norm_processor,
        "_active_parse_skill_names",
        lambda conn: {"mineru-standard-bundle"},
    )
    monkeypatch.setattr(
        norm_processor,
        "_process_scope_with_retries",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("AI should not run")),
    )
    monkeypatch.setattr(
        norm_processor._std_repo,
        "delete_clauses",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DB replacement should not run")),
    )
    monkeypatch.setattr(norm_processor, "build_single_standard_blocks", lambda sections, tables: [
        BlockSegment(
            segment_type="normative_clause_block",
            chapter_label="1.0.1 制定本标准。",
            text="制定本标准。",
            clause_no="1.0.1",
            page_start=1,
            page_end=1,
            section_ids=["s1"],
            source_refs=["document_section:s1"],
        )
    ])

    summary = norm_processor.process_standard_ai(
        object(),
        standard_id=standard_id,
        document_id=document_id,
    )

    assert summary["status"] == "needs_review"
    assert summary["total_clauses"] == 0
    assert summary["executed_skills"] == [
        {
            "skill_name": "mineru-standard-bundle",
            "hook": "preflight_parse_asset",
            "status": "fail",
            "blocking": True,
            "messages": ["low section coverage"],
            "metrics": {"section_page_coverage_ratio": 0.2},
        }
    ]
