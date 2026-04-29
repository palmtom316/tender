from __future__ import annotations

from pathlib import Path

from docx import Document

from tender_backend.services.template_service.docx_renderer import (
    _render_financial_statements,
    _render_people,
    _render_performances,
    _sanitize_filename,
)


def test_sanitize_filename_removes_unsafe_characters() -> None:
    assert _sanitize_filename("5.1_基本情况表.docx") == "5.1__.docx"
    assert _sanitize_filename("  ") == "rendered"


def test_sanitize_filename_keeps_ascii_safe_parts() -> None:
    assert _sanitize_filename("6.1_people-summary.docx") == "6.1_people-summary.docx"


def test_render_people_adds_summary_and_resume_sections() -> None:
    doc = Document()
    _render_people(
        doc,
        {
            "people": [
                {
                    "full_name": "唐玮",
                    "role_name": "项目总经理",
                    "title": "工程师",
                    "specialty": "机电工程",
                    "years_experience": 11,
                    "resume_text": "负责过多个配网服务项目。",
                }
            ]
        },
    )

    text = "\n".join(p.text for p in doc.paragraphs)
    assert "拟委任的主要人员汇总表" in text
    assert "主要人员简历表（项目总经理）" in text
    assert "负责过多个配网服务项目。" in text


def test_render_performances_adds_table_and_detail_sections() -> None:
    doc = Document()
    _render_performances(
        doc,
        {
            "performances": [
                {
                    "project_name": "渝中片区营配低压业务外包服务",
                    "client_name": "REDACTED市区供电分公司",
                    "contract_amount": 944.39,
                    "currency": "CNY",
                    "service_scope": "低压运维与抢修",
                    "started_on": "2024-01-01",
                    "ended_on": "2025-12-31",
                    "project_status": "已开工，未完工",
                }
            ]
        },
    )

    text = "\n".join(p.text for p in doc.paragraphs)
    assert "近年完成的类似项目情况表" in text
    assert "渝中片区营配低压业务外包服务" in text
    assert "低压运维与抢修" in text


def test_render_financial_statements_builds_year_matrix() -> None:
    doc = Document()
    _render_financial_statements(
        doc,
        {
            "financial_statements": [
                {
                    "fiscal_year": 2023,
                    "statement_type": "annual_report",
                    "statement_data": {"营业收入": "9509.69万元", "净利润": "968.93万元"},
                },
                {
                    "fiscal_year": 2024,
                    "statement_type": "annual_report",
                    "statement_data": {"营业收入": "7928.06万元", "净利润": "763.36万元"},
                },
            ]
        },
    )

    assert doc.tables[0].rows[0].cells[1].text == "2023"
    assert doc.tables[0].rows[0].cells[2].text == "2024"
    body_text = "\n".join(p.text for p in doc.paragraphs)
    assert "近年财务状况表" in body_text
