#!/usr/bin/env python3
"""Offline validator for companybase CSV/XLSX workbooks.

The validator intentionally depends only on the Python standard library for CSV mode.
XLSX mode requires no third-party packages because the template stores inline strings.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
CSV_DIR = ROOT / "templates" / "csv"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ASSET_TYPES = {"vehicle", "machine", "tool", "safety"}
OWNERSHIPS = {"self", "leased", "third_party"}
ASSET_STATUSES = {"active", "maintenance", "retired"}
OWNER_TYPES = {
    "library_company",
    "company_asset",
    "company_profile",
    "person_profile",
    "project_performance",
    "qualification_certificate",
    "financial_statement",
}
ALLOWED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff"}
JSON_FIELDS = {"metadata_json", "profile_json", "extras", "statement_data"}
DATE_FIELDS = {"valid_from", "valid_to", "issued_on", "expires_on", "started_on", "ended_on", "acquired_at", "expires_at", "contract_signed_date", "contract_completed_date"}


def read_csv_tables() -> dict[str, list[dict[str, str]]]:
    tables: dict[str, list[dict[str, str]]] = {}
    for path in CSV_DIR.glob("*.csv"):
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            tables[path.stem] = list(csv.DictReader(handle))
    return tables


def read_xlsx_tables(path: Path) -> dict[str, list[dict[str, str]]]:
    with zipfile.ZipFile(path, "r") as zf:
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        sheets = workbook.find("m:sheets", ns)
        sheet_names = [sheet.attrib["name"] for sheet in list(sheets) if sheets is not None]
        tables: dict[str, list[dict[str, str]]] = {}
        for idx, name in enumerate(sheet_names, start=1):
            if name in {"说明", "字段字典"}:
                continue
            rows = _worksheet_rows(zf.read(f"xl/worksheets/sheet{idx}.xml"))
            if not rows:
                tables[name] = []
                continue
            header = rows[0]
            tables[name] = [dict(zip(header, row + [""] * (len(header) - len(row)))) for row in rows[1:] if any(cell.strip() for cell in row)]
        return tables


def _worksheet_rows(raw: bytes) -> list[list[str]]:
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ET.fromstring(raw)
    rows: list[list[str]] = []
    for row in root.findall("m:sheetData/m:row", ns):
        values: list[str] = []
        for cell in row.findall("m:c", ns):
            text = cell.find("m:is/m:t", ns)
            values.append(text.text if text is not None and text.text is not None else "")
        rows.append(values)
    return rows


def validate(tables: dict[str, list[dict[str, str]]]) -> list[tuple[str, str, str]]:
    issues: list[tuple[str, str, str]] = []
    company_keys = {row.get("company_key", "").strip() for row in tables.get("公司主体", []) if row.get("company_key", "").strip()}
    unique_by_owner = {
        "company_profile": {row.get("unique_key", "").strip() for row in tables.get("公司资料", [])},
        "qualification_certificate": {row.get("unique_key", "").strip() for row in tables.get("企业资质", [])},
        "person_profile": {row.get("unique_key", "").strip() for row in tables.get("人员资料", [])},
        "company_asset": {row.get("unique_key", "").strip() for row in tables.get("公司资产", [])},
        "project_performance": {row.get("unique_key", "").strip() for row in tables.get("项目业绩", [])},
        "financial_statement": {row.get("unique_key", "").strip() for row in tables.get("财务报表", [])},
        "library_company": company_keys,
    }

    for sheet, rows in tables.items():
        seen: set[str] = set()
        for index, row in enumerate(rows, start=2):
            if sheet == "公司主体":
                key_field = "company_key"
            elif sheet == "附件索引":
                key_field = "attachment_key"
            else:
                key_field = "unique_key"
            key = row.get(key_field, "").strip()
            if not key:
                issues.append(("P0", sheet, f"row {index}: {key_field} is required"))
            elif key in seen:
                issues.append(("P0", sheet, f"row {index}: duplicate {key_field}: {key}"))
            seen.add(key)

            company_key = row.get("company_key", "").strip()
            if sheet != "公司主体" and company_key and company_key not in company_keys:
                issues.append(("P0", sheet, f"row {index}: company_key not found: {company_key}"))

            for field in JSON_FIELDS:
                if row.get(field, "").strip():
                    try:
                        parsed = json.loads(row[field])
                    except json.JSONDecodeError:
                        issues.append(("P0", sheet, f"row {index}: {field} is not valid JSON"))
                        continue
                    if not isinstance(parsed, dict):
                        issues.append(("P0", sheet, f"row {index}: {field} must be a JSON object"))

            for field in DATE_FIELDS:
                value = row.get(field, "").strip()
                if value and not DATE_RE.match(value):
                    issues.append(("P0", sheet, f"row {index}: {field} must be YYYY-MM-DD"))

            if sheet == "公司资产":
                if row.get("asset_type", "").strip() not in ASSET_TYPES:
                    issues.append(("P0", sheet, f"row {index}: asset_type invalid"))
                if row.get("ownership", "").strip() not in OWNERSHIPS:
                    issues.append(("P0", sheet, f"row {index}: ownership invalid"))
                if row.get("status", "").strip() not in ASSET_STATUSES:
                    issues.append(("P0", sheet, f"row {index}: status invalid"))

            if sheet == "附件索引":
                owner_type = row.get("owner_type", "").strip()
                owner_key = row.get("owner_unique_key", "").strip()
                rel = row.get("file_relative_path", "").strip()
                if owner_type not in OWNER_TYPES:
                    issues.append(("P0", sheet, f"row {index}: owner_type invalid: {owner_type}"))
                elif owner_key and owner_key not in unique_by_owner.get(owner_type, set()):
                    issues.append(("P0", sheet, f"row {index}: owner_unique_key not found for {owner_type}: {owner_key}"))
                if not rel:
                    issues.append(("P0", sheet, f"row {index}: file_relative_path is required"))
                else:
                    path = (ROOT / rel).resolve()
                    if ROOT.resolve() not in path.parents and path != ROOT.resolve():
                        issues.append(("P0", sheet, f"row {index}: file path escapes companybase: {rel}"))
                    if path.suffix.lower() not in ALLOWED_SUFFIXES:
                        issues.append(("P0", sheet, f"row {index}: unsupported file extension: {rel}"))
                    if not path.is_file():
                        issues.append(("P1", sheet, f"row {index}: file does not exist yet: {rel}"))
                if row.get("is_blind_sensitive", "").strip().upper() not in {"TRUE", "FALSE"}:
                    issues.append(("P1", sheet, f"row {index}: is_blind_sensitive should be TRUE or FALSE"))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", nargs="?", help="optional companybase_master.xlsx; omit to validate CSV templates")
    args = parser.parse_args()
    tables = read_xlsx_tables(Path(args.workbook)) if args.workbook else read_csv_tables()
    issues = validate(tables)
    for severity, sheet, message in issues:
        print(f"{severity}\t{sheet}\t{message}")
    p0_count = sum(1 for severity, _sheet, _message in issues if severity == "P0")
    print(f"summary: {len(issues)} issue(s), {p0_count} P0")
    return 1 if p0_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
