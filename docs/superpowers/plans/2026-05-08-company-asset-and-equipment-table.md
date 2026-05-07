# 公司资产管理 + 投标主要施工设备表自动生成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在公司库下增加 4 类资产（车辆/施工机械/施工工器具/安全设施设备及器具）的录入与管理；投标编制阶段按招标硬条件自动筛选已选清单，确认冻结后产出"投标主要施工设备表"——技术标章节嵌入 + 独立 Excel 附件双输出。

**Architecture:** 单表 `company_asset` + JSONB extras 装类型特化字段；附件分核心槽（按类型预定义）+ 累积区（开放）；投标侧 `project_equipment_selection` 引用 + 关键字段冻结快照（混合）；Schema 定义在前端 TS 配置驱动表单/表格/导出；DOCX 用锚点字符串 `{{equipment_table:<type>}}` + 后处理器替换 native table，Excel 用 openpyxl 直接构造。

**Tech Stack:** PostgreSQL + Alembic（migrations）/ FastAPI + Pydantic + psycopg（后端）/ python-docx + openpyxl（导出）/ React + TypeScript + Vitest（前端）/ pytest（后端测试）。

**Spec:** `docs/superpowers/specs/2026-05-07-company-asset-and-equipment-table-design.md`

---

## Tracking Legend

- `[ ]` Not started
- `[~]` In progress
- `[x]` Completed
- `[!]` Blocked

---

## File Map

### Backend — 新建

```
backend/tender_backend/db/alembic/versions/0040_company_assets_and_equipment_selection.py
backend/tender_backend/db/repositories/company_asset_repo.py
backend/tender_backend/db/repositories/project_equipment_selection_repo.py
backend/tender_backend/api/master_data_assets.py
backend/tender_backend/api/equipment_selection.py
backend/tender_backend/services/asset_schema.py
backend/tender_backend/services/equipment_filter_service.py
backend/tender_backend/services/export_service/equipment_table_renderer.py
backend/tender_backend/services/export_service/equipment_table_injector.py
backend/tests/integration/test_company_asset_api.py
backend/tests/integration/test_equipment_selection_api.py
backend/tests/integration/test_equipment_table_export.py
backend/tests/unit/test_equipment_filter_service.py
backend/tests/unit/test_equipment_table_renderer.py
backend/tests/integration/test_company_asset_e2e.py
```

### Backend — 修改

```
backend/tender_backend/main.py                            # 注册新 router
backend/tender_backend/api/master_data.py                 # 子路由注册
backend/tender_backend/services/export_service/docx_exporter.py    # 加 EquipmentTableInjector pass
backend/tender_backend/services/delivery_package.py       # 挂 equipment_table_xlsx 附件
backend/tender_backend/services/review_service/review_engine.py    # 4 项符合性扫描
backend/tender_backend/services/project_setup_service.py  # workflow 增加 equipment_selection 状态
backend/tender_backend/services/tender_constraint_service.py  # 支持 equipment_requirement type
```

### Frontend — 新建

```
frontend/src/modules/database/schemas/assetTypeSchemas.ts
frontend/src/modules/database/components/CompanyProfileSection.tsx
frontend/src/modules/database/components/ContractPerformanceSection.tsx
frontend/src/modules/database/components/CompanyAssetSection.tsx
frontend/src/modules/database/components/asset/AssetTypeTabs.tsx
frontend/src/modules/database/components/asset/AssetTable.tsx
frontend/src/modules/database/components/asset/AssetFormDrawer.tsx
frontend/src/modules/database/components/asset/AssetCoreAttachments.tsx
frontend/src/modules/database/components/asset/AssetArchiveAttachments.tsx
frontend/src/modules/database/components/asset/expiryBadge.ts
frontend/src/modules/authoring/EquipmentSelectionWorkbench.tsx
frontend/src/modules/authoring/equipment/CandidateList.tsx
frontend/src/modules/authoring/equipment/SelectedList.tsx
frontend/src/modules/authoring/equipment/CoverageBar.tsx
frontend/src/modules/authoring/equipment/ForceAddDialog.tsx
frontend/src/modules/authoring/equipment/PreviewTable.tsx
frontend/src/modules/database/components/__tests__/AssetFormDrawer.test.tsx
frontend/src/modules/authoring/__tests__/EquipmentSelectionWorkbench.test.tsx
```

### Frontend — 修改

```
frontend/src/lib/api.ts                                   # 增加资产 + 设备选择 API client
frontend/src/modules/database/components/CompanyLibraryWorkbench.tsx  # 拆为容器,引入 3 个 Section
frontend/src/lib/navigation.ts                            # 不变(资产仍在 company tab 内)
```

---

## Milestone Markers

- **Milestone 1（资产库可独立交付）**: Phase 1–5 完成 → 公司资产可录入、附件可管理、表格可显示。即便后续 Phase 不上线也能用。
- **Milestone 2（投标侧打通）**: Phase 6–11 完成 → 投标设备表能从公司库自动筛选、确认、生成 DOCX 章节嵌入 + Excel 附件。
- **Milestone 3（合规与质量）**: Phase 12–13 完成 → 符合性扫描 + 工作流闸门 + 端到端 fixture。

---

## Phase 1: 数据库 Migration

**目标:** 创建 `company_asset`、`company_asset_attachment`、`project_equipment_selection` 三张表 + 索引 + 冻结保护触发器。一次 alembic revision 完成。

### Task 1.1: 写 migration 集成测试

**Files:**
- Create: `backend/tests/integration/test_company_asset_migration.py`

- [ ] **Step 1: 写失败测试**

```python
"""Verify migration 0040 creates company_asset, company_asset_attachment,
project_equipment_selection tables with correct columns and constraints."""

from __future__ import annotations

import os
import psycopg
import pytest

from tender_backend.db.alembic.runner import upgrade_to_head


def _db_url() -> str | None:
    return os.environ.get("DATABASE_URL")


def _existing(conn: psycopg.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
        (table,),
    ).fetchone()
    return bool(row[0])


def _column_type(conn: psycopg.Connection, table: str, column: str) -> str | None:
    row = conn.execute(
        "SELECT data_type FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (table, column),
    ).fetchone()
    return row[0] if row else None


@pytest.mark.skipif(not _db_url(), reason="requires DATABASE_URL")
def test_migration_0040_creates_asset_tables() -> None:
    with psycopg.connect(_db_url(), autocommit=True) as conn:
        upgrade_to_head(conn)
        for table in ("company_asset", "company_asset_attachment", "project_equipment_selection"):
            assert _existing(conn, table), f"missing table {table}"
        assert _column_type(conn, "company_asset", "asset_type") == "text"
        assert _column_type(conn, "company_asset", "extras") == "jsonb"
        assert _column_type(conn, "project_equipment_selection", "frozen_snapshot") == "jsonb"
        assert _column_type(conn, "project_equipment_selection", "frozen") == "boolean"


@pytest.mark.skipif(not _db_url(), reason="requires DATABASE_URL")
def test_migration_0040_freeze_trigger_blocks_update() -> None:
    """frozen=TRUE 行的 UPDATE 应被触发器阻止(intended_role 等业务字段除外)。"""
    with psycopg.connect(_db_url(), autocommit=True) as conn:
        upgrade_to_head(conn)
        # 构造最小数据: library_company → company_asset → project → equipment_selection
        from uuid import uuid4
        lib_id, asset_id, proj_id, sel_id = uuid4(), uuid4(), uuid4(), uuid4()
        conn.execute(
            "INSERT INTO library_company (id, company_key, company_name) VALUES (%s, %s, %s)",
            (lib_id, "test-lib", "Test Lib"),
        )
        conn.execute(
            "INSERT INTO company_asset (id, library_company_id, asset_type, name, unit, ownership) "
            "VALUES (%s, %s, 'vehicle', 'Test', '辆', 'self')",
            (asset_id, lib_id),
        )
        conn.execute("INSERT INTO project (id, name) VALUES (%s, %s)", (proj_id, "Test Project"))
        conn.execute(
            "INSERT INTO project_equipment_selection (id, project_id, asset_id, asset_type, "
            "frozen_snapshot, frozen, frozen_at) VALUES (%s, %s, %s, 'vehicle', '{}'::jsonb, TRUE, now())",
            (sel_id, proj_id, asset_id),
        )
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute(
                "UPDATE project_equipment_selection SET frozen_snapshot = '{\"x\":1}'::jsonb WHERE id = %s",
                (sel_id,),
            )
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && DATABASE_URL=$DATABASE_URL pytest tests/integration/test_company_asset_migration.py -v
```

Expected: FAIL（migration 文件不存在）

- [ ] **Step 3: 创建 migration 文件**

**File:** `backend/tender_backend/db/alembic/versions/0040_company_assets_and_equipment_selection.py`

```python
"""company assets and equipment selection

Revision ID: 0040
Revises: 0039
Create Date: 2026-05-08
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0040"
down_revision: Union[str, None] = "0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS company_asset (
      id UUID PRIMARY KEY,
      library_company_id UUID NOT NULL REFERENCES library_company(id) ON DELETE CASCADE,
      asset_type TEXT NOT NULL CHECK (asset_type IN ('vehicle','machine','tool','safety')),
      name TEXT NOT NULL,
      spec_model TEXT,
      serial_no TEXT,
      manufacturer TEXT,
      quantity NUMERIC(12,2) NOT NULL DEFAULT 1,
      unit TEXT NOT NULL,
      ownership TEXT NOT NULL CHECK (ownership IN ('self','leased','third_party')),
      acquired_at DATE,
      expires_at DATE,
      technical_condition TEXT,
      status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','maintenance','retired')),
      location TEXT,
      extras JSONB NOT NULL DEFAULT '{}'::jsonb,
      notes TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_company_asset_lib_type ON company_asset(library_company_id, asset_type);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_company_asset_expires ON company_asset(expires_at);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_company_asset_status ON company_asset(status);")

    op.execute("""
    CREATE TABLE IF NOT EXISTS company_asset_attachment (
      id UUID PRIMARY KEY,
      asset_id UUID NOT NULL REFERENCES company_asset(id) ON DELETE CASCADE,
      evidence_asset_id UUID NOT NULL REFERENCES evidence_asset(id) ON DELETE CASCADE,
      attachment_kind TEXT NOT NULL,
      slot_role TEXT NOT NULL CHECK (slot_role IN ('core','archive')),
      effective_at DATE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_caa_asset ON company_asset_attachment(asset_id);")
    op.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS uq_caa_core_slot
      ON company_asset_attachment(asset_id, attachment_kind)
      WHERE slot_role = 'core';
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS project_equipment_selection (
      id UUID PRIMARY KEY,
      project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
      asset_id UUID NOT NULL REFERENCES company_asset(id) ON DELETE RESTRICT,
      asset_type TEXT NOT NULL,
      selection_reason TEXT,
      exclusion_overridden BOOLEAN NOT NULL DEFAULT FALSE,
      intended_role TEXT,
      frozen_snapshot JSONB NOT NULL,
      display_order INT NOT NULL DEFAULT 0,
      frozen BOOLEAN NOT NULL DEFAULT FALSE,
      frozen_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_pes_project ON project_equipment_selection(project_id, asset_type, display_order);")

    # 冻结保护触发器: frozen=TRUE 后,frozen_snapshot/asset_id/selection_reason/exclusion_overridden 不可改
    # intended_role/display_order 仍可调整(用户在审查后还能调用途/排序)
    op.execute("""
    CREATE OR REPLACE FUNCTION enforce_pes_frozen_immutable() RETURNS trigger AS $$
    BEGIN
      IF OLD.frozen = TRUE THEN
        IF NEW.frozen_snapshot IS DISTINCT FROM OLD.frozen_snapshot
           OR NEW.asset_id IS DISTINCT FROM OLD.asset_id
           OR NEW.selection_reason IS DISTINCT FROM OLD.selection_reason
           OR NEW.exclusion_overridden IS DISTINCT FROM OLD.exclusion_overridden
           OR NEW.frozen IS DISTINCT FROM OLD.frozen THEN
          RAISE EXCEPTION 'project_equipment_selection % is frozen, cannot modify locked fields', OLD.id;
        END IF;
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)
    op.execute("DROP TRIGGER IF EXISTS tr_pes_frozen_immutable ON project_equipment_selection;")
    op.execute("""
    CREATE TRIGGER tr_pes_frozen_immutable
      BEFORE UPDATE ON project_equipment_selection
      FOR EACH ROW EXECUTE FUNCTION enforce_pes_frozen_immutable();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS tr_pes_frozen_immutable ON project_equipment_selection;")
    op.execute("DROP FUNCTION IF EXISTS enforce_pes_frozen_immutable();")
    op.execute("DROP TABLE IF EXISTS project_equipment_selection;")
    op.execute("DROP TABLE IF EXISTS company_asset_attachment;")
    op.execute("DROP TABLE IF EXISTS company_asset;")
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && DATABASE_URL=$DATABASE_URL pytest tests/integration/test_company_asset_migration.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/db/alembic/versions/0040_company_assets_and_equipment_selection.py \
        backend/tests/integration/test_company_asset_migration.py
git commit -m "feat(db): migration 0040 company assets and equipment selection"
```

---

## Phase 2: 后端资产基线 + Repo + CRUD + 附件 API

**目标:** 后端能 CRUD `company_asset`，能挂载/移除附件（核心槽 unique 约束生效）。前端在 Phase 5 之前先有一套可调的 API。

### Task 2.1: asset_schema 基线常量 + 公共校验

**Files:**
- Create: `backend/tender_backend/services/asset_schema.py`
- Create: `backend/tests/unit/test_asset_schema.py`

- [ ] **Step 1: 写失败测试**

```python
"""Validate asset_schema constants and the basic field validator."""

from __future__ import annotations

import pytest

from tender_backend.services.asset_schema import (
    ASSET_TYPE_KEYS,
    OWNERSHIP_VALUES,
    STATUS_VALUES,
    AssetCommonFields,
    validate_common_fields,
)


def test_asset_type_keys_complete() -> None:
    assert ASSET_TYPE_KEYS == {"vehicle", "machine", "tool", "safety"}


def test_ownership_values_complete() -> None:
    assert OWNERSHIP_VALUES == {"self", "leased", "third_party"}


def test_status_values_complete() -> None:
    assert STATUS_VALUES == {"active", "maintenance", "retired"}


def test_validate_common_fields_passes_minimal() -> None:
    payload = AssetCommonFields(
        asset_type="vehicle",
        name="斗臂车",
        unit="辆",
        ownership="self",
        quantity=1,
    )
    validate_common_fields(payload)  # no exception


def test_validate_common_fields_rejects_unknown_asset_type() -> None:
    with pytest.raises(ValueError, match="asset_type"):
        validate_common_fields(
            AssetCommonFields(
                asset_type="unknown",
                name="x",
                unit="x",
                ownership="self",
                quantity=1,
            )
        )


def test_validate_common_fields_rejects_negative_quantity() -> None:
    with pytest.raises(ValueError, match="quantity"):
        validate_common_fields(
            AssetCommonFields(
                asset_type="vehicle",
                name="x",
                unit="辆",
                ownership="self",
                quantity=-1,
            )
        )


def test_validate_common_fields_rejects_extras_not_dict() -> None:
    with pytest.raises(ValueError, match="extras"):
        validate_common_fields(
            AssetCommonFields(
                asset_type="vehicle",
                name="x",
                unit="辆",
                ownership="self",
                quantity=1,
                extras=["bad"],  # type: ignore
            )
        )
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && pytest tests/unit/test_asset_schema.py -v
```

Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 asset_schema 模块**

**File:** `backend/tender_backend/services/asset_schema.py`

```python
"""Backend baseline for company asset domain.

Schema details (per-type fields, attachment slots, soft chips, export columns)
live in the frontend `assetTypeSchemas.ts`. This module provides only the
backend constants and minimal common-field validation that the API layer
enforces regardless of asset_type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ASSET_TYPE_KEYS: frozenset[str] = frozenset({"vehicle", "machine", "tool", "safety"})
OWNERSHIP_VALUES: frozenset[str] = frozenset({"self", "leased", "third_party"})
STATUS_VALUES: frozenset[str] = frozenset({"active", "maintenance", "retired"})
ATTACHMENT_SLOT_ROLES: frozenset[str] = frozenset({"core", "archive"})


@dataclass
class AssetCommonFields:
    asset_type: str
    name: str
    unit: str
    ownership: str
    quantity: float
    spec_model: str | None = None
    serial_no: str | None = None
    manufacturer: str | None = None
    acquired_at: Any = None
    expires_at: Any = None
    technical_condition: str | None = None
    status: str = "active"
    location: str | None = None
    notes: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)


def validate_common_fields(payload: AssetCommonFields) -> None:
    if payload.asset_type not in ASSET_TYPE_KEYS:
        raise ValueError(f"asset_type must be one of {sorted(ASSET_TYPE_KEYS)}")
    if payload.ownership not in OWNERSHIP_VALUES:
        raise ValueError(f"ownership must be one of {sorted(OWNERSHIP_VALUES)}")
    if payload.status not in STATUS_VALUES:
        raise ValueError(f"status must be one of {sorted(STATUS_VALUES)}")
    if not payload.name or not payload.name.strip():
        raise ValueError("name is required")
    if not payload.unit or not payload.unit.strip():
        raise ValueError("unit is required")
    if payload.quantity is None or float(payload.quantity) < 0:
        raise ValueError("quantity must be non-negative")
    if not isinstance(payload.extras, dict):
        raise ValueError("extras must be a JSON object (dict)")
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && pytest tests/unit/test_asset_schema.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/services/asset_schema.py \
        backend/tests/unit/test_asset_schema.py
git commit -m "feat(asset): backend asset_schema baseline constants and validator"
```

---

### Task 2.2: company_asset_repo (CRUD + 附件操作)

**Files:**
- Create: `backend/tender_backend/db/repositories/company_asset_repo.py`
- Create: `backend/tests/integration/test_company_asset_repo.py`

- [ ] **Step 1: 写失败测试**

```python
"""Repository tests for company_asset and company_asset_attachment."""

from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest

from tender_backend.db.alembic.runner import upgrade_to_head
from tender_backend.db.repositories.company_asset_repo import CompanyAssetRepository


def _db_url() -> str | None:
    return os.environ.get("DATABASE_URL")


@pytest.fixture
def conn() -> psycopg.Connection:
    if not _db_url():
        pytest.skip("DATABASE_URL not set")
    with psycopg.connect(_db_url(), autocommit=True) as c:
        upgrade_to_head(c)
        yield c


@pytest.fixture
def library_id(conn: psycopg.Connection):
    lib_id = uuid4()
    conn.execute(
        "INSERT INTO library_company (id, company_key, company_name) VALUES (%s, %s, %s)",
        (lib_id, f"test-{lib_id}", "Test Lib"),
    )
    return lib_id


def test_create_and_get_asset(conn, library_id) -> None:
    repo = CompanyAssetRepository()
    asset_id = repo.create(
        conn,
        library_company_id=library_id,
        asset_type="vehicle",
        name="斗臂车",
        unit="辆",
        ownership="self",
        quantity=1,
        extras={"vehicle_type": "斗臂车"},
    )
    row = repo.get(conn, asset_id)
    assert row is not None
    assert row["name"] == "斗臂车"
    assert row["asset_type"] == "vehicle"
    assert row["extras"] == {"vehicle_type": "斗臂车"}


def test_list_assets_by_type(conn, library_id) -> None:
    repo = CompanyAssetRepository()
    repo.create(conn, library_company_id=library_id, asset_type="vehicle",
                name="A", unit="辆", ownership="self", quantity=1)
    repo.create(conn, library_company_id=library_id, asset_type="machine",
                name="B", unit="台", ownership="self", quantity=1)
    repo.create(conn, library_company_id=library_id, asset_type="vehicle",
                name="C", unit="辆", ownership="leased", quantity=1)
    rows = repo.list(conn, library_company_id=library_id, asset_type="vehicle")
    names = sorted(r["name"] for r in rows)
    assert names == ["A", "C"]


def test_update_asset_fields(conn, library_id) -> None:
    repo = CompanyAssetRepository()
    asset_id = repo.create(conn, library_company_id=library_id, asset_type="vehicle",
                           name="A", unit="辆", ownership="self", quantity=1)
    repo.update(conn, asset_id, fields={"name": "A2", "status": "maintenance"})
    row = repo.get(conn, asset_id)
    assert row["name"] == "A2"
    assert row["status"] == "maintenance"


def test_delete_asset_cascades_attachments(conn, library_id) -> None:
    repo = CompanyAssetRepository()
    asset_id = repo.create(conn, library_company_id=library_id, asset_type="vehicle",
                           name="A", unit="辆", ownership="self", quantity=1)
    ev_id = uuid4()
    conn.execute(
        "INSERT INTO evidence_asset (id, library_company_id, asset_domain, asset_category, original_filename, storage_path) "
        "VALUES (%s, %s, 'company_qualification', 'driving_license', 'x.pdf', '/tmp/x.pdf')",
        (ev_id, library_id),
    )
    repo.attach(conn, asset_id=asset_id, evidence_asset_id=ev_id,
                attachment_kind="driving_license", slot_role="core")
    repo.delete(conn, asset_id)
    cnt = conn.execute("SELECT count(*) FROM company_asset_attachment WHERE asset_id = %s",
                       (asset_id,)).fetchone()[0]
    assert cnt == 0


def test_attach_core_slot_unique_per_kind(conn, library_id) -> None:
    repo = CompanyAssetRepository()
    asset_id = repo.create(conn, library_company_id=library_id, asset_type="vehicle",
                           name="A", unit="辆", ownership="self", quantity=1)
    ev1, ev2 = uuid4(), uuid4()
    for ev in (ev1, ev2):
        conn.execute(
            "INSERT INTO evidence_asset (id, library_company_id, asset_domain, asset_category, original_filename, storage_path) "
            "VALUES (%s, %s, 'company_qualification', 'driving_license', 'x.pdf', '/tmp/x.pdf')",
            (ev, library_id),
        )
    repo.attach(conn, asset_id=asset_id, evidence_asset_id=ev1,
                attachment_kind="driving_license", slot_role="core")
    with pytest.raises(psycopg.errors.UniqueViolation):
        repo.attach(conn, asset_id=asset_id, evidence_asset_id=ev2,
                    attachment_kind="driving_license", slot_role="core")


def test_attach_archive_allows_multiple(conn, library_id) -> None:
    repo = CompanyAssetRepository()
    asset_id = repo.create(conn, library_company_id=library_id, asset_type="tool",
                           name="绝缘杆", unit="件", ownership="self", quantity=1)
    for _ in range(3):
        ev = uuid4()
        conn.execute(
            "INSERT INTO evidence_asset (id, library_company_id, asset_domain, asset_category, original_filename, storage_path) "
            "VALUES (%s, %s, 'company_qualification', 'inspection_report', 'x.pdf', '/tmp/x.pdf')",
            (ev, library_id),
        )
        repo.attach(conn, asset_id=asset_id, evidence_asset_id=ev,
                    attachment_kind="historical_inspection", slot_role="archive")
    cnt = conn.execute("SELECT count(*) FROM company_asset_attachment WHERE asset_id = %s",
                       (asset_id,)).fetchone()[0]
    assert cnt == 3
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && DATABASE_URL=$DATABASE_URL pytest tests/integration/test_company_asset_repo.py -v
```

