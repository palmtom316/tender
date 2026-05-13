from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from tender_backend.core.security import CurrentUser, Role, get_current_user
from tender_backend.main import app
from tender_backend.test_support.asgi_client import SyncASGIClient

_AUTH_HEADERS = {"Authorization": "Bearer dev-token"}


def _override_auth() -> CurrentUser:
    return CurrentUser(token="dev-token", role=Role.ADMIN, display_name="Developer")


def _workbook(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "公司主体"
    ws.append(["company_key", "company_name", "company_type", "enabled", "metadata_json"])
    ws.append(["main_company", "某某电力工程有限公司", "bidder", "TRUE", '{}'])
    wb.save(path)


def test_companybase_validate_endpoint_accepts_workbook(tmp_path: Path) -> None:
    path = tmp_path / "companybase.xlsx"
    _workbook(path)
    app.dependency_overrides[get_current_user] = _override_auth
    client = SyncASGIClient(app)
    client.headers.update(_AUTH_HEADERS)
    try:
        with path.open("rb") as handle:
            response = client.post(
                "/api/master-data/companybase/validate",
                files={"file": ("companybase.xlsx", handle, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["summary"]["公司主体"] == 1
        assert body["p0_count"] == 0
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_companybase_backup_endpoint_returns_archive() -> None:
    app.dependency_overrides[get_current_user] = _override_auth
    client = SyncASGIClient(app)
    client.headers.update(_AUTH_HEADERS)
    try:
        response = client.get("/api/master-data/companybase/backup")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/gzip"
        assert response.content[:2] == b"\x1f\x8b"
    finally:
        client.close()
        app.dependency_overrides.clear()
