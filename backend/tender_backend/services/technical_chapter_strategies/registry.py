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
    "8.1": TechnicalChapterStrategy(
        key="construction_organization_design",
        purpose="说明施工总体部署、施工流程、资源组织和国网工程管理措施。",
        sections=(
            ("施工总体部署", "结合工程范围、现场条件和国网工程管理要求进行施工区段、工序和资源部署。"),
            ("关键施工流程", "按准备、实施、验收、移交的主线组织工序，明确关键控制点和交接标准。"),
            ("资源投入与现场协调", "统筹人员、机械、材料、停电窗口和外部协调，降低交叉作业风险。"),
        ),
        required_facts=("project_scope", "project_location", "construction_period"),
        required_standards=("construction_process", "sgcc_management"),
        required_charts=("construction_flow",),
        innovation_slots=("停电窗口协同表", "移动化工序验收记录"),
        self_check_rules=("施工流程必须覆盖准备、实施、验收、移交", "需体现国网工程要求"),
    ),
    "8.2": TechnicalChapterStrategy(
        key="construction_technical_measures",
        purpose="说明关键施工技术措施、设备工具、质量验收和风险控制。",
        sections=(
            ("关键施工技术措施", "围绕主要工序列明施工方法、工器具、人员分工和验收标准。"),
            ("过程控制与验收标准", "对关键工序设置旁站、复核、隐蔽验收和资料同步要求。"),
            ("风险预控与创新措施", "针对交叉作业、停电窗口、设备到货等风险设置预控和纠偏措施。"),
        ),
        required_facts=("construction_method_constraints", "selected_equipment"),
        required_standards=("construction_technical", "acceptance"),
        required_charts=("construction_flow",),
        innovation_slots=("工序二维码交底", "关键节点影像留痕"),
        self_check_rules=("每项措施必须有责任岗位和验收标准", "不得泛泛承诺"),
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


def strategy_for_chapter(chapter_code: str | None) -> TechnicalChapterStrategy | None:
    return CHAPTER_STRATEGIES.get(str(chapter_code or ""))


def chart_recommendations_for_chapter(chapter_code: str | None) -> list[str]:
    strategy = strategy_for_chapter(chapter_code)
    return list(strategy.required_charts) if strategy else []