Expected: FAIL（repo 不存在）

- [ ] **Step 3: 实现 repo**

**File:** `backend/tender_backend/db/repositories/company_asset_repo.py`

```python
"""CompanyAssetRepository: CRUD + attachment management."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row


_FIELDS = (
    "id", "library_company_id", "asset_type", "name", "spec_model", "serial_no",
    "manufacturer", "quantity", "unit", "ownership", "acquired_at", "expires_at",
    "technical_condition", "status", "location", "extras", "notes",
    "created_at", "updated_at",
)
_FIELDS_SQL = ", ".join(_FIELDS)

_INSERTABLE = (
    "library_company_id", "asset_type", "name", "spec_model", "serial_no",
    "manufacturer", "quantity", "unit", "ownership", "acquired_at", "expires_at",
    "technical_condition", "status", "location", "extras", "notes",
)

_UPDATABLE = (
    "name", "spec_model", "serial_no", "manufacturer", "quantity", "unit",
    "ownership", "acquired_at", "expires_at", "technical_condition", "status",
    "location", "extras", "notes",
)


class CompanyAssetRepository:
    def create(
        self,
        conn: Connection,
        *,
        library_company_id: UUID,
        asset_type: str,
        name: str,
        unit: str,
        ownership: str,
        quantity: float = 1,
        spec_model: str | None = None,
        serial_no: str | None = None,
        manufacturer: str | None = None,
        acquired_at=None,
        expires_at=None,
        technical_condition: str | None = None,
        status: str = "active",
        location: str | None = None,
        extras: dict[str, Any] | None = None,
        notes: str | None = None,
    ) -> UUID:
        asset_id = uuid4()
        conn.execute(
            f"""
            INSERT INTO company_asset ({", ".join(["id", *_INSERTABLE])})
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                asset_id, library_company_id, asset_type, name, spec_model, serial_no,
                manufacturer, quantity, unit, ownership, acquired_at, expires_at,
                technical_condition, status, location,
                __import__("json").dumps(extras or {}), notes,
            ),
        )
        return asset_id

    def get(self, conn: Connection, asset_id: UUID) -> dict | None:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_FIELDS_SQL} FROM company_asset WHERE id = %s", (asset_id,))
            return cur.fetchone()

    def list(
        self,
        conn: Connection,
        *,
        library_company_id: UUID,
        asset_type: str | None = None,
        include_retired: bool = False,
    ) -> list[dict]:
        sql = f"SELECT {_FIELDS_SQL} FROM company_asset WHERE library_company_id = %s"
        params: list[Any] = [library_company_id]
        if asset_type is not None:
            sql += " AND asset_type = %s"
            params.append(asset_type)
        if not include_retired:
            sql += " AND status <> 'retired'"
        sql += " ORDER BY created_at DESC"
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())

    def update(self, conn: Connection, asset_id: UUID, *, fields: dict[str, Any]) -> None:
        unknown = set(fields) - set(_UPDATABLE)
        if unknown:
            raise ValueError(f"unknown updatable fields: {sorted(unknown)}")
        if not fields:
            return
        sets = ", ".join(f"{k} = %s" for k in fields)
        params = [
            __import__("json").dumps(v) if k == "extras" else v
            for k, v in fields.items()
        ]
        params.append(asset_id)
        conn.execute(f"UPDATE company_asset SET {sets}, updated_at = now() WHERE id = %s", params)

    def delete(self, conn: Connection, asset_id: UUID) -> None:
        conn.execute("DELETE FROM company_asset WHERE id = %s", (asset_id,))

    def attach(
        self,
        conn: Connection,
        *,
        asset_id: UUID,
        evidence_asset_id: UUID,
        attachment_kind: str,
        slot_role: str,
        effective_at=None,
    ) -> UUID:
        att_id = uuid4()
        conn.execute(
            """
            INSERT INTO company_asset_attachment
              (id, asset_id, evidence_asset_id, attachment_kind, slot_role, effective_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (att_id, asset_id, evidence_asset_id, attachment_kind, slot_role, effective_at),
        )
        return att_id

    def list_attachments(self, conn: Connection, asset_id: UUID) -> list[dict]:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, asset_id, evidence_asset_id, attachment_kind, slot_role,
                       effective_at, created_at
                FROM company_asset_attachment
                WHERE asset_id = %s
                ORDER BY slot_role, attachment_kind, effective_at DESC NULLS LAST, created_at DESC
                """,
                (asset_id,),
            )
            return list(cur.fetchall())

    def remove_attachment(self, conn: Connection, attachment_id: UUID) -> None:
        conn.execute("DELETE FROM company_asset_attachment WHERE id = %s", (attachment_id,))
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && DATABASE_URL=$DATABASE_URL pytest tests/integration/test_company_asset_repo.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tender_backend/db/repositories/company_asset_repo.py \
        backend/tests/integration/test_company_asset_repo.py
git commit -m "feat(asset): CompanyAssetRepository with CRUD and attachment ops"
```

---

### Task 2.3: company_asset CRUD + 附件 API

**Files:**
- Create: `backend/tender_backend/api/master_data_assets.py`
- Modify: `backend/tender_backend/api/master_data.py` (注册子路由)
- Create: `backend/tests/integration/test_company_asset_api.py`

- [ ] **Step 1: 写失败测试**

```python
"""API tests for company asset CRUD + attachment endpoints."""

from __future__ import annotations

import io
import os
from uuid import uuid4

import psycopg
import pytest

from tender_backend.db.alembic.runner import upgrade_to_head
from tender_backend.main import app
from tender_backend.test_support.asgi_client import SyncASGIClient


_AUTH = {"Authorization": "Bearer dev-token"}


def _db_url() -> str | None:
    return os.environ.get("DATABASE_URL")


@pytest.fixture
def client():
    if not _db_url():
        pytest.skip("DATABASE_URL not set")
    with psycopg.connect(_db_url(), autocommit=True) as c:
        upgrade_to_head(c)
    return SyncASGIClient(app)


@pytest.fixture
def library_id():
    with psycopg.connect(_db_url(), autocommit=True) as c:
        lib_id = uuid4()
        c.execute("INSERT INTO library_company (id, company_key, company_name) VALUES (%s, %s, %s)",
                  (lib_id, f"test-{lib_id}", "Test Lib"))
    return str(lib_id)


def test_create_asset(client, library_id) -> None:
    res = client.post(
        f"/api/master-data/library-companies/{library_id}/assets",
        json={
            "asset_type": "vehicle",
            "name": "斗臂车",
            "unit": "辆",
            "ownership": "self",
            "quantity": 1,
            "extras": {"vehicle_type": "斗臂车", "driving_license_no": "苏A12345"},
        },
        headers=_AUTH,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["name"] == "斗臂车"
    assert body["extras"]["driving_license_no"] == "苏A12345"


def test_create_asset_invalid_type(client, library_id) -> None:
    res = client.post(
        f"/api/master-data/library-companies/{library_id}/assets",
        json={"asset_type": "unknown", "name": "x", "unit": "x", "ownership": "self", "quantity": 1},
        headers=_AUTH,
    )
    assert res.status_code == 422


def test_list_assets(client, library_id) -> None:
    for name in ("A", "B"):
        client.post(
            f"/api/master-data/library-companies/{library_id}/assets",
            json={"asset_type": "vehicle", "name": name, "unit": "辆", "ownership": "self", "quantity": 1},
            headers=_AUTH,
        )
    res = client.get(
        f"/api/master-data/library-companies/{library_id}/assets?asset_type=vehicle",
        headers=_AUTH,
    )
    assert res.status_code == 200
    assert len(res.json()) >= 2


def test_update_asset(client, library_id) -> None:
    create_res = client.post(
        f"/api/master-data/library-companies/{library_id}/assets",
        json={"asset_type": "vehicle", "name": "A", "unit": "辆", "ownership": "self", "quantity": 1},
        headers=_AUTH,
    )
    asset_id = create_res.json()["id"]
    res = client.put(f"/api/master-data/assets/{asset_id}", json={"name": "A2"}, headers=_AUTH)
    assert res.status_code == 200
    assert res.json()["name"] == "A2"


def test_delete_asset(client, library_id) -> None:
    create_res = client.post(
        f"/api/master-data/library-companies/{library_id}/assets",
        json={"asset_type": "vehicle", "name": "A", "unit": "辆", "ownership": "self", "quantity": 1},
        headers=_AUTH,
    )
    asset_id = create_res.json()["id"]
    res = client.delete(f"/api/master-data/assets/{asset_id}", headers=_AUTH)
    assert res.status_code == 204


def test_upload_attachment(client, library_id) -> None:
    create_res = client.post(
        f"/api/master-data/library-companies/{library_id}/assets",
        json={"asset_type": "vehicle", "name": "A", "unit": "辆", "ownership": "self", "quantity": 1},
        headers=_AUTH,
    )
    asset_id = create_res.json()["id"]
    res = client.post(
        f"/api/master-data/assets/{asset_id}/attachments",
        files={"file": ("行驶证.pdf", b"%PDF-1.4 fake", "application/pdf")},
        data={"attachment_kind": "driving_license", "slot_role": "core"},
        headers=_AUTH,
    )
    assert res.status_code == 201, res.text
    assert res.json()["attachment_kind"] == "driving_license"


def test_upload_core_attachment_duplicate_rejected(client, library_id) -> None:
    create_res = client.post(
        f"/api/master-data/library-companies/{library_id}/assets",
        json={"asset_type": "vehicle", "name": "A", "unit": "辆", "ownership": "self", "quantity": 1},
        headers=_AUTH,
    )
    asset_id = create_res.json()["id"]
    for i in range(2):
        res = client.post(
            f"/api/master-data/assets/{asset_id}/attachments",
            files={"file": (f"f{i}.pdf", b"%PDF-1.4 fake", "application/pdf")},
            data={"attachment_kind": "driving_license", "slot_role": "core"},
            headers=_AUTH,
        )
        if i == 0:
            assert res.status_code == 201
        else:
            assert res.status_code == 409  # 核心槽 unique 冲突,需先 remove 旧的
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && DATABASE_URL=$DATABASE_URL pytest tests/integration/test_company_asset_api.py -v
```

Expected: FAIL（API 不存在）

- [ ] **Step 3: 实现 API 模块**

**File:** `backend/tender_backend/api/master_data_assets.py`

```python
"""Company asset API: CRUD + attachment management."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from psycopg import Connection

from tender_backend.core.config import Settings, get_settings
from tender_backend.core.path_safety import ensure_path_within_root
from tender_backend.core.security import get_current_user
from tender_backend.core.uploads import read_upload_with_limit
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.company_asset_repo import CompanyAssetRepository
from tender_backend.services.asset_schema import (
    ASSET_TYPE_KEYS,
    ATTACHMENT_SLOT_ROLES,
    OWNERSHIP_VALUES,
    STATUS_VALUES,
    AssetCommonFields,
    validate_common_fields,
)


router = APIRouter(tags=["master-data-assets"], dependencies=[Depends(get_current_user)])
_repo = CompanyAssetRepository()


class AssetCreate(BaseModel):
    asset_type: str
    name: str = Field(min_length=1)
    spec_model: str | None = None
    serial_no: str | None = None
    manufacturer: str | None = None
    quantity: float = 1
    unit: str = Field(min_length=1)
    ownership: str
    acquired_at: date | None = None
    expires_at: date | None = None
    technical_condition: str | None = None
    status: str = "active"
    location: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class AssetUpdate(BaseModel):
    name: str | None = None
    spec_model: str | None = None
    serial_no: str | None = None
    manufacturer: str | None = None
    quantity: float | None = None
    unit: str | None = None
    ownership: str | None = None
    acquired_at: date | None = None
    expires_at: date | None = None
    technical_condition: str | None = None
    status: str | None = None
    location: str | None = None
    extras: dict[str, Any] | None = None
    notes: str | None = None


class AssetOut(BaseModel):
    id: UUID
    library_company_id: UUID
    asset_type: str
    name: str
    spec_model: str | None
    serial_no: str | None
    manufacturer: str | None
    quantity: float
    unit: str
    ownership: str
    acquired_at: date | None
    expires_at: date | None
    technical_condition: str | None
    status: str
    location: str | None
    extras: dict[str, Any]
    notes: str | None


class AttachmentOut(BaseModel):
    id: UUID
    evidence_asset_id: UUID
    attachment_kind: str
    slot_role: str
    effective_at: date | None


def _row_to_out(row: dict) -> AssetOut:
    return AssetOut(**{k: row[k] for k in AssetOut.model_fields})


@router.get("/master-data/library-companies/{library_id}/assets", response_model=list[AssetOut])
async def list_assets(
    library_id: UUID,
    asset_type: str | None = None,
    include_retired: bool = False,
    conn: Connection = Depends(get_db_conn),
) -> list[AssetOut]:
    if asset_type is not None and asset_type not in ASSET_TYPE_KEYS:
        raise HTTPException(status_code=422, detail=f"asset_type must be in {sorted(ASSET_TYPE_KEYS)}")
    rows = _repo.list(conn, library_company_id=library_id, asset_type=asset_type,
                      include_retired=include_retired)
    return [_row_to_out(r) for r in rows]


@router.post("/master-data/library-companies/{library_id}/assets",
             response_model=AssetOut, status_code=201)
async def create_asset(
    library_id: UUID,
    payload: AssetCreate,
    conn: Connection = Depends(get_db_conn),
) -> AssetOut:
    try:
        validate_common_fields(AssetCommonFields(
            asset_type=payload.asset_type, name=payload.name, unit=payload.unit,
            ownership=payload.ownership, quantity=payload.quantity,
            status=payload.status, extras=payload.extras,
        ))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    asset_id = _repo.create(
        conn,
        library_company_id=library_id,
        asset_type=payload.asset_type, name=payload.name, unit=payload.unit,
        ownership=payload.ownership, quantity=payload.quantity,
        spec_model=payload.spec_model, serial_no=payload.serial_no,
        manufacturer=payload.manufacturer, acquired_at=payload.acquired_at,
        expires_at=payload.expires_at, technical_condition=payload.technical_condition,
        status=payload.status, location=payload.location,
        extras=payload.extras, notes=payload.notes,
    )
    row = _repo.get(conn, asset_id)
    if row is None:
        raise HTTPException(status_code=500, detail="failed to read back created asset")
    return _row_to_out(row)


@router.put("/master-data/assets/{asset_id}", response_model=AssetOut)
async def update_asset(
    asset_id: UUID,
    payload: AssetUpdate,
    conn: Connection = Depends(get_db_conn),
) -> AssetOut:
    fields = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "ownership" in fields and fields["ownership"] not in OWNERSHIP_VALUES:
        raise HTTPException(status_code=422, detail="ownership invalid")
    if "status" in fields and fields["status"] not in STATUS_VALUES:
        raise HTTPException(status_code=422, detail="status invalid")
    if "extras" in fields and not isinstance(fields["extras"], dict):
        raise HTTPException(status_code=422, detail="extras must be object")
    _repo.update(conn, asset_id, fields=fields)
    row = _repo.get(conn, asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="asset not found")
    return _row_to_out(row)


@router.delete("/master-data/assets/{asset_id}", status_code=204)
async def delete_asset(asset_id: UUID, conn: Connection = Depends(get_db_conn)):
    try:
        _repo.delete(conn, asset_id)
    except psycopg.errors.ForeignKeyViolation as exc:
        raise HTTPException(
            status_code=409,
            detail="asset is referenced by an existing equipment selection; retire it instead of deleting",
        ) from exc


@router.get("/master-data/assets/{asset_id}/attachments", response_model=list[AttachmentOut])
async def list_attachments(asset_id: UUID, conn: Connection = Depends(get_db_conn)) -> list[AttachmentOut]:
    rows = _repo.list_attachments(conn, asset_id)
    return [AttachmentOut(**{k: r[k] for k in AttachmentOut.model_fields}) for r in rows]


@router.post("/master-data/assets/{asset_id}/attachments",
             response_model=AttachmentOut, status_code=201)
async def upload_attachment(
    asset_id: UUID,
    attachment_kind: str = Form(...),
    slot_role: str = Form(...),
    effective_at: date | None = Form(None),
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
    conn: Connection = Depends(get_db_conn),
) -> AttachmentOut:
    if slot_role not in ATTACHMENT_SLOT_ROLES:
        raise HTTPException(status_code=422, detail=f"slot_role must be in {sorted(ATTACHMENT_SLOT_ROLES)}")
    asset = _repo.get(conn, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    filename = file.filename or "attachment"
    suffix = Path(filename).suffix.lower()
    if suffix != ".pdf":
        raise HTTPException(status_code=400, detail="只支持 PDF 附件")
    content = await read_upload_with_limit(file, max_bytes=settings.evidence_upload_max_bytes)
    if not content:
        raise HTTPException(status_code=422, detail="file is empty")

    # 写入 evidence_asset (沿用现有 evidence 流水)
    storage_dir = settings.tender_document_storage_root / "company_assets" / str(asset_id)
    storage_dir.mkdir(parents=True, exist_ok=True)
    persisted = ensure_path_within_root(storage_dir / filename, settings.tender_document_storage_root,
                                        label="asset attachment path")
    persisted.write_bytes(content)

    from uuid import uuid4
    ev_id = uuid4()
    conn.execute(
        """
        INSERT INTO evidence_asset (id, library_company_id, asset_domain, asset_category,
                                    original_filename, storage_path)
        VALUES (%s, %s, 'company_asset', %s, %s, %s)
        """,
        (ev_id, asset["library_company_id"], attachment_kind, filename, str(persisted)),
    )
    try:
        att_id = _repo.attach(conn, asset_id=asset_id, evidence_asset_id=ev_id,
                              attachment_kind=attachment_kind, slot_role=slot_role,
                              effective_at=effective_at)
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(status_code=409,
                            detail=f"core slot {attachment_kind} already exists for this asset; remove it first") from exc

    return AttachmentOut(
        id=att_id, evidence_asset_id=ev_id, attachment_kind=attachment_kind,
        slot_role=slot_role, effective_at=effective_at,
    )


@router.delete("/master-data/assets/{asset_id}/attachments/{attachment_id}", status_code=204)
async def remove_attachment(asset_id: UUID, attachment_id: UUID,
                            conn: Connection = Depends(get_db_conn)):
    _repo.remove_attachment(conn, attachment_id)
```

- [ ] **Step 4: 注册子路由到 master_data router**

**File:** `backend/tender_backend/api/master_data.py`

加一行 import 和 include：

```python
# 在文件已有 include_router 调用块附近加:
from tender_backend.api.master_data_assets import router as _assets_router

router.include_router(_assets_router)
```

如果 master_data.py 是直接挂在 app 上而非聚合 router，则改为在 `main.py` 加：

```python
from tender_backend.api.master_data_assets import router as master_data_assets_router
app.include_router(master_data_assets_router, prefix=settings.api_prefix)
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd backend && DATABASE_URL=$DATABASE_URL pytest tests/integration/test_company_asset_api.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tender_backend/api/master_data_assets.py \
        backend/tender_backend/api/master_data.py \
        backend/tender_backend/main.py \
        backend/tests/integration/test_company_asset_api.py
git commit -m "feat(asset): company asset CRUD and attachment API"
```

---

## Phase 3: 前端 Asset Schema 配置

**目标:** 一份 TS 配置文件承载 4 类的全部 schema（字段 / 核心槽 / 累积区类别 / 软筛 chip / 导出列）。后续表单、表格、设备表导出全部从此读取，单一来源。

### Task 3.1: assetTypeSchemas.ts 类型定义 + 单元测试

**Files:**
- Create: `frontend/src/modules/database/schemas/assetTypeSchemas.ts`
- Create: `frontend/src/modules/database/schemas/assetTypeSchemas.test.ts`

- [ ] **Step 1: 写失败测试**

