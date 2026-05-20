# Requirement–Evidence Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 `project_requirement` / `requirement_match` / `chapter_draft` / `compliance_check_*` 表与服务之上，建立"招标要求 → 证明材料 → 已生成段落"的闭环台账，并把"业绩/人员疑似编造"等编造类风险加入规则化合规检查。

**Architecture:**
- 五步增量改造，每步独立可上线、向下兼容、TDD 单元测试覆盖。
- 不引入新表，只给现有 `project_requirement` 增加首选字段（部分已在 `source_metadata` 里），给 `chapter_draft` 增加反查数组（参照已有 `referenced_chart_keys`），合规规则全部走 `ComplianceCheckService._build_findings` 同一通道。
- LLM 只负责抽取与生成；所有 gap 判定继续由规则跑。

**Tech Stack:** Python 3.12 / FastAPI / psycopg / Alembic / pytest（unit 用 `_Conn` / `_Cursor` 假对象，integration 用真实 Postgres）。

---

## 文件结构

新建：
- `backend/tender_backend/db/alembic/versions/0062_requirement_evidence_fields.py` — 给 `project_requirement` 增列：`is_scoring_point bool`、`evidence_required bool`、`evidence_type text`、`coverage_status text`
- `backend/tender_backend/db/alembic/versions/0063_chapter_draft_referenced_ids.py` — 给 `chapter_draft` 增列：`referenced_requirement_ids UUID[]`、`referenced_performance_ids UUID[]`、`referenced_personnel_ids UUID[]`
- `backend/tender_backend/services/requirement_coverage_aggregator.py` — 反向汇总服务（Task 5）
- `backend/tests/unit/test_compliance_evidence_rules.py`
- `backend/tests/unit/test_requirement_coverage_aggregator.py`

修改：
- `backend/tender_backend/services/compliance_check_service.py` — Task 1、Task 4 加规则
- `backend/tender_backend/services/tender_constraint_service.py:62-86` — Task 2 抽取阶段把 metadata 字段提升为列
- `backend/tender_backend/db/repositories/requirement_repo.py:13-220` — Task 2 字段允许更新
- `backend/tender_backend/services/technical_bid_writer.py:670-740` — Task 3 写入 referenced_*_ids
- `backend/tender_backend/services/bid_chapter_generation.py:380-500` — Task 3 写入 referenced_*_ids
- `backend/tender_backend/services/longform_quality.py:229-342` — Task 4 给 `build_coverage_report` 加新规则（scoring/编造）

---

## Task 1：用 `requirement_match.missing` 数据生成 `evidence_required_unmatched` finding

**目的：** 立刻把 `requirement_matching.py` 已经算出的 `missing` 行用起来。零 schema 改动，单文件改造，先把"白白浪费的数据"接进闸口。

**Files:**
- Modify: `backend/tender_backend/services/compliance_check_service.py:135-192`
- Create: `backend/tests/unit/test_compliance_evidence_rules.py`

- [ ] **Step 1：写失败测试 — evidence_required_unmatched finding 产生 P1**

```python
# backend/tests/unit/test_compliance_evidence_rules.py
from __future__ import annotations

from uuid import uuid4

from tender_backend.services.compliance_check_service import ComplianceCheckService


def test_evidence_required_unmatched_emits_p1_finding() -> None:
    service = ComplianceCheckService()
    requirement_id = uuid4()
    requirement_rows = [
        {
            "id": requirement_id,
            "category": "performance",
            "title": "类似工程业绩",
            "requirement_text": "投标人需提供类似工程业绩",
            "source_text": "",
            "human_confirmed": True,
            "is_veto": False,
            "is_hard_constraint": False,
        }
    ]
    match_rows = [
        {
            "requirement_id": requirement_id,
            "match_status": "missing",
            "missing_reason": "未找到可证明该业绩要求的企业业绩资料",
            "matched_source_type": "project_performance",
        }
    ]

    findings = service._evaluate_requirement_match_rules(
        requirement_rows=requirement_rows,
        match_rows=match_rows,
    )

    codes = [f["rule_code"] for f in findings]
    assert "evidence_required_unmatched" in codes
    finding = next(f for f in findings if f["rule_code"] == "evidence_required_unmatched")
    assert finding["severity"] == "P1"
    assert finding["requirement_id"] == requirement_id


def test_evidence_required_unmatched_skipped_when_match_satisfied() -> None:
    service = ComplianceCheckService()
    requirement_id = uuid4()
    findings = service._evaluate_requirement_match_rules(
        requirement_rows=[
            {
                "id": requirement_id,
                "category": "performance",
                "title": "业绩",
                "requirement_text": "",
                "source_text": "",
                "human_confirmed": True,
                "is_veto": False,
                "is_hard_constraint": False,
            }
        ],
        match_rows=[
            {
                "requirement_id": requirement_id,
                "match_status": "satisfied",
                "missing_reason": None,
                "matched_source_type": "project_performance",
            }
        ],
    )
    assert findings == []
```

