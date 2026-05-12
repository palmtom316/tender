#!/usr/bin/env python3
"""Generate the companybase XLSX template without third-party dependencies."""

from __future__ import annotations

import csv
import html
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
CSV_DIR = ROOT / "templates" / "csv"
OUTPUT = ROOT / "templates" / "companybase_master.xlsx"

SHEETS = [
    ("说明", None),
    ("字段字典", None),
    ("公司主体", "公司主体.csv"),
    ("公司资料", "公司资料.csv"),
    ("企业资质", "企业资质.csv"),
    ("人员资料", "人员资料.csv"),
    ("公司资产", "公司资产.csv"),
    ("项目业绩", "项目业绩.csv"),
    ("财务报表", "财务报表.csv"),
    ("制度能力", "制度能力.csv"),
    ("附件索引", "附件索引.csv"),
]

FIELD_DICTIONARY = [
    ["sheet", "field", "required", "system_mapping", "note"],
    ["通用", "unique_key", "Y", "metadata_json.import.unique_key", "稳定唯一键，用于幂等导入"],
    ["公司主体", "company_key", "Y", "library_company.company_key", "公司主体稳定键"],
    ["公司主体", "company_name", "Y", "library_company.company_name", "公司全称"],
    ["企业资质", "certificate_name", "Y", "qualification_certificate.certificate_name", "证书名称"],
    ["人员资料", "full_name", "Y", "person_profile.full_name", "人员姓名，暗标敏感"],
    ["公司资产", "asset_type", "Y", "company_asset.asset_type", "vehicle/machine/tool/safety"],
    ["公司资产", "ownership", "Y", "company_asset.ownership", "self/leased/third_party"],
    ["项目业绩", "project_name", "Y", "project_performance.project_name", "业绩项目名称，暗标敏感"],
    ["附件索引", "owner_type", "Y", "evidence_asset.owner_type", "附件挂靠对象类型"],
    ["附件索引", "owner_unique_key", "N", "owner_id lookup", "通过对应主数据 unique_key 解析 owner_id"],
    ["附件索引", "file_relative_path", "Y", "evidence_asset.file_path", "相对 companybase/ 的文件路径"],
]

README_ROWS = [
    ["tender 公司资料基座模板"],
    ["用途", "一次录入，多环境复用；结构化主数据和 PDF/图片附件通过附件索引关联。"],
    ["填写顺序", "公司主体 -> 公司资料 -> 企业资质 -> 人员资料 -> 公司资产 -> 项目业绩 -> 财务报表/制度能力 -> 附件索引。"],
    ["唯一键", "所有主数据行必须填写 unique_key；公司主体使用 company_key。"],
    ["附件", "附件文件放入 companybase/files/ 下，附件索引只填写相对路径。"],
    ["日期格式", "YYYY-MM-DD。"],
    ["JSON 字段", "必须是 JSON object，例如 {\"source\":\"companybase\"}。"],
    ["暗标", "含公司、人员、联系方式、地址、证书编号等敏感信息的附件，is_blind_sensitive 填 TRUE。"],
]


def _read_csv(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [row for row in csv.reader(handle)]


def _col_name(index: int) -> str:
    result = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        result = chr(65 + rem) + result
    return result


def _sheet_xml(rows: list[list[str]]) -> str:
    max_col = max((len(row) for row in rows), default=1)
    max_row = max(len(rows), 1)
    dimension = f"A1:{_col_name(max_col - 1)}{max_row}"
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
        f'<dimension ref="{dimension}"/>',
        '<sheetViews><sheetView workbookViewId="0"/></sheetViews>',
        '<sheetFormatPr defaultRowHeight="18"/>',
        '<sheetData>',
    ]
    for r_idx, row in enumerate(rows, start=1):
        parts.append(f'<row r="{r_idx}">')
        for c_idx, value in enumerate(row):
            ref = f"{_col_name(c_idx)}{r_idx}"
            style = "1" if r_idx == 1 else "0"
            escaped = html.escape(str(value or ""))
            parts.append(f'<c r="{ref}" t="inlineStr" s="{style}"><is><t>{escaped}</t></is></c>')
        parts.append('</row>')
    parts.extend([
        '</sheetData>',
        '<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>',
        '</worksheet>',
    ])
    return "".join(parts)


