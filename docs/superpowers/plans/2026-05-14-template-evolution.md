# Template Evolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a template evolution system that lets per-project template modifications flow back into the global template library safely, through versioned packages, category variants evolved from real usage clusters, dual-channel reflow (manual proposals + offline clustering analysis), and a template administrator review workbench.

**Architecture:** Three orthogonal mechanisms:
1. **Versioned packages** — each `bid_template_package` row becomes one version of a package family; in-flight projects pin to a specific version so global upgrades cannot break a running bid.
2. **Category variants** — `bid_template_variant` sits between global package and project instance; variants are explicit specializations (国网华东 / 南网 / 用户配电) that snapshot from a parent package version and can be rebased explicitly. Variants evolve from clusters of project-level modifications, not predefined.
3. **Dual-channel reflow** — manual proposals (already scaffolded by the P1 plan's `template_promotion_proposal`) plus an offline clustering job that surfaces repeated cross-project modifications as automatically-generated proposals. Both channels feed one admin review queue.

**Tech Stack:** FastAPI, psycopg, Alembic, PostgreSQL JSONB, React 18, TypeScript, TanStack Query, Vitest, pytest. Reuses `Role.ADMIN` from `tender_backend.core.security` for the template administrator role.

**Prerequisite:** This plan depends on the Project Template Instance Workflow plan (`docs/superpowers/plans/2026-05-14-project-template-instance-workflow.md`) being merged. Tables `project_template_instance`, `project_template_chapter`, `project_template_block`, `project_template_revision`, `template_promotion_proposal` must exist. Migration 0051 is reserved by that plan; this plan starts at 0052.

---

## Product Decision Record

- 模板有"版本"概念。已开始的项目锁定基础模板版本，全局升级不影响在跑项目。
- 类别变体（变体 = variant）不在系统初始化时预定义，而是从实际项目修订聚类中演化出来。先有相似修订，再有变体。
- 项目实例的修订有两条沉淀通道：
  - 主动通道：投标工程师项目结束后勾选改动，走 `template_promotion_proposal`。
  - 被动通道：后台离线任务对所有项目实例做 block-level diff 聚类，发现重复修订自动生成提议。
- 两条通道都汇入**同一个**模板管理员审核队列。管理员是 `Role.ADMIN`，由产品设定为公司层面的高级投标工程师 / 投标主管。
- 审核通过的修订目标三选一：
  - 升级到父级包的新版本（全局改进）。
  - 进入现有变体的新版本（变体改进）。
  - 抽取为新变体（类别特化）。
- 任何回流操作都先剥离项目特定动态资料引用（具体业绩、人员、报价数字），只保留占位符与选取规则。
- 模板管理员的判断不可被绕过。不做自动合并，diff 都要人看。
- 变体可以"rebase"到父级包的新版本，但 rebase 是显式动作，不是自动推送。

## Existing Context

### Will exist after P1 plan merges

- `project_template_instance` (id, project_id, base_template_package_id, category_code, display_name, status, version, confirmed_at, ...)
- `project_template_chapter` (id, template_instance_id, source_template_item_id, chapter_code, chapter_title, sort_order, enabled, ...)
- `project_template_block` (id, template_chapter_id, block_type, content_text, prompt_text, placeholder_key, asset_type, render_options_json, condition_json, ...)
- `project_template_revision` (id, template_instance_id, revision_no, change_type, change_summary, snapshot_json, created_by, created_at)
- `template_promotion_proposal` (id, template_instance_id, base_template_package_id, project_id, proposal_status, diff_json, created_by, reviewed_by, ...)

### Existing now

- `bid_template_package` (id, package_key UNIQUE, display_name, package_type, category_code, source_root, source_manifest, created_at, updated_at) — see `backend/tender_backend/db/repositories/bid_template_package_repo.py:13-25`.
- `bid_template_item` (id, package_id, item_code, item_name, filename, relative_path, source_kind, item_type, render_mode, is_required, sort_order)
- `template_package_category` (code, display_name, description, sort_order, enabled, metadata_json) — see `backend/tender_backend/api/template_packages.py:34-71` for seeded categories.
- `Role.ADMIN` / `Role.EDITOR` / `Role.REVIEWER` in `backend/tender_backend/core/security.py:24-27`.
- `require_role(Role.ADMIN)` factory in `backend/tender_backend/core/security.py:108-117`.
- "database / templates" tab in `frontend/src/lib/navigation.ts:36-47` — global templates UI lives here.

## Target Flow

- [ ] Each existing `bid_template_package` row is versioned (`version` column, `is_current` flag). Existing rows are seeded as `version=1, is_current=TRUE`.
- [ ] Project template instance creation pins to the current version of the selected package at clone time.
- [ ] A new project starting today gets the latest package version; a project that started before an upgrade keeps its original version.
- [ ] Variant table allows specializations of a package family. Variants are not pre-seeded; they appear when an admin promotes a project modification cluster into a new variant.
- [ ] Project instance creation can select a variant instead of the raw global package; chosen variant's items are used as the clone source.
- [ ] When a project instance is modified and revisions are confirmed, the modifications are eligible for two reflow paths:
  - Active: investor explicitly creates a `template_promotion_proposal` from the workbench.
  - Passive: nightly clustering job groups similar modifications across projects and auto-creates proposals when frequency exceeds threshold.
- [ ] Admin review workbench surfaces all pending proposals with block-level diffs, project provenance, and decision actions: 升级全局新版 / 进入变体新版 / 抽取为新变体 / 拒绝。
- [ ] Decision = approve creates a new version of the target package or variant and marks proposal `approved`.
- [ ] Variants support explicit rebase: admin can ask the system "if I rebase variant X onto package family Y v3, what conflicts will I have?" and resolve them in the same workbench.

## Frontend Workflow Additions

The existing `database / templates` tab is the **global template library**. It needs two new sub-pages:

- `database / templates / families` — list of package families, each shows: latest version, project count using it, variant count.
- `database / templates / variants` — variant browser: tree by family, showing parent version pinning and rebase status.

A new top-level admin module appears for users with `Role.ADMIN`:

- `settings / template-evolution` — admin review workbench. Lives in the existing `settings` module since that's where admin-only configuration lives.

Per-tab content:

- **Family list** (`database/templates/families`): one row per `package_key`. Click to drill into version history with version-to-version diff. Shows "升级" button if the admin queue has approved proposals not yet released.
- **Variant browser** (`database/templates/variants`): tree of family → variants → versions. Each variant card shows: parent version, lag indicator ("基于父版本 v2，父最新 v4"), rebase action.
- **Template evolution workbench** (`settings/template-evolution`): list of pending proposals (manual + clustered), block-level diff view, decision panel.

### Project Creation Flow Updates

The project template selection flow (currently picks a `bid_template_package` via `category_code`) gets a variant picker:

- When a category has variants, the picker first asks "通用模板 / 国网华东变体 / 国网浙江变体..." and then proceeds.
- The chosen variant + its current version are recorded in the project template instance.

## File Structure

### Backend Create

- `backend/tender_backend/db/alembic/versions/0052_template_versioning.py`
  - Adds `version`, `is_current`, `family_id` to `bid_template_package`; backfills existing rows.

- `backend/tender_backend/db/alembic/versions/0053_template_variants.py`
  - Creates `bid_template_variant`, `bid_template_variant_item` tables; extends `project_template_instance` with `base_template_variant_id`, `base_template_version` columns.

- `backend/tender_backend/db/alembic/versions/0054_promotion_proposal_extensions.py`
  - Extends `template_promotion_proposal` with `proposal_kind`, `target_kind`, `target_id`, `cluster_id`, `cluster_size`.
  - Creates `template_modification_cluster` table.

- `backend/tender_backend/db/repositories/bid_template_variant_repo.py`
  - CRUD for variants + variant items.

- `backend/tender_backend/db/repositories/template_evolution_repo.py`
  - Read/write for proposals (extends existing), clusters, and admin queue queries.

- `backend/tender_backend/services/template_diff_service.py`
  - Block-level diff between two snapshots (package version vs project instance, or variant vs package).

- `backend/tender_backend/services/template_promotion_sanitizer.py`
  - Strips project-specific material references from a diff before promotion.

- `backend/tender_backend/services/template_clustering_service.py`
  - Offline batch: group similar block-level modifications across all project instances.

- `backend/tender_backend/services/template_evolution_service.py`
  - Apply a proposal decision: bump package version / create variant / bump variant version.

- `backend/tender_backend/api/template_evolution.py`
  - Admin endpoints: list/approve/reject proposals, trigger clustering manually, manage variants.

- `backend/tender_backend/workflows/run_template_clustering.py`
  - Entry point for the nightly clustering job (intended to be triggered by cron / scheduler).

- `backend/tests/unit/test_template_diff_service.py`
- `backend/tests/unit/test_template_promotion_sanitizer.py`
- `backend/tests/unit/test_template_clustering_service.py`
- `backend/tests/unit/test_template_evolution_service.py`
- `backend/tests/integration/test_template_evolution_api.py`
- `backend/tests/integration/test_template_variants_api.py`

### Backend Modify

- `backend/tender_backend/main.py`
  - Register `template_evolution` router.

- `backend/tender_backend/db/repositories/bid_template_package_repo.py`
  - Add `version`, `is_current`, `family_id` to dataclass and queries.
  - New methods: `list_versions_for_family`, `get_current_version`, `create_new_version`.

- `backend/tender_backend/api/template_packages.py`
  - Default reads return `is_current=TRUE` rows.
  - Add `GET /api/template-packages/{family_id}/versions` for version history.

- `backend/tender_backend/services/project_template_instance_service.py`
  - On project instance creation, pin to the current package version (or selected variant).
  - Store `base_template_package_version` on the instance.

- `backend/tender_backend/services/template_selection_service.py`
  - Selection now considers variants. Returns variant list alongside package list for a category.

### Frontend Create

- `frontend/src/modules/templates/TemplateFamilyList.tsx`
  - Lists package families with version + variant + usage counts.

- `frontend/src/modules/templates/TemplateVariantBrowser.tsx`
  - Tree view: family → variants → versions, with rebase action.

- `frontend/src/modules/templates/TemplateVersionDiff.tsx`
  - Block-level side-by-side diff between two template versions.

- `frontend/src/modules/settings/TemplateEvolutionWorkbench.tsx`
  - Admin review queue + diff view + decision panel.

- `frontend/src/modules/settings/templateEvolutionModel.ts`
  - Pure helpers: classify proposal kind, format decision targets, validate decision payload.

- `frontend/src/modules/settings/templateEvolutionModel.test.ts`
- `frontend/src/modules/settings/TemplateEvolutionWorkbench.test.tsx`
- `frontend/src/modules/templates/TemplateFamilyList.test.tsx`
- `frontend/src/modules/templates/TemplateVariantBrowser.test.tsx`

### Frontend Modify

- `frontend/src/lib/navigation.ts`
  - Add `families` and `variants` sub-tabs to `database/templates`. The existing single `templates` tab becomes a parent or is split — see Task 6 for decision.
  - Add `template-evolution` tab under `settings`.

- `frontend/src/lib/api.ts`
  - Add types and fetchers for: version list, variants, evolution proposals, decisions, clustering trigger.

- `frontend/src/modules/projects/ProjectsModule.tsx`
  - When creating a project, after picking category, if variants exist, show variant picker before continuing.

- `frontend/src/modules/templates/ProjectTemplateWorkbench.tsx`
  - (Created by P1 plan.) Show "基于父模板版本 vX" badge. Show "this revision can be proposed for promotion" CTA after a confirmed revision.

## Data Model

### Modify `bid_template_package` (migration 0052)

Add columns:

- `family_id UUID NOT NULL DEFAULT gen_random_uuid()` — identifies the package family. All versions of a family share this id.
- `version INT NOT NULL DEFAULT 1`
- `is_current BOOLEAN NOT NULL DEFAULT TRUE`

Constraints:

- Drop existing `UNIQUE (package_key)`.
- Add `UNIQUE (package_key, version)`.
- Add `UNIQUE (family_id, version)`.
- Add partial `UNIQUE INDEX template_package_one_current_per_family ON bid_template_package (family_id) WHERE is_current = TRUE`.

Backfill:

- Existing rows get `version = 1`, `is_current = TRUE`, `family_id = gen_random_uuid()` per row.

### Create `bid_template_variant` (migration 0053)

- `id UUID PRIMARY KEY`
- `family_id UUID NOT NULL` — references the package family this variant specializes.
- `variant_key TEXT NOT NULL`
- `display_name TEXT NOT NULL`
- `description TEXT NULL`
- `parent_package_id UUID NOT NULL REFERENCES bid_template_package(id) ON DELETE RESTRICT` — pins to the specific package version this variant was created from.
- `parent_version INT NOT NULL` — denormalized for fast queries.
- `variant_version INT NOT NULL DEFAULT 1`
- `is_current BOOLEAN NOT NULL DEFAULT TRUE`
- `scope_rules_json JSONB NOT NULL DEFAULT '{}'::jsonb` — e.g., `{"招标人": ["国网"], "地区": ["华东"]}`. Used by selection service as hints, not hard filters.
- `metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_by TEXT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Constraints:

- `UNIQUE (family_id, variant_key, variant_version)`
- partial `UNIQUE INDEX template_variant_one_current ON bid_template_variant (family_id, variant_key) WHERE is_current = TRUE`

### Create `bid_template_variant_item` (migration 0053)

Same columns as `bid_template_item` but bound to `variant_id` instead of `package_id`. Specifically:

- `id UUID PRIMARY KEY`
- `variant_id UUID NOT NULL REFERENCES bid_template_variant(id) ON DELETE CASCADE`
- `item_code TEXT NULL`
- `item_name TEXT NOT NULL`
- `filename TEXT NOT NULL`
- `relative_path TEXT NOT NULL`
- `source_kind TEXT NOT NULL`
- `item_type TEXT NOT NULL`
- `render_mode TEXT NOT NULL`
- `is_required BOOLEAN NOT NULL DEFAULT TRUE`
- `sort_order INT NOT NULL DEFAULT 0`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

### Modify `project_template_instance` (migration 0053)

Add columns:

- `base_template_variant_id UUID NULL REFERENCES bid_template_variant(id) ON DELETE SET NULL`
- `base_template_package_version INT NOT NULL DEFAULT 1`
- `base_template_variant_version INT NULL`

Constraint: at most one of `base_template_variant_id` or unmodified package source applies. Enforced in service layer, not DB.

### Extend `template_promotion_proposal` (migration 0054)

Add columns:

- `proposal_kind TEXT NOT NULL DEFAULT 'manual'` — values: `manual`, `clustered`.
- `target_kind TEXT NOT NULL DEFAULT 'package_version'` — values: `package_version`, `variant_version`, `new_variant`.
- `target_family_id UUID NULL` — for `package_version` and `new_variant`.
- `target_variant_id UUID NULL` — for `variant_version`.
- `target_variant_key TEXT NULL` — for `new_variant`.
- `cluster_id UUID NULL REFERENCES template_modification_cluster(id) ON DELETE SET NULL`
- `cluster_size INT NULL`
- `decision_notes TEXT NULL`

### Create `template_modification_cluster` (migration 0054)

- `id UUID PRIMARY KEY`
- `family_id UUID NOT NULL`
- `chapter_signature TEXT NOT NULL` — stable signature of which chapter is being modified.
- `block_signature TEXT NOT NULL` — stable signature of which block within the chapter.
- `change_signature TEXT NOT NULL` — hash of the normalized change content.
- `project_ids UUID[] NOT NULL` — projects exhibiting this change.
- `representative_diff_json JSONB NOT NULL` — a canonical example diff for review.
- `first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `cluster_status TEXT NOT NULL DEFAULT 'open'` — values: `open`, `proposed`, `dismissed`.

Constraint: `UNIQUE (family_id, chapter_signature, block_signature, change_signature)`.

## API Contract

All endpoints under `Role.ADMIN` unless noted.

### Package versioning

- `GET /api/template-packages/families` — list package families with current version, variant count, project usage count. Available to all logged-in users.
- `GET /api/template-packages/families/{family_id}/versions` — list all versions of a family.
- `GET /api/template-packages/{package_id}/diff?against_package_id={other_id}` — block-level diff between two versions.

### Variants

- `GET /api/template-variants?family_id={family_id}` — list variants for a family. All logged-in users.
- `POST /api/template-variants` — create new variant. Admin only.
- `GET /api/template-variants/{variant_id}` — variant detail with items. All logged-in users.
- `POST /api/template-variants/{variant_id}/rebase` — preview/apply rebase onto a newer parent version. Admin only.

### Evolution / Proposals

- `GET /api/template-evolution/proposals` — list pending proposals (manual + clustered), filtered by status. Admin only.
- `GET /api/template-evolution/proposals/{proposal_id}` — proposal detail with diff. Admin only.
- `POST /api/template-evolution/proposals/{proposal_id}/decision` — body: `{decision: "approve" | "reject", target_kind, target_family_id?, target_variant_id?, new_variant_key?, decision_notes?}`. Admin only.
- `POST /api/template-evolution/clustering/run` — trigger clustering job (sync, blocking, intended for manual admin retry). Admin only.
- `GET /api/template-evolution/clusters` — list discovered clusters not yet proposed. Admin only.

### Selection

- `GET /api/template-packages/select?category_code={code}` — updated to return packages plus variants for the category.

## Implementation Tasks

### Task 1: Add Package Versioning

**Files:**
- Create: `backend/tender_backend/db/alembic/versions/0052_template_versioning.py`
- Modify: `backend/tender_backend/db/repositories/bid_template_package_repo.py`
- Test: `backend/tests/unit/test_bid_template_package_repo.py` (extend existing or create if missing)

- [ ] Write repository test: existing package gets `version=1, is_current=TRUE, family_id` populated after migration.
- [ ] Write repository test: `create_new_version(package_id, items)` returns new package row with version N+1, sets old `is_current=FALSE`.
- [ ] Write repository test: `get_current_version(family_id)` returns only the row with `is_current=TRUE`.
- [ ] Run: `cd backend && ../.venv/bin/pytest tests/unit/test_bid_template_package_repo.py -q`
- [ ] Expected initial result: FAIL — repository methods missing, migration not run.
- [ ] Write migration `0052_template_versioning.py`:

```python
"""template_package versioning: family_id, version, is_current

Revision ID: 0052
Revises: 0051
Create Date: 2026-05-14
"""

from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "0052"
down_revision: Union[str, None] = "0051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE bid_template_package
      ADD COLUMN IF NOT EXISTS family_id UUID,
      ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 1,
      ADD COLUMN IF NOT EXISTS is_current BOOLEAN NOT NULL DEFAULT TRUE;
    """)
    op.execute("""
    UPDATE bid_template_package
    SET family_id = gen_random_uuid()
    WHERE family_id IS NULL;
    """)
    op.execute("""
    ALTER TABLE bid_template_package
      ALTER COLUMN family_id SET NOT NULL;
    """)
    op.execute("""
    ALTER TABLE bid_template_package
      DROP CONSTRAINT IF EXISTS bid_template_package_package_key_key;
    """)
    op.execute("""
    ALTER TABLE bid_template_package
      ADD CONSTRAINT bid_template_package_package_key_version_key
        UNIQUE (package_key, version);
    """)
    op.execute("""
    ALTER TABLE bid_template_package
      ADD CONSTRAINT bid_template_package_family_id_version_key
        UNIQUE (family_id, version);
    """)
    op.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS template_package_one_current_per_family
      ON bid_template_package (family_id) WHERE is_current = TRUE;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS template_package_one_current_per_family;")
    op.execute("ALTER TABLE bid_template_package DROP CONSTRAINT IF EXISTS bid_template_package_family_id_version_key;")
    op.execute("ALTER TABLE bid_template_package DROP CONSTRAINT IF EXISTS bid_template_package_package_key_version_key;")
    op.execute("ALTER TABLE bid_template_package ADD CONSTRAINT bid_template_package_package_key_key UNIQUE (package_key);")
    op.execute("""
    ALTER TABLE bid_template_package
      DROP COLUMN IF EXISTS is_current,
      DROP COLUMN IF EXISTS version,
      DROP COLUMN IF EXISTS family_id;
    """)
```

- [ ] Update `BidTemplatePackageRow` dataclass to include `family_id: UUID`, `version: int`, `is_current: bool`.
- [ ] Update `_PACKAGE_COLUMNS` constant and `_to_package` mapper accordingly.
- [ ] Add `list_versions_for_family(conn, *, family_id)`.
- [ ] Add `get_current_version(conn, *, family_id)`.
- [ ] Add `create_new_version(conn, *, family_id, package_key, display_name, package_type, category_code, source_root, source_manifest)` — sets old `is_current=FALSE`, inserts new row with `version = max+1, is_current=TRUE`.
- [ ] Update existing `list_all` to filter `WHERE is_current = TRUE` by default; add `include_history` flag.
- [ ] Rerun tests, confirm PASS.
- [ ] Commit:

```bash
git add backend/tender_backend/db/alembic/versions/0052_template_versioning.py \
  backend/tender_backend/db/repositories/bid_template_package_repo.py \
  backend/tests/unit/test_bid_template_package_repo.py
git commit -m "feat: version template packages with family_id and is_current"
```

### Task 2: Pin Project Template Instances To Package Version

**Files:**
- Create: `backend/tender_backend/db/alembic/versions/0053_template_variants.py` (multi-purpose: also adds variant tables in Task 3; do this part now)
- Modify: `backend/tender_backend/services/project_template_instance_service.py`
- Test: `backend/tests/unit/test_project_template_instance_service.py` (extend)

- [ ] Add migration sections in `0053_template_variants.py` that add `base_template_package_version`, `base_template_variant_id`, `base_template_variant_version` to `project_template_instance`:

```python
op.execute("""
ALTER TABLE project_template_instance
  ADD COLUMN IF NOT EXISTS base_template_package_version INT NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS base_template_variant_id UUID NULL,
  ADD COLUMN IF NOT EXISTS base_template_variant_version INT NULL;
""")
```

(Full migration body added in Task 3.)

- [ ] Write test: `ensure_for_project` records `base_template_package_version = <current version at clone time>`.
- [ ] Write test: if package family is later upgraded, existing instance still reflects the old `base_template_package_version`.
- [ ] Run tests. Expected: FAIL (service does not yet read version).
- [ ] Update `ProjectTemplateInstanceService.ensure_for_project` to call `BidTemplatePackageRepository.get_current_version(family_id=...)` after resolving the family from the selected package id, then store the resolved version into the instance row.
- [ ] Update `project_template_instance_repo.create_instance` signature to accept `base_template_package_version: int` and persist it.
- [ ] Rerun tests, confirm PASS.
- [ ] Commit:

```bash
git add backend/tender_backend/db/alembic/versions/0053_template_variants.py \
  backend/tender_backend/services/project_template_instance_service.py \
  backend/tender_backend/db/repositories/project_template_instance_repo.py \
  backend/tests/unit/test_project_template_instance_service.py
git commit -m "feat: pin project template instances to package version"
```

### Task 3: Add Template Variant Tables And Repository

**Files:**
- Modify: `backend/tender_backend/db/alembic/versions/0053_template_variants.py` (complete the migration)
- Create: `backend/tender_backend/db/repositories/bid_template_variant_repo.py`
- Create: `backend/tests/unit/test_bid_template_variant_repo.py`

- [ ] Write repository test: creating a variant clones the parent package's items into `bid_template_variant_item` rows.
- [ ] Write repository test: creating variant version 2 sets variant version 1's `is_current=FALSE`.
- [ ] Write repository test: `list_variants_for_family(family_id)` returns only `is_current=TRUE` rows by default.
- [ ] Run tests. Expected: FAIL — tables missing.
- [ ] Complete migration `0053_template_variants.py`:

```python
"""template variants and project instance variant pinning

Revision ID: 0053
Revises: 0052
Create Date: 2026-05-14
"""

from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "0053"
down_revision: Union[str, None] = "0052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS bid_template_variant (
      id UUID PRIMARY KEY,
      family_id UUID NOT NULL,
      variant_key TEXT NOT NULL,
      display_name TEXT NOT NULL,
      description TEXT NULL,
      parent_package_id UUID NOT NULL REFERENCES bid_template_package(id) ON DELETE RESTRICT,
      parent_version INT NOT NULL,
      variant_version INT NOT NULL DEFAULT 1,
      is_current BOOLEAN NOT NULL DEFAULT TRUE,
      scope_rules_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_by TEXT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS template_variant_family_key_version
      ON bid_template_variant (family_id, variant_key, variant_version);
    """)
    op.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS template_variant_one_current
      ON bid_template_variant (family_id, variant_key) WHERE is_current = TRUE;
    """)
    op.execute("""
    CREATE TABLE IF NOT EXISTS bid_template_variant_item (
      id UUID PRIMARY KEY,
      variant_id UUID NOT NULL REFERENCES bid_template_variant(id) ON DELETE CASCADE,
      item_code TEXT NULL,
      item_name TEXT NOT NULL,
      filename TEXT NOT NULL,
      relative_path TEXT NOT NULL,
      source_kind TEXT NOT NULL,
      item_type TEXT NOT NULL,
      render_mode TEXT NOT NULL,
      is_required BOOLEAN NOT NULL DEFAULT TRUE,
      sort_order INT NOT NULL DEFAULT 0,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("""
    ALTER TABLE project_template_instance
      ADD COLUMN IF NOT EXISTS base_template_package_version INT NOT NULL DEFAULT 1,
      ADD COLUMN IF NOT EXISTS base_template_variant_id UUID NULL,
      ADD COLUMN IF NOT EXISTS base_template_variant_version INT NULL;
    """)
    op.execute("""
    ALTER TABLE project_template_instance
      ADD CONSTRAINT project_template_instance_base_variant_fkey
        FOREIGN KEY (base_template_variant_id)
        REFERENCES bid_template_variant(id) ON DELETE SET NULL;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE project_template_instance DROP CONSTRAINT IF EXISTS project_template_instance_base_variant_fkey;")
    op.execute("""
    ALTER TABLE project_template_instance
      DROP COLUMN IF EXISTS base_template_variant_version,
      DROP COLUMN IF EXISTS base_template_variant_id,
      DROP COLUMN IF EXISTS base_template_package_version;
    """)
    op.execute("DROP TABLE IF EXISTS bid_template_variant_item;")
    op.execute("DROP INDEX IF EXISTS template_variant_one_current;")
    op.execute("DROP INDEX IF EXISTS template_variant_family_key_version;")
    op.execute("DROP TABLE IF EXISTS bid_template_variant;")
```

- [ ] Implement `bid_template_variant_repo.py` following the pattern of `bid_template_package_repo.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row


@dataclass(frozen=True)
class BidTemplateVariantRow:
    id: UUID
    family_id: UUID
    variant_key: str
    display_name: str
    description: str | None
    parent_package_id: UUID
    parent_version: int
    variant_version: int
    is_current: bool
    scope_rules_json: dict[str, Any]
    metadata_json: dict[str, Any]
    created_by: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class BidTemplateVariantItemRow:
    id: UUID
    variant_id: UUID
    item_code: str | None
    item_name: str
    filename: str
    relative_path: str
    source_kind: str
    item_type: str
    render_mode: str
    is_required: bool
    sort_order: int
    created_at: datetime


_VARIANT_COLUMNS = (
    "id, family_id, variant_key, display_name, description, parent_package_id, "
    "parent_version, variant_version, is_current, scope_rules_json, metadata_json, "
    "created_by, created_at, updated_at"
)
_VARIANT_ITEM_COLUMNS = (
    "id, variant_id, item_code, item_name, filename, relative_path, source_kind, "
    "item_type, render_mode, is_required, sort_order, created_at"
)


def _to_variant(row: dict[str, Any]) -> BidTemplateVariantRow:
    return BidTemplateVariantRow(
        id=row["id"],
        family_id=row["family_id"],
        variant_key=row["variant_key"],
        display_name=row["display_name"],
        description=row.get("description"),
        parent_package_id=row["parent_package_id"],
        parent_version=row["parent_version"],
        variant_version=row["variant_version"],
        is_current=row["is_current"],
        scope_rules_json=dict(row["scope_rules_json"] or {}),
        metadata_json=dict(row["metadata_json"] or {}),
        created_by=row.get("created_by"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class BidTemplateVariantRepository:
    def list_variants_for_family(
        self, conn: Connection, *, family_id: UUID, include_history: bool = False
    ) -> list[BidTemplateVariantRow]:
        sql = f"SELECT {_VARIANT_COLUMNS} FROM bid_template_variant WHERE family_id = %s"
        if not include_history:
            sql += " AND is_current = TRUE"
        sql += " ORDER BY display_name, variant_version DESC"
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(sql, (family_id,)).fetchall()
        return [_to_variant(r) for r in rows]

    def get_current_variant(
        self, conn: Connection, *, family_id: UUID, variant_key: str
    ) -> BidTemplateVariantRow | None:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                f"""
                SELECT {_VARIANT_COLUMNS} FROM bid_template_variant
                WHERE family_id = %s AND variant_key = %s AND is_current = TRUE
                """,
                (family_id, variant_key),
            ).fetchone()
        return _to_variant(row) if row else None

    def create_variant(
        self,
        conn: Connection,
        *,
        family_id: UUID,
        variant_key: str,
        display_name: str,
        description: str | None,
        parent_package_id: UUID,
        parent_version: int,
        scope_rules_json: dict[str, Any],
        metadata_json: dict[str, Any],
        created_by: str | None,
    ) -> BidTemplateVariantRow:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE bid_template_variant
                SET is_current = FALSE, updated_at = now()
                WHERE family_id = %s AND variant_key = %s AND is_current = TRUE
                """,
                (family_id, variant_key),
            )
            cur.execute(
                """
                SELECT COALESCE(MAX(variant_version), 0) AS max_version
                FROM bid_template_variant
                WHERE family_id = %s AND variant_key = %s
                """,
                (family_id, variant_key),
            )
            max_version_row = cur.fetchone()
            new_version = int(max_version_row["max_version"]) + 1
            row = cur.execute(
                f"""
                INSERT INTO bid_template_variant (
                  id, family_id, variant_key, display_name, description,
                  parent_package_id, parent_version, variant_version, is_current,
                  scope_rules_json, metadata_json, created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s::jsonb, %s::jsonb, %s)
                RETURNING {_VARIANT_COLUMNS}
                """,
                (
                    uuid4(), family_id, variant_key, display_name, description,
                    parent_package_id, parent_version, new_version,
                    __import__("json").dumps(scope_rules_json, ensure_ascii=False),
                    __import__("json").dumps(metadata_json, ensure_ascii=False),
                    created_by,
                ),
            ).fetchone()
        assert row is not None
        return _to_variant(row)

    def clone_items_from_package(
        self, conn: Connection, *, variant_id: UUID, source_package_id: UUID
    ) -> int:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bid_template_variant_item (
                  id, variant_id, item_code, item_name, filename, relative_path,
                  source_kind, item_type, render_mode, is_required, sort_order
                )
                SELECT gen_random_uuid(), %s, item_code, item_name, filename,
                       relative_path, source_kind, item_type, render_mode,
                       is_required, sort_order
                FROM bid_template_item
                WHERE package_id = %s
                """,
                (variant_id, source_package_id),
            )
            return cur.rowcount

    def list_items(self, conn: Connection, *, variant_id: UUID) -> list[BidTemplateVariantItemRow]:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"SELECT {_VARIANT_ITEM_COLUMNS} FROM bid_template_variant_item "
                "WHERE variant_id = %s ORDER BY sort_order, filename",
                (variant_id,),
            ).fetchall()
        return [
            BidTemplateVariantItemRow(
                id=r["id"], variant_id=r["variant_id"], item_code=r["item_code"],
                item_name=r["item_name"], filename=r["filename"],
                relative_path=r["relative_path"], source_kind=r["source_kind"],
                item_type=r["item_type"], render_mode=r["render_mode"],
                is_required=r["is_required"], sort_order=r["sort_order"],
                created_at=r["created_at"],
            )
            for r in rows
        ]
```

- [ ] Rerun tests, confirm PASS.
- [ ] Commit:

```bash
git add backend/tender_backend/db/alembic/versions/0053_template_variants.py \
  backend/tender_backend/db/repositories/bid_template_variant_repo.py \
  backend/tests/unit/test_bid_template_variant_repo.py
git commit -m "feat: add template variant tables and repository"
```

### Task 4: Block-Level Template Diff Service

**Files:**
- Create: `backend/tender_backend/services/template_diff_service.py`
- Create: `backend/tests/unit/test_template_diff_service.py`

- [ ] Write unit test: diff between identical snapshots returns empty list.
- [ ] Write unit test: adding a block in instance vs package produces a `block_added` entry with full content.
- [ ] Write unit test: removing a block produces `block_removed`.
- [ ] Write unit test: modifying `content_text` produces `block_modified` with `before`/`after` fields.
- [ ] Write unit test: reordering blocks within the same chapter produces `block_reordered`.
- [ ] Write unit test: chapter title change produces `chapter_modified`.
- [ ] Write unit test: blocks are matched by `(chapter_code, block_type, label)` tuple; identical content survives unchanged-position reorders.
- [ ] Run: `cd backend && ../.venv/bin/pytest tests/unit/test_template_diff_service.py -q`
- [ ] Expected: FAIL — file missing.
- [ ] Implement `template_diff_service.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

DiffKind = Literal[
    "chapter_added", "chapter_removed", "chapter_modified", "chapter_reordered",
    "block_added", "block_removed", "block_modified", "block_reordered",
]


@dataclass(frozen=True)
class BlockSnapshot:
    chapter_code: str
    block_label: str
    block_type: str
    sort_order: int
    content_text: str
    prompt_text: str
    placeholder_key: str | None
    render_options_json: dict[str, Any] = field(default_factory=dict)
    condition_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChapterSnapshot:
    chapter_code: str
    chapter_title: str
    volume_type: str
    sort_order: int
    blocks: list[BlockSnapshot]


@dataclass(frozen=True)
class DiffEntry:
    kind: DiffKind
    chapter_code: str
    block_label: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None


class TemplateDiffService:
    def diff(
        self,
        *,
        before: list[ChapterSnapshot],
        after: list[ChapterSnapshot],
    ) -> list[DiffEntry]:
        before_by_code = {c.chapter_code: c for c in before}
        after_by_code = {c.chapter_code: c for c in after}
        entries: list[DiffEntry] = []
        for code, after_ch in after_by_code.items():
            before_ch = before_by_code.get(code)
            if before_ch is None:
                entries.append(DiffEntry(
                    kind="chapter_added", chapter_code=code, block_label=None,
                    before=None, after=self._chapter_to_dict(after_ch),
                ))
                continue
            entries.extend(self._diff_chapter(before_ch, after_ch))
        for code, before_ch in before_by_code.items():
            if code not in after_by_code:
                entries.append(DiffEntry(
                    kind="chapter_removed", chapter_code=code, block_label=None,
                    before=self._chapter_to_dict(before_ch), after=None,
                ))
        return entries

    def _diff_chapter(
        self, before: ChapterSnapshot, after: ChapterSnapshot
    ) -> list[DiffEntry]:
        entries: list[DiffEntry] = []
        if (before.chapter_title, before.volume_type) != (after.chapter_title, after.volume_type):
            entries.append(DiffEntry(
                kind="chapter_modified", chapter_code=after.chapter_code,
                block_label=None,
                before={"chapter_title": before.chapter_title, "volume_type": before.volume_type},
                after={"chapter_title": after.chapter_title, "volume_type": after.volume_type},
            ))
        if before.sort_order != after.sort_order:
            entries.append(DiffEntry(
                kind="chapter_reordered", chapter_code=after.chapter_code,
                block_label=None,
                before={"sort_order": before.sort_order},
                after={"sort_order": after.sort_order},
            ))
        before_blocks = {(b.block_label, b.block_type): b for b in before.blocks}
        after_blocks = {(b.block_label, b.block_type): b for b in after.blocks}
        for key, after_b in after_blocks.items():
            before_b = before_blocks.get(key)
            if before_b is None:
                entries.append(DiffEntry(
                    kind="block_added", chapter_code=after.chapter_code,
                    block_label=after_b.block_label,
                    before=None, after=self._block_to_dict(after_b),
                ))
                continue
            if self._block_content_differs(before_b, after_b):
                entries.append(DiffEntry(
                    kind="block_modified", chapter_code=after.chapter_code,
                    block_label=after_b.block_label,
                    before=self._block_to_dict(before_b),
                    after=self._block_to_dict(after_b),
                ))
            elif before_b.sort_order != after_b.sort_order:
                entries.append(DiffEntry(
                    kind="block_reordered", chapter_code=after.chapter_code,
                    block_label=after_b.block_label,
                    before={"sort_order": before_b.sort_order},
                    after={"sort_order": after_b.sort_order},
                ))
        for key, before_b in before_blocks.items():
            if key not in after_blocks:
                entries.append(DiffEntry(
                    kind="block_removed", chapter_code=after.chapter_code,
                    block_label=before_b.block_label,
                    before=self._block_to_dict(before_b), after=None,
                ))
        return entries

    @staticmethod
    def _block_content_differs(a: BlockSnapshot, b: BlockSnapshot) -> bool:
        return (
            a.content_text != b.content_text
            or a.prompt_text != b.prompt_text
            or a.placeholder_key != b.placeholder_key
            or a.render_options_json != b.render_options_json
            or a.condition_json != b.condition_json
        )

    @staticmethod
    def _chapter_to_dict(ch: ChapterSnapshot) -> dict[str, Any]:
        return {
            "chapter_code": ch.chapter_code,
            "chapter_title": ch.chapter_title,
            "volume_type": ch.volume_type,
            "sort_order": ch.sort_order,
        }

    @staticmethod
    def _block_to_dict(b: BlockSnapshot) -> dict[str, Any]:
        return {
            "block_label": b.block_label,
            "block_type": b.block_type,
            "sort_order": b.sort_order,
            "content_text": b.content_text,
            "prompt_text": b.prompt_text,
            "placeholder_key": b.placeholder_key,
            "render_options_json": b.render_options_json,
            "condition_json": b.condition_json,
        }
```

- [ ] Rerun tests, confirm PASS.
- [ ] Commit:

```bash
git add backend/tender_backend/services/template_diff_service.py \
  backend/tests/unit/test_template_diff_service.py
git commit -m "feat: block-level template diff service"
```

### Task 5: Promotion Sanitizer (Strip Project-Specific Material)

**Files:**
- Create: `backend/tender_backend/services/template_promotion_sanitizer.py`
- Create: `backend/tests/unit/test_template_promotion_sanitizer.py`

- [ ] Write test: a `block_modified` entry where `after.content_text` contains a project material reference (e.g., `[业绩:proj_abc_123]`) has the reference replaced with `[业绩:占位符]` in the sanitized output.
- [ ] Write test: `placeholder_key` like `project_proj_xyz_team_lead_001` is normalized to `team_lead_<n>` form.
- [ ] Write test: `condition_json` references to specific project IDs are stripped to type tokens.
- [ ] Write test: pure structural changes (added/removed/reordered blocks) pass through unchanged.
- [ ] Write test: fixed text without material references passes through unchanged.
- [ ] Run: `cd backend && ../.venv/bin/pytest tests/unit/test_template_promotion_sanitizer.py -q`
- [ ] Expected: FAIL — file missing.
- [ ] Implement `template_promotion_sanitizer.py`:

```python
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from tender_backend.services.template_diff_service import DiffEntry

_PROJECT_MATERIAL_REF = re.compile(r"\[(?P<kind>业绩|人员|资质|设备|公司):[^\]]+\]")
_PROJECT_PLACEHOLDER = re.compile(r"^project_[a-zA-Z0-9_-]+?_(?P<suffix>[a-zA-Z_]+)_(?P<idx>\d+)$")


def _sanitize_text(text: str) -> str:
    return _PROJECT_MATERIAL_REF.sub(lambda m: f"[{m.group('kind')}:占位符]", text)


def _sanitize_placeholder_key(key: str | None) -> str | None:
    if key is None:
        return None
    m = _PROJECT_PLACEHOLDER.match(key)
    if not m:
        return key
    return f"{m.group('suffix')}_{m.group('idx')}"


def _sanitize_condition(cond: dict[str, Any]) -> dict[str, Any]:
    if not cond:
        return cond
    cleaned = deepcopy(cond)
    for key in list(cleaned.keys()):
        value = cleaned[key]
        if isinstance(value, str) and value.startswith("project_"):
            cleaned[key] = "<project_specific>"
        elif isinstance(value, dict):
            cleaned[key] = _sanitize_condition(value)
    return cleaned


def _sanitize_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    sanitized = deepcopy(payload)
    if "content_text" in sanitized and isinstance(sanitized["content_text"], str):
        sanitized["content_text"] = _sanitize_text(sanitized["content_text"])
    if "prompt_text" in sanitized and isinstance(sanitized["prompt_text"], str):
        sanitized["prompt_text"] = _sanitize_text(sanitized["prompt_text"])
    if "placeholder_key" in sanitized:
        sanitized["placeholder_key"] = _sanitize_placeholder_key(sanitized["placeholder_key"])
    if "condition_json" in sanitized and isinstance(sanitized["condition_json"], dict):
        sanitized["condition_json"] = _sanitize_condition(sanitized["condition_json"])
    return sanitized


class TemplatePromotionSanitizer:
    def sanitize(self, entries: list[DiffEntry]) -> list[DiffEntry]:
        return [
            DiffEntry(
                kind=e.kind,
                chapter_code=e.chapter_code,
                block_label=e.block_label,
                before=_sanitize_payload(e.before),
                after=_sanitize_payload(e.after),
            )
            for e in entries
        ]
```

- [ ] Rerun tests, confirm PASS.
- [ ] Commit:

```bash
git add backend/tender_backend/services/template_promotion_sanitizer.py \
  backend/tests/unit/test_template_promotion_sanitizer.py
git commit -m "feat: sanitize project-specific refs from promotion diffs"
```

### Task 6: Promotion Proposal Extensions And Clustering

**Files:**
- Create: `backend/tender_backend/db/alembic/versions/0054_promotion_proposal_extensions.py`
- Create: `backend/tender_backend/db/repositories/template_evolution_repo.py`
- Create: `backend/tender_backend/services/template_clustering_service.py`
- Create: `backend/tests/unit/test_template_clustering_service.py`

- [ ] Write clustering test: two project instances modifying the same `(chapter_code, block_label, content_text→content_text')` produce one cluster with `cluster_size = 2`.
- [ ] Write clustering test: three projects each making a different modification to the same block produce three distinct clusters of size 1.
- [ ] Write clustering test: re-running clustering on the same data merges into existing clusters (idempotent), not duplicates.
- [ ] Write clustering test: cluster with `cluster_size >= threshold` (default 3) auto-generates a `template_promotion_proposal` with `proposal_kind='clustered'`.
- [ ] Run: `cd backend && ../.venv/bin/pytest tests/unit/test_template_clustering_service.py -q`
- [ ] Expected: FAIL — migration/service missing.
- [ ] Write migration `0054_promotion_proposal_extensions.py`:

```python
"""promotion proposal extensions and modification clusters

Revision ID: 0054
Revises: 0053
Create Date: 2026-05-14
"""

from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "0054"
down_revision: Union[str, None] = "0053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS template_modification_cluster (
      id UUID PRIMARY KEY,
      family_id UUID NOT NULL,
      chapter_signature TEXT NOT NULL,
      block_signature TEXT NOT NULL,
      change_signature TEXT NOT NULL,
      project_ids UUID[] NOT NULL,
      representative_diff_json JSONB NOT NULL,
      first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      cluster_status TEXT NOT NULL DEFAULT 'open'
    );
    """)
    op.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS template_modification_cluster_signature_key
      ON template_modification_cluster (family_id, chapter_signature, block_signature, change_signature);
    """)
    op.execute("""
    ALTER TABLE template_promotion_proposal
      ADD COLUMN IF NOT EXISTS proposal_kind TEXT NOT NULL DEFAULT 'manual',
      ADD COLUMN IF NOT EXISTS target_kind TEXT NOT NULL DEFAULT 'package_version',
      ADD COLUMN IF NOT EXISTS target_family_id UUID NULL,
      ADD COLUMN IF NOT EXISTS target_variant_id UUID NULL,
      ADD COLUMN IF NOT EXISTS target_variant_key TEXT NULL,
      ADD COLUMN IF NOT EXISTS cluster_id UUID NULL,
      ADD COLUMN IF NOT EXISTS cluster_size INT NULL,
      ADD COLUMN IF NOT EXISTS decision_notes TEXT NULL;
    """)
    op.execute("""
    ALTER TABLE template_promotion_proposal
      ADD CONSTRAINT template_promotion_proposal_cluster_id_fkey
      FOREIGN KEY (cluster_id) REFERENCES template_modification_cluster(id) ON DELETE SET NULL;
    """)
    op.execute("""
    ALTER TABLE template_promotion_proposal
      ADD CONSTRAINT template_promotion_proposal_target_variant_fkey
      FOREIGN KEY (target_variant_id) REFERENCES bid_template_variant(id) ON DELETE SET NULL;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE template_promotion_proposal DROP CONSTRAINT IF EXISTS template_promotion_proposal_target_variant_fkey;")
    op.execute("ALTER TABLE template_promotion_proposal DROP CONSTRAINT IF EXISTS template_promotion_proposal_cluster_id_fkey;")
    op.execute("""
    ALTER TABLE template_promotion_proposal
      DROP COLUMN IF EXISTS decision_notes,
      DROP COLUMN IF EXISTS cluster_size,
      DROP COLUMN IF EXISTS cluster_id,
      DROP COLUMN IF EXISTS target_variant_key,
      DROP COLUMN IF EXISTS target_variant_id,
      DROP COLUMN IF EXISTS target_family_id,
      DROP COLUMN IF EXISTS target_kind,
      DROP COLUMN IF EXISTS proposal_kind;
    """)
    op.execute("DROP INDEX IF EXISTS template_modification_cluster_signature_key;")
    op.execute("DROP TABLE IF EXISTS template_modification_cluster;")
```

- [ ] Implement `template_evolution_repo.py` with these methods:
  - `list_pending_proposals(conn, *, family_id=None, kind=None)`
  - `get_proposal(conn, *, proposal_id) -> ProposalRow`
  - `update_proposal_decision(conn, *, proposal_id, status, decision_notes, reviewed_by)`
  - `upsert_cluster(conn, *, family_id, chapter_signature, block_signature, change_signature, project_ids, representative_diff_json) -> ClusterRow` — INSERT ... ON CONFLICT updates `project_ids` (set union) and `last_seen_at`.
  - `list_open_clusters(conn, *, family_id=None)`
  - `mark_cluster_proposed(conn, *, cluster_id, proposal_id)`
  - `create_clustered_proposal(conn, *, cluster_id, family_id, target_kind, diff_json, cluster_size)` — returns proposal id.
- [ ] Implement `template_clustering_service.py`:

```python
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from psycopg import Connection

from tender_backend.db.repositories.template_evolution_repo import (
    TemplateEvolutionRepository,
)
from tender_backend.services.template_diff_service import DiffEntry


def _signature(payload: dict | str | None) -> str:
    if payload is None:
        return "null"
    s = json.dumps(payload, sort_keys=True, ensure_ascii=False) if isinstance(payload, dict) else payload
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ClusteringInput:
    project_id: UUID
    family_id: UUID
    diff: list[DiffEntry]


@dataclass(frozen=True)
class ClusteringResult:
    clusters_created_or_updated: int
    proposals_created: int


class TemplateClusteringService:
    def __init__(self, repo: TemplateEvolutionRepository, *, propose_threshold: int = 3) -> None:
        self._repo = repo
        self._propose_threshold = propose_threshold

    def cluster(
        self, conn: Connection, inputs: list[ClusteringInput]
    ) -> ClusteringResult:
        cluster_updates = 0
        proposals = 0
        cluster_aggregation: dict[tuple[UUID, str, str, str], dict] = {}
        for inp in inputs:
            for entry in inp.diff:
                if entry.kind not in {"block_modified", "block_added", "block_removed"}:
                    continue
                chapter_sig = _signature(entry.chapter_code)
                block_sig = _signature(entry.block_label or "")
                change_sig = _signature({
                    "kind": entry.kind,
                    "after": entry.after,
                    "before": entry.before,
                })
                key = (inp.family_id, chapter_sig, block_sig, change_sig)
                bucket = cluster_aggregation.setdefault(key, {
                    "family_id": inp.family_id,
                    "chapter_signature": chapter_sig,
                    "block_signature": block_sig,
                    "change_signature": change_sig,
                    "project_ids": [],
                    "representative_diff_json": {
                        "kind": entry.kind,
                        "chapter_code": entry.chapter_code,
                        "block_label": entry.block_label,
                        "before": entry.before,
                        "after": entry.after,
                    },
                })
                if inp.project_id not in bucket["project_ids"]:
                    bucket["project_ids"].append(inp.project_id)
        for bucket in cluster_aggregation.values():
            cluster = self._repo.upsert_cluster(
                conn,
                family_id=bucket["family_id"],
                chapter_signature=bucket["chapter_signature"],
                block_signature=bucket["block_signature"],
                change_signature=bucket["change_signature"],
                project_ids=bucket["project_ids"],
                representative_diff_json=bucket["representative_diff_json"],
            )
            cluster_updates += 1
            if (
                len(bucket["project_ids"]) >= self._propose_threshold
                and cluster.cluster_status == "open"
            ):
                proposal_id = self._repo.create_clustered_proposal(
                    conn,
                    cluster_id=cluster.id,
                    family_id=cluster.family_id,
                    target_kind="package_version",
                    diff_json=bucket["representative_diff_json"],
                    cluster_size=len(bucket["project_ids"]),
                )
                self._repo.mark_cluster_proposed(
                    conn, cluster_id=cluster.id, proposal_id=proposal_id
                )
                proposals += 1
        return ClusteringResult(
            clusters_created_or_updated=cluster_updates,
            proposals_created=proposals,
        )
```

- [ ] Rerun tests, confirm PASS.
- [ ] Commit:

```bash
git add backend/tender_backend/db/alembic/versions/0054_promotion_proposal_extensions.py \
  backend/tender_backend/db/repositories/template_evolution_repo.py \
  backend/tender_backend/services/template_clustering_service.py \
  backend/tests/unit/test_template_clustering_service.py
git commit -m "feat: add modification clustering and proposal extensions"
```

### Task 7: Template Evolution Service (Apply Decisions)

**Files:**
- Create: `backend/tender_backend/services/template_evolution_service.py`
- Create: `backend/tests/unit/test_template_evolution_service.py`

- [ ] Write test: applying a decision `target_kind=package_version` creates a new package version (`version=current+1`, `is_current=TRUE`), copies items from previous version, applies sanitized diff entries.
- [ ] Write test: applying `target_kind=variant_version` creates a new variant version (`variant_version=current+1`, `is_current=TRUE`).
- [ ] Write test: applying `target_kind=new_variant` requires `target_family_id` + `new_variant_key`; creates `bid_template_variant` row at version 1 and clones items from current parent package, then applies diff.
- [ ] Write test: decision marks proposal `status=approved`, writes `decision_notes` and `reviewed_by`.
- [ ] Write test: rejecting a proposal marks `status=rejected` with notes; no package mutation.
- [ ] Write test: applying when sanitizer detects unresolved project-specific reference raises an error and does not mutate.
- [ ] Run: `cd backend && ../.venv/bin/pytest tests/unit/test_template_evolution_service.py -q`
- [ ] Expected: FAIL — service missing.
- [ ] Implement `template_evolution_service.py` with class `TemplateEvolutionService`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from psycopg import Connection

from tender_backend.db.repositories.bid_template_package_repo import (
    BidTemplatePackageRepository,
)
from tender_backend.db.repositories.bid_template_variant_repo import (
    BidTemplateVariantRepository,
)
from tender_backend.db.repositories.template_evolution_repo import (
    TemplateEvolutionRepository,
)
from tender_backend.services.template_diff_service import DiffEntry
from tender_backend.services.template_promotion_sanitizer import (
    TemplatePromotionSanitizer,
)

Decision = Literal["approve", "reject"]
TargetKind = Literal["package_version", "variant_version", "new_variant"]


@dataclass(frozen=True)
class DecisionRequest:
    proposal_id: UUID
    decision: Decision
    target_kind: TargetKind | None
    target_family_id: UUID | None
    target_variant_id: UUID | None
    new_variant_key: str | None
    new_variant_display_name: str | None
    decision_notes: str | None
    reviewed_by: str


class TemplateEvolutionService:
    def __init__(
        self,
        *,
        evolution_repo: TemplateEvolutionRepository,
        package_repo: BidTemplatePackageRepository,
        variant_repo: BidTemplateVariantRepository,
        sanitizer: TemplatePromotionSanitizer,
    ) -> None:
        self._evolution = evolution_repo
        self._packages = package_repo
        self._variants = variant_repo
        self._sanitizer = sanitizer

    def apply_decision(self, conn: Connection, req: DecisionRequest) -> None:
        proposal = self._evolution.get_proposal(conn, proposal_id=req.proposal_id)
        if proposal is None:
            raise ValueError("proposal not found")
        if proposal.proposal_status != "draft" and proposal.proposal_status != "submitted":
            raise ValueError(f"proposal is already {proposal.proposal_status}")
        if req.decision == "reject":
            self._evolution.update_proposal_decision(
                conn,
                proposal_id=req.proposal_id,
                status="rejected",
                decision_notes=req.decision_notes,
                reviewed_by=req.reviewed_by,
            )
            return
        if req.target_kind is None:
            raise ValueError("target_kind required for approve")
        diff_entries = [
            DiffEntry(**e) if isinstance(e, dict) else e
            for e in proposal.diff_json.get("entries", [])
        ]
        sanitized = self._sanitizer.sanitize(diff_entries)
        if req.target_kind == "package_version":
            self._apply_to_package(conn, proposal=proposal, sanitized=sanitized)
        elif req.target_kind == "variant_version":
            self._apply_to_variant(conn, proposal=proposal, sanitized=sanitized,
                                   variant_id=req.target_variant_id)
        elif req.target_kind == "new_variant":
            self._create_variant(conn, proposal=proposal, sanitized=sanitized, req=req)
        else:
            raise ValueError(f"unknown target_kind {req.target_kind}")
        self._evolution.update_proposal_decision(
            conn,
            proposal_id=req.proposal_id,
            status="approved",
            decision_notes=req.decision_notes,
            reviewed_by=req.reviewed_by,
        )

    def _apply_to_package(self, conn, *, proposal, sanitized):
        family_id = proposal.target_family_id
        if family_id is None and proposal.base_template_package_id is not None:
            base_pkg = self._packages.get_by_id(conn, package_id=proposal.base_template_package_id)
            family_id = base_pkg.family_id if base_pkg else None
        if family_id is None:
            raise ValueError("target_family_id missing")
        current = self._packages.get_current_version(conn, family_id=family_id)
        if current is None:
            raise ValueError("family has no current version")
        new_pkg = self._packages.create_new_version(
            conn,
            family_id=family_id,
            package_key=current.package_key,
            display_name=current.display_name,
            package_type=current.package_type,
            category_code=current.category_code,
            source_root=current.source_root,
            source_manifest=current.source_manifest,
        )
        self._copy_items_with_diff(
            conn, source_pkg_id=current.id, target_pkg_id=new_pkg.id, sanitized=sanitized
        )

    def _apply_to_variant(self, conn, *, proposal, sanitized, variant_id):
        if variant_id is None:
            raise ValueError("target_variant_id required")
        # Implementation parallel to _apply_to_package using variant_repo.
        # (Test-driven; expand here when the corresponding test runs.)
        raise NotImplementedError("variant_version application — implement in this task")

    def _create_variant(self, conn, *, proposal, sanitized, req):
        if req.target_family_id is None or req.new_variant_key is None:
            raise ValueError("target_family_id and new_variant_key required")
        current_pkg = self._packages.get_current_version(conn, family_id=req.target_family_id)
        if current_pkg is None:
            raise ValueError("family has no current version")
        variant = self._variants.create_variant(
            conn,
            family_id=req.target_family_id,
            variant_key=req.new_variant_key,
            display_name=req.new_variant_display_name or req.new_variant_key,
            description=None,
            parent_package_id=current_pkg.id,
            parent_version=current_pkg.version,
            scope_rules_json={},
            metadata_json={},
            created_by=req.reviewed_by,
        )
        self._variants.clone_items_from_package(
            conn, variant_id=variant.id, source_package_id=current_pkg.id
        )
        # Apply diff entries to the cloned variant items.
        # (Test-driven; expand here when the corresponding test runs.)

    def _copy_items_with_diff(self, conn, *, source_pkg_id, target_pkg_id, sanitized):
        # Copy bid_template_item rows from source to target package.
        # Then for each sanitized DiffEntry, apply the change to target's items.
        # (Test-driven; expand here when the corresponding test runs.)
        raise NotImplementedError("apply diff to target package — implement in this task")
```

- [ ] Replace the `raise NotImplementedError` stubs with real implementations driven by the tests written at the top of this task. The tests dictate the exact item-level mutations.
- [ ] Rerun tests, confirm PASS.
- [ ] Commit:

```bash
git add backend/tender_backend/services/template_evolution_service.py \
  backend/tests/unit/test_template_evolution_service.py
git commit -m "feat: apply template evolution decisions"
```

### Task 8: Template Evolution API

**Files:**
- Create: `backend/tender_backend/api/template_evolution.py`
- Modify: `backend/tender_backend/main.py`
- Create: `backend/tests/integration/test_template_evolution_api.py`
- Create: `backend/tests/integration/test_template_variants_api.py`

- [ ] Write integration tests covering:
  - `GET /api/template-packages/families` returns one entry per family with version + variant + usage counts.
  - `GET /api/template-packages/families/{family_id}/versions` returns version history sorted descending.
  - `GET /api/template-variants?family_id=...` returns only `is_current` variants.
  - `POST /api/template-variants` creates a variant (admin only; editor gets 403).
  - `GET /api/template-evolution/proposals` lists pending proposals (admin only).
  - `POST /api/template-evolution/proposals/{id}/decision` with `decision=reject` marks rejected.
  - `POST /api/template-evolution/proposals/{id}/decision` with `decision=approve` + `target_kind=package_version` bumps package version.
  - `POST /api/template-evolution/clustering/run` invokes clustering (admin only).
- [ ] Run: `cd backend && ../.venv/bin/pytest tests/integration/test_template_evolution_api.py tests/integration/test_template_variants_api.py -q`
- [ ] Expected: FAIL — routes missing.
- [ ] Implement `template_evolution.py` following the pattern of `template_packages.py`:

```python
from __future__ import annotations

from uuid import UUID
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from psycopg import Connection

from tender_backend.core.security import CurrentUser, Role, get_current_user, require_role
from tender_backend.db.deps import get_db_conn
from tender_backend.db.repositories.bid_template_package_repo import BidTemplatePackageRepository
from tender_backend.db.repositories.bid_template_variant_repo import BidTemplateVariantRepository
from tender_backend.db.repositories.template_evolution_repo import TemplateEvolutionRepository
from tender_backend.services.template_clustering_service import (
    TemplateClusteringService, ClusteringInput,
)
from tender_backend.services.template_evolution_service import (
    TemplateEvolutionService, DecisionRequest,
)
from tender_backend.services.template_promotion_sanitizer import TemplatePromotionSanitizer


router = APIRouter(tags=["template-evolution"], dependencies=[Depends(get_current_user)])

_package_repo = BidTemplatePackageRepository()
_variant_repo = BidTemplateVariantRepository()
_evolution_repo = TemplateEvolutionRepository()
_sanitizer = TemplatePromotionSanitizer()
_clustering = TemplateClusteringService(_evolution_repo)
_evolution_service = TemplateEvolutionService(
    evolution_repo=_evolution_repo,
    package_repo=_package_repo,
    variant_repo=_variant_repo,
    sanitizer=_sanitizer,
)


class FamilyOut(BaseModel):
    family_id: UUID
    package_key: str
    display_name: str
    current_version: int
    variant_count: int
    project_usage_count: int


class VariantOut(BaseModel):
    id: UUID
    family_id: UUID
    variant_key: str
    display_name: str
    parent_version: int
    variant_version: int
    is_current: bool


class VariantCreate(BaseModel):
    family_id: UUID
    variant_key: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1)
    description: str | None = None
    scope_rules_json: dict = Field(default_factory=dict)


