from __future__ import annotations

import json
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest

from tender_backend.services import delivery_package


class _Cursor:
    def __init__(self, conn: "_Conn", *, row_factory=None):
        self.conn = conn
        self.row_factory = row_factory
        self.result = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        if "SELECT COALESCE(MAX(version_no)" in query:
            self.result = [(1,)]
        elif "SELECT name FROM project" in query:
            self.result = [("测试项目",)]
        elif "FROM project_requirement" in query and "LEFT JOIN" not in query and "JOIN" not in query:
            self.result = []
        elif "FROM chapter_draft" in query:
            self.result = []
        elif "FROM bid_chapter_requirement" in query:
            self.result = []
        elif "FROM requirement_match" in query:
            self.result = []
        elif "FROM bid_chapter" in query:
            self.result = []
        elif "LEFT JOIN bid_chapter_requirement" in query:
            self.result = []
        elif "INSERT INTO bid_delivery_package" in query:
            metadata = params[13].obj
            self.conn.inserted = {
                "id": params[0],
                "project_id": params[1],
                "version_no": params[2],
                "status": params[3],
                "package_name": params[4],
                "package_path": params[5],
                "docx_path": params[6],
                "doc_path": params[7],
                "metadata_json": metadata,
                "created_by": params[14],
            }
            self.result = [self.conn.inserted]
        else:
            self.result = []
        return self

    def fetchone(self):
        return self.result[0] if self.result else None

    def fetchall(self):
        return self.result


class _Conn:
    def __init__(self):
        self.inserted = None
        self.committed = False

    def cursor(self, *args, **kwargs):
        return _Cursor(self, row_factory=kwargs.get("row_factory"))

    def commit(self):
        self.committed = True


def test_build_delivery_package_records_degraded_warnings(tmp_path: Path, monkeypatch) -> None:
    project_id = uuid4()

    def fake_render_docx(_conn, *, project_id, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("docx", encoding="utf-8")
        return output_path

    def fake_render_volume_docx(_conn, *, project_id, volume_type, output_path):
        if volume_type == "business":
            raise RuntimeError("volume failed")
        output_path.write_text(volume_type, encoding="utf-8")
        return output_path

    monkeypatch.setattr(delivery_package, "EXPORT_ROOT", tmp_path)
    monkeypatch.setattr(delivery_package, "render_docx", fake_render_docx)
    monkeypatch.setattr(delivery_package, "render_volume_docx", fake_render_volume_docx)
    monkeypatch.setattr(delivery_package, "convert_docx_to_doc", lambda _path: None)
    monkeypatch.setattr(delivery_package, "build_export_gate_state", lambda _conn, *, project_id: {"can_export": True, "gates": {}})
    monkeypatch.setattr(
        delivery_package,
        "EquipmentTableRenderer",
        lambda: type("Renderer", (), {"render_attachment_xlsx": lambda self, _conn, project_id: b"xlsx"})(),
    )

    conn = _Conn()
    row = delivery_package.build_delivery_package(conn, project_id=project_id, created_by="Tester")

    assert conn.committed is True
    assert row["status"] == "degraded"
    warnings = row["metadata_json"]["warnings"]
    assert {item["code"] for item in warnings} == {"doc_conversion_unavailable", "volume_render_failed"}
    assert row["metadata_json"]["volume_paths"]
    assert row["metadata_json"]["equipment_table_xlsx_path"].endswith("主要施工设备一览表.xlsx")

    package_path = Path(row["package_path"])
    assert package_path.is_file()
    with zipfile.ZipFile(package_path) as archive:
        names = set(archive.namelist())
    assert "投标文件.docx" in names
    assert "主要施工设备一览表.xlsx" in names
    assert "审查报告.json" in names
    assert "约束响应矩阵.json" in names


def test_delivery_package_json_outputs_are_valid(tmp_path: Path, monkeypatch) -> None:
    path = delivery_package._write_json(tmp_path / "nested" / "out.json", {"value": "中文"})

    assert json.loads(path.read_text(encoding="utf-8")) == {"value": "中文"}


def test_delivery_package_blocks_when_final_gate_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        delivery_package,
        "build_export_gate_state",
        lambda conn, *, project_id: {
            "can_export": False,
            "gates": {"review_passed": False, "blocking_issue_count": 1},
        },
    )

    with pytest.raises(ValueError, match="export gates block delivery package"):
        delivery_package.build_delivery_package(_Conn(), project_id=uuid4(), created_by="Tester")
