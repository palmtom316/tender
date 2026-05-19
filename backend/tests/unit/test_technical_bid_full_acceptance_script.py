from __future__ import annotations

from uuid import uuid4

import scripts.run_technical_bid_full_acceptance as acceptance
from tender_backend.services.technical_chapter_strategies.registry import strategy_for_chapter


class _Cursor:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        return self

    def fetchall(self):
        return self.rows


class _Conn:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    def cursor(self, *args, **kwargs):
        return _Cursor(self.rows)


def _complete_rows() -> list[dict]:
    rows = []
    for index in range(1, 17):
        code = str(index)
        strategy = strategy_for_chapter(code)
        required_assets = list(strategy.required_assets if strategy else ())
        rows.append(
            {
                "chapter_code": code,
                "chapter_title": f"技术章 {code}",
                "draft_id": f"draft-{code}",
                "content_md": f"# 技术章 {code}\n\n正文",
                "metadata_json": {
                    "required_assets": required_assets,
                    "blind_check": {"passed": True, "issues": []},
                },
                "coverage_report_json": {"coverage_passed": True, "issues": []},
                "chart_closure_report_json": {"chart_closure_passed": True, "issues": []},
            }
        )
    return rows


def test_collect_evidence_reports_16_ready_technical_chapters() -> None:
    project_id = uuid4()

    evidence = acceptance.collect_evidence(_Conn(_complete_rows()), project_id=project_id)

    assert evidence["project_id"] == str(project_id)
    assert evidence["hard_stop_passed"] is True
    assert evidence["hard_stop_failures"] == []
    assert len(evidence["chapters"]) == 16
    assert all(chapter["draft_exists"] for chapter in evidence["chapters"])
    assert all(chapter["required_assets_ready"] for chapter in evidence["chapters"])
    assert all(chapter["export_ready"] for chapter in evidence["chapters"])


def test_hard_stop_fails_when_a_p0_chapter_lacks_draft_or_assets() -> None:
    rows = _complete_rows()
    rows[1]["draft_id"] = None
    rows[1]["content_md"] = ""
    rows[5]["metadata_json"]["required_assets"] = []

    evidence = acceptance.collect_evidence(_Conn(rows), project_id=uuid4())

    assert evidence["hard_stop_passed"] is False
    assert "chapter 2 draft missing" in evidence["hard_stop_failures"]
    assert any("chapter 6 missing required assets" in failure for failure in evidence["hard_stop_failures"])


def test_hard_stop_fails_when_coverage_has_p0_gap() -> None:
    rows = _complete_rows()
    rows[7]["coverage_report_json"] = {
        "coverage_passed": False,
        "issues": [{"code": "missing_section", "severity": "P0", "section_code": "8.4"}],
    }

    evidence = acceptance.collect_evidence(_Conn(rows), project_id=uuid4())

    assert evidence["hard_stop_passed"] is False
    assert "chapter 8 coverage failed" in evidence["hard_stop_failures"]
