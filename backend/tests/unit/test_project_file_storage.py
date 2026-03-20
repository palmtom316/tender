from __future__ import annotations

from pathlib import Path

from tender_backend.services.storage_service.project_file_storage import ProjectFileStorage


def test_resolve_local_path_returns_existing_absolute_path(tmp_path: Path) -> None:
    storage = ProjectFileStorage()
    pdf_path = tmp_path / "spec.pdf"
    pdf_path.write_bytes(b"%PDF-1.7")

    resolved = storage.resolve_local_path(str(pdf_path))

    assert resolved == pdf_path


def test_resolve_local_path_ignores_object_storage_keys() -> None:
    storage = ProjectFileStorage()

    resolved = storage.resolve_local_path("tender-raw/project/file/spec.pdf")

    assert resolved is None


def test_delete_managed_file_removes_existing_local_file(tmp_path: Path) -> None:
    storage = ProjectFileStorage()
    pdf_path = tmp_path / "spec.pdf"
    pdf_path.write_bytes(b"%PDF-1.7")

    deleted = storage.delete_managed_file(str(pdf_path))

    assert deleted is True
    assert not pdf_path.exists()


def test_delete_managed_file_skips_object_storage_keys(tmp_path: Path) -> None:
    storage = ProjectFileStorage()
    key = "tender-raw/project/file/spec.pdf"

    deleted = storage.delete_managed_file(key)

    assert deleted is False
