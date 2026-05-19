from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import scripts.import_confidential_business_template_package as importer_script


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))
        return self

    def fetchall(self):
        return self.rows


class _Conn:
    def __init__(self, rows):
        self.rows = rows
        self.cursor_obj = None

    def cursor(self, *args, **kwargs):
        self.cursor_obj = _Cursor(self.rows)
        return self.cursor_obj


def test_import_confidential_business_template_package_sets_allowlist_and_verifies(monkeypatch, tmp_path):
    sample = tmp_path / "sgcc_distribution_business_20258B_merged.docx"
    sample.write_bytes(b"docx")
    rows = [
        {
            "item_code": "5.1",
            "source_kind": "docx",
            "render_mode": "single_docx_section",
            "relative_path": "sgcc_distribution_business_20258B_merged.docx#5.1",
        }
    ]
    conn = _Conn(rows)
    imported = SimpleNamespace(
        package_id=str(uuid4()),
        package_key="sgcc_distribution_business_v1",
        display_name="国网配网工程商务标",
        package_type="business",
        source_root=str(tmp_path),
        item_count=60,
    )
    calls = {}

    def _fake_import(conn_arg, **kwargs):
        calls["import"] = kwargs
        assert conn_arg is conn
        return imported

    monkeypatch.setattr(importer_script, "import_template_package_from_directory", _fake_import)

    evidence = importer_script.import_and_verify(
        conn,
        sample_docx=sample,
        package_key="sgcc_distribution_business_v1",
        display_name="国网配网工程商务标",
    )

    assert calls["import"]["source_dir"] == sample
    assert calls["import"]["package_key"] == "sgcc_distribution_business_v1"
    assert calls["import"]["package_type"] == "business"
    assert calls["import"]["category_code"] == "sgcc_distribution"
    assert evidence["package_key"] == "sgcc_distribution_business_v1"
    assert evidence["item_count"] == 60
    assert evidence["verified_sample_items"] == rows
    assert evidence["verification_passed"] is True
    assert conn.cursor_obj.calls[0][1][0] == "sgcc_distribution_business_v1"
