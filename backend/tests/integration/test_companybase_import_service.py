from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest
from openpyxl import Workbook

from tender_backend.services.companybase_import_service import CompanybaseImportService


def _db_url() -> str | None:
    return os.environ.get("DATABASE_URL")


def _write_workbook(path: Path) -> None:
    wb = Workbook()
    default = wb.active
    wb.remove(default)
    sheets = {
        "公司主体": [
            ["company_key", "company_name", "company_type", "enabled", "metadata_json"],
            ["main_company", "某某电力工程有限公司", "bidder", "TRUE", '{"source":"integration"}'],
        ],
        "公司资料": [
            ["unique_key", "company_key", "company_name", "company_code", "profile_json"],
            ["profile_main", "main_company", "某某电力工程有限公司", "MC-001", '{"blind_bid_alias":"投标人"}'],
        ],
        "人员资料": [
            ["unique_key", "company_key", "full_name", "role_name", "profile_json"],
            ["person_pm", "main_company", "张三", "项目经理", '{"blind_bid_alias":"项目经理"}'],
        ],
        "附件索引": [
            [
                "attachment_key",
                "company_key",
                "owner_type",
                "owner_unique_key",
                "asset_name",
                "asset_domain",
                "asset_category",
                "asset_type",
                "file_relative_path",
                "media_type",
                "metadata_json",
            ],
            [
                "att_bank",
                "main_company",
                "library_company",
                "main_company",
                "开户许可证",
                "business",
                "bank_account",
                "certificate_scan",
                "files/bank.pdf",
                "application/pdf",
                '{"core_slot":"bank"}',
            ],
        ],
        "财务报表": [
            ["unique_key", "company_key", "fiscal_year", "statement_type", "statement_data", "source_note"],
            ["finance_2025", "main_company", "2025", "annual_report", '{"revenue":1000}', "2025年审计报告"],
        ],
        "银行账户": [
            ["unique_key", "company_key", "year", "evidence_attachment_key", "metadata_json"],
            ["bank_main", "main_company", "2026", "att_bank", '{"bank_name":"开户银行"}'],
        ],
        "保证金": [
            ["unique_key", "company_key", "year", "metadata_json"],
            ["bond_2026", "main_company", "2026", '{"amount":10000}'],
        ],
        "绿证": [
            ["unique_key", "company_key", "year", "metadata_json"],
            ["green_2025", "main_company", "2025", '{"certificate_no":"GC-001"}'],
        ],
        "科技成果": [
            ["unique_key", "company_key", "year", "metadata_json"],
            ["tech_2025", "main_company", "2025", '{"achievement_name":"配网成果"}'],
        ],
        "ESG": [
            ["unique_key", "company_key", "year", "metadata_json"],
            ["esg_2025", "main_company", "2025", '{"report_name":"ESG报告"}'],
        ],
        "奖项": [
            ["unique_key", "company_key", "year", "metadata_json"],
            ["award_2025", "main_company", "2025", '{"award_name":"质量奖"}'],
        ],
    }
    for title, rows in sheets.items():
        ws = wb.create_sheet(title)
        for row in rows:
            ws.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def _reset_tables(conn: psycopg.Connection) -> None:
    conn.execute("DELETE FROM business_specialty_ledger;")
    conn.execute("DELETE FROM evidence_asset;")
    conn.execute("DELETE FROM financial_statement;")
    conn.execute("DELETE FROM person_profile;")
    conn.execute("DELETE FROM company_profile;")
    conn.execute("DELETE FROM library_company;")
    conn.commit()


def test_companybase_imports_mvp_financial_and_specialty_sheets(tmp_path: Path) -> None:
    db_url = _db_url()
    if not db_url:
        pytest.skip("DATABASE_URL not set; skipping integration test")

    files_dir = tmp_path / "files"
    files_dir.mkdir()
    (files_dir / "bank.pdf").write_bytes(b"%PDF-1.7\n")
    workbook = tmp_path / "companybase_master.xlsx"
    _write_workbook(workbook)

    with psycopg.connect(db_url) as conn:
        if conn.execute("SELECT to_regclass('business_specialty_ledger')").fetchone()[0] is None:
            pytest.skip("business_specialty_ledger table is not migrated")
        _reset_tables(conn)

        try:
            report = CompanybaseImportService(files_root=tmp_path).import_workbook(conn, workbook, dry_run=False)

            assert report.p0_count == 0
            assert report.p1_count == 0
            assert report.actions == {"created": 11, "updated": 0, "skipped": 0}

            assert conn.execute("SELECT count(*) FROM financial_statement").fetchone()[0] == 1
            ledger_rows = conn.execute(
                """
                SELECT ledger_type, evidence_asset_id, metadata_json
                FROM business_specialty_ledger
                ORDER BY ledger_type
                """
            ).fetchall()
            assert {row[0] for row in ledger_rows} == {
                "award",
                "bank_account",
                "bid_bond",
                "esg_report",
                "green_certificate",
                "technology_achievement",
            }
            bank_row = next(row for row in ledger_rows if row[0] == "bank_account")
            assert bank_row[1] is not None
            assert bank_row[2]["import"]["unique_key"] == "bank_main"
        finally:
            _reset_tables(conn)