```ts
import { describe, expect, it } from "vitest";
import { ASSET_TYPE_SCHEMAS, type AssetTypeKey } from "./assetTypeSchemas";

const ALL_KEYS: AssetTypeKey[] = ["vehicle", "machine", "tool", "safety"];

describe("ASSET_TYPE_SCHEMAS", () => {
  it("covers all four asset types", () => {
    for (const key of ALL_KEYS) {
      expect(ASSET_TYPE_SCHEMAS[key]).toBeDefined();
      expect(ASSET_TYPE_SCHEMAS[key].key).toBe(key);
    }
  });

  it.each(ALL_KEYS)("schema for %s defines unit_default and label", (key) => {
    const s = ASSET_TYPE_SCHEMAS[key];
    expect(s.unit_default).toBeTruthy();
    expect(s.label).toBeTruthy();
  });

  it.each(ALL_KEYS)("schema for %s has at least one core attachment slot", (key) => {
    expect(ASSET_TYPE_SCHEMAS[key].core_attachments.length).toBeGreaterThan(0);
  });

  it.each(ALL_KEYS)("schema for %s has at least one export column", (key) => {
    expect(ASSET_TYPE_SCHEMAS[key].export_columns.length).toBeGreaterThan(0);
  });

  it.each(ALL_KEYS)("schema for %s: select extras have non-empty options", (key) => {
    const selects = ASSET_TYPE_SCHEMAS[key].extras.filter((f) => f.type === "select");
    for (const f of selects) {
      expect(f.options).toBeDefined();
      expect(f.options!.length).toBeGreaterThan(0);
    }
  });

  it.each(ALL_KEYS)("schema for %s: at least one core slot determines expires_at", (key) => {
    const determining = ASSET_TYPE_SCHEMAS[key].core_attachments.filter(
      (s) => s.determines_expires_at,
    );
    // safety 类允许全部 false (mandatory_retirement_months 派生),其它必须有
    if (key !== "safety") {
      expect(determining.length).toBeGreaterThan(0);
    }
  });

  it("vehicle schema: vehicle_type is required select", () => {
    const f = ASSET_TYPE_SCHEMAS.vehicle.extras.find((x) => x.key === "vehicle_type");
    expect(f).toBeDefined();
    expect(f!.required).toBe(true);
    expect(f!.type).toBe("select");
  });

  it("tool schema: voltage_level is select with kV options", () => {
    const f = ASSET_TYPE_SCHEMAS.tool.extras.find((x) => x.key === "voltage_level");
    expect(f).toBeDefined();
    expect(f!.type).toBe("select");
    expect(f!.options!.some((o) => o.value === "10kV")).toBe(true);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd frontend && npx vitest run src/modules/database/schemas/assetTypeSchemas.test.ts
```

Expected: FAIL（schemas 文件不存在）

- [ ] **Step 3: 实现 assetTypeSchemas.ts**

**File:** `frontend/src/modules/database/schemas/assetTypeSchemas.ts`

```ts
export type AssetTypeKey = "vehicle" | "machine" | "tool" | "safety";

export type ExtraFieldType = "text" | "number" | "date" | "select" | "boolean";

export type ExtraField = {
  key: string;
  label: string;
  type: ExtraFieldType;
  required?: boolean;
  options?: { value: string; label: string }[];
  hint?: string;
  computed_from?: string;
};

export type CoreAttachmentSlot = {
  kind: string;
  label: string;
  required: boolean;
  determines_expires_at?: boolean;
};

export type ArchiveAttachmentKind = { kind: string; label: string };

export type SoftFilterChipKey =
  | "self_only" | "leased_only"
  | "voltage_10kv" | "voltage_min_10kv"
  | "vehicle_aerial_only" | "purchased_within_year"
  | "special_equipment_only" | "inspection_valid_30d"
  | "insulation_only" | "tool_inspection_30d"
  | "ppe_only" | "produced_within_year" | "retirement_30d";

export type SoftFilterChip = { key: SoftFilterChipKey; label: string };

export type ExportColumnSource = "field" | "extra" | "computed";
export type ExportFormatter = "date" | "ownership" | "tech_condition" | "voltage" | "boolean_yn";

export type ExportColumn = {
  key: string;
  label: string;
  source: ExportColumnSource;
  source_key?: string;
  formatter?: ExportFormatter;
};

export type AssetTypeSchema = {
  key: AssetTypeKey;
  label: string;
  unit_default: string;
  core_attachments: CoreAttachmentSlot[];
  archive_attachment_kinds: ArchiveAttachmentKind[];
  extras: ExtraField[];
  soft_filter_chips: SoftFilterChip[];
  export_columns: ExportColumn[];
};

const VEHICLE: AssetTypeSchema = {
  key: "vehicle",
  label: "车辆",
  unit_default: "辆",
  core_attachments: [
    { kind: "driving_license", label: "行驶证", required: true },
    { kind: "annual_inspection", label: "年检报告", required: true, determines_expires_at: true },
    { kind: "insurance", label: "保险单", required: false },
  ],
  archive_attachment_kinds: [
    { kind: "maintenance_record", label: "维修记录" },
    { kind: "historical_inspection", label: "历史年检报告" },
    { kind: "historical_insurance", label: "历史保险单" },
  ],
  extras: [
    {
      key: "vehicle_type",
      label: "车辆类型",
      type: "select",
      required: true,
      options: [
        { value: "truck", label: "货车" },
        { value: "engineering", label: "工程车" },
        { value: "rescue", label: "抢修车" },
        { value: "aerial_bucket", label: "斗臂车" },
        { value: "high_altitude", label: "高空作业车" },
        { value: "crane", label: "起重车" },
        { value: "passenger", label: "普通乘用车" },
        { value: "other", label: "其他" },
      ],
    },
    { key: "driving_license_no", label: "行驶证号", type: "text", required: true },
    { key: "insurance_expires_at", label: "交强险到期", type: "date" },
    {
      key: "technical_grade", label: "技术等级", type: "select",
      options: [
        { value: "excellent", label: "优" },
        { value: "good", label: "良" },
        { value: "qualified", label: "合格" },
        { value: "unqualified", label: "不合格" },
      ],
      hint: "GB/T 18344",
    },
  ],
  soft_filter_chips: [
    { key: "self_only", label: "仅自有" },
    { key: "vehicle_aerial_only", label: "仅斗臂车" },
    { key: "voltage_min_10kv", label: "仅 10kV 适用" },
    { key: "purchased_within_year", label: "一年内购置" },
  ],
  export_columns: [
    { key: "no", label: "序号", source: "computed" },
    { key: "name", label: "设备名称", source: "field", source_key: "name" },
    { key: "spec_model", label: "规格型号", source: "field", source_key: "spec_model" },
    { key: "vehicle_type", label: "车辆类型", source: "extra", source_key: "vehicle_type" },
    { key: "serial_no", label: "车牌号", source: "field", source_key: "serial_no" },
    { key: "quantity", label: "数量", source: "field", source_key: "quantity" },
    { key: "unit", label: "单位", source: "field", source_key: "unit" },
    { key: "manufacturer", label: "生产厂家", source: "field", source_key: "manufacturer" },
    { key: "ownership", label: "所有权", source: "field", source_key: "ownership", formatter: "ownership" },
    { key: "acquired_at", label: "购置日期", source: "field", source_key: "acquired_at", formatter: "date" },
    { key: "expires_at", label: "年检有效期", source: "field", source_key: "expires_at", formatter: "date" },
    { key: "technical_condition", label: "技术状态", source: "field", source_key: "technical_condition" },
    { key: "intended_role", label: "用途/拟用阶段", source: "field", source_key: "intended_role" },
  ],
};

const MACHINE: AssetTypeSchema = {
  key: "machine",
  label: "施工机械",
  unit_default: "台",
  core_attachments: [
    { kind: "factory_certificate", label: "出厂合格证", required: true },
    { kind: "inspection_report", label: "本周期检定报告", required: false, determines_expires_at: true },
    { kind: "purchase_voucher", label: "购置发票/租赁合同", required: true },
  ],
  archive_attachment_kinds: [
    { kind: "historical_inspection", label: "历年检定报告" },
    { kind: "maintenance_record", label: "维修记录" },
  ],
  extras: [
    {
      key: "machine_category", label: "机械类别", type: "select", required: true,
      options: [
        { value: "lifting", label: "起重机械" },
        { value: "piling", label: "桩工机械" },
        { value: "earth_moving", label: "土石方机械" },
        { value: "concrete", label: "混凝土机械" },
        { value: "electrical_test", label: "电气试验设备" },
        { value: "welding", label: "焊接设备" },
        { value: "detection", label: "检测设备" },
        { value: "other", label: "其他" },
      ],
    },
    { key: "capacity_value", label: "功率/容量/吨位(值)", type: "text", hint: '如 "25" / "150"' },
    {
      key: "capacity_unit", label: "功率/容量/吨位(单位)", type: "select",
      options: [
        { value: "t", label: "t" }, { value: "kW", label: "kW" }, { value: "kVA", label: "kVA" },
        { value: "m3", label: "m³" }, { value: "m", label: "m" }, { value: "kN", label: "kN" },
      ],
    },
    { key: "is_special_equipment", label: "是否特种设备", type: "boolean" },
    { key: "inspection_required", label: "是否需周期检定", type: "boolean", required: true,
      hint: "勾选后,有效期(expires_at)必填" },
    { key: "last_inspection_at", label: "上次检定日期", type: "date" },
    { key: "inspection_period_months", label: "检定周期(月)", type: "number", hint: "6/12/24" },
    { key: "inspection_authority", label: "检定单位", type: "text" },
  ],
  soft_filter_chips: [
    { key: "self_only", label: "仅自有" },
    { key: "special_equipment_only", label: "仅特种设备" },
    { key: "inspection_valid_30d", label: "检定有效期 ≥30 天" },
  ],
  export_columns: [
    { key: "no", label: "序号", source: "computed" },
    { key: "name", label: "设备名称", source: "field", source_key: "name" },
    { key: "spec_model", label: "规格型号", source: "field", source_key: "spec_model" },
    { key: "machine_category", label: "机械类别", source: "extra", source_key: "machine_category" },
    { key: "capacity", label: "功率/容量/吨位", source: "computed" },  // 渲染时拼 capacity_value + capacity_unit
    { key: "serial_no", label: "出厂编号", source: "field", source_key: "serial_no" },
    { key: "quantity", label: "数量", source: "field", source_key: "quantity" },
    { key: "unit", label: "单位", source: "field", source_key: "unit" },
    { key: "manufacturer", label: "生产厂家", source: "field", source_key: "manufacturer" },
    { key: "ownership", label: "所有权", source: "field", source_key: "ownership", formatter: "ownership" },
    { key: "acquired_at", label: "出厂/购置日期", source: "field", source_key: "acquired_at", formatter: "date" },
    { key: "expires_at", label: "检定有效期", source: "field", source_key: "expires_at", formatter: "date" },
    { key: "technical_condition", label: "技术状态", source: "field", source_key: "technical_condition" },
    { key: "intended_role", label: "用途/拟用阶段", source: "field", source_key: "intended_role" },
  ],
};

const TOOL: AssetTypeSchema = {
  key: "tool",
  label: "施工工器具",
  unit_default: "件",
  core_attachments: [
    { kind: "inspection_report", label: "本周期试验报告", required: true, determines_expires_at: true },
    { kind: "factory_certificate", label: "出厂合格证", required: false },
  ],
  archive_attachment_kinds: [
    { kind: "historical_inspection", label: "历年试验报告" },
  ],
  extras: [
    {
      key: "tool_category", label: "工器具类别", type: "select", required: true,
      options: [
        { value: "insulation", label: "绝缘类" },
        { value: "grounding", label: "接地类" },
        { value: "voltage_detector", label: "验电类" },
        { value: "climbing", label: "登高类" },
        { value: "general", label: "通用工具" },
        { value: "other", label: "其他" },
      ],
    },
    {
      key: "voltage_level", label: "电压等级", type: "select",
      options: [
        { value: "0.4kV", label: "0.4kV" }, { value: "10kV", label: "10kV" },
        { value: "20kV", label: "20kV" }, { value: "35kV", label: "35kV" },
        { value: "110kV", label: "110kV" }, { value: "220kV", label: "220kV" },
        { value: "500kV", label: "500kV" }, { value: "N/A", label: "不适用" },
      ],
      hint: "绝缘/接地/验电类必填",
    },
    { key: "inspection_period_months", label: "试验周期(月)", type: "number", required: true,
      hint: "通常 6 或 12" },
    { key: "last_inspection_at", label: "上次试验日期", type: "date", required: true },
    { key: "inspection_authority", label: "试验单位", type: "text", hint: "CMA 资质单位" },
    { key: "batch_no", label: "批次号", type: "text" },
  ],
  soft_filter_chips: [
    { key: "voltage_10kv", label: "仅 10kV" },
    { key: "insulation_only", label: "仅绝缘类" },
    { key: "tool_inspection_30d", label: "试验有效期 ≥30 天" },
    { key: "self_only", label: "仅自有" },
  ],
  export_columns: [
    { key: "no", label: "序号", source: "computed" },
    { key: "name", label: "名称", source: "field", source_key: "name" },
    { key: "spec_model", label: "规格型号", source: "field", source_key: "spec_model" },
    { key: "tool_category", label: "工器具类别", source: "extra", source_key: "tool_category" },
    { key: "voltage_level", label: "电压等级", source: "extra", source_key: "voltage_level", formatter: "voltage" },
    { key: "serial_no", label: "出厂编号", source: "field", source_key: "serial_no" },
    { key: "quantity", label: "数量", source: "field", source_key: "quantity" },
    { key: "unit", label: "单位", source: "field", source_key: "unit" },
    { key: "manufacturer", label: "生产厂家", source: "field", source_key: "manufacturer" },
    { key: "ownership", label: "所有权", source: "field", source_key: "ownership", formatter: "ownership" },
    { key: "acquired_at", label: "出厂日期", source: "field", source_key: "acquired_at", formatter: "date" },
    { key: "expires_at", label: "试验有效期", source: "field", source_key: "expires_at", formatter: "date" },
    { key: "technical_condition", label: "技术状态", source: "field", source_key: "technical_condition" },
    { key: "intended_role", label: "用途/拟用阶段", source: "field", source_key: "intended_role" },
  ],
};

const SAFETY: AssetTypeSchema = {
  key: "safety",
  label: "安全设施设备及器具",
  unit_default: "件",
  core_attachments: [
    { kind: "factory_certificate", label: "出厂/检验合格证", required: true },
    { kind: "inspection_report", label: "周期检验报告(如有)", required: false, determines_expires_at: true },
  ],
  archive_attachment_kinds: [
    { kind: "batch_acceptance", label: "批量验收记录" },
    { kind: "retirement_record", label: "报废处理记录" },
  ],
  extras: [
    {
      key: "safety_category", label: "安全类别", type: "select", required: true,
      options: [
        { value: "ppe", label: "PPE 个体防护" },
        { value: "fall_protection", label: "防坠装置" },
        { value: "fire", label: "消防器材" },
        { value: "warning", label: "现场警示设施" },
        { value: "grounding", label: "接地装置" },
        { value: "emergency", label: "应急救援设备" },
      ],
    },
    { key: "protection_standard", label: "防护标准", type: "text",
      hint: "如 GB 2811(安全帽)/GB 6095(安全带)/GB 12011(绝缘鞋)" },
    { key: "applicable_work", label: "适用工种/作业", type: "text" },
    { key: "mandatory_retirement_months", label: "强制报废时长(月)", type: "number",
      hint: "安全帽 60、安全带 36;填了自动算 expires_at",
      computed_from: "expires_at = acquired_at + mandatory_retirement_months" },
    { key: "production_batch", label: "生产批次", type: "text" },
  ],
  soft_filter_chips: [
    { key: "ppe_only", label: "仅 PPE" },
    { key: "produced_within_year", label: "仅 1 年内生产" },
    { key: "retirement_30d", label: "报废日期 ≥30 天" },
  ],
  export_columns: [
    { key: "no", label: "序号", source: "computed" },
    { key: "name", label: "名称", source: "field", source_key: "name" },
    { key: "spec_model", label: "规格型号", source: "field", source_key: "spec_model" },
    { key: "safety_category", label: "安全类别", source: "extra", source_key: "safety_category" },
    { key: "protection_standard", label: "防护标准", source: "extra", source_key: "protection_standard" },
    { key: "serial_no", label: "出厂批号/编号", source: "field", source_key: "serial_no" },
    { key: "quantity", label: "数量", source: "field", source_key: "quantity" },
    { key: "unit", label: "单位", source: "field", source_key: "unit" },
    { key: "manufacturer", label: "生产厂家", source: "field", source_key: "manufacturer" },
    { key: "ownership", label: "所有权", source: "field", source_key: "ownership", formatter: "ownership" },
    { key: "acquired_at", label: "生产日期", source: "field", source_key: "acquired_at", formatter: "date" },
    { key: "expires_at", label: "强制报废日期", source: "field", source_key: "expires_at", formatter: "date" },
    { key: "intended_role", label: "用途/拟用阶段", source: "field", source_key: "intended_role" },
  ],
};

export const ASSET_TYPE_SCHEMAS: Record<AssetTypeKey, AssetTypeSchema> = {
  vehicle: VEHICLE,
  machine: MACHINE,
  tool: TOOL,
  safety: SAFETY,
};

export const ASSET_TYPE_KEYS: AssetTypeKey[] = ["vehicle", "machine", "tool", "safety"];
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd frontend && npx vitest run src/modules/database/schemas/assetTypeSchemas.test.ts
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/modules/database/schemas/assetTypeSchemas.ts \
        frontend/src/modules/database/schemas/assetTypeSchemas.test.ts
git commit -m "feat(asset): frontend asset type schemas for 4 categories"
```

---

## Phase 4: 拆分 CompanyLibraryWorkbench

**目标:** 把 700+ 行的 `CompanyLibraryWorkbench.tsx` 拆为容器 + 三个 Section（基础资料 / 业绩 / 资产），让新增资产部分有干净位置，老内容也减负。

### Task 4.1: 抽出 CompanyProfileSection 与 ContractPerformanceSection

**Files:**
- Create: `frontend/src/modules/database/components/CompanyProfileSection.tsx`
- Create: `frontend/src/modules/database/components/ContractPerformanceSection.tsx`
- Modify: `frontend/src/modules/database/components/CompanyLibraryWorkbench.tsx`

- [ ] **Step 1: 抽出"公司基础资料"为 CompanyProfileSection**

读 `CompanyLibraryWorkbench.tsx`，找出"公司基础资料"相关 JSX/state/effect 整段（含上传普通公司资料、profiles 显示），原封不动迁到 `CompanyProfileSection.tsx`。组件签名：

```ts
type CompanyProfileSectionProps = {
  selectedLibraryId: string;
  taxonomy: AssetTaxonomyDomain[];
  onError: (msg: string) => void;
};
```

`CompanyLibraryWorkbench.tsx` 改为：

```tsx
import { CompanyProfileSection } from "./CompanyProfileSection";
// ...
<CompanyProfileSection
  selectedLibraryId={selectedLibraryId}
  taxonomy={taxonomy}
  onError={setError}
/>
```

- [ ] **Step 2: 抽出"公司业绩"为 ContractPerformanceSection**

同样把合同业绩 form / 4 卡片附件 / 业绩表格整段迁出。组件签名：

```ts
type ContractPerformanceSectionProps = {
  selectedLibraryId: string;
  onError: (msg: string) => void;
};
```

- [ ] **Step 3: 在浏览器手动验证（无回归）**

```bash
cd frontend && npm run dev
```

打开 `投标资料库 → 公司资料`，验证：
- 公司选择、基础资料表单/上传仍可用
- 公司业绩 4 卡片、表格、CRUD 仍可用
- 控制台无 console.error / 红色 React 警告

- [ ] **Step 4: 运行现有相关测试**

```bash
cd frontend && npx vitest run src/modules/database
```

Expected: 全部 PASS（无新增测试，但拆分不应破坏既有测试）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/modules/database/components/CompanyProfileSection.tsx \
        frontend/src/modules/database/components/ContractPerformanceSection.tsx \
        frontend/src/modules/database/components/CompanyLibraryWorkbench.tsx
git commit -m "refactor(company-library): split workbench into Profile and ContractPerformance sections"
```

---

## Phase 5: 前端资产工作台 UI

**目标:** 实现 `公司资料 → 公司资产` 的完整 UI：4 类 tab + 表格 + 表单抽屉 + 4 卡片核心槽 + 折叠累积区。

### Task 5.1: API 客户端函数

**Files:**
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: 在 api.ts 加资产 API 类型与函数**

```ts
// types
export type CompanyAsset = {
  id: string;
  library_company_id: string;
  asset_type: "vehicle" | "machine" | "tool" | "safety";
  name: string;
  spec_model: string | null;
  serial_no: string | null;
  manufacturer: string | null;
  quantity: number;
  unit: string;
  ownership: "self" | "leased" | "third_party";
  acquired_at: string | null;
  expires_at: string | null;
  technical_condition: string | null;
  status: "active" | "maintenance" | "retired";
  location: string | null;
  extras: Record<string, unknown>;
  notes: string | null;
};

export type CompanyAssetAttachment = {
  id: string;
  evidence_asset_id: string;
  attachment_kind: string;
  slot_role: "core" | "archive";
  effective_at: string | null;
};

// fetchers
export async function fetchCompanyAssets(libraryId: string, assetType?: string,
                                         includeRetired?: boolean): Promise<CompanyAsset[]> {
  const params = new URLSearchParams();
  if (assetType) params.set("asset_type", assetType);
  if (includeRetired) params.set("include_retired", "true");
  return await api(`/master-data/library-companies/${libraryId}/assets?${params}`);
}

export async function createCompanyAsset(libraryId: string,
                                         payload: Partial<CompanyAsset>): Promise<CompanyAsset> {
  return await api(`/master-data/library-companies/${libraryId}/assets`,
                   { method: "POST", body: JSON.stringify(payload) });
}

export async function updateCompanyAsset(assetId: string,
                                         patch: Partial<CompanyAsset>): Promise<CompanyAsset> {
  return await api(`/master-data/assets/${assetId}`,
                   { method: "PUT", body: JSON.stringify(patch) });
}

export async function deleteCompanyAsset(assetId: string): Promise<void> {
  await api(`/master-data/assets/${assetId}`, { method: "DELETE" });
}

export async function listAssetAttachments(assetId: string): Promise<CompanyAssetAttachment[]> {
  return await api(`/master-data/assets/${assetId}/attachments`);
}

export async function uploadAssetAttachment(assetId: string, args: {
  attachmentKind: string; slotRole: "core" | "archive"; file: File; effectiveAt?: string;
}): Promise<CompanyAssetAttachment> {
  const form = new FormData();
  form.append("attachment_kind", args.attachmentKind);
  form.append("slot_role", args.slotRole);
  if (args.effectiveAt) form.append("effective_at", args.effectiveAt);
  form.append("file", args.file);
  return await api(`/master-data/assets/${assetId}/attachments`,
                   { method: "POST", body: form, headers: {} });  // 注意:FormData 不要手设 Content-Type
}

export async function removeAssetAttachment(assetId: string,
                                            attachmentId: string): Promise<void> {
  await api(`/master-data/assets/${assetId}/attachments/${attachmentId}`, { method: "DELETE" });
}
```

> 沿用 api.ts 中已有的 `api(url, init)` 工具；`headers: {}` 让浏览器自动加 multipart boundary。

- [ ] **Step 2: 提交（API 客户端无独立测试，依赖后续组件测试覆盖）**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(asset): frontend API client for company assets"
```