class ProposalOut(BaseModel):
    id: UUID
    proposal_status: str
    proposal_kind: str
    target_kind: str
    cluster_size: int | None
    diff_summary: dict
    created_at: str


class DecisionIn(BaseModel):
    decision: str  # "approve" or "reject"
    target_kind: str | None = None
    target_family_id: UUID | None = None
    target_variant_id: UUID | None = None
    new_variant_key: str | None = None
    new_variant_display_name: str | None = None
    decision_notes: str | None = None


@router.get("/template-packages/families", response_model=list[FamilyOut])
async def list_families(
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
) -> list[FamilyOut]:
    return _evolution_repo.list_families_with_counts(conn)


@router.get("/template-packages/families/{family_id}/versions")
async def list_family_versions(
    family_id: UUID,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
):
    return _package_repo.list_versions_for_family(conn, family_id=family_id)


@router.get("/template-variants", response_model=list[VariantOut])
async def list_variants(
    family_id: UUID = Query(...),
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(get_current_user),
):
    rows = _variant_repo.list_variants_for_family(conn, family_id=family_id)
    return [VariantOut(**row.__dict__) for row in rows]


@router.post("/template-variants", response_model=VariantOut)
async def create_variant(
    body: VariantCreate,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(require_role(Role.ADMIN)),
):
    current_pkg = _package_repo.get_current_version(conn, family_id=body.family_id)
    if current_pkg is None:
        raise HTTPException(status_code=404, detail="family has no current package version")
    variant = _variant_repo.create_variant(
        conn,
        family_id=body.family_id,
        variant_key=body.variant_key,
        display_name=body.display_name,
        description=body.description,
        parent_package_id=current_pkg.id,
        parent_version=current_pkg.version,
        scope_rules_json=body.scope_rules_json,
        metadata_json={},
        created_by=user.display_name,
    )
    _variant_repo.clone_items_from_package(
        conn, variant_id=variant.id, source_package_id=current_pkg.id
    )
    return VariantOut(**variant.__dict__)


