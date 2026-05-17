# Chapter 8 Quality Fix Plan (Trackable)

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development` 或 `superpowers:executing-plans`，按 checkbox 顺序推进。
>
> **依赖文档：**
> - 根因分析：`docs/reports/2026-05-16-chapter-8-live-test-rca.md`（本计划的输入）
> - 上一版导出关闭计划：`docs/superpowers/plans/2026-05-16-chapter-8-export-closure-plan.md`（操作层关 stale run，本计划聚焦代码层修复）
> - 5/11 整改方案：`docs/reviews/2026-05-11-配网技术标第8-10.3章提示词及图表整改方案.md`（REM-* 编号沿用）

## Goal

让 `project_id=d3ed99c0-1d79-4fad-bd4b-6a77a08cc530` 的第 8 章在 **2026-05-19** 之前达到 `can_export=true`，且 DOCX 实测页数 ≥ 90，可直接用于真实评标。

## Tech Stack

FastAPI backend、PostgreSQL（chapter_draft / chart_asset / workflow_run）、`LongformSectionGenerator`、`ChartGenerationService`、`build_export_gate_state`、ai_gateway (`generate_section` profile)、pytest、frontend bid-generation 模块。

## Architecture

修复分两阶段，**Phase A 必须先于 Phase B**：

- **Phase A（P0 系统根因）**：修 R1（chart 兜底）、R2（跨章约束误报）、R3（表格硬匹配）、C1（chart 审批 API），目标"任何一份非空 longform 输出 + 已配置好的 chart_asset 都能放行 export gate"。
- **Phase B（P1 内容质量）**：续写策略 C2、模型 F1、chart 配置同源 F3/F4、mermaid sidecar F5，目标"输出长度稳定 ≥ 90 页且图表可读"。
- **Phase C（验收）**：端到端复跑 + 证据落库。

Phase A 单独完成即可解锁"可导出"，但 DOCX 质量仍可能在 60~80 页区间；Phase B 完成后才达到"可直接评标"。

---

## Current Baseline (2026-05-16)

- run `113ece1d-f548-4a74-bfd4-80c5e44f9909` 完成 15/15，state=completed
- draft `0e5514d1-eab6-44ad-ba9b-e23d96761179`
- `can_export=false`
  - `coverage_passed=false`，19 issues（code 分布未知）
  - `chart_closure_passed=false`，9 个 chart_not_rendered

---

## Success Criteria (hard stop)

**Phase A 出口**：

- [ ] `coverage_passed=true` 且 P0 issue=0（包含 R2/R3 的真假阳分类完成）
- [ ] `chart_closure_passed=true` 且 chart_not_rendered=0
- [ ] `charts_approved=true`（自动 approve 路径就位 + 非暗标项目跑通）
- [ ] `can_export=true`

**Phase B 出口**：

- [ ] `export_record.metadata_json.render_evidence.page_count` ≥ 90
- [ ] 评标专家盲评（≥ 1 位）"可直接用于实际投标"

**Phase C 出口**：

- [ ] `docs/acceptance/2026-05-16-chapter-8-real-sample-evidence.json` 完整归档
- [ ] `docs/acceptance/2026-05-15-longform-launch-closure.md` 追加 Go 决策块
- [ ] 上线说明追加到 PRODUCT.md（如有里程碑变化）

---

## Step 0 — 强制前置：dump 真实 issue 分布

**为什么必须做**：19 + 9 是聚合数；不知道真实 code 分布就无法判断 R1~R3 修完之后还剩多少需要内容侧补救。

**Files:**
- Read: `docs/reports/2026-05-16-chapter-8-live-test-rca.md` § 七
- Write: `docs/acceptance/2026-05-16-chapter-8-issue-distribution.json`

- [ ] **Step 0.1：启动本地 DB（如未启动）**

```bash
cd infra && docker compose up -d postgres
```

- [ ] **Step 0.2：执行快照脚本（RCA § 七.1）**

把脚本输出（含 coverage 按 code 分桶 + chart asset 全行 + metadata.validation/provenance/blind_bid_scan）保存到上面的 JSON 路径。

- [ ] **Step 0.3：把分布写进本计划**

在本文件 § Phase A 的开头 "Baseline (after Step 0)" 块里填入真实 code 分桶（如 `hard_constraint_uncovered: 9, missing_required_table: 6, ...`）。

**验收**：JSON 文件存在；本文件 Baseline 块已更新；19 + 9 的 code 分桶全部为非 null。

---

## Phase A — 系统根因修复（P0）

### Baseline (after Step 0)

```
TODO: 由 Step 0 填充，例如：
- coverage issues by code:
    - missing_section: ?
    - section_too_short: ?
    - missing_required_chart: ?
    - missing_required_table: ?
    - required_table_empty: ?
    - hard_constraint_uncovered: ?
