from __future__ import annotations

from typing import Any


PRIORITY_POLICY = "tender_extracted_requirements_override_template"
SGCC_DISTRIBUTION_BUSINESS_TEMPLATE_KEY = "sgcc_distribution_business_v1"
SGCC_DISTRIBUTION_TECHNICAL_TEMPLATE_KEY = "sgcc_distribution_technical_v1"


QUALIFICATION_CHAPTERS: list[dict[str, Any]] = [
    {
        "chapter_code": "1.1",
        "chapter_title": "法定资格与资质响应",
        "volume_type": "qualification",
    },
    {
        "chapter_code": "1.2",
        "chapter_title": "企业业绩响应",
        "volume_type": "qualification",
    },
    {
        "chapter_code": "1.3",
        "chapter_title": "项目管理团队响应",
        "volume_type": "qualification",
    },
]


SGCC_DISTRIBUTION_BUSINESS_CHAPTERS: list[dict[str, Any]] = [
    {"chapter_code": "1", "chapter_title": "商务偏差表"},
    {"chapter_code": "2", "chapter_title": "无违法失信行为的承诺函"},
    {"chapter_code": "3", "chapter_title": "企业营业执照"},
    {"chapter_code": "4", "chapter_title": "法定代表人身份证明"},
    {"chapter_code": "5", "chapter_title": "基本情况"},
    {"chapter_code": "5.1", "chapter_title": "基本情况表", "parent_code": "5"},
    {"chapter_code": "5.2", "chapter_title": "安全质量事故查询响应表", "parent_code": "5"},
    {"chapter_code": "6", "chapter_title": "企业信用信息公示报告"},
    {"chapter_code": "6.1", "chapter_title": "人员汇总表及人员简历表", "parent_code": "6"},
    {"chapter_code": "7", "chapter_title": "与国家电网公司系统人员关系说明"},
    {"chapter_code": "8", "chapter_title": "近三年财务状况"},
    {"chapter_code": "8.1", "chapter_title": "2023年财务会计报表", "parent_code": "8"},
    {"chapter_code": "8.1.1", "chapter_title": "资产负债表2023", "parent_code": "8.1"},
    {"chapter_code": "8.1.2", "chapter_title": "现金流量表2023", "parent_code": "8.1"},
    {"chapter_code": "8.1.3", "chapter_title": "利润表2023", "parent_code": "8.1"},
    {"chapter_code": "8.1.4", "chapter_title": "其他2023", "parent_code": "8.1"},
    {"chapter_code": "8.2", "chapter_title": "2024年财务会计报表", "parent_code": "8"},
    {"chapter_code": "8.2.1", "chapter_title": "资产负债表2024", "parent_code": "8.2"},
    {"chapter_code": "8.2.2", "chapter_title": "现金流量表2024", "parent_code": "8.2"},
    {"chapter_code": "8.2.3", "chapter_title": "利润表2024", "parent_code": "8.2"},
    {"chapter_code": "8.2.4", "chapter_title": "其他2024", "parent_code": "8.2"},
    {"chapter_code": "8.3", "chapter_title": "2025年财务会计报表", "parent_code": "8"},
    {"chapter_code": "8.3.1", "chapter_title": "资产负债表2025", "parent_code": "8.3"},
    {"chapter_code": "8.3.2", "chapter_title": "现金流量表2025", "parent_code": "8.3"},
    {"chapter_code": "8.3.3", "chapter_title": "利润表2025", "parent_code": "8.3"},
    {"chapter_code": "8.3.4", "chapter_title": "其他2025", "parent_code": "8.3"},
    {"chapter_code": "9", "chapter_title": "联合体协议书"},
    {"chapter_code": "10", "chapter_title": "企业银行基本账户开户许可证、基本存款账户信息"},
    {"chapter_code": "11", "chapter_title": "绿色发展顶层规划及执行情况"},
    {"chapter_code": "12", "chapter_title": "绿色管理体系认证"},
    {"chapter_code": "12.1", "chapter_title": "能源管理体系认证证书", "parent_code": "12"},
    {"chapter_code": "12.2", "chapter_title": "质量管理体系认证证书", "parent_code": "12"},
    {"chapter_code": "12.3", "chapter_title": "职业健康安全管理体系认证证书", "parent_code": "12"},
    {"chapter_code": "12.4", "chapter_title": "环境管理体系认证证书", "parent_code": "12"},
    {"chapter_code": "13", "chapter_title": "ESG报告、环评能评报告、废水废气废固报告"},
    {"chapter_code": "13.1", "chapter_title": "ESG报告", "parent_code": "13"},
    {"chapter_code": "13.2", "chapter_title": "环评／能评报告", "parent_code": "13"},
    {"chapter_code": "13.3", "chapter_title": "废水／废气／废固报告", "parent_code": "13"},
    {"chapter_code": "13.4", "chapter_title": "环境行政处罚", "parent_code": "13"},
    {"chapter_code": "14", "chapter_title": "绿色电力证书交易凭证和绿色电力证书"},
    {"chapter_code": "15", "chapter_title": "取得的科技成果"},
    {"chapter_code": "16", "chapter_title": "创新激励相关政策和机制"},
    {"chapter_code": "17", "chapter_title": "研发团队规模"},
    {"chapter_code": "18", "chapter_title": "中国质量奖、中国中国质量奖提名奖及中国工业大奖"},
    {"chapter_code": "19", "chapter_title": "高新技术企业证书"},
    {"chapter_code": "20", "chapter_title": "企业名称变更"},
    {"chapter_code": "21", "chapter_title": "关于小规模纳税人的说明"},
    {"chapter_code": "22", "chapter_title": "其他税率佐证材料"},
    {"chapter_code": "23", "chapter_title": "保证金缴纳证明材料"},
    {"chapter_code": "23.1", "chapter_title": "保证金明细表", "parent_code": "23"},
    {"chapter_code": "23.2", "chapter_title": "投标保证金缴纳证明材料", "parent_code": "23"},
    {"chapter_code": "24", "chapter_title": "认为需要加以说明的其它商务内容"},
    {"chapter_code": "24.1", "chapter_title": "不良行为处理情况通报", "parent_code": "24"},
    {"chapter_code": "24.2", "chapter_title": "公共信用信息报告、企业信用信息公示报告", "parent_code": "24"},
    {"chapter_code": "24.3", "chapter_title": "影响招投标工作公正性行为的凭证", "parent_code": "24"},
    {"chapter_code": "24.4", "chapter_title": "科研经费占比", "parent_code": "24"},
    {"chapter_code": "24.5", "chapter_title": "综合实力", "parent_code": "24"},
    {"chapter_code": "24.6", "chapter_title": "投标响应", "parent_code": "24"},
    {"chapter_code": "24.7", "chapter_title": "经营状况", "parent_code": "24"},
    {"chapter_code": "24.8", "chapter_title": "其他", "parent_code": "24"},
]


