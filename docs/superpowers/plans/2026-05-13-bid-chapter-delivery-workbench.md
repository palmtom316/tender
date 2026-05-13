# Bid Chapter Delivery Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a delivery-oriented chapter/template workbench where tender engineers operate on chapters, material slots, writing requirements, and chart task cards instead of raw binding/JSON internals.

**Architecture:** This is a frontend-first restructuring that reuses existing backend APIs. `TemplateFieldWorkbench` gets a default delivery mode with the old technical controls moved into an advanced disclosure. `EditorContent` is split into small presentational helpers for chapter type, material-slot summaries, technical writing controls, and chart task cards while preserving existing mutations.

**Tech Stack:** React 18, TypeScript, TanStack Query, Vitest, React Testing Library, existing `frontend/src/lib/api.ts` client and `frontend/src/styles/utilities.css` design system.

---

## Design References

- Spec: `docs/superpowers/specs/2026-05-13-bid-chapter-delivery-workbench-design.md`
- Existing frontend context: `PRODUCT.md`
- Primary files:
  - `frontend/src/modules/database/components/TemplateFieldWorkbench.tsx`
  - `frontend/src/modules/authoring/EditorContent.tsx`
  - `frontend/src/modules/authoring/EditorContent.test.tsx`
  - `frontend/src/styles/utilities.css`

## File Structure

### Create

- `frontend/src/modules/authoring/chapterDelivery.ts`
  - Pure helper functions for chapter classification, material-slot summaries, chart task labels, and chart task metadata.
  - Reason: keep `EditorContent.tsx` readable and make behavior unit-testable without rendering.

- `frontend/src/modules/authoring/chapterDelivery.test.ts`
  - Unit tests for helper behavior.

### Modify

- `frontend/src/modules/database/components/TemplateFieldWorkbench.tsx`
  - Add delivery-mode state.
  - Render delivery status/problem list by default.
  - Move old binding editor, preflight detail, mapping suggestions, and raw context preview into a `<details>` advanced maintenance section.

- `frontend/src/modules/authoring/EditorContent.tsx`
  - Reorganize the current editor into delivery-oriented layout.
  - Replace “图表生成与插入” global block with chart task cards.
  - Add material-composition panels for non-technical chapters.
  - Keep all existing mutations and API calls.

- `frontend/src/modules/authoring/EditorContent.test.tsx`
  - Update existing tests to match new labels and layout.
  - Add tests for material composition mode and chart task cards.

- `frontend/src/styles/utilities.css`
  - Add layout/classes for delivery workbench, material slots, advanced maintenance disclosure, and chart task cards.

## Implementation Tasks

### Task 1: Add pure chapter delivery helpers

**Files:**
- Create: `frontend/src/modules/authoring/chapterDelivery.ts`
- Create: `frontend/src/modules/authoring/chapterDelivery.test.ts`

- [ ] **Step 1: Write failing helper tests**

Create `frontend/src/modules/authoring/chapterDelivery.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { BidChapter, ChartAsset } from "../../lib/api";
import {
  buildChartTaskCards,
  buildMaterialSlots,
  chapterDeliveryKind,
  deliveryKindLabel,
  readableContextCount,
} from "./chapterDelivery";

function chapter(overrides: Partial<BidChapter>): BidChapter {
  return {
    id: "chapter-1",
    chapter_code: "3",
    chapter_title: "企业资信情况",
    volume_type: "business",
    sort_order: 1,
    metadata_json: {},
    ...overrides,
  };
}

describe("chapterDelivery", () => {
  it("classifies confirmed technical chapters as ai_content", () => {
    expect(chapterDeliveryKind(chapter({ chapter_code: "8", volume_type: "technical" }))).toBe("ai_content");
    expect(deliveryKindLabel("ai_content")).toBe("AI 正文");
  });

  it("classifies non-technical chapters as material_composition", () => {
    expect(chapterDeliveryKind(chapter({ chapter_code: "3", volume_type: "business" }))).toBe("material_composition");
    expect(deliveryKindLabel("material_composition")).toBe("资料编排");
  });

  it("builds material slots from business assembly missing materials", () => {
    const slots = buildMaterialSlots(chapter({ chapter_code: "3" }), {
      missing_materials: [
        { chapter_code: "3", material_name: "安全生产许可证", material_type: "certificate", reason: "未选择证书" },
        { chapter_code: "4", material_name: "项目经理", material_type: "person", reason: "其他章节" },
      ],
    });

    expect(slots).toEqual([
      expect.objectContaining({
        label: "安全生产许可证",
        sourceLabel: "证书/附件",
        status: "missing",
        helpText: "未选择证书",
      }),
    ]);
  });

  it("provides default material slots when no backend slot data exists", () => {
    const slots = buildMaterialSlots(chapter({ chapter_title: "企业资信情况" }), undefined);

    expect(slots.map((slot) => slot.label)).toContain("企业营业执照");
    expect(slots.map((slot) => slot.label)).toContain("资质证书");
  });

  it("builds chart task cards from recommended charts and assets", () => {
    const assets: ChartAsset[] = [
      {
        id: "asset-1",
        project_id: "proj-1",
        outline_node_id: "chapter-1",
        chart_type: "quality_system",
        title: "质量管理体系图",
        spec_json: {},
        rendered_svg: "<svg />",
        placeholder_key: "quality_system",
        status: "draft",
        created_at: "2026-05-10T00:00:00Z",
      },
    ];

    const tasks = buildChartTaskCards(["quality_system", "schedule_gantt"], assets);

    expect(tasks).toEqual([
      expect.objectContaining({ key: "quality_system", title: "质量管理体系图", status: "draft", assetId: "asset-1" }),
      expect.objectContaining({ key: "schedule_gantt", title: "施工进度横道图", status: "not_generated", assetId: null }),
    ]);
  });

  it("counts context arrays in readable Chinese labels", () => {
    expect(readableContextCount({ constraints: [{ id: 1 }], scoring_items: [] }, "constraints")).toBe("约束：1");
    expect(readableContextCount({ constraints: [{ id: 1 }], scoring_items: [] }, "scoring_items")).toBe("评分：0");
  });
});
```