- [ ] **Step 2：跑测试确认失败**

Run: `cd backend && pytest tests/unit/test_compliance_evidence_rules.py -v`
Expected: FAIL — `AttributeError: 'ComplianceCheckService' object has no attribute '_evaluate_requirement_match_rules'`

- [ ] **Step 3：在 `ComplianceCheckService` 里实现纯函数 `_evaluate_requirement_match_rules`**

在 `compliance_check_service.py` `_build_findings` 上方插入：

```python
    def _evaluate_requirement_match_rules(
        self,
        *,
        requirement_rows: list[dict[str, Any]],
        match_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not requirement_rows or not match_rows:
            return []
        requirement_by_id = {row["id"]: row for row in requirement_rows}
        findings: list[dict[str, Any]] = []
        for match in match_rows:
            if match.get("match_status") != "missing":
                continue
            requirement_id = match.get("requirement_id")
            requirement = requirement_by_id.get(requirement_id)
            if requirement is None:
                continue
            severity = "P0" if requirement.get("is_hard_constraint") or requirement.get("is_veto") else "P1"
            findings.append(
                {
                    "severity": severity,
                    "rule_code": "evidence_required_unmatched",
                    "title": f"未找到证明材料：{requirement.get('title')}",
                    "detail": match.get("missing_reason") or "",
                    "requirement_id": requirement_id,
                    "metadata_json": {
                        "matched_source_type": match.get("matched_source_type"),
                    },
                }
            )
        return findings
```

- [ ] **Step 4：跑测试确认通过**

Run: `cd backend && pytest tests/unit/test_compliance_evidence_rules.py -v`
Expected: PASS（2 个测试）

- [ ] **Step 5：在 `_build_findings` 内调用新规则**

修改 `compliance_check_service.py` `_build_findings`（约 192 行 `return findings` 之前）插入：

```python
        with conn.cursor(row_factory=dict_row) as cur:
            match_rows = cur.execute(
                """
                SELECT rm.requirement_id, rm.match_status, rm.missing_reason, rm.matched_source_type
                FROM requirement_match rm
                JOIN project_requirement pr ON pr.id = rm.requirement_id
                WHERE pr.project_id = %s
                """,
                (project_id,),
            ).fetchall()
        findings.extend(
            self._evaluate_requirement_match_rules(
                requirement_rows=[dict(r) for r in requirements],
                match_rows=[dict(r) for r in match_rows],
            )
        )
        return findings
```

- [ ] **Step 6：跑全量回归（含已有 compliance 集成测试）**

Run: `cd backend && pytest tests/unit/test_compliance_evidence_rules.py tests/unit/test_compliance_matrix.py tests/unit/test_export_gates.py -v`
Expected: PASS

- [ ] **Step 7：提交**

```bash
git add backend/tender_backend/services/compliance_check_service.py \
        backend/tests/unit/test_compliance_evidence_rules.py
git commit -m "feat(compliance): emit evidence_required_unmatched finding from requirement_match"
```

---

## Task 2：把 `project_requirement` 隐性字段提升为一等列

**目的：** 报告里 Ledger 真正缺的 `is_scoring_point / evidence_required / evidence_type / coverage_status`，其中 `evidence_need` 已存在于 `source_metadata`（见 `tender_constraint_service.py:80`），但散落在 jsonb 里规则引擎用不上。本任务把它们提升为列。

**Files:**
- Create: `backend/tender_backend/db/alembic/versions/0062_requirement_evidence_fields.py`
- Modify: `backend/tender_backend/db/repositories/requirement_repo.py:13-220`
- Modify: `backend/tender_backend/services/tender_constraint_service.py:62-86`
- Test: `backend/tests/unit/test_requirement_repo_evidence_fields.py`

- [ ] **Step 1：写 alembic migration**

```python
# backend/tender_backend/db/alembic/versions/0062_requirement_evidence_fields.py
"""promote requirement evidence fields to columns

Revision ID: 0062
Revises: 0061
Create Date: 2026-05-20
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0062"
down_revision: Union[str, None] = "0061"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_COLUMNS = (
    "is_scoring_point BOOLEAN NOT NULL DEFAULT false",
    "evidence_required BOOLEAN NOT NULL DEFAULT false",
    "evidence_type TEXT",
    "coverage_status TEXT NOT NULL DEFAULT 'pending'",
)

_COVERAGE_STATUS_VALUES = ("pending", "covered", "partially_covered", "needs_evidence", "not_applicable")


def upgrade() -> None:
    for column in _NEW_COLUMNS:
        op.execute(f"ALTER TABLE project_requirement ADD COLUMN IF NOT EXISTS {column};")
    op.execute(
        "ALTER TABLE project_requirement "
        "ADD CONSTRAINT project_requirement_coverage_status_chk "
        f"CHECK (coverage_status IN {_COVERAGE_STATUS_VALUES});"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_requirement_coverage "
        "ON project_requirement (project_id, coverage_status);"
    )
    # 回填：scoring_criteria 表里出现过的 requirement 推断为 scoring point
    op.execute(
        """
        UPDATE project_requirement
        SET is_scoring_point = true
        WHERE category = 'scoring'
        """
    )
    # 回填：从 source_metadata.evidence_need 提取布尔
    op.execute(
        """
        UPDATE project_requirement
        SET evidence_required = true
        WHERE (source_metadata ->> 'evidence_need') IS NOT NULL
          AND (source_metadata ->> 'evidence_need') NOT IN ('', 'false', 'no', '否', 'none')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_project_requirement_coverage;")
    op.execute("ALTER TABLE project_requirement DROP CONSTRAINT IF EXISTS project_requirement_coverage_status_chk;")
    for column in ("coverage_status", "evidence_type", "evidence_required", "is_scoring_point"):
        op.execute(f"ALTER TABLE project_requirement DROP COLUMN IF EXISTS {column};")
```

