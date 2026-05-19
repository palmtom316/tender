from __future__ import annotations

from uuid import uuid4

from docx import Document

import scripts.run_business_bid_acceptance as business_acceptance


class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.result = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        if "FROM chapter_draft" in query:
            self.result = self.conn.chapter_rows
        else:
            self.result = []
        return self

    def fetchall(self):
        return self.result


class _Conn:
    def __init__(self, chapter_rows):
        self.chapter_rows = chapter_rows

    def cursor(self, *args, **kwargs):
        return _Cursor(self)


def test_run_business_bid_acceptance_collects_24_chapter_evidence(monkeypatch, tmp_path):
    project_id = uuid4()
    company_id = uuid4()
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    rows = []
    for index in range(1, 25):
        path = artifact_dir / f"{index}.docx"
        path.write_bytes(b"DOCX")
        rows.append(
            {
                "chapter_code": str(index),
                "rendered_docx_path": str(path),
                "rendered_artifact_json": {
                    "missing_materials": [],
                    "placeholder_status": {"unfilled_count": 0},
                },
            }
        )

    class _Assembler:
        def assemble(self, conn, *, project_id, created_by=None):
            return {"project_id": str(project_id), "rendered_artifacts": []}

    def _render_volume_docx(conn, *, project_id, volume_type, output_path):
        document = Document()
        document.add_paragraph("business bid")
        document.save(output_path)
        return output_path

    monkeypatch.setattr(business_acceptance, "BusinessBidAssembler", _Assembler)
    monkeypatch.setattr(business_acceptance, "render_volume_docx", _render_volume_docx)

    evidence = business_acceptance.run_acceptance(
        _Conn(rows),
        project_id=project_id,
        company_id=company_id,
        output_dir=tmp_path,
        enable_docxtpl=True,
    )

    assert evidence["project_id"] == str(project_id)
    assert evidence["company_id"] == str(company_id)
    assert evidence["docxtpl_enabled"] is True
    assert evidence["hard_stop_passed"] is True
    assert evidence["output_docx"].endswith(".docx")
    assert len(evidence["chapters"]) == 24
    assert evidence["chapters"][4]["chapter_code"] == "5"
    assert evidence["chapters"][4]["rendered"] is True
    assert evidence["chapters"][4]["size_kb"] > 0