- [ ] **Step 2: Run helper tests to verify they fail**

Run:

```bash
cd frontend && npm run test -- src/modules/authoring/chapterDelivery.test.ts
```

Expected: FAIL because `chapterDelivery.ts` does not exist.

- [ ] **Step 3: Implement helpers**

Create `frontend/src/modules/authoring/chapterDelivery.ts`:

```ts
import type { BidChapter, ChartAsset } from "../../lib/api";

export type ChapterDeliveryKind = "material_composition" | "ai_content";
export type MaterialSlotStatus = "ready" | "missing";
export type ChartTaskStatus = "not_generated" | "draft" | "needs_review" | "approved" | "failed" | "rejected" | string;

export interface MaterialSlotSummary {
  key: string;
  label: string;
  sourceLabel: string;
  status: MaterialSlotStatus;
  helpText: string;
}

export interface ChartTaskCard {
  key: string;
  title: string;
  chartType: string;
  purpose: string;
  sourceSummary: string;
  placeholder: string;
  status: ChartTaskStatus;
  assetId: string | null;
  renderedSvg: string | null;
}

const CHART_LABELS: Record<string, string> = {
  org_chart: "项目组织机构图",
  responsibility_matrix: "岗位职责矩阵",
  construction_flow: "施工流程图",
  quality_system: "质量管理体系图",
  safety_system: "安全管理体系图",
  risk_matrix: "风险分级管控矩阵",
  emergency_org: "应急组织图",
  schedule_gantt: "施工进度横道图",
  response_matrix: "条款响应矩阵",
  indicator_table: "指标台账",
  interface_table: "协调接口表",
  equipment_table: "设备配置表",
  closure_flow: "闭环流程图",
  data_flow: "数据流转图",
  critical_path: "关键路径图",
};

const CHART_PURPOSES: Record<string, string> = {
  schedule_gantt: "响应工期及进度保证措施，展示关键节点和施工顺序。",
  critical_path: "说明影响工期的关键工作和前后依赖关系。",
  quality_system: "响应质量保证体系要求，展示质量管理职责链路。",
  safety_system: "响应安全管理要求，展示安全责任体系。",
  risk_matrix: "响应危险源辨识与风险控制要求。",
  construction_flow: "说明主要工序和施工组织逻辑。",
  org_chart: "展示项目管理组织和岗位分工。",
  equipment_table: "说明主要施工机械、车辆和工器具投入。",
  response_matrix: "逐项对应招标条款、评分点或技术规范要求。",
};

const CHART_SOURCES: Record<string, string> = {
  schedule_gantt: "招标工期、关键节点、施工工序模板。",
  critical_path: "工序依赖、里程碑、工期约束。",
  quality_system: "项目组织、质量岗位、检查闭环。",
  safety_system: "项目组织、安全岗位、危险源控制措施。",
  risk_matrix: "危险源清单、控制措施、责任岗位。",
  construction_flow: "施工方案、主要工序、项目类型。",
  org_chart: "项目人员选择和岗位职责。",
  equipment_table: "公司设备库和本项目设备选择。",
  response_matrix: "招标条款、评分点、章节正文。",
};

function chartPlaceholder(asset: Pick<ChartAsset, "placeholder_key" | "chart_type">) {
  return asset.placeholder_key || asset.chart_type;
}

function chartTitle(chartType: string) {
  return CHART_LABELS[chartType] ?? chartType;
}

function materialSourceLabel(materialType: unknown) {
  const value = typeof materialType === "string" ? materialType : "";
  if (value.includes("person")) return "人员资料库";
  if (value.includes("performance") || value.includes("业绩")) return "业绩库";
  if (value.includes("certificate") || value.includes("asset") || value.includes("证书")) return "证书/附件";
  return "公司资料库";
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

export function chapterDeliveryKind(chapter: BidChapter | null | undefined): ChapterDeliveryKind {
  return chapter?.volume_type === "technical" ? "ai_content" : "material_composition";
}

export function deliveryKindLabel(kind: ChapterDeliveryKind) {
  return kind === "ai_content" ? "AI 正文" : "资料编排";
}

export function readableContextCount(context: Record<string, unknown> | undefined, key: string) {
  const labels: Record<string, string> = {
    constraints: "约束",
    scoring_items: "评分",
    standard_clauses: "标准",
    personnel_selections: "人员",
    equipment_selections: "设备",
    chart_assets: "图表",
  };
  const value = context?.[key];
  const count = Array.isArray(value) ? value.length : 0;
  return `${labels[key] ?? key}：${count}`;
}

export function buildMaterialSlots(
  chapter: BidChapter | null | undefined,
  assembly: { missing_materials?: Array<Record<string, unknown>> } | undefined,
): MaterialSlotSummary[] {
  if (!chapter) return [];

  const missing = assembly?.missing_materials ?? [];
  const matchingMissing = missing.filter((item) => {
    const record = asRecord(item);
    return record.chapter_code === chapter.chapter_code || record.chapter_id === chapter.id;
  });

  if (matchingMissing.length > 0) {
    return matchingMissing.map((item, index) => {
      const record = asRecord(item);
      const label = String(record.material_name ?? record.name ?? record.title ?? `待补资料 ${index + 1}`);
      return {
        key: String(record.material_key ?? record.id ?? `${chapter.id}-${index}`),
        label,
        sourceLabel: materialSourceLabel(record.material_type ?? record.source_type),
        status: "missing",
        helpText: String(record.reason ?? record.message ?? "选择或补充该资料后重新检查。"),
      };
    });
  }

  const title = chapter.chapter_title;
  if (/人员|项目经理|团队/.test(title)) {
    return [
      { key: "project_manager", label: "项目经理", sourceLabel: "人员资料库", status: "ready", helpText: "从项目人员选择中带入。" },
      { key: "technical_lead", label: "技术负责人", sourceLabel: "人员资料库", status: "ready", helpText: "从项目人员选择中带入。" },
      { key: "safety_officer", label: "安全员", sourceLabel: "人员资料库", status: "ready", helpText: "从项目人员选择中带入。" },
    ];
  }

  if (/业绩|类似/.test(title)) {
    return [
      { key: "similar_performance", label: "类似项目业绩", sourceLabel: "业绩库", status: "ready", helpText: "从公司合同业绩台账带入。" },
      { key: "performance_attachment", label: "业绩证明附件", sourceLabel: "证书/附件", status: "ready", helpText: "从证明材料库带入。" },
    ];
  }

  return [
    { key: "business_license", label: "企业营业执照", sourceLabel: "公司资料库", status: "ready", helpText: "从公司基础资料带入。" },
    { key: "qualification_certificate", label: "资质证书", sourceLabel: "证书/附件", status: "ready", helpText: "从公司资质证书库带入。" },
    { key: "safety_license", label: "安全生产许可证", sourceLabel: "证书/附件", status: "ready", helpText: "从公司资质证书库带入。" },
  ];
}

export function buildChartTaskCards(recommendedChartKeys: string[], assets: ChartAsset[]): ChartTaskCard[] {
  const allKeys = Array.from(new Set([
    ...recommendedChartKeys,
    ...assets.map((asset) => chartPlaceholder(asset)).filter(Boolean),
  ]));

  return allKeys.map((key) => {
    const asset = assets.find((item) => chartPlaceholder(item) === key || item.chart_type === key);
    const chartType = asset?.chart_type ?? key;
    return {
      key,
      title: asset?.title ?? chartTitle(chartType),
      chartType,
      purpose: CHART_PURPOSES[chartType] ?? "辅助说明本章技术响应内容。",
      sourceSummary: CHART_SOURCES[chartType] ?? "章节正文、招标要求和已选资料。",
      placeholder: `{{chart:${key}}}`,
      status: asset?.status ?? "not_generated",
      assetId: asset?.id ?? null,
      renderedSvg: asset?.rendered_svg ?? null,
    };
  });
}
```