- chart_not_rendered keys: [..., ...]
- chart_asset failure modes:
    - validation_failed: ?
    - blind_bid_scan: ?
    - provenance: ?
```

---

### Task A1 — 修复图表生成失败兜底（R1，task #1）

**根因引用**：RCA § 四"9 个 chart_not_rendered 全部是 create_or_update 三个失败分支的直接产物"。

**Files:**
- Modify: `backend/tender_backend/services/chart_generation_service.py`
- Test: `backend/tests/unit/test_chart_generation_service.py`
- Test: `backend/tests/unit/test_longform_quality.py`

**实施步骤：**

- [ ] **Step A1.1：抽出兜底渲染辅助函数**

  在 `ChartGenerationService` 内新增 `_render_with_default(chart_type, title, placeholder_key, project_id, reason)`：调用 `default_chart_spec` → `parse_chart_spec` → `render_chart_spec` → `_write_png`，返回 `(rendered_svg, rendered_png_path)`。

- [ ] **Step A1.2：把三个失败分支改为"兜底渲染 + needs_review"**

  对 `create_or_update` 中：
  - L77 validation 失败
  - L100 blind_bid 命中（**暗标项目除外**：暗标仍走 None/None，安全优先）
  - L126 provenance 失败

  从「`rendered_svg=None, rendered_png_path=None`」改为「调用 `_render_with_default(...)` 写入 svg + png」，保留 `status='needs_review'`，并在 `metadata_json.fallback_render` 写入 `{"reason": "validation_failed|provenance|blind_bid", "original_errors": ...}`。

- [ ] **Step A1.3：单测**

  ```bash
  cd backend && PYTHONPATH=. ../.venv/bin/pytest tests/unit/test_chart_generation_service.py -q -k "validation_failed or provenance or blind_bid"
  ```

  新增用例：
  1. spec 缺字段 → asset 行 status=needs_review，**有** rendered_svg、rendered_png_path，metadata.fallback_render.reason='validation_failed'。
  2. schedule_gantt 缺 source_refs → 同上 reason='provenance'。
  3. 非暗标项目 blind_bid_blacklist 命中 → 同上 reason='blind_bid'。
  4. 暗标项目 blind_bid 命中 → asset 仍 None/None（安全保留）。

- [ ] **Step A1.4：回归 chart_closure_report**

  对真实 draft 重算 `build_chart_closure_report`，预期 `chart_not_rendered` = 0（暗标项目除外）。

**验收：** chart_closure_report 不再因 9 个不渲染卡死；剩余只可能是 chart_not_approved（由 Task A4 接管）。

**回滚：** 单环境关闭兜底渲染（settings `chart_fallback_render_enabled=False`），恢复原行为。

---

### Task A2 — 修复 coverage 跨章约束误报（R2，task #5）

**根因引用**：RCA § 三.2 "build_coverage_report 把全部 critical 约束都当作本章应覆盖"。

**Files:**
- Modify: `backend/tender_backend/services/longform_quality.py`
- Modify: `backend/tender_backend/services/technical_bid_writer.py`（传 chapter_code 进 build_coverage_report）
- Test: `backend/tests/unit/test_longform_quality.py`

**实施步骤：**

- [ ] **Step A2.1：扩展 build_coverage_report 签名**

  增加参数 `chapter_code: str | None = None`（当前 chapter 的章号，如 "8"）。

- [ ] **Step A2.2：约束筛选**

  L222-234 改为：

  ```python
  for constraint in constraints:
      mapped = str(constraint.get("response_section_code") or constraint.get("mapped_section_code") or "").strip()
      if not mapped:
          continue  # 未映射的约束不进本章评估
      mapped_chapter = mapped.split(".")[0]
      if chapter_code and mapped_chapter != str(chapter_code):
          continue  # 跨章约束直接跳过
      critical = constraint.get("confirmation_level") == "critical" or bool((constraint.get("metadata_json") or {}).get("has_conflict"))
      if critical and mapped not in present_sections:
          issues.append({"code": "hard_constraint_uncovered", "constraint_id": ..., "section_code": mapped, "severity": "P0"})
  ```

- [ ] **Step A2.3：调用点传参**

  `technical_bid_writer._save_chapter_draft` 调用 `build_coverage_report(...)` 时传 `chapter_code=chapter["chapter_code"]`。

- [ ] **Step A2.4：单测**

  ```bash
  cd backend && PYTHONPATH=. ../.venv/bin/pytest tests/unit/test_longform_quality.py -q -k "hard_constraint"
  ```

  新增用例：
  1. 12 个 critical 约束（4 个 mapped 到 8.x，5 个 mapped 到 9.x，3 个无 mapped）→ 校验只对 8.x 的 4 个评估，9.x 的 5 个不进 issues，无 mapped 的 3 个 skip。
  2. chapter_code=None → 退回原行为（向后兼容）。

**验收：** 在 Step 0 dump 的 issue 分布上重算，所有 mapped_section_code 非 8.x 的 `hard_constraint_uncovered` issue 消失。

**回滚：** 把 chapter_code 调用点改回 None，恢复原行为。

---

### Task A3 — required_tables 标签集匹配（R3，task #3）

**根因引用**：RCA § 三.1 "硬字符串匹配，LLM 同义生成即误报"。

**Files:**
- Modify: `backend/tender_backend/services/longform_quality.py`
- Modify: `backend/tender_backend/services/longform_section_generation.py`
- Test: `backend/tests/unit/test_longform_quality.py`

**实施步骤：**

- [ ] **Step A3.1：把 required_tables 升级为标签集**

  `_DEFAULT_TABLES` 改成 `dict[str, tuple[str, ...]]`，每节给一组同义词：

  ```python
  _DEFAULT_TABLES: dict[str, tuple[str, ...]] = {
      "8.2": ("工程概况表", "工程概况一览表", "项目概况表"),
      "8.5": ("资源配置计划表", "施工资源配置表", "资源投入计划表"),
      "8.6": ("主要施工方法表", "主要施工方法清单", "主要施工工序表"),
      "8.8": ("质量控制点表", "WHS控制点表", "质量控制点清单"),
      "8.9": ("安全风险管控表", "危险源辨识与分级管控表", "风险分级管控清单"),
      "8.11": ("工期保证措施表", "进度保证措施表"),
      "8.12": ("重点难点应对表", "重难点分析与对策表", "重难点应对清单"),
  }
  ```

- [ ] **Step A3.2：build_coverage_report 改为"任一同义词命中即过"**

  L191-200 改为：

  ```python
  for table_spec in item.get("required_tables") or []:
      synonyms = table_spec if isinstance(table_spec, (list, tuple)) else (table_spec,)
      if not any(str(label) in body for label in synonyms):
          issues.append({"code": "missing_required_table", "section_code": section_code, "table_label": synonyms[0], "expected_synonyms": list(synonyms), "severity": "P0"})
  ```

- [ ] **Step A3.3：plan_chapter_8_sections 传出标签集**

  `plan_chapter_8_sections` 把 `required_tables` 从 `list[str]` 改为 `list[tuple[str, ...]]`，与 build_coverage_report 一致。

- [ ] **Step A3.4：单测**

  新增用例：
  - body 含 "WHS 控制点表" → 8.8 的 required_tables 不报错。
  - body 含 "重难点分析与对策表" → 8.12 不报错。
  - body 都没命中 → 报错且 expected_synonyms 在 issue 字段中可见。

**验收：** Step 0 dump 中 `missing_required_table` 的预计 5~7 个 issue 收敛到 ≤ 2 个（仅留下确实没出现任何同义词的）。

**回滚：** 把 `_DEFAULT_TABLES` 恢复为单字符串。

---

### Task A4 — chart asset 批量审批 API（C1，task #9）

**根因引用**：RCA § 四.1 "即使 chart 渲染了，charts_approved gate 仍 fail"。

**Files:**
- Modify: `backend/tender_backend/services/chart_generation_service.py`
- Modify: `backend/tender_backend/api/bid_generation.py`
- Modify: `backend/tender_backend/db/repositories/chart_asset_repo.py`（如缺 bulk update 方法）
- Test: `backend/tests/unit/test_chart_generation_service.py`
- Test: `backend/tests/unit/test_bid_generation_api.py`

**实施步骤：**

- [ ] **Step A4.1：服务层 bulk_approve**

  在 `ChartGenerationService` 新增：

  ```python
  def bulk_approve(
      self, conn, *, project_id, mode: str = "auto",
      approved_by: str = "system", only_validated: bool = True,
  ) -> dict[str, Any]:
      """Approve all draft/needs_review chart assets in one call.

      auto mode: 仅 approve validation.valid=True 且 fallback_render.reason 不在
      {"blind_bid"} 的 asset；blind_bid 必须 manual。
      manual mode: 全部 approve（暗标项目必须用此模式，且 approved_by 必须是真实用户名）。
      """
  ```

- [ ] **Step A4.2：API 路由**

  在 `bid_generation` 增加：

  ```
  POST /api/projects/{project_id}/chart-assets/bulk-approve
  body: {"mode": "auto" | "manual", "approved_by": str}
  ```

  暗标项目（`project.metadata_json.is_blind_bid=True`）传 `mode=auto` 时返回 409 + 提示"暗标需手动审批"。

- [ ] **Step A4.3：在 generate-async 完成后自动调用（可选）**

  `technical_generation_async` 的 run 完成 hook 里，对非暗标项目自动调用 `bulk_approve(mode='auto')`。

- [ ] **Step A4.4：单测**

  ```bash
  cd backend && PYTHONPATH=. ../.venv/bin/pytest tests/unit/test_chart_generation_service.py tests/unit/test_bid_generation_api.py -q -k "bulk_approve or approve"
  ```

**验收：** 调用 bulk_approve 后，`charts_approved=true`，`unapproved_chart_count=0`。

**回滚：** auto 模式默认关闭，前端只允许 manual。

---

### Phase A Acceptance

- [ ] 完成 A1~A4 全部 PR 合并主干。
- [ ] 对 project d3ed99c0 重算 `build_export_gate_state`：
  - `coverage_passed=true`、P0 issue=0
  - `chart_closure_passed=true`、chart_not_rendered=0
  - `charts_approved=true`
  - `can_export=true`
- [ ] 任一假设性回归（如其他章节）单测全绿：

  ```bash
  cd backend && PYTHONPATH=. ../.venv/bin/pytest tests/unit/test_longform_quality.py tests/unit/test_longform_section_generation.py tests/unit/test_chart_generation_service.py tests/unit/test_export_gates.py tests/unit/test_technical_bid_writer.py tests/unit/test_docx_exporter.py -q
  ```

---

## Phase B — 内容质量优化（P1）

### Task B1 — LongformSectionGenerator 续写策略（C2，task #7）

**Files:**
- Modify: `backend/tender_backend/services/longform_section_generation.py`
- Test: `backend/tests/unit/test_longform_section_generation.py`

**实施步骤：**

- [ ] **Step B1.1：扩大 existing_content_tail 窗口**

  L183 `generated[-1000:]` → `generated[-3000:]`。

- [ ] **Step B1.2：把全章骨架写进 payload**

  payload 新增字段：

  ```python
  "previous_section_outlines": [
      {"section_code": r["section_code"], "title": r["title"], "actual_chars": r["actual_chars"]}
      for r in section_results
  ],
  ```

- [ ] **Step B1.3：续写轮强化 prompt**

  `_request_ai_gateway_subsection_completion` 中 `rewrite_parts`：当 `round_index > 1` 追加：

  > "这是续写轮次。前文已生成 X 字符，请只补充缺失的子专题/数据/案例至 min_chars，禁止重复已生成段落的主旨与例句；可以新增子标题但章节编号保持不变。"

- [ ] **Step B1.4：单测**

  - 续写 2 轮后 weighted_chars 增长率 ≥ 第 1 轮的 60%（验证不卡死）。
  - `previous_section_outlines` 字段在 payload 中可见。

**验收：** Step 0 dump 中 `section_too_short` 数量在重跑后 < 50%。

---

### Task B2 — generate_section 切到 v4-pro（F1，task #8）

**Files:**
- Modify: `ai_gateway/tender_ai_gateway/task_profiles.py`
- Modify: `ai_gateway/tender_ai_gateway/fallback.py`（如 memory 所述 v4-pro 被禁，需放开）
- Test: `ai_gateway/tests/smoke/test_task_profiles.py`

**实施步骤：**

- [ ] **Step B2.1：放开 fallback.py 中 v4-pro 限制**

  搜 `v4-pro` 或 `deepseek-v4-pro` 在 fallback.py 中的禁用代码（参考 memory `project_ai_model_policy.md`），删除该禁用条件。

- [ ] **Step B2.2：profile 切换**

  ```python
  "generate_section": {
      "primary_model": "deepseek-v4-pro",
      "primary_thinking_mode": "max",
      "fallback_model": "deepseek-v4-flash",
      "max_tokens": 32768,
      "timeout": 600,
  },
  ```

- [ ] **Step B2.3：smoke test**

  ```bash
  cd ai_gateway && ../.venv/bin/pytest tests/smoke/test_task_profiles.py -q
  ```

- [ ] **Step B2.4：1 节 e2e 比对**

  挑 8.6（"主要施工方法及技术要求"，工程量大）跑一次：v4-pro 与 v4-flash 各一次，对比 weighted_chars 与质量。

**验收：** v4-pro 平均字符数 ≥ flash 的 110%，且 max_thinking 未触发 quota / timeout。

**回滚：** profile 恢复 flash + 关闭 fallback.py 放开。

---

### Task B3 — chart 配置单一来源（F3/F4，task #13）

**Files:**
- Modify: `backend/tender_backend/services/longform_section_generation.py`
- Modify: `backend/tender_backend/services/technical_chapter_strategies/registry.py`
- Test: `backend/tests/unit/test_longform_section_generation.py`
- Test: `backend/tests/unit/test_technical_chapter_context.py`

**实施步骤：**

- [ ] **Step B3.1：删除 longform_section_generation._DEFAULT_CHARTS / _DEFAULT_TABLES**

- [ ] **Step B3.2：plan_chapter_8_sections 从 registry 取值**

  ```python
  from tender_backend.services.technical_chapter_strategies.registry import CHAPTER_8_CHILD_CHARTS, CHAPTER_8_CHILD_TABLES
  ...
  required_charts = list(CHAPTER_8_CHILD_CHARTS.get(section_code, ()))
  required_tables = list(CHAPTER_8_CHILD_TABLES.get(section_code, ()))
  ```

- [ ] **Step B3.3：registry 增加 CHAPTER_8_CHILD_TABLES**（迁移 A3 的标签集字典）

- [ ] **Step B3.4：单测**

  - `plan_chapter_8_sections(target_pages=100)` 的 required_charts 与 registry 完全一致。
  - 修改 registry 后 plan 立刻生效（无需改 longform）。

**验收：** longform 与 _ensure_recommended_charts 用同一份配置，chart_closure_report 与 coverage_report 检查范围一致。

**回滚：** 在 longform 里临时回写 _DEFAULT_CHARTS（保留 imports）。

---

### Task B4 — 部署 mermaid sidecar（F5，task #10）

**Files:**
- Modify: `infra/docker-compose.yml`
- Modify: `infra/.env.example`
- Read: `backend/tender_backend/services/chart_service/renderers.py:80-103`（确认 sidecar 协议）

**实施步骤：**

- [ ] **Step B4.1：docker-compose 加 mermaid 服务**

  ```yaml
  mermaid:
    image: minlag/mermaid-cli:latest  # 或自建
    # 或换成 ghcr.io 同步 hosted
    ports: ["3030:3030"]
    command: ["node", "/server.js"]  # 视镜像实际命令
  ```

- [ ] **Step B4.2：.env 增加配置**

  `MERMAID_RENDER_URL=http://mermaid:3030`
  `MERMAID_RENDER_TIMEOUT_SECONDS=30`