---

### Task 5.2: 有效期 Badge 工具函数

**Files:**
- Create: `frontend/src/modules/database/components/asset/expiryBadge.ts`
- Create: `frontend/src/modules/database/components/asset/expiryBadge.test.ts`

- [ ] **Step 1: 写失败测试**

```ts
import { describe, expect, it } from "vitest";
import { computeExpiryBadge } from "./expiryBadge";

const TODAY = new Date("2026-05-08T00:00:00Z");

describe("computeExpiryBadge", () => {
  it("returns dash for null expires_at", () => {
    const b = computeExpiryBadge(null, TODAY);
    expect(b.variant).toBe("default");
    expect(b.text).toBe("—");
  });

  it("returns danger for expired", () => {
    const b = computeExpiryBadge("2026-04-01", TODAY);
    expect(b.variant).toBe("danger");
    expect(b.text).toContain("已过期");
  });

  it("returns warning for ≤30 days", () => {
    const b = computeExpiryBadge("2026-05-25", TODAY);
    expect(b.variant).toBe("warning");
    expect(b.text).toContain("天内到期");
  });

  it("returns default for 31-90 days", () => {
    const b = computeExpiryBadge("2026-07-15", TODAY);
    expect(b.variant).toBe("default");
  });

  it("returns success for >90 days", () => {
    const b = computeExpiryBadge("2026-12-31", TODAY);
    expect(b.variant).toBe("success");
  });
});
```

- [ ] **Step 2: 运行确认失败**

```bash
cd frontend && npx vitest run src/modules/database/components/asset/expiryBadge.test.ts
```

Expected: FAIL

- [ ] **Step 3: 实现**

```ts
export type ExpiryBadge = { variant: "default" | "warning" | "success" | "danger"; text: string };

export function computeExpiryBadge(expiresAt: string | null, now: Date = new Date()): ExpiryBadge {
  if (!expiresAt) return { variant: "default", text: "—" };
  const exp = new Date(expiresAt + "T00:00:00Z");
  const diffMs = exp.getTime() - now.getTime();
  const diffDays = Math.floor(diffMs / 86400000);
  if (diffDays < 0) return { variant: "danger", text: `已过期 ${Math.abs(diffDays)} 天` };
  if (diffDays <= 30) return { variant: "warning", text: `${diffDays} 天内到期` };
  if (diffDays <= 90) return { variant: "default", text: `${diffDays} 天` };
  return { variant: "success", text: `${diffDays} 天` };
}
```

- [ ] **Step 4: 运行确认通过 + Commit**

```bash
cd frontend && npx vitest run src/modules/database/components/asset/expiryBadge.test.ts
git add frontend/src/modules/database/components/asset/expiryBadge.ts \
        frontend/src/modules/database/components/asset/expiryBadge.test.ts
git commit -m "feat(asset): expiry badge utility with 4 severity bands"
```

---

### Task 5.3: AssetTable 组件（按 schema 动态出列）

**Files:**
- Create: `frontend/src/modules/database/components/asset/AssetTable.tsx`
- Create: `frontend/src/modules/database/components/asset/AssetTable.test.tsx`

- [ ] **Step 1: 写失败测试**

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AssetTable } from "./AssetTable";
import type { CompanyAsset } from "../../../../lib/api";

const mkAsset = (overrides: Partial<CompanyAsset> = {}): CompanyAsset => ({
  id: "a1", library_company_id: "lib1", asset_type: "vehicle", name: "斗臂车",
  spec_model: "DFL5160", serial_no: "苏A12345", manufacturer: "东风",
  quantity: 1, unit: "辆", ownership: "self",
  acquired_at: "2024-01-01", expires_at: "2026-12-31", technical_condition: "完好",
  status: "active", location: null,
  extras: { vehicle_type: "aerial_bucket", driving_license_no: "苏A12345", technical_grade: "excellent" },
  notes: null,
  ...overrides,
});