- [ ] **Step 2：跑 migration 验证 SQL 通过**

Run: `cd backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head`
Expected: 三步均无 error

- [ ] **Step 3：写失败测试 — RequirementRepository 接受新字段**

```python
# backend/tests/unit/test_requirement_repo_evidence_fields.py
from __future__ import annotations

from tender_backend.db.repositories.requirement_repo import RequirementRepository


def test_update_allows_evidence_fields() -> None:
    repo = RequirementRepository()
    allowed = repo._allowed_update_fields()  # to be added in Step 5
    for field in ("is_scoring_point", "evidence_required", "evidence_type", "coverage_status"):
        assert field in allowed
```

- [ ] **Step 4：跑测试确认失败**

Run: `cd backend && pytest tests/unit/test_requirement_repo_evidence_fields.py -v`
Expected: FAIL — `AttributeError: '_allowed_update_fields'`

- [ ] **Step 5：暴露 `_allowed_update_fields` 并加入新字段**

修改 `requirement_repo.py`，把 `update` 内的 `allowed = {...}` 字面集合抽成类方法：

```python
    @staticmethod
    def _allowed_update_fields() -> set[str]:
        return {
            "category",
            "title",
            "requirement_text",
            "source_text",
            "source_file",
            "source_locator",
            "confidence",
            "is_veto",
            "requires_human_confirm",
            "human_confirmed",
            "ignored_for_pricing",
            "applies_to_chapter",
            "review_status",
            "review_note",
            "source_metadata",
            "is_hard_constraint",
            "is_stale",
            "stale_reason",
            "stale_by_clarification_id",
            "superseded_by_requirement_id",
            "is_scoring_point",
            "evidence_required",
            "evidence_type",
            "coverage_status",
        }
```

并把 `update` 方法里的 `allowed = {...}` 替换为 `allowed = self._allowed_update_fields()`。

- [ ] **Step 6：跑测试确认通过**

Run: `cd backend && pytest tests/unit/test_requirement_repo_evidence_fields.py -v`
Expected: PASS

- [ ] **Step 7：在抽取阶段把 metadata 同步回填到列**

修改 `tender_constraint_service.py:62-86`，在 `for requirement in requirements:` 循环内、`row = cur.execute(...)` 之前插入：

```python
                # 把 metadata 里的隐性标记同步到 project_requirement 一等列，规则引擎才能用
                evidence_need = None
                if isinstance(requirement_metadata, dict):
                    evidence_need = requirement_metadata.get("evidence_need")
                evidence_required = bool(evidence_need) and str(evidence_need).strip().lower() not in {"false", "no", "否", "none", ""}
                is_scoring_point = requirement.get("category") == "scoring" or bool(
                    isinstance(requirement_metadata, dict) and requirement_metadata.get("is_scoring_point")
                )
                if evidence_required or is_scoring_point:
                    cur.execute(
                        """
                        UPDATE project_requirement
                        SET evidence_required = %s,
                            is_scoring_point = %s,
                            evidence_type = COALESCE(%s, evidence_type),
                            updated_at = now()
                        WHERE id = %s
                        """,
                        (
                            evidence_required,
                            is_scoring_point,
                            (requirement_metadata.get("evidence_type") if isinstance(requirement_metadata, dict) else None),
                            requirement["id"],
                        ),
                    )
```

- [ ] **Step 8：跑相关回归**

Run: `cd backend && pytest tests/unit/test_requirement_repo_evidence_fields.py tests/unit/test_requirement_matching.py tests/unit/test_requirement_grouping_service.py -v`
Expected: PASS

- [ ] **Step 9：提交**

```bash
git add backend/tender_backend/db/alembic/versions/0062_requirement_evidence_fields.py \
        backend/tender_backend/db/repositories/requirement_repo.py \
        backend/tender_backend/services/tender_constraint_service.py \
        backend/tests/unit/test_requirement_repo_evidence_fields.py
git commit -m "feat(requirement): promote evidence_required/is_scoring_point/coverage_status to columns"
```

