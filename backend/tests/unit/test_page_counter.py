from tender_backend.services.export_service.page_counter import count_docx_pages


def test_count_docx_pages_returns_unchecked_when_soffice_missing(monkeypatch, tmp_path):
    docx = tmp_path / "sample.docx"
    docx.write_bytes(b"not a real docx for this branch")
    monkeypatch.setattr("tender_backend.services.export_service.page_counter.shutil.which", lambda name: None)

    result = count_docx_pages(docx)

    assert result["status"] == "unchecked"
    assert result["actual_pages"] is None
    assert result["method"] == "libreoffice_pdf_unavailable"


def test_count_docx_pages_uses_pdf_page_count_when_converter_available(monkeypatch, tmp_path):
    docx = tmp_path / "sample.docx"
    pdf = tmp_path / "sample.pdf"
    docx.write_bytes(b"fake")
    pdf.write_bytes(b"%PDF fake")
    monkeypatch.setattr("tender_backend.services.export_service.page_counter.shutil.which", lambda name: "/usr/bin/soffice")

    class _Completed:
        returncode = 0
        stderr = ""

    monkeypatch.setattr("tender_backend.services.export_service.page_counter.subprocess.run", lambda *args, **kwargs: _Completed())

    class _Doc:
        def __init__(self, path):
            self.path = path

        def __len__(self):
            return 12

        def close(self):
            pass

    monkeypatch.setattr("tender_backend.services.export_service.page_counter.fitz.open", lambda path: _Doc(path))

    result = count_docx_pages(docx)

    assert result["status"] == "counted"
    assert result["actual_pages"] == 12
    assert result["method"] == "libreoffice_pdf_pymupdf"
