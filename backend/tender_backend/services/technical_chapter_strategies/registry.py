"""Versioned SGCC technical chapter strategies."""

from __future__ import annotations

from dataclasses import dataclass


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
    forbidden_terms: tuple[str, ...] = ("报价", "投标报价", "最高限价", "单价", "总价")


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
    "8.2": ("risk_matrix",),
    "8.3": ("construction_flow",),
    "8.4": ("construction_flow", "risk_matrix"),
    "8.5": ("quality_system",),
    "8.6": ("safety_system", "risk_matrix"),
    "8.7": ("schedule_gantt",),
}


CHAPTER_STRATEGIES: dict[str, TechnicalChapterStrategy] = {
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
        self_check_rules=("人员数量和证书要求必须逐项响应", "不得出现报价信息"),
    ),
    "8": TechnicalChapterStrategy(
        key="construction_plan_and_technical_measures",
        purpose="按用户确认的第8章内部15项子目录，系统化编制施工方案与技术措施。",
        sections=CHAPTER_8_SECTIONS,
        required_facts=("project_scope", "project_location", "construction_period", "quality_requirement"),
        required_standards=("construction_process", "construction_technical", "acceptance", "sgcc_management"),
        required_charts=("construction_flow", "risk_matrix", "quality_system", "safety_system", "schedule_gantt"),
        innovation_slots=("标准化SOP", "FMEA风险矩阵", "WBS进度分解", "数字化施工留痕", "装配化施工条件化应用"),
        self_check_rules=(
            "15项必须作为第8章内部子目录，不得提升为技术标一级章节",
            "地域、设备、标准、创新和服务承诺必须有招标文件、评分标准、标准库或企业资料来源",
            "不得输出内部评分提示语、虚构参数或无佐证领先性表述",
        ),
    ),
    "10.1": TechnicalChapterStrategy(
        key="quality_assurance",
        purpose="响应质量目标并说明质量体系、过程控制、验收和闭环改进。",
        sections=(
            ("质量目标响应", "逐项响应招标文件质量目标，确保工程质量、资料质量和验收结果满足国网工程要求。"),
            ("质量管理组织", "建立项目经理牵头、技术负责人主控、专业人员分级负责的质量管理体系。"),
            ("过程质量控制措施", "覆盖材料设备进场、工序交接、隐蔽工程、关键节点验收和资料同步归档。"),
            ("质量检查与闭环改进", "通过自检、互检、专检、问题整改、复验销项形成质量闭环。"),
        ),
        required_facts=("quality_requirement", "quality_constraints"),
        required_standards=("quality_acceptance", "sgcc_quality"),
        required_charts=("quality_system",),
        innovation_slots=("质量问题销项看板", "首件样板引路"),
        self_check_rules=("质量目标必须原文响应", "必须包含检查与整改闭环"),
    ),
    "10.2": TechnicalChapterStrategy(
        key="safety_green_construction",
        purpose="响应安全文明施工与绿色施工要求，说明风险分级管控和应急闭环。",
        sections=(
            ("安全文明施工目标", "响应安全文明施工和绿色施工要求，落实国网工程安全管理标准。"),
            ("风险识别与分级管控", "识别临电、吊装、高处、交叉作业、消防和交通等风险，形成预控清单。"),
            ("现场文明与绿色施工措施", "控制扬尘、噪声、废弃物、材料堆放和现场标识，保持作业面有序。"),
            ("应急响应与持续改进", "建立应急组织、预案演练、事件报告和复盘改进机制。"),
        ),
        required_facts=("safety_constraints", "site_conditions"),
        required_standards=("safety", "green_construction"),
        required_charts=("safety_system", "risk_matrix"),
        innovation_slots=("风险四色看板", "班前会移动签到"),
        self_check_rules=("必须包含文明施工和绿色施工", "必须包含风险分级管控"),
    ),
    "10.3": TechnicalChapterStrategy(
        key="schedule_assurance",
        purpose="响应工期目标并说明里程碑、关键路径、资源保障和纠偏机制。",
        sections=(
            ("里程碑计划", "将总工期分解为准备、施工、调试、验收、移交等里程碑并明确完成标准。"),
            ("关键路径与资源保障", "围绕关键工序配置人员、设备、材料和协调资源，保障连续施工。"),
            ("进度预警与纠偏机制", "建立日跟踪、周分析、节点预警和资源加倍投入等纠偏措施。"),
        ),
        required_facts=("construction_period", "schedule_constraints"),
        required_standards=("schedule_management",),
        required_charts=("schedule_gantt",),
        innovation_slots=("节点预警清单", "资源动态调配机制"),
        self_check_rules=("必须响应工期目标", "必须包含纠偏措施"),
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
    )


def strategy_for_chapter(chapter_code: str | None) -> TechnicalChapterStrategy | None:
    return CHAPTER_STRATEGIES.get(str(chapter_code or ""))


def chart_recommendations_for_chapter(chapter_code: str | None) -> list[str]:
    strategy = strategy_for_chapter(chapter_code)
    return list(strategy.required_charts) if strategy else []