@router.get("/template-evolution/proposals", response_model=list[ProposalOut])
async def list_proposals(
    status: str = Query("submitted"),
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(require_role(Role.ADMIN)),
):
    return _evolution_repo.list_pending_proposals(conn, status=status)


@router.post("/template-evolution/proposals/{proposal_id}/decision")
async def decide_proposal(
    proposal_id: UUID,
    body: DecisionIn,
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(require_role(Role.ADMIN)),
):
    if body.decision not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="decision must be approve or reject")
    req = DecisionRequest(
        proposal_id=proposal_id,
        decision=body.decision,  # type: ignore[arg-type]
        target_kind=body.target_kind,  # type: ignore[arg-type]
        target_family_id=body.target_family_id,
        target_variant_id=body.target_variant_id,
        new_variant_key=body.new_variant_key,
        new_variant_display_name=body.new_variant_display_name,
        decision_notes=body.decision_notes,
        reviewed_by=user.display_name,
    )
    _evolution_service.apply_decision(conn, req)
    return {"detail": "ok"}


@router.post("/template-evolution/clustering/run")
async def run_clustering(
    conn: Connection = Depends(get_db_conn),
    user: CurrentUser = Depends(require_role(Role.ADMIN)),
):
    inputs = _evolution_repo.collect_clustering_inputs(conn)
    result = _clustering.cluster(conn, inputs)
    return {
        "clusters_created_or_updated": result.clusters_created_or_updated,
        "proposals_created": result.proposals_created,
    }