- [ ] **Step B4.3：本地启动并 smoke**

  ```bash
  cd infra && docker compose up -d mermaid
  curl -s -X POST http://localhost:3030/render -H 'Content-Type: application/json' \
    -d '{"source": "flowchart TB\\n  A --> B"}'
  ```

  返回应包含 `<svg`。

- [ ] **Step B4.4：跑 1 节 e2e 验证 flow/gantt 图正确渲染**

**验收：** rendered_png 中 flow 拓扑不再是竖线；gantt 出现依赖箭头。

**回滚：** 关闭 mermaid 服务，sidecar fail 后 fallback 仍走系统 renderer（已知缺陷 CR-1/CR-2，沿用 5/11 整改方案后续 P0）。

---

## Phase C — 端到端验收（task #6）

**Files:**
- Write: `docs/acceptance/2026-05-16-chapter-8-real-sample-evidence.json`
- Modify: `docs/acceptance/2026-05-15-longform-launch-closure.md`

- [ ] **Step C1：清理 stale runs**（参考 5/16 export closure plan Task A1）

- [ ] **Step C2：发起新 async run**

  ```bash
  curl -sS -X POST "http://127.0.0.1:8000/api/projects/d3ed99c0-1d79-4fad-bd4b-6a77a08cc530/technical-bid/chapters/bb832f27-5c8c-4951-9f66-84faf4ac3b77/generate-async" \
    -H "Authorization: Bearer dev-token" \
    -H "Content-Type: application/json" \
    -d '{"target_pages": 100, "rewrite_note": "在 Phase A/B 修复基础上重新生成。"}'
  ```