---

## Task 3：`chapter_draft` 增加 `referenced_*_ids` 反查列并在生成时回填

**目的：** 报告里 Evidence Citation 的"段落级反查"短期内不做（成本太高），先做 chapter 级的多个引用数组，与已有 `referenced_chart_keys` 平行。这让 Task 4 的编造检测有数据可用。

**Files:**
- Create: `backend/tender_backend/db/alembic/versions/0063_chapter_draft_referenced_ids.py`
- Modify: `backend/tender_backend/services/technical_bid_writer.py:670-740`
- Modify: `backend/tender_backend/services/bid_chapter_generation.py:380-500`
- Test: `backend/tests/unit/test_chapter_draft_referenced_ids.py`

- [ ] **Step 1：写 alembic migration**

```python
# backend/tender_backend/db/alembic/versions/0063_chapter_draft_referenced_ids.py
"""add referenced_*_ids columns to chapter_draft

Revision ID: 0063
Revises: 0062
Create Date: 2026-05-20
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0063"
down_revision: Union[str, None] = "0062"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_COLUMNS = (
    "referenced_requirement_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[]",
    "referenced_performance_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[]",
    "referenced_personnel_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[]",
)


def upgrade() -> None:
    for column in _NEW_COLUMNS:
        op.execute(f"ALTER TABLE chapter_draft ADD COLUMN IF NOT EXISTS {column};")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chapter_draft_requirement_ids "
        "ON chapter_draft USING GIN (referenced_requirement_ids);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_chapter_draft_requirement_ids;")
    for column in ("referenced_personnel_ids", "referenced_performance_ids", "referenced_requirement_ids"):
        op.execute(f"ALTER TABLE chapter_draft DROP COLUMN IF EXISTS {column};")
```

- [ ] **Step 2：跑 migration**

Run: `cd backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head`
Expected: 无 error

- [ ] **Step 3：写失败测试 — 纯函数 `derive_referenced_ids_from_context` 从 context 提取引用 ID**

```python
# backend/tests/unit/test_chapter_draft_referenced_ids.py
from __future__ import annotations

from uuid import uuid4

from tender_backend.services.technical_chapter_context import derive_referenced_ids_from_context  # to be added


def test_derive_referenced_ids_collects_requirement_performance_personnel() -> None:
    req_id_1 = uuid4()
    req_id_2 = uuid4()
    perf_id = uuid4()
    person_id = uuid4()

    context = {
        "constraints": [
            {"requirement_id": req_id_1},
            {"requirement_id": req_id_2},
            {"requirement_id": None},
        ],
        "personnel_selections": [
            {"snapshot_json": {"person_id": str(person_id)}},
        ],
        "company_assets": {
            "performances": [{"id": perf_id, "project_name": "示例"}],
        },
    }

    derived = derive_referenced_ids_from_context(context)

    assert set(derived["referenced_requirement_ids"]) == {req_id_1, req_id_2}
    assert derived["referenced_performance_ids"] == [perf_id]
    assert derived["referenced_personnel_ids"] == [person_id]


def test_derive_referenced_ids_empty_when_context_missing_keys() -> None:
    assert derive_referenced_ids_from_context({}) == {
        "referenced_requirement_ids": [],
        "referenced_performance_ids": [],
        "referenced_personnel_ids": [],
    }
```

- [ ] **Step 4：跑测试确认失败**

Run: `cd backend && pytest tests/unit/test_chapter_draft_referenced_ids.py -v`
Expected: FAIL — `ImportError: cannot import name 'derive_referenced_ids_from_context'`

- [ ] **Step 5：在 `technical_chapter_context.py` 末尾实现纯函数**

在 `technical_chapter_context.py` `__all__` 之前插入：

```python
def derive_referenced_ids_from_context(context: dict[str, Any]) -> dict[str, list[Any]]:
    """从 chapter context pack 收集要回写到 chapter_draft 的引用 ID。

    生成阶段 context 已包含每章筛选过的 constraints / personnel_selections /
    performances；这里只是把它们 ID 化，不做任何 LLM 推断。
    """
    constraints = context.get("constraints") or []
    requirement_ids = []
    seen_requirement: set[Any] = set()
    for item in constraints:
        rid = item.get("requirement_id") if isinstance(item, dict) else None
        if rid and rid not in seen_requirement:
            seen_requirement.add(rid)
            requirement_ids.append(rid)

    performances = ((context.get("company_assets") or {}).get("performances") or [])
    performance_ids = [row["id"] for row in performances if isinstance(row, dict) and row.get("id")]

    personnel_ids: list[Any] = []
    for selection in context.get("personnel_selections") or []:
        if not isinstance(selection, dict):
            continue
        snapshot = selection.get("snapshot_json") or {}
        person_id = snapshot.get("person_id") if isinstance(snapshot, dict) else None
        if person_id:
            from uuid import UUID
            try:
                person_id = UUID(str(person_id))
            except (TypeError, ValueError):
                continue
            personnel_ids.append(person_id)

    return {
        "referenced_requirement_ids": requirement_ids,
        "referenced_performance_ids": performance_ids,
        "referenced_personnel_ids": personnel_ids,
    }
```