```

- [ ] Register router in `backend/tender_backend/main.py`:

```python
from tender_backend.api import template_evolution
app.include_router(template_evolution.router, prefix="/api")
```

- [ ] Rerun integration tests, confirm PASS.
- [ ] Commit:

```bash
git add backend/tender_backend/api/template_evolution.py \
  backend/tender_backend/main.py \
  backend/tests/integration/test_template_evolution_api.py \
  backend/tests/integration/test_template_variants_api.py
git commit -m "feat: add template evolution and variant API"
```

### Task 9: Frontend Template Family / Variant Browser

**Files:**
- Modify: `frontend/src/lib/navigation.ts`
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/modules/templates/TemplateFamilyList.tsx`
- Create: `frontend/src/modules/templates/TemplateVariantBrowser.tsx`
- Create: `frontend/src/modules/templates/TemplateVersionDiff.tsx`
- Create: `frontend/src/modules/templates/TemplateFamilyList.test.tsx`
- Create: `frontend/src/modules/templates/TemplateVariantBrowser.test.tsx`

- [ ] Add new tabs to `database` module in `frontend/src/lib/navigation.ts`. Replace the existing `templates` tab with three:

```ts
{ id: "templates", label: "投标文件模版" },
{ id: "template-families", label: "模板家族" },
{ id: "template-variants", label: "模板变体" },
```

