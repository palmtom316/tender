from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID, uuid4

from tender_backend.db.repositories.master_data_repo import (
    POWER_CERTIFICATE_GRADES,
    POWER_CERTIFICATE_TYPES,
    POWER_PERFORMANCE_METADATA_FIELDS,
    MasterDataRepository,
    build_power_performance_metadata,
)


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


def _certificate_row(
    *,
    record_id: UUID | None = None,
    library_company_id: UUID | None = None,
    certificate_type: str = "承装（修、试）电力设施许可证",
    grade: str = "三级",
    metadata_json: dict | None = None,
) -> dict:
    now = datetime(2026, 5, 19, 9, 0, 0)
    return {
        "id": record_id or uuid4(),
        "library_company_id": library_company_id,
        "certificate_name": "电力设施许可证",
        "certificate_type": certificate_type,
        "certificate_no": "TEST-NO",
        "holder_name": "测试公司",
        "grade": grade,
        "specialty": "承装",
        "issued_by": "发证机构",
        "valid_from": None,
        "valid_to": None,
        "status": "active",
        "metadata_json": metadata_json or {},
        "created_at": now,
        "updated_at": now,
    }


def _performance_row(
    *,
    record_id: UUID | None = None,
    library_company_id: UUID | None = None,
    metadata_json: dict | None = None,
) -> dict:
    now = datetime(2026, 5, 19, 9, 0, 0)
    return {
        "id": record_id or uuid4(),
        "library_company_id": library_company_id,
        "project_name": "配网改造业绩",
        "client_name": "业主单位",
        "contract_amount": None,
        "currency": "CNY",
        "started_on": None,
        "ended_on": None,
        "project_status": "completed",
        "service_scope": "配网施工",
        "peak_staffing": None,
        "average_staffing": None,
        "contact_name": None,
        "contact_phone": None,
        "evidence_summary": None,
        "metadata_json": metadata_json or {},
        "created_at": now,
        "updated_at": now,
    }


def test_power_industry_master_data_options_are_soft_string_enums() -> None:
    assert "承装（修、试）电力设施许可证" in POWER_CERTIFICATE_TYPES
    assert "输变电工程专业承包" in POWER_CERTIFICATE_TYPES
    assert "电力工程施工总承包" in POWER_CERTIFICATE_TYPES
    assert POWER_CERTIFICATE_GRADES == ("一级", "二级", "三级", "四级", "五级")
    assert {
        "voltage_level_kv",
        "circuit_count",
        "capacity_mva",
        "distribution_type",
        "is_live_work",
    } <= set(POWER_PERFORMANCE_METADATA_FIELDS)


def test_certificate_repository_accepts_power_qualification_strings_without_hard_enum() -> None:
    library_company_id = uuid4()
    row = _certificate_row(library_company_id=library_company_id, grade="五级")
    conn = _FakeConn(_RecordingCursor([row]))

    created = MasterDataRepository().create_certificate(
        conn,
        library_company_id=library_company_id,
        certificate_name="电力设施许可证",
        certificate_type="承装（修、试）电力设施许可证",
        certificate_no="TEST-NO",
        holder_name="测试公司",
        grade="五级",
        specialty="承试",
        issued_by="发证机构",
        metadata_json={"recommended_type": True},
    )

    assert created.certificate_type == "承装（修、试）电力设施许可证"
    assert created.grade == "五级"
    insert_sql, insert_params = conn.cursor_obj.executed[0]
    assert "INSERT INTO qualification_certificate" in insert_sql
    assert insert_params[3] == "承装（修、试）电力设施许可证"
    assert insert_params[6] == "五级"


def test_power_performance_metadata_helper_merges_domain_fields_without_dropping_free_text() -> None:
    metadata = build_power_performance_metadata(
        {"custom_legacy_field": "保留"},
        voltage_level_kv=10,
        circuit_count=2,
        capacity_mva=6.3,
        distribution_type="架空线+台区",
        is_live_work=True,
    )

    assert metadata == {
        "custom_legacy_field": "保留",
        "voltage_level_kv": 10,
        "circuit_count": 2,
        "capacity_mva": 6.3,
        "distribution_type": "架空线+台区",
        "is_live_work": True,
    }


def test_project_performance_repository_persists_power_domain_metadata() -> None:
    library_company_id = uuid4()
    metadata = {
        "voltage_level_kv": 10,
        "circuit_count": 2,
        "capacity_mva": 6.3,
        "distribution_type": "电缆",
        "is_live_work": False,
    }
    row = _performance_row(library_company_id=library_company_id, metadata_json=metadata)
    conn = _FakeConn(_RecordingCursor([row]))

    created = MasterDataRepository().create_project_performance(
        conn,
        library_company_id=library_company_id,
        project_name="配网改造业绩",
        client_name="业主单位",
        project_status="completed",
        service_scope="配网施工",
        metadata_json=metadata,
    )

    assert created.metadata_json == metadata
    insert_sql, insert_params = conn.cursor_obj.executed[0]
    assert "INSERT INTO project_performance" in insert_sql
    assert json.loads(insert_params[-1]) == metadata


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