- [ ] **Step 4: Run helper tests to verify they pass**

Run:

```bash
cd frontend && npm run test -- src/modules/authoring/chapterDelivery.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add frontend/src/modules/authoring/chapterDelivery.ts frontend/src/modules/authoring/chapterDelivery.test.ts
git commit -m "feat: add chapter delivery helpers"
```

---

### Task 2: Convert template page default view to delivery mode

**Files:**
- Modify: `frontend/src/modules/database/components/TemplateFieldWorkbench.tsx`
- Modify: `frontend/src/styles/utilities.css`

- [ ] **Step 1: Add delivery-mode state and simple issue helpers**

In `TemplateFieldWorkbench.tsx`, inside `TemplateFieldWorkbench`, after `showOnlyBlockedItems` state, add:

```ts
  const [showAdvancedMaintenance, setShowAdvancedMaintenance] = useState(false);
```

After `blockedPreflightItems` memo, add:

```ts
  const selectedItemIssues = preflightItem?.issues ?? [];
  const selectedItemReady = preflightItem?.ready ?? itemContext?.ready ?? false;
  const selectedItemSuggestion = suggestionQuery.data?.suggestions?.[0] ?? null;
```

- [ ] **Step 2: Replace hero labels with delivery language**

Change the hero eyebrow and description from technical language to:

```tsx
<p className="template-panel__eyebrow">模板交付检查</p>
<h2>{selectedItem ? `${selectedItem.item_code ?? ""} ${selectedItem.item_name}`.trim() : "请选择模板项"}</h2>
<p className="template-panel__description">
  {selectedItem ? "检查该模板项是否缺资料、缺绑定或需要模板管理员处理。" : "选择 DOCX 模板项后，按待处理清单补齐资料并确认可导出。"}
</p>
```

Update summary pill labels:

```tsx
<span>资料来源</span>
<strong>{itemBindingsQuery.data?.length ?? 0}</strong>
```

```tsx
<span>当前项</span>
<strong>{selectedItemReady ? "可生成" : "待处理"}</strong>
```

```tsx
<span>待处理</span>
<strong>{selectedItemIssues.length}</strong>
```