SGCC_DISTRIBUTION_TECHNICAL_CHAPTERS: list[dict[str, Any]] = [
    {"chapter_code": "1", "chapter_title": "技术偏差表"},
    {"chapter_code": "2", "chapter_title": "关于施工监理项目人员执业合规的承诺函"},
    {"chapter_code": "3", "chapter_title": "工期响应"},
    {"chapter_code": "4", "chapter_title": "资质情况"},
    {"chapter_code": "5", "chapter_title": "业绩情况"},
    {"chapter_code": "5.1", "chapter_title": "业绩证明1", "parent_code": "5"},
    {"chapter_code": "5.2", "chapter_title": "业绩证明2", "parent_code": "5"},
    {"chapter_code": "5.3", "chapter_title": "业绩证明3", "parent_code": "5"},
    {"chapter_code": "5.4", "chapter_title": "业绩证明（投标人员在公司资料库中自行选择）", "parent_code": "5"},
    {"chapter_code": "6", "chapter_title": "项目团队情况"},
    {"chapter_code": "7", "chapter_title": "其他资格条件情况"},
    {"chapter_code": "8", "chapter_title": "施工方案与技术措施"},
    {"chapter_code": "8.1", "chapter_title": "编制依据与标准", "parent_code": "8"},
    {"chapter_code": "8.2", "chapter_title": "工程概况与施工重难点分析", "parent_code": "8"},
    {"chapter_code": "8.3", "chapter_title": "施工组织与部署", "parent_code": "8"},
    {"chapter_code": "8.4", "chapter_title": "主要施工方法及技术要求", "parent_code": "8"},
    {"chapter_code": "8.5", "chapter_title": "质量管理体系与措施", "parent_code": "8"},
    {"chapter_code": "8.6", "chapter_title": "安全管理体系与措施", "parent_code": "8"},
    {"chapter_code": "8.7", "chapter_title": "施工进度计划与保障", "parent_code": "8"},
    {"chapter_code": "8.8", "chapter_title": "环境保护、绿色低碳与碳足迹管理", "parent_code": "8"},
    {"chapter_code": "8.9", "chapter_title": "科技创新与智能化应用", "parent_code": "8"},
    {"chapter_code": "8.10", "chapter_title": "地域特性专题方案", "parent_code": "8"},
    {"chapter_code": "8.11", "chapter_title": "竣工验收与数字化移交", "parent_code": "8"},
    {"chapter_code": "8.12", "chapter_title": "售后服务、培训及增值服务", "parent_code": "8"},
    {"chapter_code": "8.13", "chapter_title": "拟投入施工车辆、机具、工器具、检测设备、安全工器具及设施", "parent_code": "8"},
    {"chapter_code": "8.14", "chapter_title": "施工项目部组织架构创新设计", "parent_code": "8"},
    {"chapter_code": "8.15", "chapter_title": "国网年度框架施工工程投标其他创新内容", "parent_code": "8"},
    {"chapter_code": "9", "chapter_title": "工作规划描述"},
    {"chapter_code": "10", "chapter_title": "履约能力及质量保证措施"},
    {"chapter_code": "10.1", "chapter_title": "质量保证措施", "parent_code": "10"},
    {"chapter_code": "10.2", "chapter_title": "安全和绿色施工保障措施", "parent_code": "10"},
    {"chapter_code": "10.3", "chapter_title": "工程进度计划及保证措施", "parent_code": "10"},
    {"chapter_code": "11", "chapter_title": "服务承诺"},
    {"chapter_code": "12", "chapter_title": "技术评分标准涉及的支撑材料"},
    {"chapter_code": "13", "chapter_title": "技术规范书规定的其他应提交的文件"},
    {"chapter_code": "14", "chapter_title": "履约评价证明材料"},
    {"chapter_code": "14.1", "chapter_title": "各类履约评价证明材料（投标人员在公司资料库中自行选择）", "parent_code": "14"},
    {"chapter_code": "15", "chapter_title": "其他"},
    {"chapter_code": "16", "chapter_title": "履约承诺函"},
]


def business_template_chapters() -> list[dict[str, Any]]:
    return [
        {
            **chapter,
            "volume_type": "business",
            "metadata_json": {
                "template_key": SGCC_DISTRIBUTION_BUSINESS_TEMPLATE_KEY,
                "source_sample": "docs/samples/国网公司配网工程商务标目录.md",
                "parent_code": chapter.get("parent_code"),
            },
        }
        for chapter in SGCC_DISTRIBUTION_BUSINESS_CHAPTERS
    ]


def technical_template_chapters() -> list[dict[str, Any]]:
    return [
        {
            **chapter,
            "volume_type": "technical",
            "metadata_json": {
                "template_key": SGCC_DISTRIBUTION_TECHNICAL_TEMPLATE_KEY,
                "source_sample": "docs/samples/国网公司配网工程技术标目录.md",
                "parent_code": chapter.get("parent_code"),
            },
        }
        for chapter in SGCC_DISTRIBUTION_TECHNICAL_CHAPTERS
    ]


def base_bid_chapters() -> list[dict[str, Any]]:
    return [*QUALIFICATION_CHAPTERS, *business_template_chapters(), *technical_template_chapters()]