- [ ] Add API types and fetchers to `frontend/src/lib/api.ts`:

```ts
export interface TemplateFamily {
  family_id: string;
  package_key: string;
  display_name: string;
  current_version: number;
  variant_count: number;
  project_usage_count: number;
}

export interface TemplateVariant {
  id: string;
  family_id: string;
  variant_key: string;
  display_name: string;
  parent_version: number;
  variant_version: number;
  is_current: boolean;
}

export async function listTemplateFamilies(): Promise<TemplateFamily[]> {
  return apiFetch<TemplateFamily[]>("/api/template-packages/families");
}

export async function listTemplateVariants(familyId: string): Promise<TemplateVariant[]> {
  return apiFetch<TemplateVariant[]>(
    `/api/template-variants?family_id=${encodeURIComponent(familyId)}`
  );
}

export async function listFamilyVersions(familyId: string): Promise<unknown[]> {
  return apiFetch<unknown[]>(
    `/api/template-packages/families/${encodeURIComponent(familyId)}/versions`
  );
}
```

- [ ] Write component test (`TemplateFamilyList.test.tsx`): renders one row per family with display name, current version, variant count, project usage count. Mock `listTemplateFamilies`.
- [ ] Write component test (`TemplateVariantBrowser.test.tsx`): renders variants grouped by family; shows "基于父版本 vX, 父最新 vY" when parent version lags.
- [ ] Run: `cd frontend && npx vitest run src/modules/templates/TemplateFamilyList.test.tsx src/modules/templates/TemplateVariantBrowser.test.tsx`
- [ ] Expected: FAIL — components missing.
- [ ] Implement `TemplateFamilyList.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";
import { listTemplateFamilies, type TemplateFamily } from "@/lib/api";

export function TemplateFamilyList() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["template-families"],
    queryFn: listTemplateFamilies,
  });
  if (isLoading) return <div>加载中…</div>;
  if (error) return <div>加载失败</div>;
  return (
    <table className="w-full text-sm">
      <thead>
        <tr>
          <th>模板</th>
          <th>当前版本</th>
          <th>变体数</th>
          <th>使用项目</th>
        </tr>
      </thead>
      <tbody>
        {(data ?? []).map((f: TemplateFamily) => (
          <tr key={f.family_id}>
            <td>{f.display_name}</td>
            <td>v{f.current_version}</td>
            <td>{f.variant_count}</td>
            <td>{f.project_usage_count}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] Implement `TemplateVariantBrowser.tsx` analogously, fetching variants per family.
- [ ] Implement `TemplateVersionDiff.tsx` as a side-by-side block-level diff renderer driven by data from `/api/template-packages/{id}/diff`.
- [ ] Wire `database/template-families` and `database/template-variants` tabs in the `database` module renderer (find the existing module renderer in `frontend/src/modules/database/` and add the conditional render).
- [ ] Rerun tests, confirm PASS.
- [ ] Commit:

```bash
git add frontend/src/lib/navigation.ts frontend/src/lib/api.ts \
  frontend/src/modules/templates/TemplateFamilyList.tsx \
  frontend/src/modules/templates/TemplateVariantBrowser.tsx \
  frontend/src/modules/templates/TemplateVersionDiff.tsx \
  frontend/src/modules/templates/TemplateFamilyList.test.tsx \
  frontend/src/modules/templates/TemplateVariantBrowser.test.tsx