并把 `derive_referenced_ids_from_context` 加入 `__all__`。

- [ ] **Step 6：跑测试确认通过**

Run: `cd backend && pytest tests/unit/test_chapter_draft_referenced_ids.py -v`
Expected: PASS

- [ ] **Step 7：在 `technical_bid_writer.py` 写入草稿时回填引用列**

打开 `technical_bid_writer.py`，找到 `INSERT INTO chapter_draft (...) VALUES (...) ON CONFLICT ... DO UPDATE SET ... coverage_report_json = EXCLUDED.coverage_report_json` 那一段（约 700-740 行）。在 INSERT 的列清单和 VALUES 中分别追加三列：

```python
from tender_backend.services.technical_chapter_context import derive_referenced_ids_from_context

# ... 在 build_coverage_report 之后、INSERT 之前：
referenced_ids = derive_referenced_ids_from_context(chapter_context)

# 把 INSERT 的列加入：
#   ..., referenced_requirement_ids, referenced_performance_ids, referenced_personnel_ids
# 把 VALUES 加入：
#   ..., %s, %s, %s
# 把 ON CONFLICT DO UPDATE SET 加入：
#   referenced_requirement_ids = EXCLUDED.referenced_requirement_ids,
#   referenced_performance_ids = EXCLUDED.referenced_performance_ids,
#   referenced_personnel_ids = EXCLUDED.referenced_personnel_ids,
# 把参数加入：
#   referenced_ids["referenced_requirement_ids"],
#   referenced_ids["referenced_performance_ids"],
#   referenced_ids["referenced_personnel_ids"],
```

注意：因为 `technical_bid_writer.py:705` 的 INSERT 已有完整列清单，按行精确插入；不要简化已有 SQL。

- [ ] **Step 8：在 `bid_chapter_generation.py` 同样回填**

`bid_chapter_generation.py:380-500` 有两个 INSERT 路径（task card 路径和正常生成路径）。两个都加同样的三列。`bid_chapter_generation` 没直接构建 context dict，需要从 `requirements` / `personnel_data` / `performances` 局部变量手动组装一个 minimal context 后调 `derive_referenced_ids_from_context`，或直接内联同样的提取逻辑。建议显式调用：

```python
from tender_backend.services.technical_chapter_context import derive_referenced_ids_from_context

referenced_ids = derive_referenced_ids_from_context({
    "constraints": [{"requirement_id": r.get("id")} for r in requirements or []],
    "company_assets": {"performances": performances or []},
    "personnel_selections": [
        {"snapshot_json": {"person_id": p.get("person_id")}}
        for p in (personnel_data or [])
        if p.get("person_id")
    ],
})
```

随后在 INSERT 中加入三列、三个占位符、`ON CONFLICT DO UPDATE SET` 三个赋值、三个参数。

- [ ] **Step 9：跑回归**

Run: `cd backend && pytest tests/unit/test_chapter_draft_referenced_ids.py tests/integration/test_generate_section_flow.py -v`
Expected: PASS

- [ ] **Step 10：提交**

```bash
git add backend/tender_backend/db/alembic/versions/0063_chapter_draft_referenced_ids.py \
        backend/tender_backend/services/technical_chapter_context.py \
        backend/tender_backend/services/technical_bid_writer.py \
        backend/tender_backend/services/bid_chapter_generation.py \
        backend/tests/unit/test_chapter_draft_referenced_ids.py
git commit -m "feat(chapter_draft): persist referenced requirement/performance/personnel ids"
```

---

## Task 4：在 `compliance_check_service` 加 `fabricated_performance` / `fabricated_personnel` / `scoring_point_uncovered` 规则

**目的：** Task 2 + Task 3 的数据落地后，本任务把报告里强调的"编造检测 + 评分点覆盖"规则补上。仍是纯规则，无 LLM。

**Files:**
- Modify: `backend/tender_backend/services/compliance_check_service.py`
- Modify: `backend/tests/unit/test_compliance_evidence_rules.py`（同一文件追加用例）

- [ ] **Step 1：写失败测试 — 三条新规则**

在 `test_compliance_evidence_rules.py` 追加：

