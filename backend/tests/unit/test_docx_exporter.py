from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from docx import Document

from tender_backend.services.export_service.docx_exporter import render_docx


class _Cursor:
    def __init__(self):
        self.result = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        if "SELECT name FROM project" in query:
            self.result = [("测试项目",)]
        elif "FROM chapter_draft" in query:
            self.result = [
                {
                    "chapter_code": "1.1",
                    "content_md": "# 1.1 资格响应\n\n## 响应内容\n- 已提供营业执照",
                    "chapter_title": "资格响应",
                    "volume_type": "qualification",
                    "sort_order": 1,
                }
            ]
        elif "FROM project_requirement" in query:
            self.result = []
        elif "SELECT fact_key" in query:
            self.result = []
        else:
            self.result = []
        return self

    def fetchone(self):
        return self.result[0] if self.result else None

    def fetchall(self):
        return self.result


class _Conn:
    def cursor(self, *args, **kwargs):
        return _Cursor()


def test_render_docx_without_template_creates_plain_word_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TEMPLATE_DIR", str(tmp_path / "missing-templates"))
    output = tmp_path / "out.docx"

    path = render_docx(_Conn(), project_id=uuid4(), output_path=output)

    assert path == output
    document = Document(str(output))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "测试项目 投标文件" in text
    assert "已提供营业执照" in text
