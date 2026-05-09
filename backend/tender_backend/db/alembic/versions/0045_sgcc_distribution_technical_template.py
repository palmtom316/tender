"""seed sgcc distribution technical outline template

Revision ID: 0045
Revises: 0044
Create Date: 2026-05-09
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0045"
down_revision: Union[str, None] = "0044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ITEMS: tuple[tuple[str, str], ...] = (
    ("1", "技术偏差表"),
    ("2", "关于施工监理项目人员执业合规的承诺函"),
    ("3", "工期响应"),
    ("4", "资质情况"),
    ("5", "业绩情况"),
    ("5.1", "业绩证明1"),
    ("5.2", "业绩证明2"),
    ("5.3", "业绩证明3"),
    ("5.4", "业绩证明（投标人员在公司资料库中自行选择）"),
    ("6", "项目团队情况"),
    ("7", "其他资格条件情况"),
    ("8", "对项目的理解"),
    ("8.1", "施工组织设计"),
    ("8.2", "施工技术措施"),
    ("9", "工作规划描述"),
    ("10", "履约能力及质量保证措施"),
    ("10.1", "质量保证措施"),
    ("10.2", "安全和绿色施工保障措施"),
    ("10.3", "工程进度计划及保证措施"),
    ("11", "服务承诺"),
    ("12", "技术评分标准涉及的支撑材料"),
    ("13", "技术规范书规定的其他应提交的文件"),
    ("14", "履约评价证明材料"),
    ("14.1", "各类履约评价证明材料（投标人员在公司资料库中自行选择）"),
    ("15", "其他"),
    ("16", "履约承诺函"),
)


def upgrade() -> None:
    op.execute("""
    INSERT INTO bid_template_package (
      id, package_key, display_name, package_type, category_code, source_root, source_manifest
    )
    VALUES (
      gen_random_uuid(),
      'sgcc_distribution_technical_v1',
      '国网公司配网工程技术标目录',
      'outline',
      'sgcc_10kv',
      'docs/samples',
      '{"source_file":"国网公司配网工程技术标目录.md","volume_type":"technical","outline_kind":"sgcc_distribution_technical"}'::jsonb
    )
    ON CONFLICT (package_key)
    DO UPDATE SET
      display_name = EXCLUDED.display_name,
      package_type = EXCLUDED.package_type,
      category_code = EXCLUDED.category_code,
      source_root = EXCLUDED.source_root,
      source_manifest = EXCLUDED.source_manifest,
      updated_at = now();
    """)
    values = ",\n".join(
        f"('{code}', '{title}', '{code}_{title}.md', "
        f"'国网公司配网工程技术标目录.md#{code}', 'md', 'outline_item', 'outline', true, {index})"
        for index, (code, title) in enumerate(_ITEMS, start=1)
    )
    op.execute(f"""
    WITH pkg AS (
      SELECT id FROM bid_template_package WHERE package_key = 'sgcc_distribution_technical_v1'
    )
    INSERT INTO bid_template_item (
      id, package_id, item_code, item_name, filename, relative_path,
      source_kind, item_type, render_mode, is_required, sort_order
    )
    SELECT
      gen_random_uuid(),
      pkg.id,
      item.item_code,
      item.item_name,
      item.filename,
      item.relative_path,
      item.source_kind,
      item.item_type,
      item.render_mode,
      item.is_required,
      item.sort_order
    FROM pkg
    CROSS JOIN (VALUES
      {values}
    ) AS item (
      item_code, item_name, filename, relative_path,
      source_kind, item_type, render_mode, is_required, sort_order
    )
    ON CONFLICT (package_id, relative_path)
    DO UPDATE SET
      item_code = EXCLUDED.item_code,
      item_name = EXCLUDED.item_name,
      filename = EXCLUDED.filename,
      source_kind = EXCLUDED.source_kind,
      item_type = EXCLUDED.item_type,
      render_mode = EXCLUDED.render_mode,
      is_required = EXCLUDED.is_required,
      sort_order = EXCLUDED.sort_order;
    """)


def downgrade() -> None:
    op.execute("""
    DELETE FROM bid_template_item
    WHERE package_id IN (
      SELECT id FROM bid_template_package WHERE package_key = 'sgcc_distribution_technical_v1'
    );
    """)
    op.execute("DELETE FROM bid_template_package WHERE package_key = 'sgcc_distribution_technical_v1';")