```tsx
<span>整包状态</span>
<strong>{packagePreflightQuery.data?.ready ? "可导出" : "需处理"}</strong>
```

- [ ] **Step 3: Replace the visible five-card area with delivery panels and advanced details**

In the `selectedItem ? (` branch, replace the outer `<div className="template-field-grid"> ... </div>` with this structure. Reuse the existing old binding/preflight/suggestion/context JSX by moving it into the `details` body under the comment below rather than deleting it:

```tsx
          <div className="template-delivery-grid">
            <section className="template-panel template-delivery-panel" aria-label="当前模板项交付状态">
              <div className="template-panel__header">
                <div>
                  <p className="template-panel__eyebrow">交付状态</p>
                  <h2>{selectedItemReady ? "当前项可生成" : "当前项待处理"}</h2>
                  <p className="template-panel__description">
                    {selectedItemReady
                      ? "资料来源和渲染检查已通过，可参与导出。"
                      : "先处理下方问题；无法判断的映射问题交给模板管理员。"}
                  </p>
                </div>
                <Badge variant={selectedItemReady ? "success" : "warning"}>
                  {selectedItemReady ? "可生成" : "待处理"}
                </Badge>
              </div>

              <div className="template-preflight-summary">
                <div className="template-preflight-summary__card">
                  <span>可导出模板项</span>
                  <strong>{packagePreflightQuery.data?.ready_item_count ?? 0}</strong>
                </div>
                <div className="template-preflight-summary__card">
                  <span>待处理模板项</span>
                  <strong>{packagePreflightQuery.data?.blocked_item_count ?? 0}</strong>
                </div>
                <div className="template-preflight-summary__card">
                  <span>问题总数</span>
                  <strong>{packagePreflightQuery.data?.issue_count ?? 0}</strong>
                </div>
              </div>

              <div className="template-delivery-actions">
                <ClayButton variant="outline" onClick={() => setShowOnlyBlockedItems((current) => !current)}>
                  {showOnlyBlockedItems ? "查看全部模板项" : "只看待处理项"}
                </ClayButton>
                <ClayButton variant="outline" onClick={refreshItemQueries}>
                  <Icon name="refresh" size={14} /> 重新检查
                </ClayButton>
              </div>
            </section>

            <section className="template-panel" aria-label="待处理清单">
              <div className="template-panel__header">
                <div>
                  <p className="template-panel__eyebrow">待处理清单</p>
                  <h2>{selectedItemIssues.length > 0 ? `${selectedItemIssues.length} 个问题` : "没有阻塞问题"}</h2>
                </div>
              </div>
              {selectedItemIssues.length === 0 ? (
                <div className="template-mapping-empty">该模板项已通过导出前检查。</div>
              ) : (
                <div className="template-delivery-issue-list">
                  {selectedItemIssues.map((issue, index) => (
                    <article key={`${issue.code}-${index}`} className="template-delivery-issue">
                      <div>
                        <strong>{issue.message}</strong>
                        <p>{issue.asset_name ? `关联资料：${issue.asset_name}` : "按资料来源补齐，或交给模板管理员检查绑定规则。"}</p>
                      </div>
                      <div className="template-delivery-issue__actions">
                        {selectedItemSuggestion && (
                          <ClayButton size="sm" variant="secondary" onClick={() => applySuggestion(selectedItemSuggestion)}>
                            采用系统建议
                          </ClayButton>
                        )}
                        <ClayButton size="sm" variant="ghost" onClick={() => setShowAdvancedMaintenance(true)}>
                          交给管理员
                        </ClayButton>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>

            <section className="template-panel" aria-label="生成预览">
              <div className="template-panel__header">
                <div>
                  <p className="template-panel__eyebrow">生成预览</p>
                  <h2>这项会写入什么</h2>
                </div>
                <Badge variant={itemContext?.ready ? "success" : "warning"}>{itemContext?.ready ? "已就绪" : "草稿"}</Badge>
              </div>
              <div className="template-delivery-preview">
                <p>模板路径：{selectedItem.relative_path}</p>
                <p>渲染方式：{selectedItem.render_mode} / {selectedItem.item_type}</p>
                <p>资料来源：{itemBindingsQuery.data?.length ? `${itemBindingsQuery.data.length} 条已配置` : "还没有资料来源"}</p>
                <p>系统建议：{selectedItemSuggestion ? summarizeSuggestion(selectedItemSuggestion) : "暂无可用建议"}</p>
              </div>
            </section>

            <details
              className="template-panel template-advanced-maintenance"
              open={showAdvancedMaintenance}
              onToggle={(event) => setShowAdvancedMaintenance(event.currentTarget.open)}
            >
              <summary>
                <span>
                  <strong>高级维护</strong>
                  <small>模板管理员使用：绑定规则、字段映射、上下文 JSON</small>
                </span>
              </summary>
              <div className="template-field-grid template-field-grid--advanced">
                {/* Move the existing binding editor section and right-side stack here unchanged. */}
              </div>
            </details>
          </div>
```

When moving old JSX into the `<div className="template-field-grid template-field-grid--advanced">`, preserve:

- The whole old `绑定编辑器` section.
- The old right stack containing `渲染预检`, `映射建议`, `上下文预览`.

Only change old card labels inside advanced mode:

- “绑定编辑器” stays but add header title “规则配置（高级）”.
- “上下文预览” stays but title becomes “技术上下文 JSON”.

