from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import tender_backend.api.template_packages as api
from tender_backend.db.repositories.bid_template_package_repo import (
    BidTemplatePackageRow,
    TemplatePackageCategoryRow,
)


class _Repo:
    def list_categories(self, _conn):
        return [
            TemplatePackageCategoryRow(
                code="sgcc_distribution",
                display_name="国网配网工程",
                description="国家电网配网工程类项目模板",
                sort_order=30,
                enabled=True,
                metadata_json={},
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        ]

    def list_all(self, _conn):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return [
            BidTemplatePackageRow(
                id=uuid4(),
                package_key="sgcc_distribution_technical_v1",
                display_name="国网公司配网工程技术标目录",
                package_type="outline",
                category_code="sgcc_distribution",
                source_root="docs/samples",
                source_manifest={"volume_type": "technical"},
                created_at=now,
                updated_at=now,
            ),
            BidTemplatePackageRow(
                id=uuid4(),
                package_key="sgcc-10kv-construction-methods-technical",
                display_name="国网配网工程技术标-施工方案与技术措施",
                package_type="technical",
                category_code="sgcc_distribution",
                source_root="docs/投标文件样板/tender系统模板/技术标/国网配网工程",
                source_manifest={"volume_type": "technical"},
                created_at=now,
                updated_at=now,
            ),
        ]

    def count_items_by_package(self, _conn, *, package_ids):
        return {package_id: 1 for package_id in package_ids}


def test_template_package_list_only_exposes_outline_packages(monkeypatch):
    monkeypatch.setattr(api, "_repo", _Repo())

    result = api._list_visible_template_packages(None, category_code=None)

    assert [package.display_name for package in result] == ["国网公司配网工程技术标目录"]


def test_template_categories_use_six_tender_template_kinds():
    assert [(item["code"], item["display_name"]) for item in api.TENDER_TEMPLATE_CATEGORIES] == [
        ("sgcc_substation", "国网变电工程"),
        ("sgcc_maintenance", "国网运维工程"),
        ("sgcc_distribution", "国网配网工程"),
        ("sgcc_low_voltage_distribution", "国网低压营配工程"),
        ("user_distribution", "用户配电工程"),
        ("user_maintenance", "用户运维工程"),
    ]