git commit -m "feat: template family list and variant browser"
```

### Task 10: Frontend Admin Evolution Workbench

**Files:**
- Modify: `frontend/src/lib/navigation.ts`
- Create: `frontend/src/modules/settings/TemplateEvolutionWorkbench.tsx`
- Create: `frontend/src/modules/settings/templateEvolutionModel.ts`
- Create: `frontend/src/modules/settings/templateEvolutionModel.test.ts`
- Create: `frontend/src/modules/settings/TemplateEvolutionWorkbench.test.tsx`

- [ ] Add `{ id: "template-evolution", label: "模板演进" }` to the `settings` module tabs.
- [ ] Write helper test (`templateEvolutionModel.test.ts`):
  - `decisionTargetLabel({ target_kind: "package_version", ... })` returns "升级到主模板新版"
  - `decisionTargetLabel({ target_kind: "variant_version", ... })` returns "进入现有变体新版"
  - `decisionTargetLabel({ target_kind: "new_variant", ... })` returns "抽取为新变体"
  - `validateDecision({decision: "approve", target_kind: "new_variant"})` returns error "需要 new_variant_key"
  - `validateDecision({decision: "approve", target_kind: "new_variant", new_variant_key: "x", target_family_id: "uuid"})` returns OK
- [ ] Write component test (`TemplateEvolutionWorkbench.test.tsx`):
  - Lists pending proposals.
  - Selecting a proposal opens diff view.
  - Approve with `target_kind=new_variant` requires variant key; UI disables submit until provided.
  - Submit calls `/api/template-evolution/proposals/:id/decision`.
- [ ] Run: `cd frontend && npx vitest run src/modules/settings/templateEvolutionModel.test.ts src/modules/settings/TemplateEvolutionWorkbench.test.tsx`
- [ ] Expected: FAIL — files missing.
- [ ] Implement `templateEvolutionModel.ts`:

```ts
export type TargetKind = "package_version" | "variant_version" | "new_variant";