- [ ] **Step C3：polled until completed**

- [ ] **Step C4：调用 bulk_approve（非暗标，mode=auto）**

- [ ] **Step C5：调用 export gate**

  ```bash
  curl -sS "http://127.0.0.1:8000/api/projects/d3ed99c0-1d79-4fad-bd4b-6a77a08cc530/export-gates"
  ```

  全部 gate=true、`can_export=true`。

- [ ] **Step C6：导出 DOCX，统计实际页数**

  ```bash
  curl -sS -X POST "http://127.0.0.1:8000/api/projects/d3ed99c0-1d79-4fad-bd4b-6a77a08cc530/export" -d '{"format": "single_docx"}'
  ```

- [ ] **Step C7：归档 evidence**

  跑 `scripts/run_chapter_8_acceptance.py`，把 chapter_draft / export_record / export_gate 写到 `docs/acceptance/2026-05-16-chapter-8-real-sample-evidence.json`。

- [ ] **Step C8：追加 Go 决策块**

  在 `docs/acceptance/2026-05-15-longform-launch-closure.md` 末尾加：

  ```markdown
  ## 2026-05-16 Final Decision

  - Run: ...
  - Draft: ...
  - Gates: page_count_passed=true / coverage_passed=true / chart_closure_passed=true / charts_approved=true / can_export=true
  - Actual pages: NN
  - Decision: **Go / No-Go**
  ```

