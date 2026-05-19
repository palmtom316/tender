from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from tender_backend.services.business_bid_assembler import BusinessBidAssembler


class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.result = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        self.conn.queries.append((query, params))
        if "FROM bid_outline" in query:
            self.result = [{"id": self.conn.outline_id, "project_id": self.conn.project_id, "status": "confirmed"}]
        elif "FROM bid_chapter" in query:
            self.result = [
                {
                    "id": uuid4(),
                    "chapter_code": "5",
                    "chapter_title": "基本情况",
                    "volume_type": "business",
                    "sort_order": 5,
                    "outline_md": "",
                    "metadata_json": {},
                }
            ]
        elif "FROM requirement_match" in query:
            self.result = []
        elif "FROM bid_chapter_requirement" in query:
            self.result = []
        elif "INSERT INTO bid_generation_run" in query:
            self.result = [{"id": uuid4(), "status": params[5], "metadata_json": params[6].obj}]
        elif "INSERT INTO chapter_draft" in query:
            self.conn.chapter_draft_upserts.append((query, params))
            self.result = [{"id": params[0], "chapter_code": params[2], "rendered_docx_path": params[5]}]
        else:
            self.result = []
        return self

    def fetchone(self):
        return self.result[0] if self.result else None

    def fetchall(self):
        return self.result


class _Conn:
    def __init__(self):
        self.project_id = uuid4()
        self.outline_id = uuid4()
        self.queries = []
        self.chapter_draft_upserts = []
        self.commits = 0

    def cursor(self, *args, **kwargs):
        return _Cursor(self)

    def commit(self):
        self.commits += 1


def test_business_bid_assembler_renders_docx_artifact_and_upserts_chapter_draft(monkeypatch, tmp_path: Path):
    conn = _Conn()
    package_id = uuid4()
    expected_item_id = uuid4()
    rendered_path = tmp_path / "rendered" / "005-5.docx"

    class _ConstraintService:
        def latest_confirmed(self, conn, *, project_id):
            return None

    class _TemplateRepo:
        def get_by_key(self, conn, *, package_key):
            assert package_key == "sgcc_distribution_business_v1"
            return SimpleNamespace(id=package_id)

        def list_items(self, conn, *, package_id):
            return [
                SimpleNamespace(
                    id=expected_item_id,
                    item_code="5",
                    item_name="基本情况",
                    filename="国网配网工程商务标1-24章.docx",
                    relative_path="国网配网工程商务标1-24章.docx#5",
                    render_mode="single_docx_section",
                )
            ]

    def _render_template_item_docx(conn, *, item_id, output_dir, output_filename, project_id):
        assert item_id == expected_item_id
        assert project_id == conn.project_id
        assert output_dir == tmp_path / "business_bid" / str(conn.project_id)
        assert output_filename == "005-5.docx"
        return {
            "output_path": str(rendered_path),
            "context_keys": ["company", "tender"],
            "ready": True,
        }

    monkeypatch.setattr("tender_backend.services.business_bid_assembler.TenderConstraintService", _ConstraintService)
    monkeypatch.setattr("tender_backend.services.business_bid_assembler.BidTemplatePackageRepository", _TemplateRepo)
    monkeypatch.setattr("tender_backend.services.business_bid_assembler.render_template_item_docx", _render_template_item_docx)
    monkeypatch.setattr(
        "tender_backend.services.business_bid_assembler.get_settings",
        lambda: SimpleNamespace(business_bid_docxtpl_enabled=True, template_render_root=tmp_path),
    )

    result = BusinessBidAssembler().assemble(conn, project_id=conn.project_id)

    assert result["run"]["metadata_json"]["rendered_artifact_count"] == 1
    assert len(conn.chapter_draft_upserts) == 1
    query, params = conn.chapter_draft_upserts[0]
    assert "rendered_docx_path" in query
    assert "rendered_artifact_json" in query
    assert params[2] == "5"
    assert params[3] == "business"
    assert params[5] == str(rendered_path)
    artifact = params[6].obj
    assert artifact["template_item_id"] == str(expected_item_id)
    assert artifact["render_mode"] == "single_docx_section"
    assert artifact["missing_materials"] == []
    assert artifact["placeholder_status"]["unfilled_count"] == 0