- [ ] **Step 4: Add CSS for delivery mode**

Append to `frontend/src/styles/utilities.css` near existing template classes:

```css
.template-delivery-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-5);
}

.template-delivery-panel {
  border-color: var(--color-primary-hairline);
}

.template-delivery-actions,
.template-delivery-issue__actions {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
  align-items: center;
}

.template-delivery-issue-list {
  display: grid;
  gap: var(--space-3);
}

.template-delivery-issue {
  display: flex;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-translucent);
}

.template-delivery-issue strong {
  display: block;
  margin-bottom: 4px;
}

.template-delivery-issue p,
.template-delivery-preview p {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: 1.7;
}

.template-delivery-preview {
  display: grid;
  gap: var(--space-2);
}

.template-advanced-maintenance summary {
  cursor: pointer;
  list-style: none;
}

.template-advanced-maintenance summary::-webkit-details-marker {
  display: none;
}

.template-advanced-maintenance summary span {
  display: grid;
  gap: 4px;
}

.template-advanced-maintenance summary small {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.template-field-grid--advanced {
  margin-top: var(--space-5);
}
```

- [ ] **Step 5: Run frontend typecheck/build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add frontend/src/modules/database/components/TemplateFieldWorkbench.tsx frontend/src/styles/utilities.css
git commit -m "feat: simplify template delivery workbench"
```

---

### Task 3: Add delivery-oriented tests for EditorContent

**Files:**
- Modify: `frontend/src/modules/authoring/EditorContent.test.tsx`

- [ ] **Step 1: Extend API mocks for company/personnel/evidence lists only if implementation uses them**

If Task 4 imports additional API functions such as `fetchProjectPersonnelPeople`, `fetchEvidenceAssets`, or `fetchCompanyProfiles`, add hoisted mocks and vi.mock entries. If Task 4 only derives summary from existing context and business assembly, skip this step.

- [ ] **Step 2: Add test for material composition mode**

Append this test inside `describe("EditorContent chart workflow", () => { ... })`:

```tsx
  it("shows material composition language for non-technical chapters", async () => {
    fetchBidOutlineMock.mockResolvedValueOnce({
      id: "outline-1",
      project_id: "proj-1",
      outline_name: "默认目录",
      status: "confirmed",
      chapters: [
        {
          id: "chapter-business-1",
          project_id: "proj-1",
          outline_id: "outline-1",
          chapter_code: "3",
          chapter_title: "企业资信情况",
          volume_type: "business",
          sort_order: 1,
          metadata_json: {},
        },
      ],
    });
    fetchDraftsMock.mockResolvedValueOnce([
      {
        id: "draft-business-1",
        project_id: "proj-1",
        chapter_code: "3",
        content_md: "## 企业资信情况\n我公司具备承担本项目的相关资质。",
        updated_at: "2026-05-10T00:00:00Z",
      },
    ]);
    assembleBusinessBidMock.mockResolvedValueOnce({
      project_id: "proj-1",
      run: {},
      chapters: [],
      response_matrix: [],
      missing_materials: [
        { chapter_code: "3", material_name: "安全生产许可证", material_type: "certificate", reason: "缺少有效附件" },
      ],
      boundary: "商务资料装配完成，仍有缺失资料。",
    });

    render(withClient(<EditorContent />));

    fireEvent.click(await screen.findByRole("button", { name: "资格商务装配" }));
    const chapterLabels = await screen.findAllByText("3");
    fireEvent.click(chapterLabels[1]);

    expect(await screen.findByText("资料编排"));
    expect(screen.getByText("资料位清单")).toBeInTheDocument();
    expect(screen.getByText("安全生产许可证")).toBeInTheDocument();
    expect(screen.getByText("缺少有效附件")).toBeInTheDocument();
  });
```

- [ ] **Step 3: Add test for chart task cards**

Append:

```tsx
  it("shows chart task cards with purpose, source, approval and insert actions", async () => {
    render(withClient(<EditorContent />));

    const chapterLabels = await screen.findAllByText("10.1");
    fireEvent.click(chapterLabels[1]);

    const taskRegion = await screen.findByLabelText("图表任务");
    expect(within(taskRegion).getByText("质量管理体系图")).toBeInTheDocument();
    expect(within(taskRegion).getByText("响应质量保证体系要求，展示质量管理职责链路。")).toBeInTheDocument();
    expect(within(taskRegion).getByText("{{chart:quality_system}}")).toBeInTheDocument();
    expect(within(taskRegion).getByRole("button", { name: "审批图表" })).toBeInTheDocument();
    expect(within(taskRegion).getByRole("button", { name: "插入图表" })).toBeInTheDocument();
  });
```

- [ ] **Step 4: Run tests to verify they fail before implementation**

Run:

```bash
cd frontend && npm run test -- src/modules/authoring/EditorContent.test.tsx
```

Expected: FAIL because the new delivery labels and chart task cards are not implemented.

---

### Task 4: Refactor EditorContent into chapter delivery workbench

**Files:**
- Modify: `frontend/src/modules/authoring/EditorContent.tsx`
- Modify: `frontend/src/styles/utilities.css`

- [ ] **Step 1: Import helpers**

At the top of `EditorContent.tsx`, add:

```ts
import {
  buildChartTaskCards,
  buildMaterialSlots,
  chapterDeliveryKind,
  deliveryKindLabel,
  readableContextCount,
  type ChartTaskCard,
  type MaterialSlotSummary,
} from "./chapterDelivery";
```

- [ ] **Step 2: Add selected delivery derived values**

After `const selectedTargetPages = normalizeTargetPages(selectedTargetPagesValue);`, add:

```ts
  const selectedDeliveryKind = chapterDeliveryKind(selectedOutlineChapter);
  const selectedDeliveryLabel = deliveryKindLabel(selectedDeliveryKind);
  const selectedMaterialSlots = buildMaterialSlots(selectedOutlineChapter, businessAssembly.data);
  const chartTaskCards = buildChartTaskCards(recommendedCharts, chartAssets);