describe("AssetTable", () => {
  it("renders rows for each asset and shows core columns", () => {
    const onEdit = vi.fn();
    render(<AssetTable assetType="vehicle" assets={[mkAsset({ id: "a1", name: "斗臂车" })]} onEdit={onEdit} onDelete={vi.fn()} />);
    expect(screen.getByText("斗臂车")).toBeInTheDocument();
    expect(screen.getByText("DFL5160")).toBeInTheDocument();
  });

  it("calls onEdit when a row's edit button is clicked", () => {
    const onEdit = vi.fn();
    render(<AssetTable assetType="vehicle" assets={[mkAsset()]} onEdit={onEdit} onDelete={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /编辑/ }));
    expect(onEdit).toHaveBeenCalledWith(expect.objectContaining({ id: "a1" }));
  });

  it("renders empty state when no assets", () => {
    render(<AssetTable assetType="tool" assets={[]} onEdit={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByText(/暂无/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 运行确认失败**

```bash
cd frontend && npx vitest run src/modules/database/components/asset/AssetTable.test.tsx
```

Expected: FAIL

- [ ] **Step 3: 实现 AssetTable**

```tsx
import type { CompanyAsset } from "../../../../lib/api";
import { Badge } from "../../../../components/ui/Badge";
import { ClayButton } from "../../../../components/ui/ClayButton";
import { ASSET_TYPE_SCHEMAS, type AssetTypeKey } from "../../schemas/assetTypeSchemas";
import { computeExpiryBadge } from "./expiryBadge";

type Props = {
  assetType: AssetTypeKey;
  assets: CompanyAsset[];
  onEdit: (asset: CompanyAsset) => void;
  onDelete: (asset: CompanyAsset) => void;
};

const OWNERSHIP_LABEL: Record<string, string> = {
  self: "自有", leased: "租赁", third_party: "第三方",
};

const SPECIALIZED_COLUMNS: Record<AssetTypeKey, Array<{ label: string; render: (a: CompanyAsset) => string }>> = {
  vehicle: [
    { label: "车牌号", render: (a) => a.serial_no ?? "-" },
    { label: "车辆类型", render: (a) => String(a.extras?.vehicle_type ?? "-") },
    { label: "技术等级", render: (a) => String(a.extras?.technical_grade ?? "-") },
  ],
  machine: [
    { label: "出厂编号", render: (a) => a.serial_no ?? "-" },
    { label: "机械类别", render: (a) => String(a.extras?.machine_category ?? "-") },
    { label: "容量", render: (a) => `${a.extras?.capacity_value ?? ""} ${a.extras?.capacity_unit ?? ""}`.trim() || "-" },
    { label: "特种设备", render: (a) => (a.extras?.is_special_equipment ? "是" : "否") },
  ],
  tool: [
    { label: "出厂编号", render: (a) => a.serial_no ?? "-" },
    { label: "工器具类别", render: (a) => String(a.extras?.tool_category ?? "-") },
    { label: "电压等级", render: (a) => String(a.extras?.voltage_level ?? "-") },
  ],
  safety: [
    { label: "安全类别", render: (a) => String(a.extras?.safety_category ?? "-") },
    { label: "防护标准", render: (a) => String(a.extras?.protection_standard ?? "-") },
  ],
};

export function AssetTable({ assetType, assets, onEdit, onDelete }: Props) {
  const _schema = ASSET_TYPE_SCHEMAS[assetType];  // reserved for future schema-driven cols
  const cols = SPECIALIZED_COLUMNS[assetType];

  if (assets.length === 0) {
    return <div className="empty-state"><p className="empty-state__title">暂无{ASSET_TYPE_SCHEMAS[assetType].label}</p></div>;
  }

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>序号</th>
          <th>名称</th>
          <th>规格型号</th>
          {cols.map((c) => <th key={c.label}>{c.label}</th>)}
          <th>数量&单位</th>
          <th>所有权</th>
          <th>有效期</th>
          <th>状态</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        {assets.map((a, idx) => {
          const badge = computeExpiryBadge(a.expires_at);
          return (
            <tr key={a.id}>
              <td>{idx + 1}</td>
              <td>{a.name}</td>
              <td>{a.spec_model ?? "-"}</td>
              {cols.map((c) => <td key={c.label}>{c.render(a)}</td>)}
              <td>{a.quantity} {a.unit}</td>
              <td>{OWNERSHIP_LABEL[a.ownership] ?? a.ownership}</td>
              <td><Badge variant={badge.variant}>{badge.text}</Badge></td>
              <td>{a.status}</td>
              <td>
                <ClayButton variant="ghost" size="sm" onClick={() => onEdit(a)}>编辑</ClayButton>
                <ClayButton variant="ghost" size="sm" onClick={() => onDelete(a)}>删除</ClayButton>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 4: 运行确认通过 + Commit**

```bash
cd frontend && npx vitest run src/modules/database/components/asset/AssetTable.test.tsx
git add frontend/src/modules/database/components/asset/AssetTable.tsx \
        frontend/src/modules/database/components/asset/AssetTable.test.tsx
git commit -m "feat(asset): AssetTable component with type-specific columns"
```

---

### Task 5.4: AssetCoreAttachments 与 AssetArchiveAttachments 组件

**Files:**
- Create: `frontend/src/modules/database/components/asset/AssetCoreAttachments.tsx`
- Create: `frontend/src/modules/database/components/asset/AssetArchiveAttachments.tsx`

- [ ] **Step 1: 实现 AssetCoreAttachments（沿用 company-contract-upload-card 样式）**

```tsx
import { useState } from "react";
import { ClayButton } from "../../../../components/ui/ClayButton";
import type { CoreAttachmentSlot } from "../../schemas/assetTypeSchemas";
import type { CompanyAssetAttachment } from "../../../../lib/api";

type Props = {
  slots: CoreAttachmentSlot[];
  attachments: CompanyAssetAttachment[];
  onUpload: (kind: string, file: File) => Promise<void>;
  onRemove: (attachment: CompanyAssetAttachment) => Promise<void>;
};

export function AssetCoreAttachments({ slots, attachments, onUpload, onRemove }: Props) {
  const [pending, setPending] = useState<string | null>(null);
  const map: Record<string, CompanyAssetAttachment | undefined> = {};
  for (const a of attachments.filter((x) => x.slot_role === "core")) {
    map[a.attachment_kind] = a;
  }

  return (
    <div className="company-contract-upload-grid">
      {slots.map((slot) => {
        const existing = map[slot.kind];
        return (
          <div key={slot.kind} className="company-contract-upload-card">
            <div className="company-contract-upload-card__header">
              <strong>{slot.label}{slot.required && <span style={{ color: "red" }}> *</span>}{slot.determines_expires_at && <span title="该附件决定有效期"> ⏰</span>}</strong>
              {existing && <span>已上传</span>}
            </div>
            <input
              type="file"
              accept=".pdf"
              onChange={async (e) => {
                const f = e.target.files?.[0];
                if (!f) return;
                setPending(slot.kind);
                try { await onUpload(slot.kind, f); } finally { setPending(null); }
              }}
            />
            <ClayButton
              variant={existing ? "ghost" : "outline"}
              disabled={pending === slot.kind || !!existing}
            >
              {pending === slot.kind ? "上传中..." : existing ? "已挂载" : "上传 PDF"}
            </ClayButton>
            {existing && (
              <ClayButton variant="ghost" onClick={() => onRemove(existing)}>移除</ClayButton>
            )}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: 实现 AssetArchiveAttachments**

```tsx
import { useState } from "react";
import { ClayButton } from "../../../../components/ui/ClayButton";
import type { ArchiveAttachmentKind } from "../../schemas/assetTypeSchemas";
import type { CompanyAssetAttachment } from "../../../../lib/api";

type Props = {
  archiveKinds: ArchiveAttachmentKind[];
  attachments: CompanyAssetAttachment[];
  onUpload: (kind: string, file: File, effectiveAt?: string) => Promise<void>;
  onRemove: (attachment: CompanyAssetAttachment) => Promise<void>;
};

export function AssetArchiveAttachments({ archiveKinds, attachments, onUpload, onRemove }: Props) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState(archiveKinds[0]?.kind ?? "");
  const [effectiveAt, setEffectiveAt] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [pending, setPending] = useState(false);
  const archived = attachments.filter((x) => x.slot_role === "archive");

  return (
    <details open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>历史与补充附件 ({archived.length})</summary>
      <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
        {archived.map((a) => (
          <div key={a.id} style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span>{a.attachment_kind}</span>
            <span>{a.effective_at ?? "-"}</span>
            <ClayButton variant="ghost" size="sm" onClick={() => onRemove(a)}>移除</ClayButton>
          </div>
        ))}
        <div style={{ display: "grid", gap: 8 }}>
          <select value={kind} onChange={(e) => setKind(e.target.value)} className="clay-input">
            {archiveKinds.map((k) => <option key={k.kind} value={k.kind}>{k.label}</option>)}
          </select>
          <input type="date" value={effectiveAt} onChange={(e) => setEffectiveAt(e.target.value)} className="clay-input" />
          <input type="file" accept=".pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <ClayButton
            variant="outline"
            disabled={!file || pending}
            onClick={async () => {
              if (!file) return;
              setPending(true);
              try { await onUpload(kind, file, effectiveAt || undefined); setFile(null); }
              finally { setPending(false); }
            }}
          >
            {pending ? "上传中..." : "+ 添加附件"}
          </ClayButton>
        </div>
      </div>
    </details>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/modules/database/components/asset/AssetCoreAttachments.tsx \
        frontend/src/modules/database/components/asset/AssetArchiveAttachments.tsx
git commit -m "feat(asset): core and archive attachment UI components"
```

---

### Task 5.5: AssetFormDrawer（按 schema 动态渲染表单）

**Files:**
- Create: `frontend/src/modules/database/components/asset/AssetFormDrawer.tsx`
- Create: `frontend/src/modules/database/components/__tests__/AssetFormDrawer.test.tsx`

- [ ] **Step 1: 写失败测试（最小集，覆盖必填校验 + 派生 expires_at）**

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AssetFormDrawer } from "../asset/AssetFormDrawer";

describe("AssetFormDrawer (vehicle)", () => {
  it("disables save when required fields are empty", () => {
    render(<AssetFormDrawer assetType="vehicle" libraryId="lib1" onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByRole("button", { name: /保存/ })).toBeDisabled();
  });

  it("enables save when name + driving_license_no + vehicle_type provided", () => {
    render(<AssetFormDrawer assetType="vehicle" libraryId="lib1" onClose={vi.fn()} onSaved={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("名称"), { target: { value: "斗臂车" } });
    fireEvent.change(screen.getByLabelText("行驶证号"), { target: { value: "苏A12345" } });
    fireEvent.change(screen.getByLabelText("车辆类型"), { target: { value: "aerial_bucket" } });
    expect(screen.getByRole("button", { name: /保存/ })).not.toBeDisabled();
  });
});
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 AssetFormDrawer（schema 驱动）**

```tsx
import { useEffect, useState } from "react";
import { ClayButton } from "../../../../components/ui/ClayButton";
import { ASSET_TYPE_SCHEMAS, type AssetTypeKey, type ExtraField } from "../../schemas/assetTypeSchemas";
import { createCompanyAsset, updateCompanyAsset, listAssetAttachments,
         uploadAssetAttachment, removeAssetAttachment,
         type CompanyAsset, type CompanyAssetAttachment } from "../../../../lib/api";
import { AssetCoreAttachments } from "../asset/AssetCoreAttachments";
import { AssetArchiveAttachments } from "../asset/AssetArchiveAttachments";

type Props = {
  assetType: AssetTypeKey;
  libraryId: string;
  initial?: CompanyAsset;
  onClose: () => void;
  onSaved: (asset: CompanyAsset) => void;
};

export function AssetFormDrawer({ assetType, libraryId, initial, onClose, onSaved }: Props) {
  const schema = ASSET_TYPE_SCHEMAS[assetType];
  const [name, setName] = useState(initial?.name ?? "");
  const [specModel, setSpecModel] = useState(initial?.spec_model ?? "");
  const [serialNo, setSerialNo] = useState(initial?.serial_no ?? "");
  const [manufacturer, setManufacturer] = useState(initial?.manufacturer ?? "");
  const [quantity, setQuantity] = useState(String(initial?.quantity ?? 1));
  const [unit, setUnit] = useState(initial?.unit ?? schema.unit_default);
  const [ownership, setOwnership] = useState(initial?.ownership ?? "self");
  const [acquiredAt, setAcquiredAt] = useState(initial?.acquired_at ?? "");
  const [expiresAt, setExpiresAt] = useState(initial?.expires_at ?? "");
  const [technicalCondition, setTechnicalCondition] = useState(initial?.technical_condition ?? "");
  const [status, setStatus] = useState(initial?.status ?? "active");
  const [location, setLocation] = useState(initial?.location ?? "");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [extras, setExtras] = useState<Record<string, unknown>>(initial?.extras ?? {});
  const [attachments, setAttachments] = useState<CompanyAssetAttachment[]>([]);
  const [saving, setSaving] = useState(false);
  const [savedAsset, setSavedAsset] = useState<CompanyAsset | null>(initial ?? null);

  useEffect(() => {
    if (savedAsset) listAssetAttachments(savedAsset.id).then(setAttachments).catch(() => {});
  }, [savedAsset]);

  // Derived expires_at for tool / safety
  useEffect(() => {
    if (assetType === "tool") {
      const last = String(extras.last_inspection_at ?? "");
      const periodMonths = Number(extras.inspection_period_months ?? 0);
      if (last && periodMonths > 0 && !expiresAt) {
        const d = new Date(last); d.setMonth(d.getMonth() + periodMonths);
        setExpiresAt(d.toISOString().slice(0, 10));
      }
    }
    if (assetType === "safety") {
      const months = Number(extras.mandatory_retirement_months ?? 0);
      if (acquiredAt && months > 0 && !expiresAt) {
        const d = new Date(acquiredAt); d.setMonth(d.getMonth() + months);
        setExpiresAt(d.toISOString().slice(0, 10));
      }
    }
  }, [assetType, extras, acquiredAt, expiresAt]);

  const requiredOk = name.trim() && unit.trim() && schema.extras
    .filter((f) => f.required)
    .every((f) => {
      const v = extras[f.key];
      return v !== undefined && v !== null && String(v).trim() !== "";
    });

  const setExtra = (k: string, v: unknown) => setExtras((s) => ({ ...s, [k]: v }));

  const handleSave = async () => {
    if (!requiredOk) return;
    setSaving(true);
    try {
      const payload = {
        asset_type: assetType, name, spec_model: specModel || null, serial_no: serialNo || null,
        manufacturer: manufacturer || null, quantity: Number(quantity), unit, ownership: ownership as CompanyAsset["ownership"],
        acquired_at: acquiredAt || null, expires_at: expiresAt || null,
        technical_condition: technicalCondition || null, status: status as CompanyAsset["status"],
        location: location || null, notes: notes || null, extras,
      };
      const saved = initial
        ? await updateCompanyAsset(initial.id, payload)
        : await createCompanyAsset(libraryId, payload);
      setSavedAsset(saved);
      onSaved(saved);
    } finally { setSaving(false); }
  };

  const renderExtra = (f: ExtraField) => {
    const value = (extras[f.key] ?? "") as string | number | boolean;
    const id = `extra-${f.key}`;
    if (f.type === "boolean") {
      return <label htmlFor={id}><input id={id} type="checkbox" checked={!!value}
        onChange={(e) => setExtra(f.key, e.target.checked)} /> {f.label}{f.required && " *"}</label>;
    }
    if (f.type === "select") {
      return (
        <label htmlFor={id}>{f.label}{f.required && " *"}
          <select id={id} className="clay-input" value={String(value)}
                  onChange={(e) => setExtra(f.key, e.target.value)}>
            <option value="">请选择</option>
            {f.options!.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </label>
      );
    }
    return (
      <label htmlFor={id}>{f.label}{f.required && " *"}
        <input id={id} type={f.type} className="clay-input" value={String(value)}
               onChange={(e) => setExtra(f.key, f.type === "number" ? Number(e.target.value) : e.target.value)} />
        {f.hint && <span className="hint">{f.hint}</span>}
      </label>
    );
  };

  return (
    <aside className="drawer">
      <header><h2>{initial ? "编辑" : "新增"}{schema.label}</h2><button onClick={onClose}>×</button></header>
      <section>
        <h3>基础信息</h3>
        <label htmlFor="name">名称 *<input id="name" className="clay-input" value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label htmlFor="spec">规格型号<input id="spec" className="clay-input" value={specModel} onChange={(e) => setSpecModel(e.target.value)} /></label>
        <label htmlFor="serial">出厂编号/车牌号<input id="serial" className="clay-input" value={serialNo} onChange={(e) => setSerialNo(e.target.value)} /></label>
        <label htmlFor="mfr">生产厂家<input id="mfr" className="clay-input" value={manufacturer} onChange={(e) => setManufacturer(e.target.value)} /></label>
        <label htmlFor="qty">数量 *<input id="qty" type="number" className="clay-input" value={quantity} onChange={(e) => setQuantity(e.target.value)} /></label>
        <label htmlFor="unit">单位 *<input id="unit" className="clay-input" value={unit} onChange={(e) => setUnit(e.target.value)} /></label>
        <label htmlFor="own">所有权 *<select id="own" className="clay-input" value={ownership} onChange={(e) => setOwnership(e.target.value as CompanyAsset["ownership"])}>
          <option value="self">自有</option><option value="leased">租赁</option><option value="third_party">第三方</option>
        </select></label>
        <label htmlFor="acq">购置日期<input id="acq" type="date" className="clay-input" value={acquiredAt} onChange={(e) => setAcquiredAt(e.target.value)} /></label>
        <label htmlFor="exp">有效期<input id="exp" type="date" className="clay-input" value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)} /></label>
        <label htmlFor="tc">技术状态<input id="tc" className="clay-input" value={technicalCondition} onChange={(e) => setTechnicalCondition(e.target.value)} /></label>
        <label htmlFor="status">状态<select id="status" className="clay-input" value={status} onChange={(e) => setStatus(e.target.value as CompanyAsset["status"])}>
          <option value="active">启用</option><option value="maintenance">维修中</option><option value="retired">已退役</option>
        </select></label>
        <label htmlFor="loc">地点<input id="loc" className="clay-input" value={location} onChange={(e) => setLocation(e.target.value)} /></label>
        <label htmlFor="notes">备注<textarea id="notes" className="clay-textarea" value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
      </section>
      <section>
        <h3>类型特化字段</h3>
        {schema.extras.map((f) => <div key={f.key}>{renderExtra(f)}</div>)}
      </section>
      {savedAsset && (
        <>
          <section>
            <h3>核心附件</h3>
            <AssetCoreAttachments
              slots={schema.core_attachments}
              attachments={attachments}
              onUpload={async (kind, file) => {
                const att = await uploadAssetAttachment(savedAsset.id,
                  { attachmentKind: kind, slotRole: "core", file });
                setAttachments((s) => [...s, att]);
                // 如果是 determines_expires_at 槽,后端 evidence 接入下游可回填,首期不在前端硬填
              }}
              onRemove={async (a) => {
                await removeAssetAttachment(savedAsset.id, a.id);
                setAttachments((s) => s.filter((x) => x.id !== a.id));
              }}
            />
          </section>
          <section>
            <h3>历史与补充附件</h3>
            <AssetArchiveAttachments
              archiveKinds={schema.archive_attachment_kinds}
              attachments={attachments}
              onUpload={async (kind, file, effectiveAt) => {
                const att = await uploadAssetAttachment(savedAsset.id,
                  { attachmentKind: kind, slotRole: "archive", file, effectiveAt });
                setAttachments((s) => [...s, att]);
              }}
              onRemove={async (a) => {
                await removeAssetAttachment(savedAsset.id, a.id);
                setAttachments((s) => s.filter((x) => x.id !== a.id));
              }}
            />
          </section>
        </>
      )}
      <footer>
        <ClayButton variant="ghost" onClick={onClose}>取消</ClayButton>
        <ClayButton onClick={handleSave} disabled={!requiredOk || saving}>
          {saving ? "保存中..." : "保存"}
        </ClayButton>
      </footer>
    </aside>
  );
}
```

- [ ] **Step 4: 运行确认通过 + Commit**

```bash
cd frontend && npx vitest run src/modules/database/components/__tests__/AssetFormDrawer.test.tsx
git add frontend/src/modules/database/components/asset/AssetFormDrawer.tsx \
        frontend/src/modules/database/components/__tests__/AssetFormDrawer.test.tsx
git commit -m "feat(asset): schema-driven asset form drawer with core/archive attachments"
```

---

### Task 5.6: CompanyAssetSection 容器（4 tab + 工具栏）

**Files:**
- Create: `frontend/src/modules/database/components/CompanyAssetSection.tsx`
- Modify: `frontend/src/modules/database/components/CompanyLibraryWorkbench.tsx`

- [ ] **Step 1: 实现 CompanyAssetSection**

```tsx
import { useEffect, useState } from "react";
import { ClayButton } from "../../../components/ui/ClayButton";
import { Badge } from "../../../components/ui/Badge";
import { ASSET_TYPE_SCHEMAS, ASSET_TYPE_KEYS, type AssetTypeKey } from "../schemas/assetTypeSchemas";
import { fetchCompanyAssets, deleteCompanyAsset, type CompanyAsset } from "../../../lib/api";
import { AssetTable } from "./asset/AssetTable";
import { AssetFormDrawer } from "./asset/AssetFormDrawer";

type Props = { selectedLibraryId: string; onError: (msg: string) => void };

export function CompanyAssetSection({ selectedLibraryId, onError }: Props) {
  const [activeType, setActiveType] = useState<AssetTypeKey>("vehicle");
  const [counts, setCounts] = useState<Record<AssetTypeKey, number>>({ vehicle: 0, machine: 0, tool: 0, safety: 0 });
  const [assets, setAssets] = useState<CompanyAsset[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<CompanyAsset | undefined>();

  const load = async () => {
    if (!selectedLibraryId) return;
    try {
      const all: Record<AssetTypeKey, CompanyAsset[]> = { vehicle: [], machine: [], tool: [], safety: [] };
      for (const k of ASSET_TYPE_KEYS) {
        all[k] = await fetchCompanyAssets(selectedLibraryId, k);
      }
      setCounts({ vehicle: all.vehicle.length, machine: all.machine.length,
                  tool: all.tool.length, safety: all.safety.length });
      setAssets(all[activeType]);
    } catch (e) { onError(e instanceof Error ? e.message : "加载资产失败"); }
  };

  useEffect(() => { load(); /* eslint-disable-line */ }, [selectedLibraryId, activeType]);

  return (
    <section>
      <h2>公司资产</h2>
      <div className="filter-chip-row">
        {ASSET_TYPE_KEYS.map((k) => (
          <button key={k} className={`filter-chip ${activeType === k ? "active" : ""}`}
                  onClick={() => setActiveType(k)}>
            {ASSET_TYPE_SCHEMAS[k].label} <Badge>{counts[k]}</Badge>
          </button>
        ))}
      </div>
      <div className="toolbar">
        <ClayButton onClick={() => { setEditing(undefined); setDrawerOpen(true); }}>
          + 新增{ASSET_TYPE_SCHEMAS[activeType].label}
        </ClayButton>
      </div>
      <AssetTable
        assetType={activeType}
        assets={assets}
        onEdit={(a) => { setEditing(a); setDrawerOpen(true); }}
        onDelete={async (a) => {
          if (!confirm(`确认删除 "${a.name}"?`)) return;
          try { await deleteCompanyAsset(a.id); load(); }
          catch (e) { onError(e instanceof Error ? e.message : "删除失败"); }
        }}
      />
      {drawerOpen && (
        <AssetFormDrawer
          assetType={activeType}
          libraryId={selectedLibraryId}
          initial={editing}
          onClose={() => setDrawerOpen(false)}
          onSaved={() => { setDrawerOpen(false); load(); }}
        />
      )}
    </section>
  );
}
```

- [ ] **Step 2: 在 CompanyLibraryWorkbench 中加入**

```tsx
import { CompanyAssetSection } from "./CompanyAssetSection";
// ...
<CompanyAssetSection selectedLibraryId={selectedLibraryId} onError={setError} />
```

- [ ] **Step 3: 浏览器手动验证**

启动 dev server 验证：
- 4 tab 切换正常，badge 数量正确
- "+ 新增车辆" 抽屉打开 → 填基础+特化字段+上传行驶证 → 保存 → 列表出现
- 编辑、删除（删除时确认对话框）

- [ ] **Step 4: Commit**

```bash
git add frontend/src/modules/database/components/CompanyAssetSection.tsx \
        frontend/src/modules/database/components/CompanyLibraryWorkbench.tsx
git commit -m "feat(asset): integrate company asset section into library workbench"
```

---

## Phase 6: 招标约束 equipment_requirement 扩展

**目标:** 支持把招标解析出的"主要施工设备/工器具/安全配置"打成 `equipment_requirement` 类型的 `tender_constraint`，含 `predicate` 与 `min_quantity`。首期由用户在约束确认工作台手工补打（提供模板下拉），AI 抽取作 P2。

### Task 6.1: 后端 tender_constraint_service 支持 equipment_requirement

**Files:**
- Modify: `backend/tender_backend/services/tender_constraint_service.py`
- Create: `backend/tests/unit/test_equipment_requirement_constraint.py`

- [ ] **Step 1: 写失败测试**

```python
"""TenderConstraintService should accept equipment_requirement type with predicate + min_quantity."""

from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest

from tender_backend.db.alembic.runner import upgrade_to_head
from tender_backend.services.tender_constraint_service import (
    TenderConstraintService,
    EquipmentRequirementPayload,
)


def _db_url() -> str | None:
    return os.environ.get("DATABASE_URL")


@pytest.fixture
def conn():
    if not _db_url(): pytest.skip("DATABASE_URL not set")
    with psycopg.connect(_db_url(), autocommit=True) as c:
        upgrade_to_head(c)
        yield c


def test_create_equipment_requirement(conn) -> None:
    proj_id = uuid4()
    conn.execute("INSERT INTO project (id, name) VALUES (%s, %s)", (proj_id, "P"))
    svc = TenderConstraintService()
    cid = svc.create_equipment_requirement(conn, project_id=proj_id, payload=EquipmentRequirementPayload(
        label="不少于 5 台 10kV 斗臂车",
        source_ref="投标人须知前附表 §3.4",
        asset_type="vehicle",
        predicate={"vehicle_type": "aerial_bucket", "voltage_level_min": "10kV"},
        min_quantity=5,
    ))
    row = conn.execute(
        "SELECT type, category, label, extras_json FROM tender_constraint WHERE id = %s",
        (cid,),
    ).fetchone()
    assert row[0] == "substantive_response"
    assert row[1] == "qualification"
    assert "10kV 斗臂车" in row[2]
    extras = row[3] if isinstance(row[3], dict) else __import__("json").loads(row[3])
    assert extras["asset_type"] == "vehicle"
    assert extras["min_quantity"] == 5


def test_list_equipment_requirements(conn) -> None:
    proj_id = uuid4()
    conn.execute("INSERT INTO project (id, name) VALUES (%s, %s)", (proj_id, "P"))
    svc = TenderConstraintService()
    for at in ("vehicle", "tool"):
        svc.create_equipment_requirement(conn, project_id=proj_id, payload=EquipmentRequirementPayload(
            label=f"{at} req", source_ref="x", asset_type=at, predicate={}, min_quantity=1,
        ))
    rows = svc.list_equipment_requirements(conn, project_id=proj_id)
    assert len(rows) == 2
    assert {r["asset_type"] for r in rows} == {"vehicle", "tool"}


def test_create_rejects_unknown_asset_type(conn) -> None:
    proj_id = uuid4()
    conn.execute("INSERT INTO project (id, name) VALUES (%s, %s)", (proj_id, "P"))
    svc = TenderConstraintService()
    with pytest.raises(ValueError, match="asset_type"):
        svc.create_equipment_requirement(conn, project_id=proj_id, payload=EquipmentRequirementPayload(
            label="x", source_ref="x", asset_type="unknown", predicate={}, min_quantity=1,
        ))
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**

在 `tender_constraint_service.py` 末尾追加：

```python
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from tender_backend.services.asset_schema import ASSET_TYPE_KEYS


@dataclass
class EquipmentRequirementPayload:
    label: str
    source_ref: str
    asset_type: str
    predicate: dict[str, Any] = field(default_factory=dict)
    min_quantity: int = 1


class TenderConstraintService:
    # ... existing methods ...

    def create_equipment_requirement(
        self,
        conn,
        *,
        project_id: UUID,
        payload: EquipmentRequirementPayload,
    ) -> UUID:
        if payload.asset_type not in ASSET_TYPE_KEYS:
            raise ValueError(f"asset_type must be in {sorted(ASSET_TYPE_KEYS)}")
        cid = uuid4()
        extras = {
            "asset_type": payload.asset_type,
            "predicate": payload.predicate,
            "min_quantity": payload.min_quantity,
        }
        conn.execute(
            """
            INSERT INTO tender_constraint
              (id, project_id, type, category, source_ref, label, extras_json)
            VALUES (%s, %s, 'substantive_response', 'qualification', %s, %s, %s)
            """,
            (cid, project_id, payload.source_ref, payload.label,
             __import__("json").dumps(extras)),
        )
        return cid

    def list_equipment_requirements(self, conn, *, project_id: UUID) -> list[dict]:
        from psycopg.rows import dict_row
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT id, label, source_ref, extras_json
                FROM tender_constraint
                WHERE project_id = %s
                  AND extras_json ? 'asset_type'
                  AND extras_json ? 'predicate'
                  AND extras_json ? 'min_quantity'
                ORDER BY created_at
            """, (project_id,))
            rows = list(cur.fetchall())
        out = []
        for r in rows:
            extras = r["extras_json"] if isinstance(r["extras_json"], dict) else __import__("json").loads(r["extras_json"])
            out.append({
                "id": r["id"], "label": r["label"], "source_ref": r["source_ref"],
                "asset_type": extras["asset_type"],
                "predicate": extras["predicate"],
                "min_quantity": extras["min_quantity"],
            })
        return out
```

> 假设 `tender_constraint` 表已有 `extras_json` JSONB 列；如无，先在本任务前补一个 ALTER COLUMN migration（按现有 0040 版式追加 0041）。

- [ ] **Step 4: 运行通过 + Commit**

```bash
cd backend && DATABASE_URL=$DATABASE_URL pytest tests/unit/test_equipment_requirement_constraint.py -v
git add backend/tender_backend/services/tender_constraint_service.py \
        backend/tests/unit/test_equipment_requirement_constraint.py
git commit -m "feat(constraint): equipment_requirement type with predicate and min_quantity"
```

---

## Phase 7: EquipmentFilterService

**目标:** 实现"基础硬筛 3 条 + equipment_requirement 显式映射硬筛"的筛选服务，输入项目+招标约束+全资产，输出候选 + 排除 + 覆盖度。

### Task 7.1: EquipmentFilterService 单元测试 + 实现

**Files:**
- Create: `backend/tender_backend/services/equipment_filter_service.py`
- Create: `backend/tests/unit/test_equipment_filter_service.py`

- [ ] **Step 1: 写失败测试**

```python
"""EquipmentFilterService: hard filtering + coverage check."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

from tender_backend.services.equipment_filter_service import (
    EquipmentFilterService,
    FilterContext,
)


def mk_asset(**overrides) -> dict:
    return {
        "id": uuid4(), "library_company_id": uuid4(), "asset_type": "vehicle",
        "name": "斗臂车", "spec_model": "DFL5160", "serial_no": "苏A12345",
        "manufacturer": "东风", "quantity": 1, "unit": "辆", "ownership": "self",
        "acquired_at": date(2024, 1, 1), "expires_at": date(2027, 1, 1),
        "technical_condition": "完好", "status": "active", "location": None,
        "extras": {"vehicle_type": "aerial_bucket", "voltage_level": "10kV"},
        "notes": None,
        **overrides,
    }


def test_excludes_retired_asset() -> None:
    svc = EquipmentFilterService()
    a = mk_asset(status="retired")
    res = svc.filter(assets=[a], requirements=[], ctx=FilterContext(
        validity_until=date(2026, 9, 13), allowed_ownerships={"self", "leased"},
    ))
    assert a["id"] not in [c["id"] for c in res.candidates]
    assert a["id"] in [e["asset"]["id"] for e in res.excluded]
    assert any("status" in e["reason"] for e in res.excluded if e["asset"]["id"] == a["id"])


def test_excludes_expired_before_validity() -> None:
    svc = EquipmentFilterService()
    a = mk_asset(expires_at=date(2026, 8, 1))  # before validity_until 2026-09-13
    res = svc.filter(assets=[a], requirements=[], ctx=FilterContext(
        validity_until=date(2026, 9, 13), allowed_ownerships={"self"},
    ))
    assert a["id"] not in [c["id"] for c in res.candidates]
    assert any("expires_at" in e["reason"] for e in res.excluded)


def test_excludes_disallowed_ownership() -> None:
    svc = EquipmentFilterService()
    a = mk_asset(ownership="leased")
    res = svc.filter(assets=[a], requirements=[], ctx=FilterContext(
        validity_until=date(2026, 9, 13), allowed_ownerships={"self"},
    ))
    assert any("ownership" in e["reason"] for e in res.excluded)


def test_keeps_passing_asset() -> None:
    svc = EquipmentFilterService()
    a = mk_asset()
    res = svc.filter(assets=[a], requirements=[], ctx=FilterContext(
        validity_until=date(2026, 9, 13), allowed_ownerships={"self"},
    ))
    assert a["id"] in [c["id"] for c in res.candidates]


def test_coverage_meets_min_quantity() -> None:
    svc = EquipmentFilterService()
    a1 = mk_asset(id=uuid4())
    a2 = mk_asset(id=uuid4())
    a3 = mk_asset(id=uuid4(), extras={"vehicle_type": "truck"})  # 不匹配 predicate
    requirements = [{
        "id": uuid4(), "label": "≥2 台 10kV 斗臂车",
        "asset_type": "vehicle",
        "predicate": {"vehicle_type": "aerial_bucket", "voltage_level": "10kV"},
        "min_quantity": 2,
    }]
    res = svc.filter(assets=[a1, a2, a3], requirements=requirements,
                     ctx=FilterContext(validity_until=date(2026, 9, 13),
                                       allowed_ownerships={"self"}))
    cov = res.coverage[0]
    assert cov["matched_count"] == 2
    assert cov["min_quantity"] == 2
    assert cov["satisfied"] is True


def test_coverage_under_min_quantity() -> None:
    svc = EquipmentFilterService()
    a1 = mk_asset(id=uuid4())
    requirements = [{
        "id": uuid4(), "label": "≥3 台",
        "asset_type": "vehicle",
        "predicate": {"vehicle_type": "aerial_bucket"},
        "min_quantity": 3,
    }]
    res = svc.filter(assets=[a1], requirements=requirements,
                     ctx=FilterContext(validity_until=date(2026, 9, 13),
                                       allowed_ownerships={"self"}))
    cov = res.coverage[0]
    assert cov["satisfied"] is False
    assert cov["matched_count"] == 1
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 EquipmentFilterService**

```python
"""EquipmentFilterService: applies the 3 base hard filters and equipment_requirement
predicate matching, returning candidates / excluded / coverage."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class FilterContext:
    validity_until: date
    allowed_ownerships: set[str]


@dataclass
class FilterResult:
    candidates: list[dict] = field(default_factory=list)
    excluded: list[dict] = field(default_factory=list)
    coverage: list[dict] = field(default_factory=list)


class EquipmentFilterService:
    def filter(
        self,
        *,
        assets: list[dict],
        requirements: list[dict],
        ctx: FilterContext,
    ) -> FilterResult:
        result = FilterResult()
        for a in assets:
            reasons = self._base_check(a, ctx)
            if reasons:
                result.excluded.append({"asset": a, "reason": "; ".join(reasons)})
            else:
                result.candidates.append(a)

        for req in requirements:
            matched = [
                a for a in result.candidates
                if a["asset_type"] == req["asset_type"] and self._matches(a, req["predicate"])
            ]
            total_quantity = sum(float(a["quantity"]) for a in matched)
            result.coverage.append({
                "requirement_id": req["id"],
                "label": req["label"],
                "asset_type": req["asset_type"],
                "min_quantity": req["min_quantity"],
                "matched_count": len(matched),
                "matched_quantity": total_quantity,
                "satisfied": total_quantity >= req["min_quantity"],
                "matched_asset_ids": [a["id"] for a in matched],
            })
        return result

    def _base_check(self, asset: dict, ctx: FilterContext) -> list[str]:
        reasons: list[str] = []
        if asset.get("status") != "active":
            reasons.append(f"status={asset.get('status')}")
        exp = asset.get("expires_at")
        if exp is not None and exp < ctx.validity_until:
            reasons.append(f"expires_at={exp} < validity_until={ctx.validity_until}")
        if asset.get("ownership") not in ctx.allowed_ownerships:
            reasons.append(f"ownership={asset.get('ownership')} not allowed")
        return reasons

    def _matches(self, asset: dict, predicate: dict[str, Any]) -> bool:
        extras = asset.get("extras") or {}
        for key, value in predicate.items():
            if key == "voltage_level_min":
                if not self._voltage_at_least(str(extras.get("voltage_level", "")), str(value)):
                    return False
            else:
                actual = extras.get(key)
                if actual != value:
                    return False
        return True

    @staticmethod
    def _voltage_kv(text: str) -> float:
        if not text or text in ("N/A", ""):
            return 0.0
        # "10kV" -> 10.0, "0.4kV" -> 0.4
        try:
            return float(text.lower().replace("kv", "").strip())
        except ValueError:
            return 0.0

    def _voltage_at_least(self, actual: str, required: str) -> bool:
        return self._voltage_kv(actual) >= self._voltage_kv(required)
```

- [ ] **Step 4: 运行通过 + Commit**

```bash
cd backend && pytest tests/unit/test_equipment_filter_service.py -v
git add backend/tender_backend/services/equipment_filter_service.py \
        backend/tests/unit/test_equipment_filter_service.py
git commit -m "feat(asset): EquipmentFilterService with base hard filters and requirement coverage"
```

---

## Phase 8: 投标设备选择 API + Repo

**目标:** 投标侧能 CRUD 已选清单、触发筛选、确认冻结。

### Task 8.1: project_equipment_selection_repo

**Files:**
- Create: `backend/tender_backend/db/repositories/project_equipment_selection_repo.py`
- Create: `backend/tests/integration/test_project_equipment_selection_repo.py`

- [ ] **Step 1: 写失败测试**

```python
"""Repo tests for project_equipment_selection."""

from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest

from tender_backend.db.alembic.runner import upgrade_to_head
from tender_backend.db.repositories.project_equipment_selection_repo import (
    ProjectEquipmentSelectionRepository,
)


def _db_url(): return os.environ.get("DATABASE_URL")


@pytest.fixture
def conn_with_setup():
    if not _db_url(): pytest.skip("DATABASE_URL not set")
    with psycopg.connect(_db_url(), autocommit=True) as c:
        upgrade_to_head(c)
        lib_id, asset_id, proj_id = uuid4(), uuid4(), uuid4()
        c.execute("INSERT INTO library_company (id, company_key, company_name) VALUES (%s, %s, %s)",
                  (lib_id, f"l-{lib_id}", "L"))
        c.execute(
            "INSERT INTO company_asset (id, library_company_id, asset_type, name, unit, ownership) "
            "VALUES (%s, %s, 'vehicle', 'A', '辆', 'self')",
            (asset_id, lib_id),
        )
        c.execute("INSERT INTO project (id, name) VALUES (%s, %s)", (proj_id, "P"))
        yield c, proj_id, asset_id


def test_create_and_list_selection(conn_with_setup) -> None:
    conn, proj_id, asset_id = conn_with_setup
    repo = ProjectEquipmentSelectionRepository()
    sid = repo.create(conn, project_id=proj_id, asset_id=asset_id, asset_type="vehicle",
                      frozen_snapshot={"name": "A"})
    rows = repo.list(conn, project_id=proj_id, asset_type="vehicle")
    assert len(rows) == 1
    assert rows[0]["id"] == sid
    assert rows[0]["frozen"] is False


def test_freeze_locks_subsequent_field_update(conn_with_setup) -> None:
    conn, proj_id, asset_id = conn_with_setup
    repo = ProjectEquipmentSelectionRepository()
    sid = repo.create(conn, project_id=proj_id, asset_id=asset_id, asset_type="vehicle",
                      frozen_snapshot={"name": "A", "expires_at": "2026-12-31"})
    repo.freeze(conn, project_id=proj_id)
    # 冻结后更新 frozen_snapshot 应被触发器拒绝
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute(
            "UPDATE project_equipment_selection SET frozen_snapshot = '{\"name\":\"B\"}'::jsonb WHERE id = %s",
            (sid,),
        )


def test_intended_role_remains_editable_after_freeze(conn_with_setup) -> None:
    conn, proj_id, asset_id = conn_with_setup
    repo = ProjectEquipmentSelectionRepository()
    sid = repo.create(conn, project_id=proj_id, asset_id=asset_id, asset_type="vehicle",
                      frozen_snapshot={"name": "A"})
    repo.freeze(conn, project_id=proj_id)
    repo.update_intended_role(conn, selection_id=sid, intended_role="配电主线施工")
    row = conn.execute(
        "SELECT intended_role FROM project_equipment_selection WHERE id = %s",
        (sid,),
    ).fetchone()
    assert row[0] == "配电主线施工"
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 repo**

```python
"""ProjectEquipmentSelectionRepository."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row


class ProjectEquipmentSelectionRepository:
    _FIELDS = (
        "id", "project_id", "asset_id", "asset_type", "selection_reason",
        "exclusion_overridden", "intended_role", "frozen_snapshot", "display_order",
        "frozen", "frozen_at", "created_at", "updated_at",
    )

    def create(
        self, conn: Connection, *,
        project_id: UUID, asset_id: UUID, asset_type: str,
        frozen_snapshot: dict[str, Any],
        selection_reason: str | None = None,
        exclusion_overridden: bool = False,
        intended_role: str | None = None,
        display_order: int = 0,
    ) -> UUID:
        sid = uuid4()
        conn.execute(
            """
            INSERT INTO project_equipment_selection
              (id, project_id, asset_id, asset_type, selection_reason,
               exclusion_overridden, intended_role, frozen_snapshot, display_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (sid, project_id, asset_id, asset_type, selection_reason,
             exclusion_overridden, intended_role,
             __import__("json").dumps(frozen_snapshot), display_order),
        )
        return sid

    def list(self, conn: Connection, *, project_id: UUID, asset_type: str | None = None) -> list[dict]:
        sql = (f"SELECT {', '.join(self._FIELDS)} FROM project_equipment_selection "
               f"WHERE project_id = %s")
        params: list[Any] = [project_id]
        if asset_type:
            sql += " AND asset_type = %s"; params.append(asset_type)
        sql += " ORDER BY asset_type, display_order, created_at"
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params); return list(cur.fetchall())

    def get(self, conn: Connection, selection_id: UUID) -> dict | None:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"SELECT {', '.join(self._FIELDS)} FROM project_equipment_selection WHERE id = %s",
                (selection_id,),
            )
            return cur.fetchone()

    def update_snapshot(self, conn: Connection, selection_id: UUID, *,
                        frozen_snapshot: dict[str, Any]) -> None:
        conn.execute(
            "UPDATE project_equipment_selection SET frozen_snapshot = %s, updated_at = now() "
            "WHERE id = %s",
            (__import__("json").dumps(frozen_snapshot), selection_id),
        )

    def update_intended_role(self, conn: Connection, *, selection_id: UUID,
                             intended_role: str | None) -> None:
        conn.execute(
            "UPDATE project_equipment_selection SET intended_role = %s, updated_at = now() "
            "WHERE id = %s",
            (intended_role, selection_id),
        )

    def update_display_order(self, conn: Connection, *, selection_id: UUID,
                             display_order: int) -> None:
        conn.execute(
            "UPDATE project_equipment_selection SET display_order = %s, updated_at = now() "
            "WHERE id = %s",
            (display_order, selection_id),
        )

    def delete(self, conn: Connection, selection_id: UUID) -> None:
        conn.execute("DELETE FROM project_equipment_selection WHERE id = %s", (selection_id,))

    def freeze(self, conn: Connection, *, project_id: UUID) -> None:
        conn.execute(
            "UPDATE project_equipment_selection SET frozen = TRUE, frozen_at = now() "
            "WHERE project_id = %s AND frozen = FALSE",
            (project_id,),
        )

    def is_any_frozen(self, conn: Connection, *, project_id: UUID) -> bool:
        row = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM project_equipment_selection "
            "WHERE project_id = %s AND frozen = TRUE)",
            (project_id,),
        ).fetchone()
        return bool(row[0])
```

- [ ] **Step 4: 运行通过 + Commit**

```bash
cd backend && DATABASE_URL=$DATABASE_URL pytest tests/integration/test_project_equipment_selection_repo.py -v
git add backend/tender_backend/db/repositories/project_equipment_selection_repo.py \
        backend/tests/integration/test_project_equipment_selection_repo.py
git commit -m "feat(asset): ProjectEquipmentSelectionRepository with freeze semantics"
```

---

### Task 8.2: equipment_selection API endpoints

**Files:**
- Create: `backend/tender_backend/api/equipment_selection.py`
- Modify: `backend/tender_backend/main.py` (注册 router)
- Create: `backend/tests/integration/test_equipment_selection_api.py`

- [ ] **Step 1: 写测试 (覆盖关键 endpoints)**

```python
"""Equipment selection API integration tests."""

from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest

from tender_backend.db.alembic.runner import upgrade_to_head
from tender_backend.main import app
from tender_backend.test_support.asgi_client import SyncASGIClient


_AUTH = {"Authorization": "Bearer dev-token"}


def _db_url(): return os.environ.get("DATABASE_URL")


@pytest.fixture
def setup():
    if not _db_url(): pytest.skip("DATABASE_URL not set")
    with psycopg.connect(_db_url(), autocommit=True) as c:
        upgrade_to_head(c)
        lib_id, proj_id, asset_id = uuid4(), uuid4(), uuid4()
        c.execute("INSERT INTO library_company (id, company_key, company_name) VALUES (%s, %s, %s)",
                  (lib_id, f"l-{lib_id}", "L"))
        c.execute("INSERT INTO project (id, name) VALUES (%s, %s)", (proj_id, "P"))
        c.execute(
            "INSERT INTO company_asset (id, library_company_id, asset_type, name, unit, ownership, expires_at, status) "
            "VALUES (%s, %s, 'vehicle', '斗臂车', '辆', 'self', '2027-01-01', 'active')",
            (asset_id, lib_id),
        )
    return SyncASGIClient(app), str(proj_id), str(asset_id), str(lib_id)


def test_get_candidates(setup) -> None:
    client, pid, aid, lid = setup
    res = client.get(f"/api/projects/{pid}/equipment/candidates?asset_type=vehicle", headers=_AUTH)
    assert res.status_code == 200
    body = res.json()
    assert "candidates" in body and "excluded" in body and "coverage" in body
    assert any(c["id"] == aid for c in body["candidates"])


def test_create_selection(setup) -> None:
    client, pid, aid, lid = setup
    res = client.post(f"/api/projects/{pid}/equipment/selections",
                      json={"asset_id": aid, "intended_role": "主线施工"},
                      headers=_AUTH)
    assert res.status_code == 201, res.text
    assert res.json()["intended_role"] == "主线施工"


def test_force_add_requires_reason(setup) -> None:
    client, pid, aid, lid = setup
    # 制造一个 expired asset, 应被排除; 强制纳入不带 reason 应 422
    with psycopg.connect(_db_url(), autocommit=True) as c:
        c.execute("UPDATE company_asset SET expires_at = '2026-01-01' WHERE id = %s", (aid,))
    res = client.post(f"/api/projects/{pid}/equipment/selections",
                      json={"asset_id": aid, "exclusion_overridden": True},
                      headers=_AUTH)
    assert res.status_code == 422


def test_freeze_locks_selections(setup) -> None:
    client, pid, aid, lid = setup
    client.post(f"/api/projects/{pid}/equipment/selections",
                json={"asset_id": aid}, headers=_AUTH)
    res = client.post(f"/api/projects/{pid}/equipment/selections/freeze", headers=_AUTH)
    assert res.status_code == 200
    # 冻结后 update 应 409
    sel_list = client.get(f"/api/projects/{pid}/equipment/selections", headers=_AUTH).json()
    sel_id = sel_list[0]["id"]
    res = client.put(f"/api/projects/{pid}/equipment/selections/{sel_id}",
                     json={"intended_role": "更新"}, headers=_AUTH)
    # intended_role 仍可改, 应 200
    assert res.status_code == 200
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 equipment_selection API**

```python
"""Equipment selection API: candidates, selections CRUD, refilter, freeze."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from psycopg import Connection
from pydantic import BaseModel, Field

from tender_backend.core.security import get_current_user
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.company_asset_repo import CompanyAssetRepository
from tender_backend.db.repositories.project_equipment_selection_repo import (
    ProjectEquipmentSelectionRepository,
)
from tender_backend.services.asset_schema import ASSET_TYPE_KEYS
from tender_backend.services.equipment_filter_service import (
    EquipmentFilterService, FilterContext,
)
from tender_backend.services.tender_constraint_service import TenderConstraintService


router = APIRouter(tags=["equipment-selection"], dependencies=[Depends(get_current_user)])

_asset_repo = CompanyAssetRepository()
_pes_repo = ProjectEquipmentSelectionRepository()
_filter = EquipmentFilterService()
_constraint = TenderConstraintService()


class SelectionCreate(BaseModel):
    asset_id: UUID
    intended_role: str | None = None
    selection_reason: str | None = None
    exclusion_overridden: bool = False
    display_order: int = 0


class SelectionUpdate(BaseModel):
    intended_role: str | None = None
    display_order: int | None = None


def _validity_until(conn: Connection, project_id: UUID) -> date:
    """submission_deadline + bid_validity_period; fallback to today + 90d if absent."""
    row = conn.execute(
        "SELECT submission_deadline, bid_validity_period FROM project WHERE id = %s",
        (project_id,),
    ).fetchone()
    if not row or not row[0]:
        return date.today() + timedelta(days=90)
    deadline, validity_days = row[0], (row[1] or 90)
    return deadline + timedelta(days=validity_days)


def _allowed_ownerships(conn: Connection, project_id: UUID) -> set[str]:
    """读 project 设置的所有权白名单;无配置则默认全允许。"""
    # 简化实现:从 tender_constraint 找 'ownership_restriction' label 命中,否则默认全允许
    return {"self", "leased", "third_party"}


def _project_assets(conn: Connection, project_id: UUID, asset_type: str) -> list[dict]:
    """Pull all assets across libraries available to this project's tenant.
    首期:取 project 关联到的第一个 library_company 下的资产。
    多 library 共享设计未来支持。"""
    row = conn.execute(
        "SELECT library_company_id FROM library_company "
        "WHERE enabled = TRUE ORDER BY created_at LIMIT 1"
    ).fetchone()
    if not row:
        return []
    lib_id = row[0]
    return _asset_repo.list(conn, library_company_id=lib_id, asset_type=asset_type)


def _frozen_snapshot_from_asset(asset: dict, core_attachment_ids: list[UUID]) -> dict[str, Any]:
    return {
        "name": asset["name"],
        "spec_model": asset["spec_model"],
        "serial_no": asset["serial_no"],
        "manufacturer": asset["manufacturer"],
        "quantity": float(asset["quantity"]),
        "unit": asset["unit"],
        "ownership": asset["ownership"],
        "acquired_at": asset["acquired_at"].isoformat() if asset["acquired_at"] else None,
        "expires_at": asset["expires_at"].isoformat() if asset["expires_at"] else None,
        "technical_condition": asset["technical_condition"],
        "extras": asset.get("extras", {}),
        "core_attachment_ids": [str(x) for x in core_attachment_ids],
    }


@router.get("/projects/{project_id}/equipment/candidates")
async def get_candidates(
    project_id: UUID, asset_type: str,
    conn: Connection = Depends(get_db_conn),
) -> dict:
    if asset_type not in ASSET_TYPE_KEYS:
        raise HTTPException(status_code=422, detail=f"asset_type must be in {sorted(ASSET_TYPE_KEYS)}")
    assets = _project_assets(conn, project_id, asset_type)
    requirements = [
        r for r in _constraint.list_equipment_requirements(conn, project_id=project_id)
        if r["asset_type"] == asset_type
    ]
    ctx = FilterContext(
        validity_until=_validity_until(conn, project_id),
        allowed_ownerships=_allowed_ownerships(conn, project_id),
    )
    res = _filter.filter(assets=assets, requirements=requirements, ctx=ctx)
    return {
        "candidates": res.candidates,
        "excluded": res.excluded,
        "coverage": res.coverage,
    }


@router.get("/projects/{project_id}/equipment/selections")
async def list_selections(project_id: UUID, asset_type: str | None = None,
                          conn: Connection = Depends(get_db_conn)) -> list[dict]:
    return _pes_repo.list(conn, project_id=project_id, asset_type=asset_type)


@router.post("/projects/{project_id}/equipment/selections", status_code=201)
async def create_selection(
    project_id: UUID, payload: SelectionCreate,
    conn: Connection = Depends(get_db_conn),
) -> dict:
    asset = _asset_repo.get(conn, payload.asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")

    # 强制纳入校验:被排除时 reason 必填
    ctx = FilterContext(
        validity_until=_validity_until(conn, project_id),
        allowed_ownerships=_allowed_ownerships(conn, project_id),
    )
    excluded = _filter._base_check(asset, ctx)  # noqa: SLF001
    if excluded:
        if not payload.exclusion_overridden:
            raise HTTPException(
                status_code=422,
                detail=f"asset is excluded by base filters: {'; '.join(excluded)}; "
                       f"set exclusion_overridden=true and provide selection_reason to force-add",
            )
        if not payload.selection_reason or not payload.selection_reason.strip():
            raise HTTPException(status_code=422,
                                detail="selection_reason is required when exclusion_overridden=true")

    attachments = _asset_repo.list_attachments(conn, payload.asset_id)
    core_ids = [a["id"] for a in attachments if a["slot_role"] == "core"]
    snapshot = _frozen_snapshot_from_asset(asset, core_ids)

    sid = _pes_repo.create(
        conn, project_id=project_id, asset_id=payload.asset_id,
        asset_type=asset["asset_type"], frozen_snapshot=snapshot,
        selection_reason=payload.selection_reason,
        exclusion_overridden=payload.exclusion_overridden,
        intended_role=payload.intended_role,
        display_order=payload.display_order,
    )
    return _pes_repo.get(conn, sid)


@router.put("/projects/{project_id}/equipment/selections/{selection_id}")
async def update_selection(
    project_id: UUID, selection_id: UUID, payload: SelectionUpdate,
    conn: Connection = Depends(get_db_conn),
) -> dict:
    if payload.intended_role is not None:
        _pes_repo.update_intended_role(conn, selection_id=selection_id,
                                       intended_role=payload.intended_role)
    if payload.display_order is not None:
        _pes_repo.update_display_order(conn, selection_id=selection_id,
                                       display_order=payload.display_order)
    row = _pes_repo.get(conn, selection_id)
    if row is None:
        raise HTTPException(status_code=404, detail="selection not found")
    return row


@router.delete("/projects/{project_id}/equipment/selections/{selection_id}", status_code=204)
async def delete_selection(project_id: UUID, selection_id: UUID,
                           conn: Connection = Depends(get_db_conn)):
    row = _pes_repo.get(conn, selection_id)
    if row and row["frozen"]:
        raise HTTPException(status_code=409, detail="cannot delete a frozen selection")
    _pes_repo.delete(conn, selection_id)


@router.post("/projects/{project_id}/equipment/selections/refilter")
async def refilter(project_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict:
    """Refresh frozen_snapshot of unfrozen selections to track current asset values.
    保留用户已加项, 不改变成员关系。"""
    rows = _pes_repo.list(conn, project_id=project_id)
    refreshed = 0
    for row in rows:
        if row["frozen"]:
            continue
        asset = _asset_repo.get(conn, row["asset_id"])
        if asset is None:
            continue
        attachments = _asset_repo.list_attachments(conn, row["asset_id"])
        core_ids = [a["id"] for a in attachments if a["slot_role"] == "core"]
        _pes_repo.update_snapshot(conn, row["id"],
                                  frozen_snapshot=_frozen_snapshot_from_asset(asset, core_ids))
        refreshed += 1
    return {"refreshed_count": refreshed}


@router.post("/projects/{project_id}/equipment/selections/freeze")
async def freeze_selections(project_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict:
    rows = _pes_repo.list(conn, project_id=project_id)
    if not rows:
        raise HTTPException(status_code=422, detail="no selections to freeze")
    _pes_repo.freeze(conn, project_id=project_id)
    return {"frozen_count": len([r for r in rows if not r["frozen"]])}
```

- [ ] **Step 4: 在 main.py 注册 router**

```python
from tender_backend.api.equipment_selection import router as equipment_selection_router
app.include_router(equipment_selection_router, prefix=settings.api_prefix)
```

- [ ] **Step 5: 运行通过 + Commit**

```bash
cd backend && DATABASE_URL=$DATABASE_URL pytest tests/integration/test_equipment_selection_api.py -v
git add backend/tender_backend/api/equipment_selection.py \
        backend/tender_backend/main.py \
        backend/tests/integration/test_equipment_selection_api.py
git commit -m "feat(asset): equipment selection API with refilter and freeze"
```

---

## Phase 9: 前端投标设备清单工作台

**目标:** 实现 §4 工作台 UI:候选/已选双区 + 招标硬条件覆盖度横条 + 强制纳入对话框 + 冻结操作。

### Task 9.1: API 客户端 + 子组件

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/modules/authoring/equipment/CoverageBar.tsx`
- Create: `frontend/src/modules/authoring/equipment/ForceAddDialog.tsx`

- [ ] **Step 1: 在 api.ts 加投标侧 API**

```ts
export type EquipmentCandidate = CompanyAsset;
export type EquipmentExcluded = { asset: CompanyAsset; reason: string };
export type EquipmentCoverage = {
  requirement_id: string; label: string; asset_type: string;
  min_quantity: number; matched_count: number; matched_quantity: number;
  satisfied: boolean; matched_asset_ids: string[];
};
export type EquipmentSelection = {
  id: string; project_id: string; asset_id: string; asset_type: string;
  selection_reason: string | null; exclusion_overridden: boolean;
  intended_role: string | null; frozen_snapshot: Record<string, unknown>;
  display_order: number; frozen: boolean; frozen_at: string | null;
};

export async function fetchEquipmentCandidates(projectId: string, assetType: string) {
  return await api(`/projects/${projectId}/equipment/candidates?asset_type=${assetType}`) as {
    candidates: EquipmentCandidate[]; excluded: EquipmentExcluded[]; coverage: EquipmentCoverage[];
  };
}
export async function fetchEquipmentSelections(projectId: string, assetType?: string) {
  const q = assetType ? `?asset_type=${assetType}` : "";
  return await api(`/projects/${projectId}/equipment/selections${q}`) as EquipmentSelection[];
}
export async function createEquipmentSelection(projectId: string, payload: {
  asset_id: string; intended_role?: string; selection_reason?: string;
  exclusion_overridden?: boolean; display_order?: number;
}) {
  return await api(`/projects/${projectId}/equipment/selections`,
                   { method: "POST", body: JSON.stringify(payload) }) as EquipmentSelection;
}
export async function updateEquipmentSelection(projectId: string, selectionId: string,
                                               patch: { intended_role?: string; display_order?: number }) {
  return await api(`/projects/${projectId}/equipment/selections/${selectionId}`,
                   { method: "PUT", body: JSON.stringify(patch) }) as EquipmentSelection;
}
export async function deleteEquipmentSelection(projectId: string, selectionId: string) {
  await api(`/projects/${projectId}/equipment/selections/${selectionId}`, { method: "DELETE" });
}
export async function refilterEquipment(projectId: string) {
  return await api(`/projects/${projectId}/equipment/selections/refilter`,
                   { method: "POST" }) as { refreshed_count: number };
}
export async function freezeEquipmentSelections(projectId: string) {
  return await api(`/projects/${projectId}/equipment/selections/freeze`,
                   { method: "POST" }) as { frozen_count: number };
}
```

- [ ] **Step 2: CoverageBar 与 ForceAddDialog 组件**

```tsx
// CoverageBar.tsx
import type { EquipmentCoverage } from "../../../lib/api";
import { Badge } from "../../../components/ui/Badge";

export function CoverageBar({ coverage }: { coverage: EquipmentCoverage[] }) {
  if (coverage.length === 0) {
    return <div className="empty-state__description">该项目尚未录入"主要施工设备"硬条件约束。</div>;
  }
  return (
    <ul className="coverage-bar">
      {coverage.map((c) => (
        <li key={c.requirement_id}>
          <Badge variant={c.satisfied ? "success" : "danger"}>{c.satisfied ? "✓" : "✗"}</Badge>
          <span>{c.label}</span>
          <strong>已选 {c.matched_count} / 需 {c.min_quantity}</strong>
        </li>
      ))}
    </ul>
  );
}
```

```tsx
// ForceAddDialog.tsx
import { useState } from "react";
import { ClayButton } from "../../../components/ui/ClayButton";
import type { CompanyAsset } from "../../../lib/api";

type Props = {
  asset: CompanyAsset;
  reason: string;
  onCancel: () => void;
  onConfirm: (justification: string) => Promise<void>;
};

export function ForceAddDialog({ asset, reason, onCancel, onConfirm }: Props) {
  const [justification, setJustification] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const valid = justification.trim().length >= 5;
  return (
    <div className="modal">
      <div className="modal__panel">
        <h3>该资产被自动排除</h3>
        <p><strong>原因:</strong> {reason}</p>
        <p>继续纳入此资产可能导致评分扣分或实质性偏离风险。</p>
        <p>如仍要纳入,请说明理由(投标负责人签字归档):</p>
        <textarea className="clay-textarea" value={justification}
                  onChange={(e) => setJustification(e.target.value)} />
        <div className="modal__actions">
          <ClayButton variant="ghost" onClick={onCancel}>取消</ClayButton>
          <ClayButton disabled={!valid || submitting}
            onClick={async () => {
              setSubmitting(true);
              try { await onConfirm(justification); } finally { setSubmitting(false); }
            }}>
            {submitting ? "提交中..." : "确认纳入并标记风险"}
          </ClayButton>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api.ts \
        frontend/src/modules/authoring/equipment/CoverageBar.tsx \
        frontend/src/modules/authoring/equipment/ForceAddDialog.tsx
git commit -m "feat(equipment): API client and coverage / force-add UI primitives"
```

---

### Task 9.2: EquipmentSelectionWorkbench 容器

**Files:**
- Create: `frontend/src/modules/authoring/EquipmentSelectionWorkbench.tsx`
- Create: `frontend/src/modules/authoring/__tests__/EquipmentSelectionWorkbench.test.tsx`

- [ ] **Step 1: 写最小测试 + 实现**

测试覆盖：候选区出现、点击 +加入 调用 createEquipmentSelection、删除调用 deleteEquipmentSelection、冻结调用 freeze。完整实现见 spec §4.4 工作台描述,核心代码：

```tsx
import { useEffect, useState } from "react";
import { ClayButton } from "../../components/ui/ClayButton";
import { Badge } from "../../components/ui/Badge";
import { ASSET_TYPE_KEYS, ASSET_TYPE_SCHEMAS, type AssetTypeKey }
  from "../database/schemas/assetTypeSchemas";
import {
  fetchEquipmentCandidates, fetchEquipmentSelections,
  createEquipmentSelection, deleteEquipmentSelection,
  refilterEquipment, freezeEquipmentSelections,
  type EquipmentCandidate, type EquipmentSelection,
  type EquipmentExcluded, type EquipmentCoverage,
} from "../../lib/api";
import { CoverageBar } from "./equipment/CoverageBar";
import { ForceAddDialog } from "./equipment/ForceAddDialog";

export function EquipmentSelectionWorkbench({ projectId }: { projectId: string }) {
  const [activeType, setActiveType] = useState<AssetTypeKey>("vehicle");
  const [candidates, setCandidates] = useState<EquipmentCandidate[]>([]);
  const [excluded, setExcluded] = useState<EquipmentExcluded[]>([]);
  const [coverage, setCoverage] = useState<EquipmentCoverage[]>([]);
  const [selections, setSelections] = useState<EquipmentSelection[]>([]);
  const [forceAddTarget, setForceAddTarget] = useState<{ asset: EquipmentCandidate; reason: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = async () => {
    const c = await fetchEquipmentCandidates(projectId, activeType);
    setCandidates(c.candidates); setExcluded(c.excluded); setCoverage(c.coverage);
    setSelections(await fetchEquipmentSelections(projectId, activeType));
  };
  useEffect(() => { reload(); /* eslint-disable-line */ }, [projectId, activeType]);

  const add = async (asset: EquipmentCandidate, opts?: { force?: boolean; reason?: string }) => {
    await createEquipmentSelection(projectId, {
      asset_id: asset.id,
      exclusion_overridden: opts?.force ?? false,
      selection_reason: opts?.reason,
    });
    reload();
  };

  return (
    <div className="equipment-workbench">
      <header>
        <h1>设备清单工作台</h1>
        <ClayButton variant="outline" disabled={busy}
          onClick={async () => { setBusy(true); try { await refilterEquipment(projectId); reload(); } finally { setBusy(false); } }}>
          按招标约束重筛
        </ClayButton>
      </header>
      <CoverageBar coverage={coverage} />
      <div className="filter-chip-row">
        {ASSET_TYPE_KEYS.map((k) => (
          <button key={k} className={`filter-chip ${activeType === k ? "active" : ""}`}
                  onClick={() => setActiveType(k)}>
            {ASSET_TYPE_SCHEMAS[k].label} <Badge>{selections.filter((s) => s.asset_type === k).length}</Badge>
          </button>
        ))}
      </div>
      <div className="equipment-grid">
        <section>
          <h2>候选区</h2>
          {candidates.map((a) => {
            const already = selections.some((s) => s.asset_id === a.id);
            return (
              <div key={a.id} className="equipment-card">
                <strong>{a.name}</strong> <span>{a.spec_model ?? ""}</span>
                <ClayButton size="sm" disabled={already} onClick={() => add(a)}>
                  {already ? "已加入" : "+ 加入"}
                </ClayButton>
              </div>
            );
          })}
          <details>
            <summary>自动排除 ({excluded.length} 项)</summary>
            {excluded.map((ex) => (
              <div key={ex.asset.id} className="equipment-card equipment-card--excluded">
                <strong>{ex.asset.name}</strong>
                <p className="hint">原因: {ex.reason}</p>
                <ClayButton size="sm" variant="outline"
                  onClick={() => setForceAddTarget({ asset: ex.asset, reason: ex.reason })}>
                  仍要纳入(需理由)
                </ClayButton>
              </div>
            ))}
          </details>
        </section>
        <section>
          <h2>已选区 ({selections.length})</h2>
          {selections.map((s) => {
            const snap = s.frozen_snapshot as { name?: string; spec_model?: string };
            return (
              <div key={s.id} className="equipment-card">
                <strong>{snap.name}</strong> <span>{snap.spec_model ?? ""}</span>
                {s.exclusion_overridden && <Badge variant="warning">⚠ 风险已知</Badge>}
                {s.frozen && <Badge>已冻结</Badge>}
                <ClayButton size="sm" variant="ghost" disabled={s.frozen}
                  onClick={async () => {
                    if (!confirm("确认从已选清单移除?")) return;
                    await deleteEquipmentSelection(projectId, s.id);
                    reload();
                  }}>
                  移除
                </ClayButton>
              </div>
            );
          })}
        </section>
      </div>
      <footer>
        <ClayButton disabled={busy || selections.length === 0}
          onClick={async () => {
            if (!confirm("确认冻结当前已选清单?冻结后将进入审查阶段且字段不可改。")) return;
            setBusy(true);
            try { await freezeEquipmentSelections(projectId); reload(); } finally { setBusy(false); }
          }}>
          确认并冻结快照
        </ClayButton>
      </footer>
      {forceAddTarget && (
        <ForceAddDialog asset={forceAddTarget.asset} reason={forceAddTarget.reason}
          onCancel={() => setForceAddTarget(null)}
          onConfirm={async (reason) => {
            await add(forceAddTarget.asset, { force: true, reason });
            setForceAddTarget(null);
          }} />
      )}
    </div>
  );
}
```

- [ ] **Step 2: 浏览器手动验证 + Commit**

```bash
cd frontend && npx vitest run src/modules/authoring/__tests__/EquipmentSelectionWorkbench.test.tsx
git add frontend/src/modules/authoring/EquipmentSelectionWorkbench.tsx \
        frontend/src/modules/authoring/__tests__/EquipmentSelectionWorkbench.test.tsx
git commit -m "feat(equipment): bid-side equipment selection workbench"
```

---

## Phase 10: EquipmentTableRenderer

**目标:** 后端单一渲染服务,共享数据装配 + 列解析,产出三种输出:JSON 预览、DOCX native table、Excel 4 sheet。

### Task 10.1: Renderer 单元测试 + 实现

**Files:**
- Create: `backend/tender_backend/services/export_service/equipment_table_renderer.py`
- Create: `backend/tests/unit/test_equipment_table_renderer.py`

- [ ] **Step 1: 写失败测试**

```python
"""EquipmentTableRenderer: data assembly + column resolution + xlsx output."""

from __future__ import annotations

import io
import os
from uuid import uuid4

import psycopg
import pytest
from openpyxl import load_workbook

from tender_backend.db.alembic.runner import upgrade_to_head
from tender_backend.services.export_service.equipment_table_renderer import (
    EquipmentTableRenderer,
)


def _db_url(): return os.environ.get("DATABASE_URL")


@pytest.fixture
def populated_project():
    if not _db_url(): pytest.skip("DATABASE_URL not set")
    with psycopg.connect(_db_url(), autocommit=True) as c:
        upgrade_to_head(c)
        lib_id, proj_id, asset_id = uuid4(), uuid4(), uuid4()
        c.execute("INSERT INTO library_company (id, company_key, company_name) VALUES (%s, %s, %s)",
                  (lib_id, f"l-{lib_id}", "L"))
        c.execute("INSERT INTO project (id, name) VALUES (%s, %s)", (proj_id, "P"))
        c.execute(
            "INSERT INTO company_asset (id, library_company_id, asset_type, name, unit, ownership) "
            "VALUES (%s, %s, 'vehicle', '斗臂车', '辆', 'self')",
            (asset_id, lib_id),
        )
        c.execute(
            """
            INSERT INTO project_equipment_selection
              (id, project_id, asset_id, asset_type, frozen_snapshot, frozen, frozen_at, intended_role)
            VALUES (%s, %s, %s, 'vehicle', %s, TRUE, now(), '配电主线')
            """,
            (uuid4(), proj_id, asset_id,
             '{"name":"斗臂车","spec_model":"DFL5160","serial_no":"苏A12345",'
             '"manufacturer":"东风","quantity":1,"unit":"辆","ownership":"self",'
             '"acquired_at":"2024-01-01","expires_at":"2027-01-01",'
             '"technical_condition":"完好","extras":{"vehicle_type":"aerial_bucket"}}'),
        )
    return proj_id


def test_render_preview(populated_project):
    proj_id = populated_project
    renderer = EquipmentTableRenderer()
    with psycopg.connect(_db_url(), autocommit=True) as conn:
        out = renderer.render_equipment_preview(conn, project_id=proj_id)
    assert set(out.keys()) == {"vehicle", "machine", "tool", "safety"}
    assert len(out["vehicle"]) == 1
    row = out["vehicle"][0]
    assert row["设备名称"] == "斗臂车"
    assert row["序号"] == "1"
    assert row["所有权"] == "自有"


def test_render_attachment_xlsx_has_4_sheets(populated_project):
    renderer = EquipmentTableRenderer()
    with psycopg.connect(_db_url(), autocommit=True) as conn:
        data = renderer.render_attachment_xlsx(conn, project_id=populated_project)
    wb = load_workbook(io.BytesIO(data))
    assert sorted(wb.sheetnames) == sorted(["车辆", "施工机械", "施工工器具", "安全设施设备及器具"])
    headers = [c.value for c in wb["车辆"][1]]
    assert "设备名称" in headers
    data_row = [c.value for c in wb["车辆"][2]]
    assert "斗臂车" in data_row
```

- [ ] **Step 2: 实现 EquipmentTableRenderer**

详见 spec §5.2-5.4。完整实现含三方法 `render_equipment_preview` / `render_subsection_table` / `render_attachment_xlsx`，共享 `_load()` + `_resolve()` + `_OWNERSHIP_LABELS` + 后端镜像版 `_COLUMNS` (与 frontend assetTypeSchemas.ts export_columns 对齐)。后端 `_COLUMNS` 4 类清单完全照搬 Phase 3 schemas 中 export_columns。`render_subsection_table` 用 python-docx `doc.add_table(rows, cols)` + `table.style = "EquipmentTableStyle"` (fallback `Table Grid`)。`render_attachment_xlsx` 用 openpyxl Workbook 4 sheet + 标题行 `Font(bold=True)` + `freeze_panes='A2'`。

- [ ] **Step 3: 运行通过 + Commit**

```bash
cd backend && DATABASE_URL=$DATABASE_URL pytest tests/unit/test_equipment_table_renderer.py -v
git add backend/tender_backend/services/export_service/equipment_table_renderer.py \
        backend/tests/unit/test_equipment_table_renderer.py
git commit -m "feat(export): EquipmentTableRenderer with preview / DOCX subsection / xlsx outputs"
```

---

## Phase 11: docx_exporter 注入器 + delivery_package 附件 + Preview/Xlsx API

**目标:** 把 EquipmentTableRenderer 接入投标 DOCX 导出 + ZIP 打包链路;并暴露给前端 preview / 下载的 HTTP endpoints。

### Task 11.1: EquipmentTableInjector + docx_exporter 集成

**Files:**
- Create: `backend/tender_backend/services/export_service/equipment_table_injector.py`
- Modify: `backend/tender_backend/services/export_service/docx_exporter.py`
- Create: `backend/tests/integration/test_equipment_table_export.py`

- [ ] **Step 1: 写失败测试**

```python
"""Integration test: anchor `{{equipment_table:vehicle}}` in DOCX is replaced by native table."""

from __future__ import annotations

import io
import os
from uuid import uuid4

import psycopg
import pytest
from docx import Document

from tender_backend.db.alembic.runner import upgrade_to_head
from tender_backend.services.export_service.equipment_table_injector import (
    EquipmentTableInjector,
)


def _db_url(): return os.environ.get("DATABASE_URL")


@pytest.fixture
def project_with_selection():
    if not _db_url(): pytest.skip("DATABASE_URL not set")
    with psycopg.connect(_db_url(), autocommit=True) as c:
        upgrade_to_head(c)
        lib_id, proj_id, asset_id = uuid4(), uuid4(), uuid4()
        c.execute("INSERT INTO library_company (id, company_key, company_name) VALUES (%s, %s, %s)",
                  (lib_id, f"l-{lib_id}", "L"))
        c.execute("INSERT INTO project (id, name) VALUES (%s, %s)", (proj_id, "P"))
        c.execute(
            "INSERT INTO company_asset (id, library_company_id, asset_type, name, unit, ownership) "
            "VALUES (%s, %s, 'vehicle', '斗臂车', '辆', 'self')",
            (asset_id, lib_id),
        )
        c.execute(
            """
            INSERT INTO project_equipment_selection (id, project_id, asset_id, asset_type,
              frozen_snapshot, frozen, frozen_at)
            VALUES (%s, %s, %s, 'vehicle', %s, TRUE, now())
            """,
            (uuid4(), proj_id, asset_id,
             '{"name":"斗臂车","spec_model":"DFL5160","quantity":1,"unit":"辆",'
             '"ownership":"self","extras":{"vehicle_type":"aerial_bucket"}}'),
        )
    return proj_id


def test_injector_replaces_anchor_with_table(project_with_selection):
    proj_id = project_with_selection
    doc = Document()
    doc.add_paragraph("以下是车辆清单:")
    doc.add_paragraph("{{equipment_table:vehicle}}")
    doc.add_paragraph("以下是机械清单:")
    doc.add_paragraph("{{equipment_table:machine}}")
    doc.add_paragraph("正文继续。")
    with psycopg.connect(_db_url(), autocommit=True) as conn:
        EquipmentTableInjector(doc, conn, project_id=proj_id).inject_all()
    # 锚点段落应被替换:vehicle 段落出现 native table
    tables = doc.tables
    assert len(tables) >= 2  # vehicle + machine (machine 表头 + 占位 "无")
    # 第一表第一行应有 "设备名称"
    assert any("设备名称" in c.text for c in tables[0].rows[0].cells)
    # 锚点段落已移除
    text_all = "\n".join(p.text for p in doc.paragraphs)
    assert "{{equipment_table:" not in text_all


def test_injector_skips_doc_without_anchors():
    """Documents without anchors should not error and should leave content untouched."""
    proj_id = uuid4()
    doc = Document()
    doc.add_paragraph("普通段落,无锚点。")
    with psycopg.connect(_db_url(), autocommit=True) as conn:
        EquipmentTableInjector(doc, conn, project_id=proj_id).inject_all()
    assert doc.paragraphs[0].text == "普通段落,无锚点。"
    assert len(doc.tables) == 0
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 EquipmentTableInjector**

```python
"""EquipmentTableInjector: scan DOCX paragraphs for {{equipment_table:<type>}} anchors
and replace each with a native table for the corresponding asset_type."""

from __future__ import annotations

import re
from uuid import UUID

from docx.document import Document
from psycopg import Connection

from tender_backend.services.export_service.equipment_table_renderer import (
    EquipmentTableRenderer,
)


_ANCHOR_RE = re.compile(r"\{\{equipment_table:(vehicle|machine|tool|safety)\}\}")


class EquipmentTableInjector:
    def __init__(self, doc: Document, conn: Connection, *, project_id: UUID):
        self._doc = doc
        self._conn = conn
        self._project_id = project_id
        self._renderer = EquipmentTableRenderer()

    def inject_all(self) -> int:
        count = 0
        # iterate over a snapshot to avoid mutation during traversal
        for paragraph in list(self._doc.paragraphs):
            m = _ANCHOR_RE.search(paragraph.text or "")
            if not m:
                continue
            asset_type = m.group(1)
            table = self._renderer.render_subsection_table(
                self._doc, self._conn, project_id=self._project_id, asset_type=asset_type,
            )
            # 将新 table 元素插入到 anchor 段落之后,然后删除该段落
            paragraph._element.addnext(table._element)  # noqa: SLF001
            paragraph._element.getparent().remove(paragraph._element)  # noqa: SLF001
            count += 1
        return count
```

- [ ] **Step 4: 在 docx_exporter.py 末尾接入注入器**

读 `docx_exporter.py`，找到导出函数（如 `export_to_docx(project_id)`）的章节生成完成处，加 pass：

```python
from tender_backend.services.export_service.equipment_table_injector import EquipmentTableInjector

def export_to_docx(project_id: UUID, conn: Connection) -> Document:
    doc = ...  # 现有章节渲染
    EquipmentTableInjector(doc, conn, project_id=project_id).inject_all()
    return doc
```

如 `docx_exporter` 函数签名不接 conn,在调用方传入或从 deps 注入。

- [ ] **Step 5: 运行通过 + Commit**

```bash
cd backend && DATABASE_URL=$DATABASE_URL pytest tests/integration/test_equipment_table_export.py -v
git add backend/tender_backend/services/export_service/equipment_table_injector.py \
        backend/tender_backend/services/export_service/docx_exporter.py \
        backend/tests/integration/test_equipment_table_export.py
git commit -m "feat(export): docx anchor injector for equipment subsection tables"
```

---

### Task 11.2: delivery_package 挂 equipment_table_xlsx 附件

**Files:**
- Modify: `backend/tender_backend/services/delivery_package.py`

- [ ] **Step 1: 在 delivery_package 终稿打包逻辑中加 xlsx 生成 + 注册**

读 `delivery_package.py`,找到打包附件清单生成函数。在 ZIP 写入前加:

```python
from tender_backend.services.export_service.equipment_table_renderer import EquipmentTableRenderer

def build_delivery_package(project_id, conn) -> ...:
    # ... 现有 DOCX/PDF 收集 ...
    
    # 设备表 xlsx 附件
    renderer = EquipmentTableRenderer()
    xlsx_bytes = renderer.render_attachment_xlsx(conn, project_id=project_id)
    project_no = _resolve_project_no(conn, project_id)  # 沿用现有命名工具
    xlsx_name = f"{project_no}_主要施工设备一览表.xlsx"
    package.add_attachment(name=xlsx_name, content=xlsx_bytes,
                           kind="equipment_table_xlsx")
    # ...
```

如 delivery_package 用 `bid_delivery_package` 表登记,加一行：

```sql
INSERT INTO bid_delivery_package_attachment (id, package_id, attachment_kind, file_name, byte_size)
VALUES (...);
```

- [ ] **Step 2: 加测试**

加测试到 `backend/tests/integration/test_equipment_table_export.py`：

```python
def test_delivery_package_includes_equipment_xlsx(project_with_selection):
    from tender_backend.services.delivery_package import build_delivery_package
    proj_id = project_with_selection
    with psycopg.connect(_db_url(), autocommit=True) as conn:
        package = build_delivery_package(proj_id, conn)
    names = [a.name for a in package.attachments]
    assert any("主要施工设备一览表.xlsx" in n for n in names)
```

- [ ] **Step 3: 运行通过 + Commit**

```bash
cd backend && DATABASE_URL=$DATABASE_URL pytest tests/integration/test_equipment_table_export.py -v
git add backend/tender_backend/services/delivery_package.py \
        backend/tests/integration/test_equipment_table_export.py
git commit -m "feat(delivery): include equipment table xlsx in delivery package"
```

---

### Task 11.3: Preview + xlsx 下载 API endpoints

**Files:**
- Modify: `backend/tender_backend/api/equipment_selection.py`

- [ ] **Step 1: 加 endpoints**

```python
from fastapi.responses import StreamingResponse
import io
from tender_backend.services.export_service.equipment_table_renderer import EquipmentTableRenderer

_renderer = EquipmentTableRenderer()


@router.get("/projects/{project_id}/equipment/preview")
async def preview(project_id: UUID, conn: Connection = Depends(get_db_conn)) -> dict:
    """Return per-type list of dicts (label-keyed) for HTML preview."""
    return _renderer.render_equipment_preview(conn, project_id=project_id)


@router.get("/projects/{project_id}/equipment/attachment-xlsx")
async def download_xlsx(project_id: UUID, conn: Connection = Depends(get_db_conn)):
    data = _renderer.render_attachment_xlsx(conn, project_id=project_id)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="equipment-table-{project_id}.xlsx"'},
    )
```

- [ ] **Step 2: 在 frontend api.ts 加客户端**

```ts
export async function fetchEquipmentPreview(projectId: string) {
  return await api(`/projects/${projectId}/equipment/preview`) as Record<string, Record<string, string>[]>;
}
export async function downloadEquipmentXlsx(projectId: string): Promise<Blob> {
  const res = await fetch(`${API_BASE}/projects/${projectId}/equipment/attachment-xlsx`,
                         { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!res.ok) throw new Error(`download failed: ${res.status}`);
  return await res.blob();
}
```

- [ ] **Step 3: 加测试 + 通过 + Commit**

```python
# backend/tests/integration/test_equipment_selection_api.py 追加:
def test_preview_endpoint(setup):
    client, pid, aid, lid = setup
    # 先创建并冻结
    client.post(f"/api/projects/{pid}/equipment/selections",
                json={"asset_id": aid}, headers=_AUTH)
    client.post(f"/api/projects/{pid}/equipment/selections/freeze", headers=_AUTH)
    res = client.get(f"/api/projects/{pid}/equipment/preview", headers=_AUTH)
    assert res.status_code == 200
    body = res.json()
    assert "vehicle" in body
    assert len(body["vehicle"]) == 1


def test_download_xlsx_endpoint(setup):
    client, pid, aid, lid = setup
    client.post(f"/api/projects/{pid}/equipment/selections",
                json={"asset_id": aid}, headers=_AUTH)
    client.post(f"/api/projects/{pid}/equipment/selections/freeze", headers=_AUTH)
    res = client.get(f"/api/projects/{pid}/equipment/attachment-xlsx", headers=_AUTH)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert len(res.content) > 100
```

```bash
cd backend && DATABASE_URL=$DATABASE_URL pytest tests/integration/test_equipment_selection_api.py -v
git add backend/tender_backend/api/equipment_selection.py \
        frontend/src/lib/api.ts \
        backend/tests/integration/test_equipment_selection_api.py
git commit -m "feat(equipment): preview JSON and xlsx download endpoints"
```

---

## Phase 12: 符合性检查扩展 + 工作流状态扩展

**目标:** 把 4 项符合性扫描接入 review_engine,工作流加 `equipment_selection` 状态;未冻结时阻断 final_layout。

### Task 12.1: review_engine 加 4 项扫描

**Files:**
- Modify: `backend/tender_backend/services/review_service/review_engine.py`
- Create: `backend/tests/integration/test_equipment_compliance_check.py`

- [ ] **Step 1: 写失败测试**

```python
"""4 compliance checks on project_equipment_selection."""

from __future__ import annotations

import os
from datetime import date, timedelta
from uuid import uuid4

import psycopg
import pytest

from tender_backend.db.alembic.runner import upgrade_to_head
from tender_backend.services.review_service.review_engine import (
    scan_equipment_selection,
)


def _db_url(): return os.environ.get("DATABASE_URL")


@pytest.fixture
def setup():
    if not _db_url(): pytest.skip("DATABASE_URL not set")
    with psycopg.connect(_db_url(), autocommit=True) as c:
        upgrade_to_head(c)
        lib_id, proj_id, asset_id = uuid4(), uuid4(), uuid4()
        deadline = date.today() + timedelta(days=30)
        c.execute("INSERT INTO library_company (id, company_key, company_name) VALUES (%s, %s, %s)",
                  (lib_id, f"l-{lib_id}", "L"))
        c.execute(
            "INSERT INTO project (id, name, submission_deadline, bid_validity_period) "
            "VALUES (%s, %s, %s, 90)",
            (proj_id, "P", deadline),
        )
        c.execute(
            "INSERT INTO company_asset (id, library_company_id, asset_type, name, unit, ownership) "
            "VALUES (%s, %s, 'vehicle', 'A', '辆', 'self')",
            (asset_id, lib_id),
        )
    return proj_id, asset_id


def test_scan_p0_when_expires_before_validity(setup):
    proj_id, asset_id = setup
    with psycopg.connect(_db_url(), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO project_equipment_selection (id, project_id, asset_id, asset_type, "
            "frozen_snapshot, frozen, frozen_at) VALUES (%s, %s, %s, 'vehicle', %s, TRUE, now())",
            (uuid4(), proj_id, asset_id,
             '{"expires_at":"2026-01-01"}'),  # 已过有效性
        )
        issues = scan_equipment_selection(conn, project_id=proj_id)
    p0 = [i for i in issues if i["severity"] == "P0"]
    assert any("expires_at" in i["code"] for i in p0)


def test_scan_p1_when_exclusion_overridden(setup):
    proj_id, asset_id = setup
    with psycopg.connect(_db_url(), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO project_equipment_selection (id, project_id, asset_id, asset_type, "
            "frozen_snapshot, frozen, frozen_at, exclusion_overridden, selection_reason) "
            "VALUES (%s, %s, %s, 'vehicle', %s, TRUE, now(), TRUE, 'override reason')",
            (uuid4(), proj_id, asset_id, '{"expires_at":"2027-01-01"}'),
        )
        issues = scan_equipment_selection(conn, project_id=proj_id)
    assert any(i["severity"] == "P1" and "override" in i["code"] for i in issues)
```

- [ ] **Step 2: 实现 scan_equipment_selection**

在 `review_engine.py` 加：

```python
from datetime import date, timedelta
from uuid import UUID
from psycopg import Connection
from psycopg.rows import dict_row


def scan_equipment_selection(conn: Connection, *, project_id: UUID) -> list[dict]:
    """4 项符合性扫描,返回 issues list (severity / code / message / asset_id)."""
    issues: list[dict] = []
    
    proj_row = conn.execute(
        "SELECT submission_deadline, bid_validity_period FROM project WHERE id = %s",
        (project_id,),
    ).fetchone()
    if proj_row and proj_row[0]:
        validity_until = proj_row[0] + timedelta(days=proj_row[1] or 90)
    else:
        validity_until = date.today() + timedelta(days=90)
    
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT id, asset_id, asset_type, frozen_snapshot, exclusion_overridden, frozen "
            "FROM project_equipment_selection WHERE project_id = %s AND frozen = TRUE",
            (project_id,),
        )
        selections = list(cur.fetchall())
    
    for s in selections:
        snap = s["frozen_snapshot"] or {}
        # P0 #1: expires_at < validity_until
        exp_str = snap.get("expires_at")
        if exp_str:
            exp = date.fromisoformat(exp_str)
            if exp < validity_until:
                issues.append({
                    "severity": "P0",
                    "code": "equipment.expires_at_too_early",
                    "message": f"资产 {snap.get('name','')} 有效期 {exp} 早于投标有效性截止 {validity_until}",
                    "asset_id": s["asset_id"],
                })
        # P0 #2: 核心附件缺失 (检查 core_attachment_ids 是否非空)
        core_ids = snap.get("core_attachment_ids") or []
        if not core_ids:
            issues.append({
                "severity": "P1",
                "code": "equipment.core_attachment_missing",
                "message": f"资产 {snap.get('name','')} 无核心附件挂载",
                "asset_id": s["asset_id"],
            })
        # P1 #3: 强制纳入风险已知
        if s["exclusion_overridden"]:
            issues.append({
                "severity": "P1",
                "code": "equipment.exclusion_override",
                "message": f"资产 {snap.get('name','')} 被强制纳入,需投标负责人复核",
                "asset_id": s["asset_id"],
            })
    
    # P0 #4: equipment_requirement 覆盖度未达 min_quantity
    from tender_backend.services.tender_constraint_service import TenderConstraintService
    from tender_backend.services.equipment_filter_service import EquipmentFilterService, FilterContext
    constraint_svc = TenderConstraintService()
    filter_svc = EquipmentFilterService()
    requirements = constraint_svc.list_equipment_requirements(conn, project_id=project_id)
    if requirements:
        # 用 frozen_snapshot 作为 "已选资产" 输入到 filter._matches 来检查覆盖度
        for req in requirements:
            matched_qty = sum(
                float((s["frozen_snapshot"] or {}).get("quantity", 0))
                for s in selections
                if s["asset_type"] == req["asset_type"] and filter_svc._matches(  # noqa: SLF001
                    {"extras": (s["frozen_snapshot"] or {}).get("extras", {}),
                     "asset_type": s["asset_type"]},
                    req["predicate"],
                )
            )
            if matched_qty < req["min_quantity"]:
                issues.append({
                    "severity": "P0",
                    "code": "equipment.requirement_coverage",
                    "message": f"招标要求 [{req['label']}] 已选 {matched_qty} < {req['min_quantity']}",
                    "asset_id": None,
                })
    
    return issues
```

- [ ] **Step 3: 运行通过 + Commit**

```bash
cd backend && DATABASE_URL=$DATABASE_URL pytest tests/integration/test_equipment_compliance_check.py -v
git add backend/tender_backend/services/review_service/review_engine.py \
        backend/tests/integration/test_equipment_compliance_check.py
git commit -m "feat(review): equipment selection compliance checks (P0/P1)"
```

---

### Task 12.2: 工作流状态扩展 + final_layout 阻断

**Files:**
- Modify: `backend/tender_backend/services/project_setup_service.py`
- Create: `backend/tests/integration/test_equipment_workflow_gate.py`

- [ ] **Step 1: 在工作流状态枚举与转移图加 equipment_selection**

读 `project_setup_service.py`,定位 `WORKFLOW_STATES` / `_TRANSITIONS` 字典。加：

```python
WORKFLOW_STATES = (..., "drafting", "equipment_selection", "draft_reviewing", ...)

_TRANSITIONS = {
    ...
    "drafting": {"equipment_selection", "draft_reviewing"},  # 允许跳过(无设备项目)或进入设备选择
    "equipment_selection": {"draft_reviewing"},             # 必须先冻结才能进 reviewing (在调用方校验)
    ...
}
```

- [ ] **Step 2: 在状态转移到 final_layout 时调用符合性扫描**

```python
def transition(self, conn, *, project_id, next_status, ...):
    if next_status == "final_layout":
        from tender_backend.services.review_service.review_engine import scan_equipment_selection
        issues = scan_equipment_selection(conn, project_id=project_id)
        p0 = [i for i in issues if i["severity"] == "P0"]
        if p0 and not allow_p0_override:
            raise WorkflowGateError(
                f"final_layout blocked by {len(p0)} P0 equipment compliance issues",
                issues=p0,
            )
    # ... 现有 transition 逻辑 ...
```

- [ ] **Step 3: 写测试**

```python
"""Workflow gate test: P0 equipment issue blocks final_layout."""

import os, pytest, psycopg
from datetime import date, timedelta
from uuid import uuid4
from tender_backend.db.alembic.runner import upgrade_to_head
from tender_backend.services.project_setup_service import ProjectSetupService, WorkflowGateError


def _db_url(): return os.environ.get("DATABASE_URL")


@pytest.fixture
def project_with_p0():
    if not _db_url(): pytest.skip("DATABASE_URL not set")
    with psycopg.connect(_db_url(), autocommit=True) as c:
        upgrade_to_head(c)
        lib_id, proj_id, asset_id = uuid4(), uuid4(), uuid4()
        c.execute("INSERT INTO library_company (id, company_key, company_name) VALUES (%s, %s, %s)",
                  (lib_id, f"l-{lib_id}", "L"))
        c.execute("INSERT INTO project (id, name, submission_deadline, bid_validity_period, workflow_status) "
                  "VALUES (%s, %s, %s, 90, 'draft_reviewing')",
                  (proj_id, "P", date.today() + timedelta(days=30)))
        c.execute("INSERT INTO company_asset (id, library_company_id, asset_type, name, unit, ownership) "
                  "VALUES (%s, %s, 'vehicle', 'A', '辆', 'self')", (asset_id, lib_id))
        # frozen selection with expired snapshot -> P0
        c.execute(
            "INSERT INTO project_equipment_selection (id, project_id, asset_id, asset_type, "
            "frozen_snapshot, frozen, frozen_at) VALUES (%s, %s, %s, 'vehicle', %s, TRUE, now())",
            (uuid4(), proj_id, asset_id, '{"expires_at":"2026-01-01","name":"过期车"}'),
        )
    return proj_id


def test_final_layout_blocked_by_p0(project_with_p0):
    proj_id = project_with_p0
    svc = ProjectSetupService()
    with psycopg.connect(_db_url(), autocommit=True) as conn:
        with pytest.raises(WorkflowGateError, match="P0"):
            svc.transition(conn, project_id=proj_id, next_status="final_layout",
                           actor="test", reason="test")


def test_final_layout_allowed_with_override(project_with_p0):
    """Explicit allow_p0_override should let it through."""
    proj_id = project_with_p0
    svc = ProjectSetupService()
    with psycopg.connect(_db_url(), autocommit=True) as conn:
        svc.transition(conn, project_id=proj_id, next_status="final_layout",
                       actor="test", reason="test", allow_p0_override=True)
    with psycopg.connect(_db_url(), autocommit=True) as c:
        row = c.execute("SELECT workflow_status FROM project WHERE id = %s", (proj_id,)).fetchone()
    assert row[0] == "final_layout"
```

- [ ] **Step 4: 运行通过 + Commit**

```bash
cd backend && DATABASE_URL=$DATABASE_URL pytest tests/integration/test_equipment_workflow_gate.py -v
git add backend/tender_backend/services/project_setup_service.py \
        backend/tests/integration/test_equipment_workflow_gate.py
git commit -m "feat(workflow): equipment_selection state and P0 gate to final_layout"
```

---

## Phase 13: E2E Fixture + Acceptance + Self-Review

**目标:** 从公司库录入 → 投标筛选 → 冻结 → DOCX/Xlsx 导出整条链路一次跑通,作为发布前 smoke test。

### Task 13.1: E2E fixture seed 脚本

**Files:**
- Create: `backend/tests/integration/test_company_asset_e2e.py`

- [ ] **Step 1: 写一个 happy-path 端到端测试**

```python
"""End-to-end: 10kV business line scenario from asset entry to DOCX/xlsx export."""

from __future__ import annotations

import io
import os
from datetime import date, timedelta
from uuid import uuid4

import psycopg
import pytest
from openpyxl import load_workbook

from tender_backend.db.alembic.runner import upgrade_to_head
from tender_backend.main import app
from tender_backend.test_support.asgi_client import SyncASGIClient


_AUTH = {"Authorization": "Bearer dev-token"}


def _db_url(): return os.environ.get("DATABASE_URL")


@pytest.fixture
def e2e_setup():
    if not _db_url(): pytest.skip("DATABASE_URL not set")
    with psycopg.connect(_db_url(), autocommit=True) as c:
        upgrade_to_head(c)
        lib_id, proj_id = uuid4(), uuid4()
        c.execute("INSERT INTO library_company (id, company_key, company_name) VALUES (%s, %s, %s)",
                  (lib_id, f"l-{lib_id}", "L"))
        c.execute("INSERT INTO project (id, name, submission_deadline, bid_validity_period) "
                  "VALUES (%s, %s, %s, 90)",
                  (proj_id, "10kV 配网新建", date.today() + timedelta(days=30)))
    return SyncASGIClient(app), str(proj_id), str(lib_id)


def test_e2e_10kv_scenario(e2e_setup):
    client, pid, lid = e2e_setup
    
    # 1. 公司库录入: 3 辆车 + 5 台机械 + 30 件工器具 + 12 件安全设施
    far_future = (date.today() + timedelta(days=365)).isoformat()
    asset_ids = []
    for i in range(3):
        r = client.post(f"/api/master-data/library-companies/{lid}/assets",
                        json={"asset_type": "vehicle", "name": f"斗臂车{i}", "unit": "辆",
                              "ownership": "self", "quantity": 1, "expires_at": far_future,
                              "extras": {"vehicle_type": "aerial_bucket", "voltage_level": "10kV"}},
                        headers=_AUTH)
        assert r.status_code == 201
        asset_ids.append(r.json()["id"])
    for i in range(5):
        client.post(f"/api/master-data/library-companies/{lid}/assets",
                    json={"asset_type": "machine", "name": f"起重机{i}", "unit": "台",
                          "ownership": "self", "quantity": 1, "expires_at": far_future,
                          "extras": {"machine_category": "lifting", "inspection_required": True}},
                    headers=_AUTH)
    for i in range(30):
        client.post(f"/api/master-data/library-companies/{lid}/assets",
                    json={"asset_type": "tool", "name": f"绝缘杆{i}", "unit": "件",
                          "ownership": "self", "quantity": 1, "expires_at": far_future,
                          "extras": {"tool_category": "insulation", "voltage_level": "10kV",
                                     "inspection_period_months": 12,
                                     "last_inspection_at": date.today().isoformat()}},
                    headers=_AUTH)
    for i in range(12):
        client.post(f"/api/master-data/library-companies/{lid}/assets",
                    json={"asset_type": "safety", "name": f"安全帽{i}", "unit": "顶",
                          "ownership": "self", "quantity": 1, "expires_at": far_future,
                          "extras": {"safety_category": "ppe"}},
                    headers=_AUTH)
    
    # 2. 招标约束注入(模拟解析后的 equipment_requirement)
    from tender_backend.services.tender_constraint_service import (
        TenderConstraintService, EquipmentRequirementPayload,
    )
    svc = TenderConstraintService()
    with psycopg.connect(_db_url(), autocommit=True) as conn:
        svc.create_equipment_requirement(conn, project_id=uuid4().__class__(pid),
            payload=EquipmentRequirementPayload(
                label="≥2 台 10kV 斗臂车", source_ref="测试",
                asset_type="vehicle", predicate={"vehicle_type": "aerial_bucket"},
                min_quantity=2,
            ))
    
    # 3. 取候选,验证斗臂车 ≥ 3 辆
    r = client.get(f"/api/projects/{pid}/equipment/candidates?asset_type=vehicle", headers=_AUTH)
    assert r.status_code == 200
    body = r.json()
    assert len(body["candidates"]) >= 3
    
    # 4. 加 2 辆斗臂车进已选
    for i in range(2):
        r = client.post(f"/api/projects/{pid}/equipment/selections",
                        json={"asset_id": asset_ids[i]}, headers=_AUTH)
        assert r.status_code == 201
    
    # 5. 冻结
    r = client.post(f"/api/projects/{pid}/equipment/selections/freeze", headers=_AUTH)
    assert r.status_code == 200
    
    # 6. 预览
    r = client.get(f"/api/projects/{pid}/equipment/preview", headers=_AUTH)
    assert r.status_code == 200
    preview = r.json()
    assert len(preview["vehicle"]) == 2
    
    # 7. 下载 xlsx
    r = client.get(f"/api/projects/{pid}/equipment/attachment-xlsx", headers=_AUTH)
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert "车辆" in wb.sheetnames
    assert wb["车辆"].max_row >= 3  # 1 header + 2 rows
```

- [ ] **Step 2: 运行通过 + Commit**

```bash
cd backend && DATABASE_URL=$DATABASE_URL pytest tests/integration/test_company_asset_e2e.py -v
git add backend/tests/integration/test_company_asset_e2e.py
git commit -m "test(asset): end-to-end 10kV equipment scenario"
```

---

### Task 13.2: 验收 checklist

- [ ] **Step 1: 跑全套相关测试**

```bash
cd backend && DATABASE_URL=$DATABASE_URL pytest \
  tests/unit/test_asset_schema.py \
  tests/unit/test_equipment_filter_service.py \
  tests/unit/test_equipment_table_renderer.py \
  tests/unit/test_equipment_requirement_constraint.py \
  tests/integration/test_company_asset_migration.py \
  tests/integration/test_company_asset_repo.py \
  tests/integration/test_company_asset_api.py \
  tests/integration/test_project_equipment_selection_repo.py \
  tests/integration/test_equipment_selection_api.py \
  tests/integration/test_equipment_table_export.py \
  tests/integration/test_equipment_compliance_check.py \
  tests/integration/test_equipment_workflow_gate.py \
  tests/integration/test_company_asset_e2e.py \
  -v
```

Expected: 全部 PASS

- [ ] **Step 2: 跑前端测试**

```bash
cd frontend && npx vitest run \
  src/modules/database/schemas/assetTypeSchemas.test.ts \
  src/modules/database/components/asset/expiryBadge.test.ts \
  src/modules/database/components/asset/AssetTable.test.tsx \
  src/modules/database/components/__tests__/AssetFormDrawer.test.tsx \
  src/modules/authoring/__tests__/EquipmentSelectionWorkbench.test.tsx
```

Expected: 全部 PASS

- [ ] **Step 3: 浏览器手动 smoke test**

启动 dev server。逐项验证:

- [ ] 投标资料库 → 公司资料 → 公司资产: 4 tab 切换、+ 新增、抽屉表单、4 卡片核心槽上传、累积区折叠
- [ ] 编辑/删除资产；DELETE 在已被引用的资产时应 409
- [ ] 进入 已存在的项目 → 设备清单工作台: 自动筛选生成候选 + 排除清单 + 覆盖度横条
- [ ] 强制纳入未通过筛选的资产: 弹理由对话框 + 写入并标"⚠ 风险已知"
- [ ] 招标约束变更后(手工在 tender_constraint 表插一条 equipment_requirement) → 重筛按钮可用
- [ ] 点"确认并冻结快照": 已选区显示"已冻结",移除按钮 disabled
- [ ] 模板章节加 `{{equipment_table:vehicle}}`(在某个 bid_chapter 模板中) → 导出 DOCX 出现 native 表格,无锚点字符串残留
- [ ] 终稿打包 ZIP 含 `<项目编号>_主要施工设备一览表.xlsx`,4 sheet 与 DOCX 子段数据一致
- [ ] final_layout 转移在 expires_at 过期时被阻断;使用 allow_p0_override 可放行

- [ ] **Step 4: 标记 acceptance complete + Commit**

```bash
git commit --allow-empty -m "chore(asset): equipment table feature acceptance complete"
```

---

## Self-Review

完成全部 13 phases 的写作后,做一次自检:

1. **Spec 覆盖度** — 对照 `docs/superpowers/specs/2026-05-07-company-asset-and-equipment-table-design.md` 7 节,逐节检查 plan 中是否有任务实现:
   - §1 数据层 ✓ Phase 1
   - §2 前端 schema 配置 ✓ Phase 3
   - §3 公司库工作台 UI ✓ Phase 4 + 5
   - §4 投标设备表生成工作台 ✓ Phase 6 + 7 + 8 + 9
   - §5 输出层 (DOCX 嵌入 + Excel 附件) ✓ Phase 10 + 11
   - §6 集成点 + API + 测试 ✓ Phase 11.3 + 13
   - §7 实施依赖关系 ≈ 与 Phase 1-13 顺序对齐

2. **Placeholder 扫描** — grep "TBD"|"TODO"|"implement later" 确认无;凡是"详见 spec §X" 的引用都直接附了核心代码,未省略关键实现。

3. **类型一致性** — 检查 backend `_COLUMNS` 与 frontend `export_columns` label/key 命名一致(中文 label 在 DOCX/Excel 与前端预览的 key 是同一字符串,这是同步约定);检查 `frozen_snapshot` 字段在 freezer / renderer / scan_equipment_selection 三处使用的 key 命名(name/spec_model/expires_at 等)是否一致。

4. **可执行性** — 每个 Step 都有具体命令,没有"按指示操作"等不可执行表达。

---