**验收：** Phase A 出口 + Phase B 出口全部满足。

---

## Risk Controls

- [ ] 任一 Phase A 任务在自检阶段 fail，**停止 Phase B**，先 RCA。
- [ ] 暗标项目的兜底渲染 / 自动 approve 必须显式禁用（A1.2、A4 暗标分支）。
- [ ] 任何修改不影响其他章节（9 / 10.1 / 10.2 / 10.3）的 coverage 评估——A2 改动后必须对一份"含 9/10 章 draft" 的 fixture 做单测。
- [ ] B2 切换 v4-pro 前先查 ai_gateway 余额与并发限制，避免 quota 超限。

## Reporting Cadence

- [ ] 每完成一个 Phase A 任务，在本文件勾选 + 提交一份 commit message `[FIX-A-N] ...`。
- [ ] Phase A 结束后，在 RCA 报告 `docs/reports/2026-05-16-chapter-8-live-test-rca.md` 末尾追加"修复回写"段：把 19 + 9 真实 dump 的每一项标记 ✓/△/✗。
- [ ] Phase B 结束后，更新 `docs/reviews/2026-05-11-...整改方案.md` 中 REM-* 编号对应的状态。
- [ ] Phase C 完成后，把 Final Decision 写入 acceptance 文档并 commit。

