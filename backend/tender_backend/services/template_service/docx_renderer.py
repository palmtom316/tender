from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID

from docx import Document
from psycopg import Connection

from tender_backend.db.repositories.bid_template_package_repo import BidTemplatePackageRepository
from tender_backend.services.template_service.context_preview import build_item_render_context


_RENDER_ROOT = Path("/tmp/tender_template_renders")


def _sanitize_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "rendered"


def _add_key_value_table(doc: Document, pairs: list[tuple[str, object]]) -> None:
    table = doc.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for key, value in pairs:
        row = table.add_row().cells
        row[0].text = str(key)
        row[1].text = "" if value is None else str(value)


def _coerce_records(value: object) -> list[dict]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _format_period(started: object, ended: object) -> str:
    start = str(started or "").strip()
    end = str(ended or "").strip()
    if start and end:
        return f"{start} 至 {end}"
    return start or end


def _render_company_profile(doc: Document, context: dict) -> None:
    company = context.get("company") or {}
    doc.add_paragraph("应答人基本情况表")
    pairs = [
        ("单位名称", company.get("company_name")),
        ("统一社会信用代码", company.get("unified_social_credit_code")),
        ("单位地址", company.get("registered_address")),
        ("联系人", company.get("contact_name")),
        ("联系电话", company.get("contact_phone")),
        ("联系邮箱", company.get("contact_email")),
        ("网址", company.get("website")),
        ("注册资本", company.get("registered_capital")),
        ("单位性质", company.get("company_type")),
        ("经营范围", company.get("business_scope")),
    ]
    _add_key_value_table(doc, pairs)
    extra_profile = company.get("profile_json") or {}
    if extra_profile:
        doc.add_paragraph("补充信息")
        _add_key_value_table(doc, [(key, value) for key, value in extra_profile.items()])


def _render_people(doc: Document, context: dict) -> None:
    people = _coerce_records(context.get("people"))
    if not people:
        people = _coerce_records(context.get("person"))

    doc.add_paragraph("拟委任的主要人员汇总表")
    table = doc.add_table(rows=1, cols=6)
    table.style = "Table Grid"
    headers = table.rows[0].cells
    headers[0].text = "姓名"
    headers[1].text = "岗位"
    headers[2].text = "职称"
    headers[3].text = "专业"
    headers[4].text = "从业年限"
    headers[5].text = "联系方式"

    for person in people:
        row = table.add_row().cells
        row[0].text = str(person.get("full_name") or "")
        row[1].text = str(person.get("role_name") or "")
        row[2].text = str(person.get("title") or "")
        row[3].text = str(person.get("specialty") or "")
        row[4].text = "" if person.get("years_experience") is None else str(person.get("years_experience"))
        row[5].text = str(person.get("phone") or person.get("email") or "")

    for person in people:
        doc.add_heading(f"主要人员简历表（{person.get('role_name') or person.get('full_name') or '人员'}）", level=2)
        _add_key_value_table(
            doc,
            [
                ("姓名", person.get("full_name")),
                ("岗位", person.get("role_name")),
                ("性别", person.get("gender")),
                ("年龄", person.get("age")),
                ("学历", person.get("education")),
                ("职称", person.get("title")),
                ("专业", person.get("specialty")),
                ("从业年限", person.get("years_experience")),
                ("联系方式", person.get("phone") or person.get("email")),
            ],
        )
        resume_text = str(person.get("resume_text") or "").strip()
        if resume_text:
            doc.add_paragraph(resume_text)


def _render_performances(doc: Document, context: dict) -> None:
    performances = _coerce_records(context.get("performances"))
    if not performances:
        performances = _coerce_records(context.get("performance"))

    doc.add_paragraph("近年完成的类似项目情况表")
    table = doc.add_table(rows=1, cols=7)
    table.style = "Table Grid"
    headers = table.rows[0].cells
    headers[0].text = "项目名称"
    headers[1].text = "业主单位"
    headers[2].text = "合同金额"
    headers[3].text = "服务范围"
    headers[4].text = "服务期间"
    headers[5].text = "人员配置"
    headers[6].text = "联系人"

    for performance in performances:
        row = table.add_row().cells
        row[0].text = str(performance.get("project_name") or "")
        row[1].text = str(performance.get("client_name") or "")
        amount = performance.get("contract_amount")
        currency = performance.get("currency") or "CNY"
        row[2].text = "" if amount is None else f"{amount} {currency}"
        row[3].text = str(performance.get("service_scope") or "")
        row[4].text = _format_period(performance.get("started_on"), performance.get("ended_on"))
        peak = performance.get("peak_staffing")
        avg = performance.get("average_staffing")
        staffing = []
        if peak is not None:
            staffing.append(f"高峰 {peak}")
        if avg is not None:
            staffing.append(f"平均 {avg}")
        row[5].text = " / ".join(staffing)
        row[6].text = str(performance.get("contact_name") or performance.get("contact_phone") or "")

    for performance in performances:
        doc.add_heading(str(performance.get("project_name") or "项目说明"), level=2)
        doc.add_paragraph(str(performance.get("service_scope") or ""))
        note_pairs = [
            ("项目状态", performance.get("project_status")),
            ("服务期间", _format_period(performance.get("started_on"), performance.get("ended_on"))),
            ("联系人", performance.get("contact_name")),
            ("联系电话", performance.get("contact_phone")),
            ("证明摘要", performance.get("evidence_summary")),
        ]
        _add_key_value_table(doc, note_pairs)


