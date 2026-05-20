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
    ('0', '技术标重点资料索引'),
    ('0.1', '技术评分标准支撑材料'),
    ('0.2', '技术规范书规定应该提交的材料'),
    ('0.3', '标书目录'),
    ('1', '技术偏差表'),
    ('2', '关于施工项目人员执业合规的承诺函'),
    ('3', '工期响应'),
    ('4', '资质情况'),
    ('5', '业绩情况'),
    ('5.1', '类似工程业绩情况汇总表'),
    ('5.2', '近年完成的类似项目情况及证明材料'),
    ('5.3', '正在施工的和新承接的类似项目情况及证明材料'),
    ('6', '现场管理机构设置'),
    ('7', '其他资格条件情况'),
    ('8', '施工方案与技术措施'),
    ('8.1', '编制依据与标准'),
    ('8.2', '工程概况与施工重难点分析'),
    ('8.3', '施工组织与部署'),
    ('8.4', '主要施工方法及技术要求'),
    ('8.5', '质量管理体系与措施'),
    ('8.6', '安全管理体系与措施'),
    ('8.7', '施工进度计划与保障'),
    ('8.8', '环境保护、绿色低碳与碳足迹管理'),
    ('8.9', '科技创新与智能化应用'),
    ('8.10', '地域特性专题方案'),
    ('8.11', '竣工验收与数字化移交'),
    ('8.12', '售后服务、培训及增值服务'),
    ('8.13', '拟投入施工车辆、机具、工器具、检测设备、安全工器具及设施'),
    ('8.14', '施工项目部组织架构创新设计'),
    ('8.15', '国网年度框架施工工程投标其他创新内容'),
    ('9', '工作规划描述'),
    ('9.1', '项目理解与总体工作思路'),
    ('9.2', '工作目标分解与任务策划'),
    ('9.3', '项目管理组织与制度规划'),
    ('9.4', '协调配合工作规划'),
    ('9.5', '技术管理与创新应用规划'),
    ('9.6', '风险防控与应急管理规划'),
    ('9.7', '履约创优与标准化管理规划'),
    ('9.8', '跨章节协同与边界管理'),
    ('10', '质量进度安全绿色施工保障措施'),
    ('10.1', '质量保障措施'),
    ('10.2', '安全和绿色施工保障措施'),
    ('10.3', '工程进度计划及保证措施'),
    ('11', '履约评价证明材料'),
    ('12', '施工外包管理'),
    ('13', '其他'),
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
      'sgcc_distribution',
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