```python
def test_fabricated_performance_when_draft_references_unknown_performance() -> None:
    service = ComplianceCheckService()
    real_perf = uuid4()
    fabricated_perf = uuid4()
    findings = service._evaluate_fabrication_rules(
        chapter_draft_rows=[
            {
                "chapter_code": "5.1",
                "referenced_performance_ids": [real_perf, fabricated_perf],
                "referenced_personnel_ids": [],
            }
        ],
        allowed_performance_ids={real_perf},
        allowed_personnel_ids=set(),
    )
    codes = [f["rule_code"] for f in findings]
    assert codes == ["fabricated_performance_risk"]
    assert findings[0]["severity"] == "P0"
    assert findings[0]["metadata_json"]["performance_id"] == str(fabricated_perf)


def test_fabricated_personnel_when_draft_references_unknown_person() -> None:
    service = ComplianceCheckService()
    fabricated_person = uuid4()
    findings = service._evaluate_fabrication_rules(
        chapter_draft_rows=[
            {
                "chapter_code": "9",
                "referenced_performance_ids": [],
                "referenced_personnel_ids": [fabricated_person],
            }
        ],
        allowed_performance_ids=set(),
        allowed_personnel_ids=set(),
    )
    codes = [f["rule_code"] for f in findings]
    assert "fabricated_personnel_risk" in codes


def test_scoring_point_uncovered_when_requirement_has_no_chapter_draft_reference() -> None:
    service = ComplianceCheckService()
    scoring_req = uuid4()
    findings = service._evaluate_scoring_coverage_rules(
        requirement_rows=[
            {
                "id": scoring_req,
                "title": "技术方案完整性 10 分",
                "is_scoring_point": True,
            },
            {
                "id": uuid4(),
                "title": "普通要求",
                "is_scoring_point": False,
            },
        ],
        referenced_requirement_ids={uuid4()},  # 不含 scoring_req
    )
    codes = [f["rule_code"] for f in findings]
    assert "scoring_point_uncovered" in codes
    assert findings[0]["requirement_id"] == scoring_req
```

- [ ] **Step 2：跑测试确认失败**

Run: `cd backend && pytest tests/unit/test_compliance_evidence_rules.py -v`
Expected: 3 个新用例 FAIL

- [ ] **Step 3：实现两条纯函数规则**

在 `compliance_check_service.py` `_evaluate_requirement_match_rules` 下方插入：

```python
    def _evaluate_fabrication_rules(
        self,
        *,
        chapter_draft_rows: list[dict[str, Any]],
        allowed_performance_ids: set,
        allowed_personnel_ids: set,
    ) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        for draft in chapter_draft_rows:
            chapter_code = draft.get("chapter_code") or ""
            for perf_id in draft.get("referenced_performance_ids") or []:
                if perf_id not in allowed_performance_ids:
                    findings.append({
                        "severity": "P0",
                        "rule_code": "fabricated_performance_risk",
                        "title": f"第 {chapter_code} 章引用了未在企业资料库的业绩",
                        "detail": "正文引用的业绩 ID 不在已选业绩集合内，疑似 AI 编造。",
                        "metadata_json": {
                            "chapter_code": chapter_code,
                            "performance_id": str(perf_id),
                        },
                    })
            for person_id in draft.get("referenced_personnel_ids") or []:
                if person_id not in allowed_personnel_ids:
                    findings.append({
                        "severity": "P0",
                        "rule_code": "fabricated_personnel_risk",
                        "title": f"第 {chapter_code} 章引用了未在企业资料库的人员",
                        "detail": "正文引用的人员 ID 不在已选人员集合内，疑似 AI 编造。",
                        "metadata_json": {
                            "chapter_code": chapter_code,
                            "personnel_id": str(person_id),
                        },
                    })
        return findings

    def _evaluate_scoring_coverage_rules(
        self,
        *,
        requirement_rows: list[dict[str, Any]],
        referenced_requirement_ids: set,
    ) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        for row in requirement_rows:
            if not row.get("is_scoring_point"):
                continue
            if row["id"] in referenced_requirement_ids:
                continue
            findings.append({
                "severity": "P1",
                "rule_code": "scoring_point_uncovered",
                "title": f"评分点未在正文响应：{row.get('title')}",
                "requirement_id": row["id"],
            })
        return findings
```

- [ ] **Step 4：跑测试确认通过**

Run: `cd backend && pytest tests/unit/test_compliance_evidence_rules.py -v`
Expected: 5 个用例全部 PASS

- [ ] **Step 5：在 `_build_findings` 调用新规则**

在 `_build_findings` 末尾（`return findings` 之前）追加：

```python
        with conn.cursor(row_factory=dict_row) as cur:
            draft_rows = cur.execute(
                """
                SELECT chapter_code, referenced_performance_ids, referenced_personnel_ids,
                       referenced_requirement_ids
                FROM chapter_draft
                WHERE project_id = %s
                """,
                (project_id,),
            ).fetchall()
            allowed_perf = cur.execute(
                """
                SELECT pps.performance_id AS id
                FROM project_performance_selection pps
                WHERE pps.project_id = %s
                UNION
                SELECT p.id FROM project_performance p
                """,
                (project_id,),
            ).fetchall()
            allowed_personnel = cur.execute(
                """
                SELECT (snapshot_json ->> 'person_id')::uuid AS id
                FROM project_personnel_selection
                WHERE project_id = %s
                  AND snapshot_json ? 'person_id'
                """,
                (project_id,),
            ).fetchall()
        draft_dicts = [dict(r) for r in draft_rows]
        findings.extend(
            self._evaluate_fabrication_rules(
                chapter_draft_rows=draft_dicts,
                allowed_performance_ids={r["id"] for r in allowed_perf if r.get("id")},
                allowed_personnel_ids={r["id"] for r in allowed_personnel if r.get("id")},
            )
        )
        referenced_requirement_ids: set = set()
        for draft in draft_dicts:
            for rid in draft.get("referenced_requirement_ids") or []:
                referenced_requirement_ids.add(rid)
        findings.extend(
            self._evaluate_scoring_coverage_rules(
                requirement_rows=[dict(r) for r in requirements],
                referenced_requirement_ids=referenced_requirement_ids,
            )
        )
        return findings
```

