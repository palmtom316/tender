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


def _render_company_profile(doc: Document, context: dict) -> None:
    company = context.get("company") or {}
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


def _render_people(doc: Document, context: dict) -> None:
    people = context.get("people")
    if people is None:
        people = context.get("person")
    if isinstance(people, dict):
        people = [people]
    people = people or []

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


def _render_performances(doc: Document, context: dict) -> None:
    performances = context.get("performances")
    if performances is None:
        performances = context.get("performance")
    if isinstance(performances, dict):
        performances = [performances]
    performances = performances or []

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
        started = performance.get("started_on") or ""
        ended = performance.get("ended_on") or ""
        row[4].text = f"{started} 至 {ended}".strip(" 至")
        peak = performance.get("peak_staffing")
        avg = performance.get("average_staffing")
        staffing = []
        if peak is not None:
            staffing.append(f"高峰 {peak}")
        if avg is not None:
            staffing.append(f"平均 {avg}")
        row[5].text = " / ".join(staffing)
        row[6].text = str(performance.get("contact_name") or performance.get("contact_phone") or "")


def _render_certificates(doc: Document, context: dict) -> None:
    certificates = context.get("certificates")
    if certificates is None:
        certificates = context.get("certificate")
    if isinstance(certificates, dict):
        certificates = [certificates]
    certificates = certificates or []

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
    statements = context.get("financial_statements")
    if statements is None:
        statements = context.get("financial_statement")
    if isinstance(statements, dict):
        statements = [statements]
    statements = statements or []

    for statement in statements:
        year = statement.get("fiscal_year")
        statement_type = statement.get("statement_type")
        doc.add_heading(f"{year} - {statement_type}", level=2)
        data = statement.get("statement_data") or {}
        _add_key_value_table(doc, [(key, value) for key, value in data.items()])


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
    elif "人员" in item_name or item_code.startswith("6"):
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
