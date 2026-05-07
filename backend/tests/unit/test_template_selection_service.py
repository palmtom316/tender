from uuid import uuid4

from tender_backend.services.template_selection_service import TemplateSelectionService


class FakeProjectRepo:
    def get(self, conn, *, project_id):
        return type(
            "Project",
            (),
            {
                "__dict__": {
                    "id": project_id,
                    "industry": "power",
                    "business_line": "10kV",
                    "voltage_level": ["10kV"],
                    "employer_type": "国网",
                    "evaluation_method": "综合评估法",
                    "qualification_review_type": "资格后审",
                    "tender_platform": "ECP",
                    "project_type": None,
                    "sub_type": None,
                }
            },
        )()


class FakeTemplateRepo:
    def list_all(self, conn):
        return [
            type(
                "Package",
                (),
                {
                    "id": uuid4(),
                    "package_key": "power-10kv-sgcc-ecp",
                    "display_name": "国网10kV综合评估法模板",
                    "package_type": "technical",
                    "category_code": "power",
                    "source_manifest": {"tags": ["10kV", "国网", "ECP", "综合评估法", "资格后审"]},
                },
            )(),
            type(
                "Package",
                (),
                {
                    "id": uuid4(),
                    "package_key": "municipal-general",
                    "display_name": "市政通用模板",
                    "package_type": "technical",
                    "category_code": "municipal",
                    "source_manifest": {},
                },
            )(),
        ]


def test_template_selection_prefers_matching_power_package():
    service = TemplateSelectionService(project_repo=FakeProjectRepo(), template_repo=FakeTemplateRepo())

    preview = service.preview(None, project_id=uuid4())

    assert preview["recommended"]["display_name"] == "国网10kV综合评估法模板"
    assert preview["recommended"]["score"] > preview["candidates"][1]["score"]