def _render_certificates(doc: Document, context: dict) -> None:
    certificates = _coerce_records(context.get("certificates"))
    if not certificates:
        certificates = _coerce_records(context.get("certificate"))

    table = doc.add_table(rows=1, cols=6)
    table.style = "Table Grid"
    headers = table.rows[0].cells
    headers[0].text = "证书名称"
    headers[1].text = "证书编号"
    headers[2].text = "持有人"
    headers[3].text = "等级"
    headers[4].text = "有效期止"
    headers[5].text = "状态"

    for certificate in certificates:
        row = table.add_row().cells
        row[0].text = str(certificate.get("certificate_name") or "")
        row[1].text = str(certificate.get("certificate_no") or "")
        row[2].text = str(certificate.get("holder_name") or "")
        row[3].text = str(certificate.get("grade") or "")
        row[4].text = str(certificate.get("valid_to") or "")
        row[5].text = str(certificate.get("status") or "")


def _render_financial_statements(doc: Document, context: dict) -> None:
    statements = _coerce_records(context.get("financial_statements"))
    if not statements:
        statements = _coerce_records(context.get("financial_statement"))

    doc.add_paragraph("近年财务状况表")
    if not statements:
        return

    years = [statement.get("fiscal_year") for statement in statements]
    metric_names: list[str] = []
    metric_values_by_statement: list[dict] = []
    for statement in statements:
        data = statement.get("statement_data") or {}
        metric_values_by_statement.append(data)
        for key in data.keys():
            if key not in metric_names:
                metric_names.append(key)

    if metric_names:
        table = doc.add_table(rows=1, cols=len(statements) + 1)
        table.style = "Table Grid"
        header = table.rows[0].cells
        header[0].text = "财务指标"
        for idx, year in enumerate(years, start=1):
            header[idx].text = str(year or "")
        for metric_name in metric_names:
            row = table.add_row().cells
            row[0].text = str(metric_name)
            for idx, data in enumerate(metric_values_by_statement, start=1):
                row[idx].text = "" if data.get(metric_name) is None else str(data.get(metric_name))

    for statement in statements:
        year = statement.get("fiscal_year")
        statement_type = statement.get("statement_type")
        doc.add_heading(f"{year} - {statement_type}", level=2)
        doc.add_paragraph(str(statement.get("source_note") or ""))


def _render_generic_context(doc: Document, context: dict) -> None:
    for key, value in context.items():
        doc.add_heading(str(key), level=2)
        if isinstance(value, list):
            for item in value:
                doc.add_paragraph(str(item))
        else:
            doc.add_paragraph("" if value is None else str(value))


def render_template_item_docx(
    conn: Connection,
    *,
    item_id: UUID,
    output_dir: Path | None = None,
) -> dict[str, object]:
    repo = BidTemplatePackageRepository()
    item = repo.get_item_by_id(conn, item_id=item_id)
    if item is None:
        raise LookupError("template item not found")

    render_context = build_item_render_context(conn, item_id=item_id)
    if not render_context["ready"]:
        missing = ", ".join(render_context["missing_required_bindings"])
        raise ValueError(f"template item is not ready for rendering: missing {missing}")

    context = render_context["context"]
    doc = Document()
    doc.add_heading(item.item_name, level=1)

    item_name = item.item_name
    item_code = item.item_code or ""
    if "基本情况表" in item_name:
        _render_company_profile(doc, context)
    elif "人员" in item_name or "项目团队" in item_name or item_code.startswith("6"):
        _render_people(doc, context)
    elif "业绩" in item_name or item_code.startswith("5"):
        _render_performances(doc, context)
    elif "证书" in item_name or "认证" in item_name:
        _render_certificates(doc, context)
    elif "财务" in item_name or item_code.startswith("8"):
        _render_financial_statements(doc, context)
    else:
        _render_generic_context(doc, context)

    root = output_dir or _RENDER_ROOT
    root.mkdir(parents=True, exist_ok=True)
    filename = _sanitize_filename(f"{item_code or 'item'}_{item.item_name}.docx")
    output_path = root / filename
    doc.save(str(output_path))

    return {
        "item_id": str(item.id),
        "item_name": item.item_name,
        "filename": item.filename,
        "output_path": str(output_path),
        "ready": True,
        "context_keys": sorted(context.keys()),
    }