export interface DecisionDraft {
  decision: "approve" | "reject";
  target_kind?: TargetKind;
  target_family_id?: string;
  target_variant_id?: string;
  new_variant_key?: string;
  new_variant_display_name?: string;
  decision_notes?: string;
}

export function decisionTargetLabel(draft: DecisionDraft): string {
  if (draft.decision !== "approve" || !draft.target_kind) return "—";
  switch (draft.target_kind) {
    case "package_version": return "升级到主模板新版";
    case "variant_version": return "进入现有变体新版";
    case "new_variant": return "抽取为新变体";
  }
}

export function validateDecision(draft: DecisionDraft): string | null {
  if (draft.decision === "reject") return null;
  if (!draft.target_kind) return "需要 target_kind";
  if (draft.target_kind === "package_version" && !draft.target_family_id) {
    return "需要 target_family_id";
  }
  if (draft.target_kind === "variant_version" && !draft.target_variant_id) {
    return "需要 target_variant_id";
  }
  if (draft.target_kind === "new_variant") {
    if (!draft.target_family_id) return "需要 target_family_id";
    if (!draft.new_variant_key) return "需要 new_variant_key";
  }
  return null;
}
```

- [ ] Implement `TemplateEvolutionWorkbench.tsx` as a two-pane layout: left = proposal list; right = diff + decision form. Reuse `TemplateVersionDiff` for the diff rendering.
- [ ] Add API fetchers to `frontend/src/lib/api.ts`:

```ts
export async function listEvolutionProposals(status = "submitted"): Promise<unknown[]> {
  return apiFetch<unknown[]>(
    `/api/template-evolution/proposals?status=${encodeURIComponent(status)}`
  );
}

