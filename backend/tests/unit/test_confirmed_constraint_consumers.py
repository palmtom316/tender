from __future__ import annotations

from uuid import uuid4

from tender_backend.services.compliance_check_service import ComplianceCheckService
from tender_backend.services.submission_checklist_service import SubmissionChecklistService
from tender_backend.services import delivery_package


def _constraint_item(**overrides):
    row = {
        "id": uuid4(),
        "requirement_id": uuid4(),
        "category": "format",
        "constraint_subtype": "signature_seal",
        "status": "accepted",
        "confirmation_level": "auto_accept",
        "title": "签章要求",
        "constraint_text": "投标文件须加盖单位公章并由法定代表人签字。",
        "source_file": "招标文件.pdf",
        "source_locator": "p10",
        "metadata_json": {},
    }
    row.update(overrides)
    return row


class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.result = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        self.conn.queries.append(query)
        if "FROM tender_constraint_set" in query:
            self.result = [self.conn.constraint_set] if self.conn.constraint_set else []
        elif "FROM tender_constraint_item" in query:
            self.result = self.conn.constraint_items
        elif "SELECT * FROM project WHERE id" in query:
            self.result = [self.conn.project]
        elif "FROM external_bid_attachment" in query and "COUNT" in query:
            self.result = [{"c": 1}]
        elif "FROM external_bid_attachment" in query:
            self.result = []
        elif "FROM project_requirement" in query:
            if self.conn.fail_on_raw_requirements:
                raise AssertionError("raw project_requirement should not be read when confirmed constraints exist")
            self.result = self.conn.raw_requirements
        else:
            self.result = []
        return self

    def fetchone(self):
        return self.result[0] if self.result else None

    def fetchall(self):
        return self.result


class _Conn:
    def __init__(self, *, confirmed: bool = True):
        self.project_id = uuid4()
        self.constraint_set = {
            "id": uuid4(),
            "project_id": self.project_id,
            "version": 1,
            "status": "confirmed",
            "metadata_json": {},
        } if confirmed else None
        self.constraint_items = [_constraint_item()]
        self.raw_requirements = []
        self.project = {
            "id": self.project_id,
            "submission_deadline": "2026-06-01",
            "bid_validity_period": 90,
            "selected_template_package_id": uuid4(),
            "submission_target": "local_zip",
            "platform_file_rules": {},
            "procurement_type": "single",
            "bid_bond_deadline": None,
        }
        self.fail_on_raw_requirements = confirmed
        self.queries = []

    def cursor(self, *args, **kwargs):
        return _Cursor(self)


def test_compliance_check_build_findings_prefers_confirmed_constraints():
    conn = _Conn(confirmed=True)

    findings = ComplianceCheckService()._build_findings(conn, project_id=conn.project_id)

    assert findings == []
    assert any("FROM tender_constraint_item" in query for query in conn.queries)


def test_submission_checklist_prefers_confirmed_constraints():
    conn = _Conn(confirmed=True)

    checklist = SubmissionChecklistService().build(conn, project_id=conn.project_id)

    assert checklist["signature_items"] == [
        {
            "requirement_id": str(conn.constraint_items[0]["id"]),
            "title": "签章要求",
            "confirmed": True,
        }
    ]
    assert any("FROM tender_constraint_item" in query for query in conn.queries)


def test_delivery_confirmation_and_traceability_prefer_confirmed_constraints():
    conn = _Conn(confirmed=True)

    confirmations = delivery_package._load_confirmation_records(conn, conn.project_id)
    traceability = delivery_package._load_traceability(conn, conn.project_id)

    assert confirmations[0]["id"] == conn.constraint_items[0]["id"]
    assert confirmations[0]["human_confirmed"] is True
    assert traceability[0]["constraint_subtype"] == "signature_seal"
