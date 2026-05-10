from __future__ import annotations

from uuid import uuid4

from tender_backend.services.review_service.compliance_matrix import build_compliance_matrix


class _Cursor:
    def __init__(self):
        self.result = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        if "FROM tender_constraint_set" in query:
            self.result = []
        elif "FROM project_requirement" in query:
            self.result = [
                {"id": uuid4(), "title": "营业执照", "category": "qualification", "source_text": ""},
                {"id": uuid4(), "title": "项目经理 证书", "category": "project_team", "source_text": ""},
                {"id": uuid4(), "title": "安全生产许可证", "category": "qualification", "source_text": ""},
            ]
        elif "FROM chapter_draft" in query:
            self.result = [
                {"chapter_code": "1.1", "content_md": "本章响应营业执照要求。"},
                {"chapter_code": "1.2", "content_md": "项目经理已提供相关证书。"},
            ]
        else:
            self.result = []
        return self

    def fetchall(self):
        return self.result

    def fetchone(self):
        return self.result[0] if self.result else None


class _Conn:
    def cursor(self, *args, **kwargs):
        return _Cursor()


def test_build_compliance_matrix_marks_covered_partial_and_uncovered() -> None:
    entries = build_compliance_matrix(_Conn(), project_id=uuid4())
    coverage_by_title = {entry.requirement_title: entry.coverage for entry in entries}

    assert coverage_by_title["营业执照"] == "covered"
    assert coverage_by_title["项目经理 证书"] == "partial"
    assert coverage_by_title["安全生产许可证"] == "uncovered"


def test_build_compliance_matrix_prefers_confirmed_constraints(monkeypatch) -> None:
    project_id = uuid4()
    constraint_id = uuid4()

    class _ConstraintService:
        def latest_confirmed(self, conn, *, project_id):
            return {
                "id": uuid4(),
                "version": 1,
                "status": "confirmed",
                "items": [
                    {
                        "id": constraint_id,
                        "category": "technical",
                        "title": "质量目标",
                        "constraint_text": "质量目标合格率100%。",
                    }
                ],
            }

    monkeypatch.setattr("tender_backend.services.review_service.compliance_matrix.TenderConstraintService", _ConstraintService)

    entries = build_compliance_matrix(_Conn(), project_id=project_id)

    assert len(entries) == 1
    assert entries[0].requirement_id == str(constraint_id)
    assert entries[0].requirement_title == "质量目标"