**注意：** `project_performance_selection` 表是否存在需先确认；若不存在则只用 `project_performance.id` 全集（保守，不会假阳性）。把上方 `UNION SELECT p.id FROM project_performance p` 保留即可——空 selection 表时也能正常运行。

- [ ] **Step 6：跑全量回归**

Run: `cd backend && pytest tests/unit/test_compliance_evidence_rules.py tests/unit/test_compliance_matrix.py tests/unit/test_export_gates.py tests/integration/test_export_gate_and_render.py -v`
Expected: PASS

- [ ] **Step 7：提交**

```bash
git add backend/tender_backend/services/compliance_check_service.py \
        backend/tests/unit/test_compliance_evidence_rules.py
git commit -m "feat(compliance): add fabricated_performance/personnel and scoring_point_uncovered rules"
```

---

## Task 5：`requirement_coverage_aggregator` 反算 `coverage_status`

**目的：** Task 3 的 `referenced_requirement_ids` 落地后，把它反算成每条 requirement 的 `coverage_status`，让 Ledger 真正闭环。日后前端可以直接按 `coverage_status` 渲染状态徽章。

**Files:**
- Create: `backend/tender_backend/services/requirement_coverage_aggregator.py`
- Create: `backend/tests/unit/test_requirement_coverage_aggregator.py`
- Modify: `backend/tender_backend/services/technical_bid_writer.py` — 章节生成成功后调用 aggregator
- Modify: `backend/tender_backend/services/bid_chapter_generation.py` — 同上

- [ ] **Step 1：写失败测试 — 纯函数 `compute_coverage_status`**

```python
# backend/tests/unit/test_requirement_coverage_aggregator.py
from __future__ import annotations

from uuid import uuid4

from tender_backend.services.requirement_coverage_aggregator import (
    compute_coverage_status,
)


def test_pending_when_no_draft_reference_and_no_match() -> None:
    req_id = uuid4()
    status = compute_coverage_status(
        requirement={"id": req_id, "evidence_required": False},
        referenced_in_drafts=False,
        match_status=None,
    )
    assert status == "pending"


def test_needs_evidence_when_required_but_match_missing() -> None:
    req_id = uuid4()
    status = compute_coverage_status(
        requirement={"id": req_id, "evidence_required": True},
        referenced_in_drafts=True,
        match_status="missing",
    )
    assert status == "needs_evidence"


def test_covered_when_referenced_and_match_satisfied() -> None:
    req_id = uuid4()
    status = compute_coverage_status(
        requirement={"id": req_id, "evidence_required": True},
        referenced_in_drafts=True,
        match_status="satisfied",
    )
    assert status == "covered"


def test_partially_covered_when_referenced_but_match_needs_review() -> None:
    req_id = uuid4()
    status = compute_coverage_status(
        requirement={"id": req_id, "evidence_required": True},
        referenced_in_drafts=True,
        match_status="likely_satisfied",
    )
    assert status == "partially_covered"


def test_covered_when_no_evidence_required_and_referenced() -> None:
    req_id = uuid4()
    status = compute_coverage_status(
        requirement={"id": req_id, "evidence_required": False},
        referenced_in_drafts=True,
        match_status=None,
    )
    assert status == "covered"
```

- [ ] **Step 2：跑测试确认失败**

