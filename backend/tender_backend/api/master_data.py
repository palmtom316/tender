from __future__ import annotations

from fastapi import APIRouter, Depends
from tender_backend.api.master_data_certificates import router as certificate_router
from tender_backend.api.master_data_companies import router as company_router
from tender_backend.api.master_data_evidence import router as evidence_router
from tender_backend.api.master_data_financials import router as financial_router
from tender_backend.api.master_data_people import router as people_router
from tender_backend.api.master_data_performances import router as performance_router
from tender_backend.core.security import get_current_user


router = APIRouter(tags=["master-data"], dependencies=[Depends(get_current_user)])
_ASSET_TAXONOMY = [
    {
        "domain": "company_qualification",
        "label": "公司资质文件",
        "categories": [
            ("business_license", "营业执照"),
            ("company_credit_document", "公司信用文件"),
            ("legal_representative_id", "法人身份证"),
            ("enterprise_qualification", "企业资质证书及证明文件"),
            ("safety_quality_document", "安全质量证明文件"),
            ("financial_status_document", "企业财务状况"),
            ("account_information", "企业账户信息"),
            ("green_development_document", "企业绿色发展文件"),
            ("green_management_system", "绿色管理体系文件"),
            ("esg_document", "ESG文件"),
            ("green_power_certificate", "绿电绿证文件"),
            ("scientific_achievement", "科技成果文件"),
            ("innovation_incentive", "创新激励文件"),
            ("rd_team_document", "研发团队文件"),
            ("award_document", "获奖文件"),
            ("high_tech_enterprise", "高新技术企业文件"),
            ("company_name_change", "企业名称变更文件"),
        ],
    },
    {
        "domain": "company_asset",
        "label": "公司资产文件",
        "categories": [
            ("vehicle_certificate", "机动车辆证明文件"),
            ("tool_certificate", "工器具证明文件"),
            ("construction_equipment_certificate", "施工设备证明文件"),
        ],
    },
    {
        "domain": "company_performance",
        "label": "公司业绩文件",
        "categories": [
            ("similar_performance_table", "类似业绩表"),
            ("contract_document", "合同"),
            ("invoice_document", "发票"),
            ("invoice_verification", "发票验证"),
        ],
    },
    {
        "domain": "company_evaluation",
        "label": "公司履约评价",
        "categories": [
            ("performance_evaluation", "履约评价文件"),
        ],
    },
    {
        "domain": "personnel",
        "label": "人员资料",
        "categories": [
            ("performance_table", "业绩表"),
            ("id_card", "身份证"),
            ("graduation_certificate", "毕业证"),
            ("title_certificate", "职称证"),
            ("practice_certificate", "执业资格证"),
            ("safety_certificate", "安全生产合格证"),
            ("special_operation_certificate", "特种作业操作证"),
            ("social_security_proof", "社保参保证明"),
            ("labor_contract", "劳动合同书"),
        ],
    },
]


@router.get("/master-data/asset-taxonomy")
async def get_asset_taxonomy() -> dict[str, object]:
    return {"domains": _ASSET_TAXONOMY}
router.include_router(company_router)
router.include_router(people_router)
router.include_router(performance_router)
router.include_router(certificate_router)
router.include_router(financial_router)
router.include_router(evidence_router)