---

## Appendix A — Task ↔ RCA 根因索引

| Task | RCA 根因 | 5/11 REM 编号（如有） |
| --- | --- | --- |
| Step 0 | RCA § 七 强制前置 | - |
| A1（task #1） | R1 | 与 REM-C-3 / C-9 有交集（已知）|
| A2（task #5） | R2 | - |
| A3（task #3） | R3 | - |
| A4（task #9） | C1 | 与 5/11 § 五 REM-S-5 前端审批工作流互补 |
| B1（task #7） | C2 | - |
| B2（task #8） | F1 | - |
| B3（task #13） | F3/F4 | 部分覆盖 REM-C-6 |
| B4（task #10） | F5 | 短期补救；长期由 5/11 REM-C-1/C-2 修 fallback renderer |
| C（task #6） | 端到端验收 | 触发 5/15 acceptance 文档 Go 决策 |

## Appendix B — 不在本计划范围

- 5/11 整改方案中尚未完成的 REM-C-1/C-2 fallback renderer（拓扑塌缩、甘特图无依赖）：本计划用 B4 mermaid sidecar 短期规避；REM-C-1/C-2 仍按原方案推进。
- REM-S-1/S-2/S-3 共享子段、REM-P-* 提示词增补：与本计划解耦，按 5/11 原节奏。
- 商务标、其他章节 9/10.x 的质量优化。
- 前端审批工作流 UI（A4 只提供 API；UI 由 REM-S-5 推进）。

## Appendix C — 修订记录

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| v1.0 | 2026-05-16 | 初版落盘，基于 docs/reports/2026-05-16-chapter-8-live-test-rca.md |