Run: `cd backend && pytest tests/unit/test_requirement_coverage_aggregator.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3：实现 aggregator**

```python
# backend/tender_backend/services/requirement_coverage_aggregator.py
"""Reverse-aggregate chapter_draft references into requirement coverage_status."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row


_VALID_STATUSES = {"pending", "covered", "partially_covered", "needs_evidence", "not_applicable"}


def compute_coverage_status(
    *,
    requirement: dict[str, Any],
    referenced_in_drafts: bool,
    match_status: str | None,
) -> str:
    """从草稿引用 + 资料匹配，推断 requirement 的 coverage_status。

    规则：
      - 草稿没引用、没匹配                                → pending
      - 需要证明材料、匹配缺失（无论是否引用）            → needs_evidence
      - 草稿已引用、匹配 satisfied 或无需证明              → covered
      - 草稿已引用、匹配 likely_satisfied/needs_review     → partially_covered
      - 草稿没引用、匹配 satisfied                         → pending（写没写还看不出）
    """
    evidence_required = bool(requirement.get("evidence_required"))

    if evidence_required and match_status == "missing":
        return "needs_evidence"

    if not referenced_in_drafts:
        return "pending"

    if match_status in {"satisfied", None} and (not evidence_required or match_status == "satisfied"):
        return "covered"

    if match_status in {"likely_satisfied", "needs_review"}:
        return "partially_covered"

    return "covered"


def recompute_for_project(conn: Connection, *, project_id: UUID) -> dict[str, int]:
    """读取 chapter_draft.referenced_requirement_ids + requirement_match，回写 coverage_status。"""
    with conn.cursor(row_factory=dict_row) as cur:
        requirements = cur.execute(
            """
            SELECT id, evidence_required
            FROM project_requirement
            WHERE project_id = %s
              AND COALESCE(is_stale, false) = false
            """,
            (project_id,),
        ).fetchall()
        draft_refs = cur.execute(
            """
            SELECT DISTINCT UNNEST(referenced_requirement_ids) AS requirement_id
            FROM chapter_draft
            WHERE project_id = %s
            """,
            (project_id,),
        ).fetchall()
        matches = cur.execute(
            """
            SELECT requirement_id, match_status
            FROM requirement_match
            WHERE requirement_id IN (
              SELECT id FROM project_requirement WHERE project_id = %s
            )
            """,
            (project_id,),
        ).fetchall()

    referenced = {row["requirement_id"] for row in draft_refs if row.get("requirement_id")}
    match_by_req = {row["requirement_id"]: row.get("match_status") for row in matches}

    counts = {status: 0 for status in _VALID_STATUSES}
    with conn.cursor() as cur:
        for req in requirements:
            status = compute_coverage_status(
                requirement=dict(req),
                referenced_in_drafts=req["id"] in referenced,
                match_status=match_by_req.get(req["id"]),
            )
            cur.execute(
                "UPDATE project_requirement SET coverage_status = %s, updated_at = now() WHERE id = %s",
                (status, req["id"]),
            )
            counts[status] += 1
    conn.commit()
    return counts


__all__ = ["compute_coverage_status", "recompute_for_project"]
```

- [ ] **Step 4：跑测试确认通过**

Run: `cd backend && pytest tests/unit/test_requirement_coverage_aggregator.py -v`
Expected: 5 个用例全部 PASS

- [ ] **Step 5：在章节生成成功后触发**

`technical_bid_writer.py` 在 INSERT chapter_draft 之后追加：

```python
from tender_backend.services.requirement_coverage_aggregator import recompute_for_project

# ... 在 INSERT/UPDATE chapter_draft 提交之后：
recompute_for_project(conn, project_id=project_id)
```

`bid_chapter_generation.py` 同样追加。
注意：`recompute_for_project` 内部已 `conn.commit()`；若调用点已经有自己的事务边界，确认不会触发嵌套提交问题（当前两文件的 INSERT 都是独立 commit，无冲突）。

- [ ] **Step 6：跑回归**

Run: `cd backend && pytest tests/unit/test_requirement_coverage_aggregator.py tests/integration/test_generate_section_flow.py -v`
Expected: PASS

- [ ] **Step 7：提交**

```bash
git add backend/tender_backend/services/requirement_coverage_aggregator.py \
        backend/tender_backend/services/technical_bid_writer.py \
        backend/tender_backend/services/bid_chapter_generation.py \
        backend/tests/unit/test_requirement_coverage_aggregator.py
git commit -m "feat(requirement): aggregate chapter_draft refs into coverage_status"
```

---

## Self-Review

**Spec coverage（对照盘点报告 5 个改造点）：**
1. ✅ Task 1 — evidence_required_unmatched 规则
2. ✅ Task 2 — is_scoring_point / evidence_required / evidence_type / coverage_status 字段
3. ✅ Task 3 — chapter_draft 反查列
4. ✅ Task 4 — fabricated_performance / fabricated_personnel / scoring_point_uncovered 规则
5. ✅ Task 5 — coverage_status 反算

**Placeholder 扫描：** 已避免"TBD / 适当处理 / 类似 Task N"等占位。Task 4 Step 5 标注了 `project_performance_selection` 表的存在性需在执行时确认（这是事实问题，不是占位）。

**Type consistency：**
- `derive_referenced_ids_from_context` 在 Task 3 定义、Task 3 Step 7/8 调用，签名一致。
- `_evaluate_requirement_match_rules` / `_evaluate_fabrication_rules` / `_evaluate_scoring_coverage_rules` 均为 `ComplianceCheckService` 方法，签名匹配测试。
- `compute_coverage_status` / `recompute_for_project` Task 5 内部一致。
- `coverage_status` 取值集合在 Task 2 migration 的 CHECK 约束、Task 5 `_VALID_STATUSES` 与函数返回中三者一致：`{pending, covered, partially_covered, needs_evidence, not_applicable}`。
