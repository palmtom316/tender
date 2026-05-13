from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from psycopg import Connection

from tender_backend.core.security import get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.services.companybase_import_service import CompanybaseImportService

router = APIRouter(tags=["master-data"], dependencies=[Depends(get_current_user)])


def _save_upload(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "companybase.xlsx").suffix or ".xlsx"
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    with handle:
        shutil.copyfileobj(upload.file, handle)
    return Path(handle.name)


@router.post("/master-data/companybase/validate")
async def validate_companybase(file: UploadFile = File(...)) -> dict[str, object]:
    path = _save_upload(file)
    try:
        return CompanybaseImportService().validate_workbook(path).to_dict()
    finally:
        path.unlink(missing_ok=True)


@router.post("/master-data/companybase/import")
async def import_companybase(
    file: UploadFile = File(...),
    dry_run: bool = Query(True),
    conn: Connection = Depends(get_db_conn),
) -> dict[str, object]:
    path = _save_upload(file)
    try:
        return CompanybaseImportService().import_workbook(conn, path, dry_run=dry_run).to_dict()
    finally:
        path.unlink(missing_ok=True)


@router.get("/master-data/companybase/backup")
async def backup_companybase() -> FileResponse:
    archive = CompanybaseImportService().create_backup_archive()
    return FileResponse(
        archive,
        media_type="application/gzip",
        filename=archive.name,
    )
