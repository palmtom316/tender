"""seed sgcc distribution business outline template

Revision ID: 0043
Revises: 0042
Create Date: 2026-05-09
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0043"
down_revision: Union[str, None] = "0042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ITEMS: tuple[tuple[str, str], ...] = (
    ("1", "商务偏差表"),
    ("2", "无违法失信行为的承诺函"),
    ("3", "企业营业执照"),
    ("4", "法定代表人身份证明"),
    ("5", "基本情况"),
    ("5.1", "基本情况表"),
    ("5.2", "安全质量事故查询响应表"),
    ("6", "企业信用信息公示报告"),
    ("6.1", "人员汇总表及人员简历表"),
    ("7", "与国家电网公司系统人员关系说明"),
    ("8", "近三年财务状况"),
    ("8.1", "2023年财务会计报表"),
    ("8.1.1", "资产负债表2023"),
    ("8.1.2", "现金流量表2023"),
    ("8.1.3", "利润表2023"),
    ("8.1.4", "其他2023"),
    ("8.2", "2024年财务会计报表"),
    ("8.2.1", "资产负债表2024"),
    ("8.2.2", "现金流量表2024"),
    ("8.2.3", "利润表2024"),
    ("8.2.4", "其他2024"),
    ("8.3", "2025年财务会计报表"),
    ("8.3.1", "资产负债表2025"),
    ("8.3.2", "现金流量表2025"),
    ("8.3.3", "利润表2025"),
    ("8.3.4", "其他2025"),
    ("9", "联合体协议书"),
    ("10", "企业银行基本账户开户许可证、基本存款账户信息"),
    ("11", "绿色发展顶层规划及执行情况"),
    ("12", "绿色管理体系认证"),
    ("12.1", "能源管理体系认证证书"),
    ("12.2", "质量管理体系认证证书"),
    ("12.3", "职业健康安全管理体系认证证书"),
    ("12.4", "环境管理体系认证证书"),
    ("13", "ESG报告、环评能评报告、废水废气废固报告"),
    ("13.1", "ESG报告"),
    ("13.2", "环评／能评报告"),
    ("13.3", "废水／废气／废固报告"),
    ("13.4", "环境行政处罚"),
    ("14", "绿色电力证书交易凭证和绿色电力证书"),
    ("15", "取得的科技成果"),
    ("16", "创新激励相关政策和机制"),
    ("17", "研发团队规模"),
    ("18", "中国质量奖、中国中国质量奖提名奖及中国工业大奖"),
    ("19", "高新技术企业证书"),
    ("20", "企业名称变更"),
    ("21", "关于小规模纳税人的说明"),
    ("22", "其他税率佐证材料"),
    ("23", "保证金缴纳证明材料"),
    ("23.1", "保证金明细表"),
    ("23.2", "投标保证金缴纳证明材料"),
    ("24", "认为需要加以说明的其它商务内容"),
    ("24.1", "不良行为处理情况通报"),
    ("24.2", "公共信用信息报告、企业信用信息公示报告"),
    ("24.3", "影响招投标工作公正性行为的凭证"),
    ("24.4", "科研经费占比"),
    ("24.5", "综合实力"),
    ("24.6", "投标响应"),
    ("24.7", "经营状况"),
    ("24.8", "其他"),
)


def upgrade() -> None:
    op.execute("""
    INSERT INTO bid_template_package (
      id, package_key, display_name, package_type, category_code, source_root, source_manifest
    )
    VALUES (
      gen_random_uuid(),
      'sgcc_distribution_business_v1',
      '国网公司配网工程商务标目录',
      'outline',
      'sgcc_distribution',
      'docs/samples',
      '{"source_file":"国网公司配网工程商务标目录.md","volume_type":"business","outline_kind":"sgcc_distribution_business"}'::jsonb
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
        f"'国网公司配网工程商务标目录.md#{code}', 'md', 'outline_item', 'outline', true, {index})"
        for index, (code, title) in enumerate(_ITEMS, start=1)
    )
    op.execute(f"""
    WITH pkg AS (
      SELECT id FROM bid_template_package WHERE package_key = 'sgcc_distribution_business_v1'
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
      SELECT id FROM bid_template_package WHERE package_key = 'sgcc_distribution_business_v1'
    );
    """)
    op.execute("DELETE FROM bid_template_package WHERE package_key = 'sgcc_distribution_business_v1';")