export async function decideEvolutionProposal(
  proposalId: string, decision: DecisionDraft
): Promise<void> {
  await apiFetch(`/api/template-evolution/proposals/${proposalId}/decision`, {
    method: "POST",
    body: JSON.stringify(decision),
  });
}

export async function runClusteringNow(): Promise<{ clusters_created_or_updated: number; proposals_created: number }> {
  return apiFetch("/api/template-evolution/clustering/run", { method: "POST" });
}
```

- [ ] Rerun tests, confirm PASS.
- [ ] Commit:

```bash
git add frontend/src/lib/navigation.ts frontend/src/lib/api.ts \
  frontend/src/modules/settings/TemplateEvolutionWorkbench.tsx \
  frontend/src/modules/settings/templateEvolutionModel.ts \
  frontend/src/modules/settings/templateEvolutionModel.test.ts \
  frontend/src/modules/settings/TemplateEvolutionWorkbench.test.tsx
git commit -m "feat: admin template evolution workbench"
```

### Task 11: End-To-End Verification

**Files:** modify existing test files as needed.

- [ ] Run backend targeted suite:

```bash
cd backend && ../.venv/bin/pytest \
  tests/unit/test_bid_template_package_repo.py \
  tests/unit/test_bid_template_variant_repo.py \
  tests/unit/test_template_diff_service.py \
  tests/unit/test_template_promotion_sanitizer.py \
  tests/unit/test_template_clustering_service.py \
  tests/unit/test_template_evolution_service.py \
  tests/unit/test_project_template_instance_service.py \
  tests/integration/test_template_evolution_api.py \
  tests/integration/test_template_variants_api.py \
  tests/integration/test_project_template_instances_api.py \
  tests/integration/test_authz_routes.py \
  -q
```

- [ ] Expected: all selected tests PASS.
- [ ] Run frontend targeted suite:

```bash
cd frontend && npx vitest run \
  src/modules/templates/TemplateFamilyList.test.tsx \
  src/modules/templates/TemplateVariantBrowser.test.tsx \
  src/modules/settings/templateEvolutionModel.test.ts \
  src/modules/settings/TemplateEvolutionWorkbench.test.tsx \
  src/modules/projects/ProjectsModule.test.tsx
```

- [ ] Expected: all selected tests PASS.
- [ ] Run frontend build: `cd frontend && npm run build`. Expected PASS.
- [ ] Inspect final diff:

```bash
git status --short
git diff --stat
```

- [ ] Commit documentation update:

```bash
git add docs/superpowers/plans/2026-05-14-template-evolution.md
git commit -m "docs: template evolution implementation plan"
```

## Acceptance Criteria

- [ ] `bid_template_package` rows have `family_id`, `version`, `is_current`. Existing rows are seeded at version 1.
- [ ] Project template instance creation pins to a specific `base_template_package_version` (and optionally `base_template_variant_id` + `base_template_variant_version`).
- [ ] In-flight projects continue to see their pinned version after a global upgrade.
- [ ] Admins can create template variants from the global library.
- [ ] Admins can list pending evolution proposals from both manual and clustered sources.
- [ ] Approving a proposal with `target_kind=package_version` creates a new package version.
- [ ] Approving a proposal with `target_kind=variant_version` creates a new variant version.
- [ ] Approving a proposal with `target_kind=new_variant` creates a new variant.
- [ ] Rejecting a proposal marks it rejected with notes; no template mutation occurs.
- [ ] Clustering job groups similar block-level modifications across projects.
- [ ] Cluster size meeting threshold (default 3) auto-generates a clustered proposal.
- [ ] All cross-project project material references are stripped from diffs before promotion.
- [ ] Admin role check enforces `Role.ADMIN` on evolution and variant-mutation endpoints; editor / reviewer receive 403.
- [ ] All backend and frontend targeted tests pass.
- [ ] `npm run build` passes.

## Risk Controls

- [ ] In-flight projects are not silently upgraded; version pinning is mandatory.
- [ ] No auto-merge — every proposal requires an explicit admin decision.
- [ ] All promotion diffs are sanitized to remove project-specific references before they touch global templates.
- [ ] Variants are explicit: parent rebase requires admin action, not background sync.
- [ ] Clustering threshold is configurable in the service constructor; default = 3 to avoid noise.
- [ ] Decision audit trail kept via existing `template_promotion_proposal.reviewed_by` + new `decision_notes`.
- [ ] Old package versions are retained (`is_current = FALSE`) for evidence-period traceability; never deleted.

## Tracking Notes

- This plan depends on the Project Template Instance Workflow plan being merged. Start migration numbering at 0052 (assumes that plan uses 0051).
- Each task is one commit; commit messages use `feat:` prefix consistent with recent project commits.
- The frontend `database` module renderer needs to be located before Task 9 finalizes; if no module renderer exists yet, the navigation tab addition is still valid but rendering of the new tabs may require a follow-up.
- The `_apply_to_variant` and `_apply_to_package` item-mutation implementations are intentionally test-driven — write the assertion first, then fill in. Do not skip those tests.
- Variant rebase (carrying parent updates into an existing variant) is **not** in this plan. It is a planned follow-up; the data model supports it (`parent_version` is recorded) but the workflow is deferred.
- Project material sanitization patterns (`_PROJECT_MATERIAL_REF`, `_PROJECT_PLACEHOLDER`) are starting points and will need tuning against real project data after deployment.
