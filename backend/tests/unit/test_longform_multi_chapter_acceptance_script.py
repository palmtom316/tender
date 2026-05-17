from __future__ import annotations

from uuid import uuid4

import scripts.run_longform_multi_chapter_acceptance as longform_acceptance


class _Cursor:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))
        if "FROM chapter_draft" in query:
            self.result = self.responses["drafts"][params[1] if len(params) > 1 else params[0]]
        elif "FROM bid_generation_subsection_run" in query:
            self.result = self.responses["usage"][params[1]]
        elif "FROM export_record" in query:
            self.result = self.responses["export"]
        else:
            self.result = self.responses["gate"]
        return self

    def fetchone(self):
        return self.result


class _Conn:
    def __init__(self):
        self.responses = {
            "drafts": {
                "8": {"chapter_code": "8", "target_pages": 100, "estimated_pages": 90, "page_estimate_json": {"actual_pages": 91}, "coverage_report_json": {"checked_section_count": 15, "coverage_passed": True, "issues": []}, "chart_closure_report_json": {"chart_closure_passed": True, "issues": []}, "generation_rounds": 3},
                "9": {"chapter_code": "9", "target_pages": 40, "estimated_pages": 38, "page_estimate_json": {"actual_pages": 36}, "coverage_report_json": {"checked_section_count": 8, "coverage_passed": True, "issues": []}, "chart_closure_report_json": {"chart_closure_passed": True, "issues": []}, "generation_rounds": 2},
                "10.1": {"chapter_code": "10.1", "target_pages": 35, "estimated_pages": 33, "page_estimate_json": {"actual_pages": 34}, "coverage_report_json": {"checked_section_count": 15, "coverage_passed": True, "issues": []}, "chart_closure_report_json": {"chart_closure_passed": True, "issues": []}, "generation_rounds": 4},
                "10.2": {"chapter_code": "10.2", "target_pages": 35, "estimated_pages": 32, "page_estimate_json": {"actual_pages": 35}, "coverage_report_json": {"checked_section_count": 16, "coverage_passed": True, "issues": []}, "chart_closure_report_json": {"chart_closure_passed": True, "issues": []}, "generation_rounds": 4},
                "10.3": {"chapter_code": "10.3", "target_pages": 35, "estimated_pages": 34, "page_estimate_json": {"actual_pages": 35}, "coverage_report_json": {"checked_section_count": 15, "coverage_passed": True, "issues": []}, "chart_closure_report_json": {"chart_closure_passed": True, "issues": []}, "generation_rounds": 4},
            },
            "usage": {
                "8": {"subsection_count": 3, "input_tokens": 12, "output_tokens": 24, "latency_ms": 30, "providers": ["deepseek"], "models": ["deepseek-v4-pro"]},
                "9": {"subsection_count": 2, "input_tokens": 10, "output_tokens": 20, "latency_ms": 22, "providers": ["deepseek"], "models": ["deepseek-v4-flash"]},
                "10.1": {"subsection_count": 4, "input_tokens": 16, "output_tokens": 32, "latency_ms": 40, "providers": ["deepseek"], "models": ["deepseek-v4-pro"]},
                "10.2": {"subsection_count": 4, "input_tokens": 14, "output_tokens": 28, "latency_ms": 38, "providers": ["deepseek"], "models": ["deepseek-v4-pro"]},
                "10.3": {"subsection_count": 4, "input_tokens": 13, "output_tokens": 26, "latency_ms": 36, "providers": ["deepseek"], "models": ["deepseek-v4-pro"]},
            },
            "export": {"id": "export-1", "template_name": "plain_docx", "status": "completed", "metadata_json": {"render_evidence": {"page_count": {"actual_pages": 91}}}, "created_at": "2026-05-17T00:00:00Z"},
            "gate": {"project_id": str(uuid4()), "gates": {"can_export": True}},
        }
        self.cursor_obj = None

    def cursor(self, *args, **kwargs):
        self.cursor_obj = _Cursor(self.responses)
        return self.cursor_obj


def test_collect_evidence_returns_all_requested_chapters():
    project_id = uuid4()
    conn = _Conn()
    longform_acceptance.build_export_gate_state = lambda conn, project_id: {"gates": {"can_export": True}}

    evidence = longform_acceptance.collect_evidence(conn, project_id=project_id, chapter_codes=["8", "9", "10.1", "10.2", "10.3"])

    assert evidence["project_id"] == str(project_id)
    assert [chapter["chapter_code"] for chapter in evidence["chapters"]] == ["8", "9", "10.1", "10.2", "10.3"]
    assert evidence["chapters"][0]["model_usage"]["models"] == ["deepseek-v4-pro"]
    assert evidence["chapters"][1]["actual_pages"] == 36
    assert evidence["latest_export_record"]["template_name"] == "plain_docx"
    assert evidence["export_gate"]["gates"]["can_export"] is True