def _workbook_xml() -> str:
    sheets = []
    for idx, (name, _csv_name) in enumerate(SHEETS, start=1):
        sheets.append(f'<sheet name="{html.escape(name)}" sheetId="{idx}" r:id="rId{idx}"/>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<workbookPr date1904="false"/>'
        '<sheets>' + ''.join(sheets) + '</sheets>'
        '<calcPr calcId="0"/>'
        '</workbook>'
    )


def _workbook_rels_xml() -> str:
    rels = []
    for idx in range(1, len(SHEETS) + 1):
        rels.append(
            f'<Relationship Id="rId{idx}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{idx}.xml"/>'
        )
    style_id = len(SHEETS) + 1
    rels.append(
        f'<Relationship Id="rId{style_id}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + ''.join(rels) +
        '</Relationships>'
    )


def _content_types_xml() -> str:
    overrides = [
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
    ]
    for idx in range(1, len(SHEETS) + 1):
        overrides.append(
            f'<Override PartName="/xl/worksheets/sheet{idx}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        + ''.join(overrides) +
        '</Types>'
    )


def _root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )


def _styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2">'
        '<font><sz val="11"/><name val="Microsoft YaHei"/></font>'
        '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Microsoft YaHei"/></font>'
        '</fonts>'
        '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF305496"/><bgColor indexed="64"/></patternFill></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '<dxfs count="0"/><tableStyles count="0" defaultTableStyle="TableStyleMedium2" defaultPivotStyle="PivotStyleLight16"/>'
        '</styleSheet>'
    )


def _validate_xlsx(path: Path) -> None:
    with zipfile.ZipFile(path, "r") as zf:
        required = {"[Content_Types].xml", "_rels/.rels", "xl/workbook.xml", "xl/styles.xml"}
        names = set(zf.namelist())
        missing = required - names
        if missing:
            raise RuntimeError(f"xlsx missing parts: {sorted(missing)}")
        ET.fromstring(zf.read("xl/workbook.xml"))
        for idx in range(1, len(SHEETS) + 1):
            ET.fromstring(zf.read(f"xl/worksheets/sheet{idx}.xml"))


def main() -> int:
    work = ROOT / "templates" / ".xlsx_work"
    if work.exists():
        shutil.rmtree(work)
    (work / "_rels").mkdir(parents=True)
    (work / "xl" / "_rels").mkdir(parents=True)
    (work / "xl" / "worksheets").mkdir(parents=True)

    (work / "[Content_Types].xml").write_text(_content_types_xml(), encoding="utf-8")
    (work / "_rels" / ".rels").write_text(_root_rels_xml(), encoding="utf-8")
    (work / "xl" / "workbook.xml").write_text(_workbook_xml(), encoding="utf-8")
    (work / "xl" / "_rels" / "workbook.xml.rels").write_text(_workbook_rels_xml(), encoding="utf-8")
    (work / "xl" / "styles.xml").write_text(_styles_xml(), encoding="utf-8")

    for idx, (_name, csv_name) in enumerate(SHEETS, start=1):
        if idx == 1:
            rows = README_ROWS
        elif idx == 2:
            rows = FIELD_DICTIONARY
        else:
            assert csv_name is not None
            rows = _read_csv(CSV_DIR / csv_name)
        (work / "xl" / "worksheets" / f"sheet{idx}.xml").write_text(_sheet_xml(rows), encoding="utf-8")

    if OUTPUT.exists():
        OUTPUT.unlink()
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(work.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(work).as_posix())
    _validate_xlsx(OUTPUT)
    shutil.rmtree(work)
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