```

- [ ] **Step 3: Add local presentational components above `export function EditorContent()`**

Add these components below helper functions and before `export function EditorContent()`:

```tsx
function MaterialSlotList({ slots }: { slots: MaterialSlotSummary[] }) {
  return (
    <section className="chapter-delivery-card" aria-label="资料位清单">
      <div className="chapter-delivery-card__header">
        <div>
          <strong>资料位清单</strong>
          <p>把公司、人员、业绩或附件绑定到固定资料位，避免自由插入导致格式失控。</p>
        </div>
        <Badge variant={slots.some((slot) => slot.status === "missing") ? "warning" : "success"}>
          {slots.filter((slot) => slot.status === "missing").length} 项待补
        </Badge>
      </div>
      <div className="material-slot-list">
        {slots.map((slot) => (
          <article key={slot.key} className="material-slot-item">
            <div>
              <strong>{slot.label}</strong>
              <p>{slot.helpText}</p>
            </div>
            <div className="material-slot-item__meta">
              <Badge variant={slot.status === "missing" ? "warning" : "success"}>
                {slot.status === "missing" ? "待补资料" : "已匹配"}
              </Badge>
              <span>{slot.sourceLabel}</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function TechnicalWritingBrief({
  chapterCode,
  context,
  targetPagesValue,
  onTargetPagesChange,
  onSaveTargetPages,
  saveDisabled,
  saveLabel,
}: {
  chapterCode: string;
  context: Record<string, unknown> | undefined;
  targetPagesValue: string;
  onTargetPagesChange: (value: string) => void;
  onSaveTargetPages: () => void;
  saveDisabled: boolean;
  saveLabel: string;
}) {
  return (
    <section className="chapter-delivery-card" aria-label="章节写作要求">
      <div className="chapter-delivery-card__header">
        <div>
          <strong>章节写作要求</strong>
          <p>投标工程师优先调整业务要求；完整提示词保留在高级区。</p>
        </div>
      </div>
      <div className="workflow-gate-panel__chips">
        <span>{readableContextCount(context, "constraints")}</span>
        <span>{readableContextCount(context, "scoring_items")}</span>
        <span>{readableContextCount(context, "standard_clauses")}</span>
        <span>{readableContextCount(context, "personnel_selections")}</span>
        <span>{readableContextCount(context, "equipment_selections")}</span>
        <span>{readableContextCount(context, "chart_assets")}</span>
      </div>
      <div className="chapter-target-pages" aria-label="章节篇幅设置">
        <label>
          <span>目标页数</span>
          <input
            className="clay-input"
            type="number"
            min={1}
            max={300}
            step={1}
            value={targetPagesValue}
            onChange={(event) => onTargetPagesChange(event.target.value)}
            aria-label={`${chapterCode} 目标页数`}
          />
        </label>
        <ClayButton size="sm" variant="secondary" onClick={onSaveTargetPages} disabled={saveDisabled}>
          {saveLabel}
        </ClayButton>
        <span>生成时注入篇幅要求</span>
      </div>
    </section>
  );
}

function ChartTaskCards({
  tasks,
  generating,
  approving,
  onGenerate,
  onApprove,
  onInsert,
}: {
  tasks: ChartTaskCard[];
  generating: boolean;
  approving: boolean;
  onGenerate: (chartType: string) => void;
  onApprove: (assetId: string) => void;
  onInsert: (placeholderKey: string) => void;
}) {
  return (
    <section className="chapter-delivery-card" aria-label="图表任务">
      <div className="chapter-delivery-card__header">
        <div>
          <strong>图表任务</strong>
          <p>按“任务 → 数据/结构 → 预览 → 审批 → 插入”处理图表，不自由生成不可校核图片。</p>
        </div>
        <Badge variant="info">{tasks.length}</Badge>
      </div>
      <div className="chart-task-list">
        {tasks.map((task) => (
          <article key={task.key} className="chart-task-card">
            <div className="chart-task-card__header">
              <div>
                <strong>{task.title}</strong>
                <span>{task.chartType}</span>
              </div>
              <Badge variant={chartAssetStatusVariant(task.status)}>
                {task.status === "not_generated" ? "未生成" : task.status}
              </Badge>
            </div>
            <p>{task.purpose}</p>
            <p>来源：{task.sourceSummary}</p>
            <code>{task.placeholder}</code>
            {task.renderedSvg && (
              <div className="chart-asset-card__preview">
                <img src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(task.renderedSvg)}`} alt={task.title} />
              </div>
            )}
            <div className="chart-task-card__actions">
              <ClayButton size="sm" variant="secondary" onClick={() => onGenerate(task.chartType)} disabled={generating}>
                {task.assetId ? "重新生成" : "生成图表草案"}
              </ClayButton>
              <ClayButton
                size="sm"
                variant="secondary"
                onClick={() => task.assetId && onApprove(task.assetId)}
                disabled={!task.assetId || task.status === "approved" || approving}
              >
                {task.status === "approved" ? "已审批" : "审批图表"}
              </ClayButton>
              <ClayButton size="sm" variant="ghost" onClick={() => onInsert(task.key)} disabled={!task.assetId}>
                插入图表
              </ClayButton>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Change `generateChart` mutation to accept a chart type**

Replace the current `generateChart` mutation with:

```ts
  const generateChart = useMutation({
    mutationFn: (nextChartType: string) => {
      if (!projectId) throw new Error("No project selected");
      return generateChartAsset(projectId, {
        chart_type: nextChartType,
        title: chartTitle(nextChartType),
        placeholder_key: nextChartType,
        outline_node_id: selectedOutlineChapter?.id ?? null,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chart-assets", projectId] });
    },
  });
```

Keep `chartType` state temporarily for compatibility with any remaining dropdown. If the dropdown is removed fully, delete `chartType` state and all `setChartType` references.

- [ ] **Step 5: Remove or demote old global chart sections**

Remove the old top-level sections:

- `图表资产`
- `图表生成与插入`
- old `章节生成上下文` block

Their function is replaced by `ChartTaskCards` and `TechnicalWritingBrief` inside the selected chapter view.

- [ ] **Step 6: Update editor layout selected chapter header**

Inside `<main className="editor-main">`, replace the current `editor-toolbar` block with:

```tsx
              <div className="editor-toolbar chapter-delivery-toolbar">
                <div>
                  <h2>{selected.chapter_code} {selectedOutlineChapter?.chapter_title ?? "章节草稿"}</h2>
                  <div className="chapter-delivery-toolbar__meta">
                    <Badge variant={selectedDeliveryKind === "ai_content" ? "info" : "success"}>{selectedDeliveryLabel}</Badge>
                    {selected.is_stale && <Badge variant="danger">{selected.stale_reason || "内容已过期"}</Badge>}
                  </div>
                </div>
                <ClayButton
                  onClick={() => save.mutate({ id: selected.id, content: editContent })}
                  disabled={save.isPending}
                >
                  {save.isPending ? "保存中..." : "保存正文"}
                </ClayButton>
              </div>
```

- [ ] **Step 7: Add selected chapter delivery controls above textarea**

Immediately after the new toolbar, add:

```tsx
              <div className="chapter-delivery-controls">
                {selectedDeliveryKind === "material_composition" && <MaterialSlotList slots={selectedMaterialSlots} />}
                {selectedDeliveryKind === "ai_content" && selectedOutlineChapter && (
                  <>
                    <TechnicalWritingBrief
                      chapterCode={selectedOutlineChapter.chapter_code}
                      context={chapterContext}
                      targetPagesValue={selectedTargetPagesValue}
                      onTargetPagesChange={(value) => {
                        setTargetPagesByChapter((current) => ({
                          ...current,
                          [selectedOutlineChapter.id]: value,
                        }));
                      }}
                      onSaveTargetPages={() => {
                        if (!selectedOutlineChapter || selectedTargetPages === null) return;
                        updateTargetPages.mutate({ chapter: selectedOutlineChapter, targetPages: selectedTargetPages });
                      }}
                      saveDisabled={!selectedOutlineChapter || selectedTargetPages === null || updateTargetPages.isPending}
                      saveLabel={updateTargetPages.isPending ? "保存中..." : "保存篇幅"}
                    />
                    <ChartTaskCards
                      tasks={chartTaskCards}
                      generating={generateChart.isPending}
                      approving={approveChart.isPending}
                      onGenerate={(nextChartType) => generateChart.mutate(nextChartType)}
                      onApprove={(assetId) => approveChart.mutate(assetId)}
                      onInsert={(key) => setEditContent((current) => appendChartPlaceholder(current, key))}
                    />
                  </>
                )}
              </div>
```

- [ ] **Step 8: Rename textarea section as chapter preview**

Wrap the textarea in a section:

```tsx
              <section className="chapter-delivery-card" aria-label="章节预览">
                <div className="chapter-delivery-card__header">
                  <div>
                    <strong>{selectedDeliveryKind === "ai_content" ? "AI 生成正文" : "模板生成预览"}</strong>
                    <p>{selectedDeliveryKind === "ai_content" ? "审阅生成内容，可直接修改后保存。" : "固定文字和资料位最终会装配到该章节。"}</p>
                  </div>
                </div>
                <textarea
                  className="clay-textarea draft-editor"
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  aria-label={`${selected.chapter_code} 章节正文`}
                />
              </section>
```

Remove the old standalone textarea.

- [ ] **Step 9: Update outline items to show delivery kind**

Inside `outline?.chapters.map`, compute kind inline:

```tsx
              const kind = chapterDeliveryKind(chapter);
```

If current JSX does not allow statements inside map, change the map callback to block form:

```tsx
          {outline?.chapters.map((chapter) => {
            const kind = chapterDeliveryKind(chapter);
            return (
              <div key={chapter.id} className="outline-item">
                <span className="outline-code">{chapter.chapter_code}</span>
                <span>{chapter.chapter_title}</span>
                <Badge variant={kind === "ai_content" ? "info" : "success"}>{deliveryKindLabel(kind)}</Badge>
                <ClayButton ...>
                  {chapter.volume_type === "technical" && outline?.status === "confirmed" ? "技术生成" : "生成"}
                </ClayButton>
              </div>
            );
          })}
```

Keep the existing `ClayButton` generation logic unchanged.

- [ ] **Step 10: Add CSS for chapter delivery controls**

Append to `frontend/src/styles/utilities.css`:

```css
.chapter-delivery-toolbar {
  align-items: flex-start;
}

.chapter-delivery-toolbar__meta,
.chapter-delivery-controls {
  display: flex;
  gap: var(--space-3);
  flex-wrap: wrap;
  align-items: center;
}

.chapter-delivery-controls {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  margin-bottom: var(--space-4);
}

.chapter-delivery-card {
  display: grid;
  gap: var(--space-4);
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-translucent);
}

.chapter-delivery-card__header {
  display: flex;
  justify-content: space-between;
  gap: var(--space-4);
  align-items: flex-start;
}

.chapter-delivery-card__header p {
  margin: 4px 0 0;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: 1.6;
}

.material-slot-list,
.chart-task-list {
  display: grid;
  gap: var(--space-3);
}

.material-slot-item,
.chart-task-card {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface-translucent-strong);
}

.material-slot-item {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
}

.material-slot-item p,
.chart-task-card p {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: 1.6;
}

.material-slot-item__meta,
.chart-task-card__actions {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  flex-wrap: wrap;
}

.chart-task-card__header {
  display: flex;
  justify-content: space-between;
  gap: var(--space-3);
  align-items: flex-start;
}

.chart-task-card__header span {
  display: block;
  margin-top: 2px;
  color: var(--color-text-muted);
  font-size: var(--text-xs);
}

.chart-task-card code {
  width: fit-content;
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  background: var(--color-subtle-translucent);
  color: var(--color-text-secondary);
}
```

- [ ] **Step 11: Run EditorContent tests**

Run:

```bash
cd frontend && npm run test -- src/modules/authoring/EditorContent.test.tsx
```

Expected: PASS. If previous tests still look for removed global “图表资产” or “图表生成与插入”, update them to query the selected chapter `图表任务` region instead.

- [ ] **Step 12: Commit**

Run:

```bash
git add frontend/src/modules/authoring/EditorContent.tsx frontend/src/modules/authoring/EditorContent.test.tsx frontend/src/styles/utilities.css
git commit -m "feat: add chapter delivery editor layout"
```

---

### Task 5: Full verification and cleanup

**Files:**
- Review: all files changed in Tasks 1-4

- [ ] **Step 1: Run focused tests**

Run:

```bash
cd frontend && npm run test -- src/modules/authoring/chapterDelivery.test.ts src/modules/authoring/EditorContent.test.tsx
```

Expected: PASS.

- [ ] **Step 2: Run full frontend tests**

Run:

```bash
cd frontend && npm run test
```

Expected: PASS.

- [ ] **Step 3: Run production build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 4: Manual smoke checklist**

With the frontend running against the local backend, verify:

1. Open 投标文件模板 page.
2. Default right side says “模板交付检查”, not “模板项字段面板”.
3. JSON/context/field mapping are hidden until “高级维护” is opened.
4. Select a blocked template item; issue list shows action buttons.
5. Open 章节编辑 page.
6. Select a business/non-technical chapter; it shows “资料编排” and “资料位清单”.
7. Select a technical chapter 8/9/10; it shows “AI 正文”, “章节写作要求”, “图表任务”.
8. Generate a chart task, approve it, insert it; placeholder appears in draft textarea.
9. Save draft.
10. Save target pages and trigger 技术生成; request still includes target pages.

- [ ] **Step 5: Check for accidental technical leakage in default views**

Run:

```bash
grep -R "Context\|Resolved Bindings\|来源筛选 JSON\|输出键\|target_field\|source_field" -n frontend/src/modules/database/components/TemplateFieldWorkbench.tsx frontend/src/modules/authoring/EditorContent.tsx
```

Expected:

- Matches in `TemplateFieldWorkbench.tsx` only appear inside the advanced maintenance section.
- No default-facing labels in `EditorContent.tsx` use raw JSON/internal field language.

- [ ] **Step 6: Commit final verification adjustments**

If any cleanup changes were needed:

```bash
git add frontend/src/modules/authoring frontend/src/modules/database/components/TemplateFieldWorkbench.tsx frontend/src/styles/utilities.css
git commit -m "test: verify delivery workbench interactions"
```

If no cleanup changes were needed, do not create an empty commit.

---

## Self-Review

### Spec coverage

- Default template delivery mode: Task 2.
- Advanced maintenance mode preserving old controls: Task 2.
- Material composition chapter model: Tasks 1, 3, 4.
- AI writing requirements model: Tasks 1, 4.
- Chart task card model: Tasks 1, 3, 4.
- Existing functionality preservation: Tasks 3, 4, 5.
- Verification: Task 5.

### Placeholder scan

Placeholder scan passed. The only scoped deferral is explicit non-goal behavior from the approved design: backend material-slot model and free AI diagram generation are not part of this implementation.

### Type consistency

- `ChapterDeliveryKind`, `MaterialSlotSummary`, and `ChartTaskCard` are defined in Task 1 and imported in Task 4.
- `buildChartTaskCards` accepts recommended chart keys and `ChartAsset[]`; `EditorContent` already has both.
- `buildMaterialSlots` accepts selected `BidChapter` and business assembly data; `EditorContent` already has both.
