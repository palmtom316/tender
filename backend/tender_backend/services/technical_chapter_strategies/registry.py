"""Versioned SGCC technical chapter strategies."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class TechnicalChapterStrategy:
    key: str
    purpose: str
    sections: tuple[tuple[str, str], ...]
    required_facts: tuple[str, ...]
    required_standards: tuple[str, ...]
    required_charts: tuple[str, ...]
    innovation_slots: tuple[str, ...]
    self_check_rules: tuple[str, ...]
    required_assets: tuple[str, ...] = ()
    forbidden_terms: tuple[str, ...] = ("报价", "投标报价", "最高限价", "单价", "总价")
    prompt_template_path: str | None = None


REPO_ROOT = Path(__file__).resolve().parents[4]
CHAPTER_8_PROMPT_PATH = "docs/samples/配网施工方案及技术措施提示词.md"
WORK_PLAN_PROMPT_PATH = "docs/samples/配网工作规划描述提示词.md"
QUALITY_PROMPT_PATH = "docs/samples/配网质量保证措施提示词.md"
SAFETY_GREEN_PROMPT_PATH = "docs/samples/配网安全与绿色施工保障措施提示词.md"
SCHEDULE_PROMPT_PATH = "docs/samples/配网工程进度计划及保证措施提示词.md"

SITE_CONDITION_KEYWORDS: tuple[str, ...] = (
    "高温",
    "雨季",
    "汛期",
    "山地",
    "城区受限",
    "地下管线密集",
    "交通管制",
    "高湿",
    "酸雨",
    "雾天",
)


CHAPTER_8_SECTIONS: tuple[tuple[str, str], ...] = (
    ("8.1 编制依据与标准", "基于招标文件、已确认约束和本地标准库建立标准-条款-响应矩阵；未匹配到来源的标准只列为待补充依据。"),
    ("8.2 工程概况与施工重难点分析", "围绕工程范围、现场条件、交叉跨越、停电窗口、地下管线和关键风险进行重难点分析。"),
    ("8.3 施工组织与部署", "说明施工区段、项目组织、资源投入、现场布置、材料供应和外部协调机制。"),
    ("8.4 主要施工方法及技术要求", "按测量、开挖、基础、电杆组立、架线、电缆敷设、设备安装、接地、恢复等工序形成SOP。"),
    ("8.5 质量管理体系与措施", "将质量目标、检验批、WHS控制点、旁站监督、材料设备质量和问题闭环嵌入施工过程。"),
    ("8.6 安全管理体系与措施", "识别危险源，设置安全组织、HSE检查、专项应急、培训交底和现场安全技术措施。"),
    ("8.7 施工进度计划与保障", "分解里程碑、关键路径、资源保障、气候影响、进度预警和纠偏机制。"),
    ("8.8 环境保护、绿色低碳与碳足迹管理", "响应绿色施工、扬尘噪声控制、废弃物回收、节能节材和低碳管理要求。"),
    ("8.9 科技创新与智能化应用", "仅在招标文件、评分标准或企业资料支持时写入智能装备、数字化施工、BIM和装配化应用。"),
    ("8.10 地域特性专题方案", "项目所在地或招标文件明确存在高温、雨季、城区受限、山地等条件时生成对应专项措施。"),
    ("8.11 竣工验收与数字化移交", "说明三级自检、预验收、竣工资料、试验报告、影像资料和数字化移交。"),
    ("8.12 售后服务、培训及增值服务", "仅基于招标文件服务要求和企业能力资料编写质保、响应、培训和增值服务。"),
    ("8.13 拟投入施工车辆、机具、工器具、检测设备、安全工器具及设施", "从设备库和项目配置中组织车辆机具、检测设备、安全工器具及检定状态，缺资料则列为待补充。"),
    ("8.14 施工项目部组织架构创新设计", "在人员库和项目组织要求基础上说明管理层级、岗位职责、协同机制和资源调配。"),
    ("8.15 国网年度框架施工工程投标其他创新内容", "仅当项目属于年度框架或评分标准要求创新时，汇总可佐证的进度、质量、数字化、应急和服务创新。"),
)


CHAPTER_8_CHILD_CHARTS: dict[str, tuple[str, ...]] = {
    "8.1": ("response_matrix",),
    "8.2": ("risk_matrix",),
    "8.3": ("construction_flow",),
    "8.4": ("construction_flow", "risk_matrix"),
    "8.5": ("quality_system",),
    "8.6": ("safety_system", "risk_matrix"),
    "8.7": ("schedule_gantt",),
    "8.11": ("closure_flow",),
    "8.13": ("equipment_table",),
}

WORK_PLAN_SECTIONS: tuple[tuple[str, str], ...] = (
    ("9.1 项目理解与总体工作思路", "基于项目事实和招标约束说明项目定位、实施关注点、关键成功因素和总体工作思路。"),
    ("9.2 工作目标分解与任务策划", "将工作规划分解为组织、技术、协调、风险、履约和资料任务，并建立责任接口和成果资料。"),
    ("9.3 项目管理组织与制度规划", "规划项目管理组织、职责边界、制度清单、会议报告、审批边界和问题闭环。"),
    ("9.4 协调配合工作规划", "识别发包人、监理、设计、运行、调度、属地、管线和居民物业等协调接口和形成资料。"),
    ("9.5 技术管理与创新应用规划", "规划技术文件、图纸会审、技术交底、专项方案审批、技术问题会商和创新应用边界。"),
    ("9.6 风险防控与应急管理规划", "建立项目级风险清单、动态监控、专项预案索引、升级机制和跨章节风险治理接口。"),
    ("9.7 履约创优与标准化管理规划", "将工作规划与承包商履约评价、标准化项目部、过程检查、资料归档和创优要求衔接。"),
    ("9.8 跨章节协同与边界管理", "明确第9章与第8章、第10.1节、第10.2节、第10.3节的分工，防止重复承诺和冲突。"),
)
QUALITY_ASSURANCE_SECTIONS: tuple[tuple[str, str], ...] = (
    ("10.1.1 编制依据与质量目标", "依据招标文件、技术规范书、设计文件、答疑补遗和已确认标准条款，原文响应质量目标并建立目标分解矩阵。"),
    ("10.1.2 质量管理标准和规范", "从本地标准库和用户确认标准中形成标准-条款-响应矩阵，未确认标准不得虚构版本号。"),
    ("10.1.3 质量保证体系与组织职责", "建立项目经理负责、技术负责人主控、质量负责人监督、专业负责人落实、班组自检的质量体系。"),
    ("10.1.4 全过程质量控制措施", "覆盖施工准备、材料设备进场、过程施工、控制点、隐蔽工程、试验调试和竣工移交。"),
    ("10.1.5 质量管理制度", "按交底、图纸会审、进场验收、三检、工序交接、隐蔽验收、例会、整改闭环、奖惩和保修制度组织。"),
    ("10.1.6 施工过程质量控制", "围绕项目施工范围选择适用配网工序，形成一工序一策、WHSR控制点和记录资料。"),
    ("10.1.7 质量通病防治措施", "针对基础、电缆、接地、柜体、二次接线、自动化通信和资料一致性等通病制定预控与治理。"),
    ("10.1.8 送电前质量专项检查", "组织送电前实体状态、试验结果、相序回路、缺陷闭环、资料齐备性和现场状态联合确认。"),
    ("10.1.9 质量问题处置和持续改进", "建立质量问题分级、隔离报告、原因分析、整改复查、销项归档和复盘改进流程。"),
    ("10.1.10 质量资料同步管理", "落实一工序一资料、一设备一档案、一隐蔽一影像、一缺陷一闭环、一验收一签认。"),
    ("10.1.11 业主、监理、运行单位协同验收机制", "前置报验、隐蔽共同验收、运维提前介入、送电联合检查和缺陷清单销项。"),
    ("10.1.12 质量履约评价保障措施", "将质量管理与国网承包商履约评价、过程检查、通报整改、达标投产和保修服务衔接。"),
    ("10.1.13 质量管理创新与亮点措施", "仅基于招标要求、评分项或企业资料写入可落地、可留痕、可验收的质量创新措施。"),
    ("10.1.14 数字化质量追溯系统应用", "说明材料、设备、工序、试验、缺陷和资料的追溯链，平台对接按发包人开放要求执行。"),
    ("10.1.15 地域特殊质量保证措施", "仅基于已确认所在地和环境条件编写高温、高湿、雨季、山地、城区受限和防腐等适配措施。"),
)


SAFETY_GREEN_SECTIONS: tuple[tuple[str, str], ...] = (
    ("10.2.1 安全与绿色施工目标响应", "原文响应安全文明施工、绿色施工、环保和职业健康目标，并建立目标分解和响应矩阵。"),
    ("10.2.2 安全管理体系与组织职责", "建立项目经理负责、安全负责人监督、专业负责人落实、班组安全员现场管控的安全管理体系。"),
    ("10.2.3 安全管理制度体系", "覆盖安全责任、教育培训、技术交底、临电、高处、吊装、消防、交通、劳保、隐患和应急制度。"),
    ("10.2.4 危险源辨识与风险分级管控", "根据施工范围识别危险源，建立风险分级、重大风险控制和动态评估机制。"),
    ("10.2.5 施工过程安全保障措施", "围绕临电、基坑、电杆、架线、吊装、电缆、临近带电体、试验和交通等工序设置安全控制。"),
    ("10.2.6 专项安全技术措施", "针对高处、起重、有限空间、临近带电、地下管线、交通、防火、防汛和防暑等编制专项措施。"),
    ("10.2.7 应急预案体系与响应机制", "建立触电、坠落、中暑、防汛、火灾、管线损坏、起重、有限空间和交通事故等应急预案。"),
    ("10.2.8 安全教育培训与班组安全管理", "建立培训矩阵、站班会、安全交底、班组自查、反违章、隐患上报和复盘机制。"),
    ("10.2.9 数字化安全管控手段", "基于已确认能力说明移动巡检、隐患台账、影像留存、电子围栏、视频监控和安全看板。"),
    ("10.2.10 绿色施工总体目标与管理体系", "响应绿色施工、低碳、环保和文明施工要求，建立四节一环保组织、制度和指标分解。"),
    ("10.2.11 环境保护与文明施工措施", "覆盖扬尘、噪声、水污染、土壤、固废、危险品、地下管线环境风险、场地恢复和文明施工。"),
    ("10.2.12 节材、节水、节能与节地措施", "按节材、节水、节能、节地分类制定控制措施，量化指标必须有来源。"),
    ("10.2.13 碳排放管理与碳足迹核算", "仅在招标、评分或用户确认要求时展开核算边界、数据台账、减碳措施和报告条件。"),
    ("10.2.14 职业健康与劳动保护", "覆盖防暑、防尘、防噪、防有害气体、劳保用品、健康检查、生活区卫生和传染病管理。"),
    ("10.2.15 安全绿色履约评价保障", "将安全绿色施工与承包商履约评价、过程检查、通报整改、环保检查和服务衔接。"),
    ("10.2.16 地域特殊安全与绿色施工措施", "仅基于已确认所在地和环境条件编写高温、雨季、山地、城区受限、地下管线和交通适配措施。"),
)


SCHEDULE_ASSURANCE_SECTIONS: tuple[tuple[str, str], ...] = (
    ("10.3.1 编制依据与进度目标", "依据招标文件、技术规范书、设计文件、答疑补遗和已确认约束，原文响应工期目标并建立进度目标分解矩阵。"),
    ("10.3.2 进度管理体系与组织职责", "建立项目经理统筹、技术负责人计划审核、施工负责人落实、材料设备负责人保障和资料同步留痕的进度体系。"),
    ("10.3.3 工期约束与关键假设", "汇总工期、里程碑、停电窗口、供货周期、交叉施工和外部审批等已确认约束，不编造未确认假设。"),
    ("10.3.4 施工阶段划分与流水组织", "按施工准备、土建基础、线路或电缆施工、设备安装、试验调试和验收移交划分阶段并说明衔接条件。"),
    ("10.3.5 总体施工进度计划", "基于已确认工期和里程碑形成总体计划，并在系统推荐时插入施工进度计划图占位符。"),
    ("10.3.6 关键路径与节点控制", "识别材料到货、土建基础、电缆敷设、设备安装、试验调试、验收送电等关键工作和节点完成标准。"),
    ("10.3.7 资源配置与进度匹配", "将人员、机具、试验调试和材料供应资源与施工阶段匹配，缺少来源的资源数量列为待补充。"),
    ("10.3.8 材料设备供应进度保障", "围绕关键物资到货、进场验收、缺料预警、安装衔接和质量验收建立供应保障措施。"),
    ("10.3.9 停电窗口与外部协调保障", "覆盖停电送电、运行单位接口、占道交通、居民物业和相邻工程协调，不承诺未确认许可。"),
    ("10.3.10 进度动态管控与预警纠偏", "建立日跟踪、周分析、节点复核、预警纠偏和复盘闭环，阈值和频次必须有来源。"),
    ("10.3.11 延误风险识别与应急赶工", "识别材料、天气、地下障碍、停电窗口、外部审批和设计变更等延误风险，并给出受约束的赶工措施。"),
    ("10.3.12 质量安全环保与进度协同", "明确进度安排不得突破质量验收、安全许可、绿色施工和外部审批边界，并与10.1、10.2保持一致。"),
    ("10.3.13 数字化进度管理与资料留痕", "基于已确认能力说明移动填报、进度台账、影像留痕、节点看板和资料闭环，不指定无来源软件品牌。"),
    ("10.3.14 框架项目多项目进度协调", "仅在年度框架或批次多项目场景下说明任务排序、资源统筹、机具共享、专项技术组调配和复盘机制。"),
    ("10.3.15 地域特殊进度保障措施", "仅基于已确认所在地和环境条件编写高温、雨季、山地、城区受限、交通组织和材料运输等进度保障措施。"),
)


LONGFORM_CHAPTER_CONFIG: dict[str, dict[str, object]] = {
    "8": {"enabled": True, "min_target_pages": 80, "section_set_key": "8"},
    "9": {"enabled": True, "min_target_pages": 30, "section_set_key": "9"},
    "10.1": {"enabled": True, "min_target_pages": 35, "section_set_key": "10.1"},
    "10.2": {"enabled": True, "min_target_pages": 35, "section_set_key": "10.2"},
    "10.3": {"enabled": True, "min_target_pages": 35, "section_set_key": "10.3"},
}

LONGFORM_SECTION_SETS: dict[str, tuple[tuple[str, str], ...]] = {
    "8": CHAPTER_8_SECTIONS,
    "9": WORK_PLAN_SECTIONS,
    "10.1": QUALITY_ASSURANCE_SECTIONS,
    "10.2": SAFETY_GREEN_SECTIONS,
    "10.3": SCHEDULE_ASSURANCE_SECTIONS,
}

SECTION_WEIGHTS: dict[str, dict[str, float]] = {
    "8": {
        "8.1": 0.6,
        "8.2": 1.3,
        "8.3": 1.2,
        "8.4": 1.8,
        "8.5": 1.5,
        "8.6": 1.5,
        "8.7": 1.4,
        "8.8": 1.0,
        "8.9": 0.9,
        "8.10": 1.0,
        "8.11": 1.0,
        "8.12": 0.7,
        "8.13": 0.6,
        "8.14": 0.6,
        "8.15": 0.5,
    },
    "9": {
        "9.1": 1.2,
        "9.2": 1.2,
        "9.3": 1.4,
        "9.4": 1.2,
        "9.5": 1.1,
        "9.6": 1.2,
        "9.7": 1.0,
        "9.8": 0.8,
    },
    "10.1": {
        "10.1.1": 0.8,
        "10.1.2": 0.9,
        "10.1.3": 1.3,
        "10.1.4": 1.4,
        "10.1.5": 1.0,
        "10.1.6": 1.4,
        "10.1.7": 1.1,
        "10.1.8": 1.0,
        "10.1.9": 1.0,
        "10.1.10": 1.0,
        "10.1.11": 0.9,
        "10.1.12": 0.8,
        "10.1.13": 0.7,
        "10.1.14": 0.8,
        "10.1.15": 0.7,
    },
    "10.2": {
        "10.2.1": 0.8,
        "10.2.2": 1.2,
        "10.2.3": 1.0,
        "10.2.4": 1.4,
        "10.2.5": 1.4,
        "10.2.6": 1.2,
        "10.2.7": 1.0,
        "10.2.8": 0.8,
        "10.2.9": 0.8,
        "10.2.10": 0.9,
        "10.2.11": 1.0,
        "10.2.12": 0.9,
        "10.2.13": 0.8,
        "10.2.14": 0.7,
        "10.2.15": 0.7,
        "10.2.16": 0.7,
    },
    "10.3": {
        "10.3.1": 0.8,
        "10.3.2": 1.0,
        "10.3.3": 1.1,
        "10.3.4": 1.2,
        "10.3.5": 1.5,
        "10.3.6": 1.3,
        "10.3.7": 1.1,
        "10.3.8": 1.0,
        "10.3.9": 1.0,
        "10.3.10": 1.0,
        "10.3.11": 0.9,
        "10.3.12": 0.8,
        "10.3.13": 0.8,
        "10.3.14": 0.7,
        "10.3.15": 0.7,
    },
}

DEFAULT_CHARTS: dict[str, dict[str, tuple[str, ...]]] = {
    "8": CHAPTER_8_CHILD_CHARTS,
    "9": {
        "9.3": ("responsibility_matrix",),
        "9.4": ("interface_table",),
        "9.6": ("risk_matrix",),
    },
    "10.1": {
        "10.1.3": ("quality_system",),
        "10.1.4": ("construction_flow",),
        "10.1.9": ("closure_flow",),
        "10.1.10": ("data_flow",),
    },
    "10.2": {
        "10.2.2": ("safety_system",),
        "10.2.4": ("risk_matrix",),
        "10.2.7": ("emergency_org",),
        "10.2.11": ("indicator_table",),
    },
    "10.3": {
        "10.3.5": ("schedule_gantt",),
        "10.3.6": ("critical_path",),
        "10.3.9": ("interface_table",),
        "10.3.10": ("closure_flow",),
    },
}

DEFAULT_TABLES: dict[str, dict[str, tuple[tuple[str, ...], ...]]] = {
    "8": {
        "8.1": (("响应矩阵", "标准响应矩阵", "条款响应矩阵"),),
        "8.2": (("工程概况表", "工程概况一览表", "项目概况表", "重难点分析表", "重点难点分析表"),),
        "8.4": (("主要施工方法表", "主要施工方法清单", "主要施工工序表", "施工方法表"),),
        "8.5": (("质量控制点表", "WHS控制点表", "质量控制点清单", "WHSR控制点表", "质量控制清单"),),
        "8.6": (("安全风险管控表", "危险源辨识与分级管控表", "风险分级管控清单", "危险源辨识与管控表"),),
        "8.7": (("工期保证措施表", "进度保证措施表", "关键工期保证表"),),
        "8.13": (("设备清单", "设备配置表", "施工设备表", "拟投入设备表"),),
    },
    "9": {
        "9.2": (("工作任务分解表", "任务策划表"),),
        "9.4": (("协调接口表", "外部协调清单"),),
        "9.6": (("风险防控台账", "风险治理清单"),),
    },
    "10.1": {
        "10.1.1": (("质量目标分解表", "质量目标响应矩阵"),),
        "10.1.6": (("质量控制点表", "WHS控制点表"),),
        "10.1.7": (("质量通病防治表", "通病治理清单"),),
    },
    "10.2": {
        "10.2.4": (("危险源辨识表", "风险分级管控清单"),),
        "10.2.5": (("安全措施表", "施工安全控制清单"),),
        "10.2.11": (("环境保护措施表", "文明施工检查表"),),
    },
    "10.3": {
        "10.3.3": (("工期约束清单", "关键假设表"),),
        "10.3.5": (("总体进度计划表", "阶段计划表"),),
        "10.3.10": (("进度预警纠偏台账", "节点纠偏表"),),
    },
}


CHAPTER_STRATEGIES: dict[str, TechnicalChapterStrategy] = {
    "1": TechnicalChapterStrategy(
        key="technical_deviation_table",
        purpose="生成技术偏差表并明确无偏差或逐项偏差响应。",
        sections=(
            ("技术偏差表", "按招标技术条款逐项列示响应情况；无偏差时输出无偏差声明，不混入商务报价内容。"),
        ),
        required_facts=("technical_clauses", "confirmed_deviation_items"),
        required_standards=("technical_specification",),
        required_charts=(),
        innovation_slots=(),
        self_check_rules=("必须区分技术偏差与商务偏差", "无偏差不得编造偏差项", "不得出现报价信息"),
        required_assets=("technical_deviation_table",),
    ),
    "2": TechnicalChapterStrategy(
        key="personnel_practice_compliance_commitment",
        purpose="形成关于施工监理项目人员执业合规的承诺函。",
        sections=(
            ("承诺主体与适用范围", "说明承诺适用于本项目拟派项目人员执业资格、在岗履约和合规管理。"),
            ("人员执业合规承诺", "承诺人员证书真实有效、注册关系合规、到岗履约满足招标要求。"),
            ("违约责任与资料留存", "说明证书、社保、任命和承诺资料随投标文件提交并接受核验。"),
        ),
        required_facts=("selected_personnel", "personnel_compliance_requirements", "project_roles"),
        required_standards=("personnel_practice_compliance",),
        required_charts=(),
        innovation_slots=("人员证书核验清单",),
        self_check_rules=("人员姓名、证书和岗位必须与人员附件一致", "承诺函不得写入报价信息", "缺少证书不得编造资质"),
        required_assets=("personnel_certificates", "social_security_records", "personnel_commitment_template"),
    ),
    "3": TechnicalChapterStrategy(
        key="schedule_response",
        purpose="响应招标文件工期、里程碑和进度约束。",
        sections=(
            ("工期目标响应", "原文响应计划工期、开竣工节点、停电窗口和里程碑要求。"),
            ("工期保障承诺", "说明组织、资源、材料、协调和风险纠偏保障，不承诺未确认赶工条件。"),
        ),
        required_facts=("construction_period", "milestones", "schedule_constraints"),
        required_standards=("schedule_management",),
        required_charts=("schedule_gantt",),
        innovation_slots=("节点预警清单",),
        self_check_rules=("工期数字必须来自招标文件或用户确认", "不得与10.3进度计划冲突", "不得出现报价信息"),
        required_assets=("schedule_commitment", "milestone_plan"),
    ),
    "4": TechnicalChapterStrategy(
        key="technical_qualification_status",
        purpose="组织技术分册要求的资质证书和能力证明。",
        sections=(
            ("资质响应范围", "列示与技术标相关的企业资质、许可、体系证书和有效期。"),
            ("证书核验说明", "说明证书来源、有效状态、附件索引和缺口材料。"),
        ),
        required_facts=("qualification_requirements", "qualification_certificates"),
        required_standards=("qualification_compliance",),
        required_charts=(),
        innovation_slots=("证书有效期预警",),
        self_check_rules=("证书名称、等级、有效期必须与附件一致", "缺少证书必须列缺口", "不得出现报价信息"),
        required_assets=("qualification_certificates", "license_documents"),
    ),
    "5": TechnicalChapterStrategy(
        key="technical_performance_status",
        purpose="组织技术分册业绩材料和证明附件。",
        sections=(
            ("业绩响应范围", "按招标要求列示同类项目业绩、合同范围、完成状态和证明材料。"),
            ("业绩证明索引", "将合同、验收、评价、发票等附件与业绩条目关联。"),
        ),
        required_facts=("performance_requirements", "project_performances"),
        required_standards=("performance_compliance",),
        required_charts=(),
        innovation_slots=("业绩证明闭环索引",),
        self_check_rules=("业绩数量和时间范围必须满足招标要求", "附件不得错配", "不得出现报价信息"),
        required_assets=("performance_contracts", "acceptance_certificates", "performance_evaluations"),
    ),
    "6": TechnicalChapterStrategy(
        key="project_team",
        purpose="说明项目管理组织、关键岗位配置和职责闭环。",
        sections=(
            ("项目组织架构", "建立项目经理负责制，明确技术、质量、安全、进度、资料等岗位职责和接口关系。"),
            ("关键岗位配置", "围绕招标文件人员数量、资格、社保和到岗要求配置管理人员，确保人证岗匹配。"),
            ("职责分工与协同机制", "通过责任矩阵、例会、交底和闭环跟踪机制保障项目团队高效履约。"),
        ),
        required_facts=("personnel_requirements", "selected_personnel"),
        required_standards=("project_management",),
        required_charts=("org_chart", "responsibility_matrix"),
        innovation_slots=("岗位履约看板", "关键岗位 AB 角备份"),
        self_check_rules=("人员数量和证书要求必须逐项响应", "必须校验人证岗匹配", "必须包含项目团队任命或到岗承诺", "不得出现报价信息"),
        required_assets=("project_team_roster", "personnel_certificates", "appointment_letter", "team_commitment"),
    ),
    "7": TechnicalChapterStrategy(
        key="other_qualification_conditions",
        purpose="响应招标文件技术分册其他资格条件。",
        sections=(
            ("其他资格条件清单", "逐项列示除资质、业绩、人员外的其他技术资格条件。"),
            ("响应资料索引", "将承诺函、截图、证书、制度文件和说明材料对应到资格条件。"),
        ),
        required_facts=("other_qualification_requirements",),
        required_standards=("qualification_compliance",),
        required_charts=(),
        innovation_slots=("其他资格条件核验清单",),
        self_check_rules=("不得遗漏否决性资格条件", "缺少附件必须列缺口", "不得出现报价信息"),
        required_assets=("other_qualification_assets", "qualification_commitments"),
    ),
    "8": TechnicalChapterStrategy(
        key="construction_plan_and_technical_measures",
        purpose="按用户确认的第8章内部15项子目录，系统化编制施工方案与技术措施。",
        sections=CHAPTER_8_SECTIONS,
        required_facts=("project_scope", "project_location", "construction_period", "quality_requirement"),
        required_standards=("construction_process", "construction_technical", "acceptance", "sgcc_management"),
        required_charts=("construction_flow", "risk_matrix", "quality_system", "safety_system", "schedule_gantt", "response_matrix", "equipment_table", "closure_flow"),
        innovation_slots=("标准化SOP", "FMEA风险矩阵", "WBS进度分解", "数字化施工留痕", "装配化施工条件化应用"),
        self_check_rules=(
            "15项必须作为第8章内部子目录，不得提升为技术标一级章节",
            "地域、设备、标准、创新和服务承诺必须有招标文件、评分标准、标准库或企业资料来源",
            "不得输出内部评分提示语、虚构参数或无佐证领先性表述",
        ),
        prompt_template_path=CHAPTER_8_PROMPT_PATH,
    ),
    "9": TechnicalChapterStrategy(
        key="work_plan_description",
        purpose="按第9章《工作规划描述》提示词，说明总体规划、管理接口、协调机制、风险治理、履约创优和跨章节边界管理。",
        sections=WORK_PLAN_SECTIONS,
        required_facts=("project_scope", "project_location", "construction_period", "owner_management_requirements", "external_coordination_constraints"),
        required_standards=("project_management", "sgcc_management"),
        required_charts=("responsibility_matrix", "risk_matrix", "response_matrix", "interface_table", "indicator_table"),
        innovation_slots=("工作任务矩阵", "协调接口清单", "风险治理台账", "跨章节索引", "标准化项目部规划"),
        self_check_rules=(
            "9.1至9.8必须作为第9章内部子章节，不得误写为第7章、第8章或第10章",
            "第9章只写规划和接口，不重复第8章施工方法、第10.1质量控制、第10.2安全绿色、第10.3进度计划的详细承诺",
            "外部许可、会议频次、响应时限、创新成果和创优承诺必须有招标文件、评分标准或企业资料来源",
            "不得输出内部评分提示语、价格信息、硬编码地域或无来源绝对化承诺",
        ),
        prompt_template_path=WORK_PLAN_PROMPT_PATH,
    ),
    "10.1": TechnicalChapterStrategy(
        key="quality_assurance",
        purpose="按第10章第10.1节《质量保证措施》提示词，响应质量目标并系统说明质量体系、过程控制、验收、资料和闭环改进。",
        sections=QUALITY_ASSURANCE_SECTIONS,
        required_facts=("quality_requirement", "quality_constraints"),
        required_standards=("quality_acceptance", "sgcc_quality"),
        required_charts=("quality_system", "indicator_table", "response_matrix", "construction_flow", "closure_flow", "data_flow", "interface_table"),
        innovation_slots=("质量问题销项看板", "首件样板引路", "一设备一档案", "数字化质量追溯", "质量负面清单"),
        self_check_rules=(
            "10.1.1至10.1.15必须作为10.1节内部子章节，不得提升为第10章其他一级子项",
            "质量目标必须原文响应",
            "必须包含检查、整改、复查、销项、归档和复盘闭环",
            "地域、设备、标准、创新和承诺必须有招标文件、评分标准、标准库或企业资料来源",
        ),
        prompt_template_path=QUALITY_PROMPT_PATH,
    ),
    "10.2": TechnicalChapterStrategy(
        key="safety_green_construction",
        purpose="按第10章第10.2节《安全和绿色施工保障措施》提示词，响应安全文明施工、绿色施工、风险分级管控和应急闭环要求。",
        sections=SAFETY_GREEN_SECTIONS,
        required_facts=("safety_constraints", "site_conditions"),
        required_standards=("safety", "green_construction"),
        required_charts=("safety_system", "risk_matrix", "indicator_table", "emergency_org", "data_flow", "interface_table"),
        innovation_slots=("风险四色看板", "班前会移动签到", "隐患闭环看板", "数字化安全巡检", "绿色施工台账"),
        self_check_rules=(
            "10.2.1至10.2.16必须作为10.2节内部子章节，不得提升为第10章其他一级子项",
            "必须包含安全文明施工和绿色施工",
            "必须包含危险源辨识、风险分级管控和应急响应闭环",
            "地域、设备、标准、数字化能力、绿色指标和承诺必须有招标文件、评分标准、标准库或企业资料来源",
        ),
        prompt_template_path=SAFETY_GREEN_PROMPT_PATH,
    ),
    "10.3": TechnicalChapterStrategy(
        key="schedule_assurance",
        purpose="按第10章第10.3节《工程进度计划及保证措施》提示词，响应工期目标并系统说明里程碑、关键路径、资源匹配、外部协调和纠偏闭环。",
        sections=SCHEDULE_ASSURANCE_SECTIONS,
        required_facts=("construction_period", "schedule_constraints", "milestones", "outage_windows", "material_lead_times", "site_conditions"),
        required_standards=("schedule_management",),
        required_charts=("schedule_gantt", "responsibility_matrix", "critical_path", "indicator_table", "interface_table", "closure_flow", "data_flow"),
        innovation_slots=("节点预警清单", "资源动态调配机制", "进度数据看板", "影像留痕", "多项目调度机制"),
        self_check_rules=(
            "10.3.1至10.3.15必须作为10.3节内部子章节，不得输出第6章或提升为第10章其他一级子项",
            "工期目标、里程碑、停电窗口、外部许可和赶工承诺必须有招标文件或用户确认来源",
            "必须与第8.7节进度摘要、第10.1节质量控制、第10.2节安全许可和绿色施工要求一致",
            "不得输出内部评分提示语、价格信息、硬编码地域、无来源数值或具体软件品牌",
        ),
        prompt_template_path=SCHEDULE_PROMPT_PATH,
    ),
    "10": TechnicalChapterStrategy(
        key="performance_capability_quality_assurance",
        purpose="作为第10章总章，承接履约能力、质量、安全绿色和进度保证措施。",
        sections=(
            ("第10章组成说明", "说明本章由10.1质量、10.2安全绿色、10.3进度三部分组成，并保持三部分承诺一致。"),
        ),
        required_facts=("quality_requirement", "safety_constraints", "construction_period"),
        required_standards=("quality_acceptance", "safety", "schedule_management"),
        required_charts=(),
        innovation_slots=("质量安全进度协同索引",),
        self_check_rules=("不得替代10.1、10.2、10.3的详细内容", "不得出现报价信息"),
    ),
    "11": TechnicalChapterStrategy(
        key="service_commitment",
        purpose="形成服务承诺章节，覆盖响应时限、保修、培训、资料移交和增值服务边界。",
        sections=(
            ("服务响应承诺", "响应招标文件服务、保修、响应时限和配合要求。"),
            ("服务保障措施", "说明组织、人员、备件、资料、培训和回访机制。"),
        ),
        required_facts=("service_requirements", "warranty_requirements"),
        required_standards=("service_management",),
        required_charts=(),
        innovation_slots=("服务闭环台账", "回访记录机制"),
        self_check_rules=("响应时限必须有来源", "不得承诺无来源增值服务", "不得出现报价信息"),
        required_assets=("service_commitment_template", "after_sales_capability_assets"),
    ),
    "12": TechnicalChapterStrategy(
        key="technical_scoring_materials",
        purpose="逐项响应技术评分点并组织证明材料。",
        sections=(
            ("评分点响应索引", "逐项识别技术评分标准并建立章节、资料、证明材料对应关系。"),
            ("支撑材料组织", "按评分维度组织业绩、人员、方案、标准和创新措施证明材料。"),
        ),
        required_facts=("scoring_items",),
        required_standards=("scoring_support",),
        required_charts=(),
        innovation_slots=("评分点闭环索引",),
        self_check_rules=("评分点不得遗漏",),
    ),
    "13": TechnicalChapterStrategy(
        key="sgcc_technical_spec_response",
        purpose="对技术规范书和国网标准符合性进行集中响应。",
        sections=(
            ("技术规范响应范围", "对技术规范书要求逐条确认响应范围、实施措施和验收依据。"),
            ("国网标准符合性措施", "将国网工程施工、质量、安全、资料和验收要求嵌入实施过程。"),
        ),
        required_facts=("sgcc_constraints",),
        required_standards=("sgcc_standard",),
        required_charts=(),
        innovation_slots=("标准条款响应矩阵",),
        self_check_rules=("只能引用本地标准库或用户确认标准",),
    ),
    "14": TechnicalChapterStrategy(
        key="performance_evaluation_materials",
        purpose="组织履约评价证明材料并说明适用范围。",
        sections=(
            ("履约评价证明清单", "列示履约评价、用户评价、考核结果等证明材料。"),
            ("适用性说明", "说明证明材料与招标要求、项目类型和评价周期的对应关系。"),
        ),
        required_facts=("performance_evaluation_requirements", "performance_evaluations"),
        required_standards=("performance_evaluation",),
        required_charts=(),
        innovation_slots=("履约评价索引",),
        self_check_rules=("评价材料必须与附件一致", "不得夸大评价等级", "不得出现报价信息"),
        required_assets=("performance_evaluation_certificates",),
    ),
    "15": TechnicalChapterStrategy(
        key="other_technical_documents",
        purpose="承载招标文件要求的其他技术文件和补充说明。",
        sections=(
            ("其他技术文件清单", "列示招标文件要求但未归入前述章节的技术材料。"),
            ("补充说明", "说明每项材料对应的招标条款、附件和响应边界。"),
        ),
        required_facts=("other_technical_requirements",),
        required_standards=("technical_specification",),
        required_charts=(),
        innovation_slots=("其他技术资料索引",),
        self_check_rules=("不得把商务报价材料放入技术其他章节", "缺少材料必须列缺口", "不得出现报价信息"),
        required_assets=("other_technical_assets",),
    ),
    "16": TechnicalChapterStrategy(
        key="performance_commitment_letter",
        purpose="形成履约承诺函并绑定签章、授权和承诺附件。",
        sections=(
            ("履约承诺范围", "承诺按招标文件、合同条件、技术规范和项目管理要求履约。"),
            ("履约保障与责任", "说明人员到岗、质量安全、进度、资料移交、保修和违约责任。"),
        ),
        required_facts=("performance_commitment_requirements", "authorized_signatory"),
        required_standards=("contract_performance", "sgcc_management"),
        required_charts=(),
        innovation_slots=("履约承诺闭环清单",),
        self_check_rules=("承诺主体和签署人必须与授权资料一致", "不得承诺无来源服务或报价条件", "不得出现报价信息"),
        required_assets=("performance_commitment_template", "authorization_letter", "seal_confirmation"),
    ),
}

for _heading, _body in CHAPTER_8_SECTIONS:
    _chapter_code, _title = _heading.split(" ", 1)
    CHAPTER_STRATEGIES[_chapter_code] = TechnicalChapterStrategy(
        key=f"construction_plan_{_chapter_code.replace('.', '_')}",
        purpose=f"编制第8章内部子目录《{_title}》，并保持其不提升为技术标一级章节。",
        sections=((_title, _body),),
        required_facts=("project_scope", "project_location", "construction_period", "quality_requirement"),
        required_standards=("construction_process", "construction_technical", "acceptance", "sgcc_management"),
        required_charts=CHAPTER_8_CHILD_CHARTS.get(_chapter_code, ()),
        innovation_slots=("标准化SOP", "风险矩阵", "数字化施工留痕"),
        self_check_rules=(
            "本内容必须作为第8章内部子目录输出",
            "地域、设备、标准、创新和服务承诺必须有招标文件、评分标准、标准库或企业资料来源",
            "不得输出内部评分提示语、虚构参数或无佐证领先性表述",
        ),
        prompt_template_path=CHAPTER_8_PROMPT_PATH,
    )


def strategy_for_chapter(chapter_code: str | None) -> TechnicalChapterStrategy | None:
    return CHAPTER_STRATEGIES.get(str(chapter_code or ""))


def chart_recommendations_for_chapter(chapter_code: str | None) -> list[str]:
    strategy = strategy_for_chapter(chapter_code)
    return list(strategy.required_charts) if strategy else []


@lru_cache(maxsize=16)
def prompt_template_for_chapter(chapter_code: str | None) -> dict[str, str] | None:
    strategy = strategy_for_chapter(chapter_code)
    if strategy is None or not strategy.prompt_template_path:
        return None
    path = REPO_ROOT / strategy.prompt_template_path
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return {
            "path": strategy.prompt_template_path,
            "content_md": "",
            "status": "missing",
        }
    return {
        "path": strategy.prompt_template_path,
        "content_md": content,
        "status": "loaded",
    }
