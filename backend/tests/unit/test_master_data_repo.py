from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID, uuid4

from tender_backend.db.repositories.master_data_repo import MasterDataRepository


class _RecordingCursor:
    def __init__(self, response_rows: list[dict]) -> None:
        self.executed: list[tuple[str, object]] = []
        self._responses = list(response_rows)
        self.rowcount = 0

    def execute(self, sql: str, params: object = ()) -> "_RecordingCursor":
        self.executed.append((sql, params))
        if sql.strip().upper().startswith("DELETE"):
            self.rowcount = 1
        return self

    def fetchone(self) -> dict | None:
        return self._responses.pop(0) if self._responses else None

    def fetchall(self) -> list[dict]:
        rows = self._responses
        self._responses = []
        return rows

    def __enter__(self) -> "_RecordingCursor":
        return self

    def __exit__(self, *_: object) -> bool:
        return False


class _FakeConn:
    def __init__(self, cursor: _RecordingCursor) -> None:
        self.cursor_obj = cursor
        self.commits = 0

    def cursor(self, **_: object) -> _RecordingCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.commits += 1


def _ledger_row(
    *,
    record_id: UUID | None = None,
    library_company_id: UUID | None = None,
    company_key: str = "main_company",
    ledger_type: str = "bank_account",
    year: int = 2026,
    evidence_asset_id: UUID | None = None,
    metadata_json: dict | None = None,
) -> dict:
    now = datetime(2026, 5, 19, 9, 0, 0)
    return {
        "id": record_id or uuid4(),
        "library_company_id": library_company_id,
        "company_key": company_key,
        "ledger_type": ledger_type,
        "year": year,
        "evidence_asset_id": evidence_asset_id,
        "metadata_json": metadata_json or {},
        "created_at": now,
        "updated_at": now,
    }


def test_create_business_specialty_ledger_persists_company_year_evidence_and_metadata() -> None:
    library_company_id = uuid4()
    evidence_asset_id = uuid4()
    row = _ledger_row(
        library_company_id=library_company_id,
        evidence_asset_id=evidence_asset_id,
        metadata_json={
            "bank_name": "开户银行",
            "evidence_asset_ids": [str(evidence_asset_id)],
        },
    )
    conn = _FakeConn(_RecordingCursor([row]))

    created = MasterDataRepository().create_business_specialty_ledger(
        conn,
        library_company_id=library_company_id,
        company_key="main_company",
        ledger_type="bank_account",
        year=2026,
        evidence_asset_id=evidence_asset_id,
        metadata_json={
            "bank_name": "开户银行",
            "evidence_asset_ids": [str(evidence_asset_id)],
        },
    )

    assert created.library_company_id == library_company_id
    assert created.company_key == "main_company"
    assert created.ledger_type == "bank_account"
    assert created.year == 2026
    assert created.evidence_asset_id == evidence_asset_id
    assert created.metadata_json["bank_name"] == "开户银行"
    insert_sql, insert_params = conn.cursor_obj.executed[0]
    assert "INSERT INTO business_specialty_ledger" in insert_sql
    assert insert_params[1:] == (
        library_company_id,
        "main_company",
        "bank_account",
        2026,
        evidence_asset_id,
        json.dumps(
            {"bank_name": "开户银行", "evidence_asset_ids": [str(evidence_asset_id)]},
            ensure_ascii=False,
        ),
    )
    assert conn.commits == 1


def test_list_business_specialty_ledgers_filters_by_company_and_ledger_type() -> None:
    library_company_id = uuid4()
    row = _ledger_row(library_company_id=library_company_id, ledger_type="green_certificate")
    conn = _FakeConn(_RecordingCursor([row]))

    records = MasterDataRepository().list_business_specialty_ledgers(
        conn,
        library_company_id=library_company_id,
        ledger_type="green_certificate",
    )

    assert len(records) == 1
    assert records[0].ledger_type == "green_certificate"
    select_sql, select_params = conn.cursor_obj.executed[0]
    assert "FROM business_specialty_ledger" in select_sql
    assert "library_company_id = %s" in select_sql
    assert "ledger_type = %s" in select_sql
    assert select_params == [library_company_id, "green_certificate"]


def test_get_update_and_delete_business_specialty_ledger() -> None:
    record_id = uuid4()
    original = _ledger_row(record_id=record_id, ledger_type="award")
    updated = _ledger_row(
        record_id=record_id,
        ledger_type="award",
        metadata_json={"award_name": "质量奖"},
    )
    conn = _FakeConn(_RecordingCursor([original, updated]))
    repo = MasterDataRepository()

    found = repo.get_business_specialty_ledger(conn, record_id)
    changed = repo.update_business_specialty_ledger(
        conn,
        record_id,
        metadata_json={"award_name": "质量奖"},
    )
    deleted = repo.delete_business_specialty_ledger(conn, record_id)

    assert found is not None
    assert found.id == record_id
    assert changed is not None
    assert changed.metadata_json == {"award_name": "质量奖"}
    assert deleted is True
    assert "SELECT" in conn.cursor_obj.executed[0][0]
    assert "UPDATE business_specialty_ledger" in conn.cursor_obj.executed[1][0]
    assert "metadata_json = %s::jsonb" in conn.cursor_obj.executed[1][0]
    assert conn.cursor_obj.executed[1][1][-1] == record_id
    assert "DELETE FROM business_specialty_ledger" in conn.cursor_obj.executed[2][0]
