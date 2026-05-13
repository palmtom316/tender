from pathlib import Path
from zipfile import ZipFile

from tender_backend.services.template_service.business_template_preview import parse_business_template_preview


def _write_minimal_docx(path: Path, document_xml: str) -> None:
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
      <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
      <Default Extension="xml" ContentType="application/xml"/>
      <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
    </Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
    </Relationships>"""
    with ZipFile(path, "w") as archive:
      archive.writestr("[Content_Types].xml", content_types)
      archive.writestr("_rels/.rels", rels)
      archive.writestr("word/document.xml", document_xml)


def test_parse_business_template_preview_splits_chapters_and_pages(tmp_path: Path) -> None:
    docx_path = tmp_path / "preview.docx"
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:r><w:t>一、商务偏差表</w:t></w:r></w:p>
        <w:p><w:r><w:t>商务偏差表正文第一页</w:t></w:r><w:r><w:br w:type="page"/></w:r></w:p>
        <w:p><w:r><w:t>二、承诺函</w:t></w:r></w:p>
        <w:p><w:r><w:t>承诺函正文第一页</w:t></w:r><w:r><w:br w:type="page"/></w:r></w:p>
      </w:body>
    </w:document>"""
    _write_minimal_docx(docx_path, document_xml)

    preview = parse_business_template_preview(docx_path)

    assert [chapter.chapter_title for chapter in preview.chapters] == ["商务偏差表", "承诺函"]
    assert [(chapter.page_start, chapter.page_end) for chapter in preview.chapters] == [(1, 1), (2, 2)]
    assert preview.chapters[0].pages[0].blocks[0] == "商务偏差表正文第一页"
    assert preview.chapters[1].pages[0].blocks[0] == "承诺函正文第一页"
