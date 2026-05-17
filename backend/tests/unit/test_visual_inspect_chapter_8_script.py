from __future__ import annotations

from uuid import uuid4

import scripts.visual_inspect_chapter_8 as visual_inspect


class _Cursor:
    def __init__(self, responses):
        self.responses = responses

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        if "FROM chapter_draft" in query:
            self.result = self.responses["draft"]
        elif "FROM chart_asset" in query:
            self.result = self.responses["assets"]
        else:
            self.result = []
        return self

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result


class _Conn:
    def __init__(self, draft_id):
        self.responses = {
            "draft": {
                "id": draft_id,
                "project_id": uuid4(),
                "chapter_code": "8",
                "content_md": "## 8.1 编制依据\n\n正文{{chart:risk_matrix}}\n\n## 8.2 工程概况\n\n更多正文",
                "target_pages": 100,
                "page_estimate_json": {"actual_pages": 91},
                "coverage_report_json": {"issues": []},
                "chart_closure_report_json": {"issues": [], "residual_placeholders": ["risk_matrix"]},
                "generation_rounds": 3,
                "updated_at": "2026-05-17T00:00:00Z",
            },
            "assets": [
                {
                    "id": uuid4(),
                    "placeholder_key": "risk_matrix",
                    "chart_type": "risk_matrix",
                    "title": "风险矩阵",
                    "status": "approved",
                    "rendered_png_path": "/tmp/risk.png",
                    "rendered_path": "/tmp/risk.svg",
                }
            ],
        }

    def cursor(self, *args, **kwargs):
        return _Cursor(self.responses)


def test_build_visual_inspection_snapshot_collects_sections_and_charts(tmp_path):
    draft_id = uuid4()
    snapshot = visual_inspect.build_snapshot(_Conn(draft_id), draft_id=draft_id)

    assert snapshot["draft_id"] == str(draft_id)
    assert snapshot["actual_pages"] == 91
    assert snapshot["sections"][0]["section_code"] == "8.1"
    assert snapshot["sections"][0]["min_chars"] >= 1500
    assert snapshot["chart_assets"][0]["rendered_png_path"] == "/tmp/risk.png"
    assert snapshot["residual_chart_placeholders"] == ["risk_matrix"]
