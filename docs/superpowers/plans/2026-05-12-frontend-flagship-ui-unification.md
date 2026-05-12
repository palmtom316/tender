# Frontend Flagship UI Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify the whole frontend into a professional, steady, high-consistency tender workbench with shared button, badge/tag, tab/chip, table, form, state, and page layout patterns.

**Architecture:** First strengthen shared design-system primitives and CSS tokens so pages have one visual source of truth. Then migrate the highest-impact workspaces (`RequirementsContent`, `EditorContent`, database/company/personnel/assets/templates) away from local button/tab/table/state variants. Finish by polishing projects, review/export, settings, accessibility, and residual inline style drift.

**Tech Stack:** React 18, TypeScript, Vite, TanStack Query, Vitest/Testing Library, CSS token layers under `frontend/src/styles`.

---

## File Map

- Modify: `.impeccable.md` — already created with approved design context; keep as design source of truth.
- Modify: `frontend/src/styles/tokens.css` — add missing component tokens and semantic aliases.
- Modify: `frontend/src/styles/buttons.css` — add loading, icon, link, and segmented/chip-compatible button states.
- Modify: `frontend/src/styles/utilities.css` — consolidate badges, chips, empty/loading/error states, metric pills, asset tabs, attachment links.
- Modify: `frontend/src/styles/tables.css` — make `data-table` and `asset-table` share base table density and states.
- Modify: `frontend/src/styles/forms.css` — add field group, error/help text, textarea/select consistency.
- Modify: `frontend/src/styles/tabs.css` — add shared compact tab/chip classes for module-local tablists.
- Modify: `frontend/src/components/ui/ClayButton.tsx` — support `loading`, icon-only accessibility, and stable variant mapping.
- Modify: `frontend/src/components/ui/Badge.tsx` — add optional `size` and `tone` compatibility without breaking existing calls.
- Create: `frontend/src/components/ui/SegmentedTabs.tsx` — shared local tab/chip primitive for asset tabs, filters, and preview switches.
- Create: `frontend/src/components/ui/EmptyState.tsx` — shared empty/error/recovery state block.
- Create: `frontend/src/components/ui/LoadingState.tsx` — shared skeleton stack helper.
- Create: `frontend/src/components/ui/Toolbar.tsx` — shared toolbar row with responsive wrapping.
- Modify: `frontend/src/modules/authoring/RequirementsContent.tsx` — replace filter chips and metric buttons with shared primitives; remove inline style.
- Modify: `frontend/src/modules/authoring/EditorContent.tsx` — normalize toolbar, empty states, action hierarchy.
- Modify: `frontend/src/modules/authoring/EquipmentSelectionWorkbench.tsx` — replace local asset tabs with `SegmentedTabs`.
- Modify: `frontend/src/modules/authoring/PersonnelSelectionWorkbench.tsx` — normalize filters/table states.
- Modify: `frontend/src/modules/database/components/CompanyAssetSection.tsx` — replace local asset tabs with `SegmentedTabs` and shared toolbar.
- Modify: `frontend/src/modules/database/components/asset/AssetTable.tsx` — use shared empty state and attachment link/button semantics.
- Modify: `frontend/src/modules/database/components/asset/AssetFormDrawer.tsx` — normalize textarea, attachment links, footer actions.
- Modify: `frontend/src/modules/database/components/PersonnelLibraryWorkbench.tsx` — normalize table action/link/button patterns.
- Modify: `frontend/src/modules/database/components/CompanyLibraryWorkbench.tsx` — normalize summary pills and content buttons.
- Modify: `frontend/src/modules/database/components/TemplateFieldWorkbench.tsx` — normalize summary pills, preview tabs, suggestion badges, buttons.
- Modify: `frontend/src/modules/database/components/StandardSearchCard.tsx` — use shared empty state if needed.
- Modify: `frontend/src/modules/database/components/StandardClauseTree.tsx` — use shared empty state class structure.
- Modify: `frontend/src/modules/projects/ProjectsModule.tsx` — replace plain empty text with shared empty state and align create form.
- Modify: `frontend/src/modules/review/ReviewIssuesContent.tsx` — normalize toolbar and empty states.
- Modify: `frontend/src/modules/review/ComplianceContent.tsx` — normalize empty state and table wrapper.
- Modify: `frontend/src/modules/export/ExportGateContent.tsx` — normalize empty/error states and action hierarchy.
- Modify: `frontend/src/modules/export/ExportHistoryContent.tsx` — normalize empty states and tables.
- Modify: `frontend/src/modules/settings/SettingsModule.tsx` — remove layout inline styles and use shared empty/form/action patterns.
- Test: `frontend/src/components/ui/SegmentedTabs.test.tsx`
- Test: `frontend/src/components/ui/EmptyState.test.tsx`
- Test: `frontend/src/components/ui/ClayButton.test.tsx`
- Test: `frontend/src/styles/design-system-contract.test.ts`

## Task 1: Add design-system contract tests

**Files:**
- Create: `frontend/src/styles/design-system-contract.test.ts`
- Create: `frontend/src/components/ui/ClayButton.test.tsx`
- Create: `frontend/src/components/ui/EmptyState.test.tsx`
- Create: `frontend/src/components/ui/SegmentedTabs.test.tsx`

- [ ] **Step 1: Create CSS contract test**

Create `frontend/src/styles/design-system-contract.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(__dirname, "../..");
const read = (path: string) => readFileSync(resolve(root, path), "utf8");

describe("design-system CSS contracts", () => {
  it("defines shared component tokens used across pages", () => {
    const tokens = read("src/styles/tokens.css");
    expect(tokens).toContain("--control-height-sm");
    expect(tokens).toContain("--control-height-md");
    expect(tokens).toContain("--control-height-lg");
    expect(tokens).toContain("--table-row-height");
    expect(tokens).toContain("--toolbar-gap");
    expect(tokens).toContain("--state-icon-size");
  });

  it("shares table styling between data and asset tables", () => {
    const tables = read("src/styles/tables.css");
    expect(tables).toContain(":where(.data-table, .asset-table)");
    expect(tables).toContain(":where(.data-table, .asset-table) th");
    expect(tables).toContain(":where(.data-table, .asset-table) td");
  });

  it("provides unified chip and local tab classes", () => {
    const tabs = read("src/styles/tabs.css") + read("src/styles/utilities.css");
    expect(tabs).toContain(".segmented-tabs");
    expect(tabs).toContain(".segmented-tab");
    expect(tabs).toContain(".filter-chip");
  });
});
```

- [ ] **Step 2: Create ClayButton behavior test**

Create `frontend/src/components/ui/ClayButton.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ClayButton } from "./ClayButton";

describe("ClayButton", () => {
  it("maps secondary to outline for backwards compatibility", () => {
    render(<ClayButton variant="secondary">次级</ClayButton>);
    expect(screen.getByRole("button", { name: "次级" })).toHaveClass("clay-btn--outline");
  });

  it("exposes busy state when loading", () => {
    render(<ClayButton loading>保存</ClayButton>);
    const button = screen.getByRole("button", { name: "保存中" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });
});
```

- [ ] **Step 3: Create EmptyState test**

Create `frontend/src/components/ui/EmptyState.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EmptyState } from "./EmptyState";


describe("EmptyState", () => {
  it("renders title, description, icon, and action", () => {
    render(
      <EmptyState
        icon="项"
        title="先选择投标项目"
        description="选择项目后，可继续上传和解析招标文件。"
        action={<button type="button">去选择</button>}
      />,
    );

    expect(screen.getByText("项")).toBeInTheDocument();
    expect(screen.getByText("先选择投标项目")).toBeInTheDocument();
    expect(screen.getByText("选择项目后，可继续上传和解析招标文件。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "去选择" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: Create SegmentedTabs test**

Create `frontend/src/components/ui/SegmentedTabs.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SegmentedTabs } from "./SegmentedTabs";

const items = [
  { id: "vehicle", label: "车辆", count: 2 },
  { id: "equipment", label: "施工机械", count: 4 },
];

describe("SegmentedTabs", () => {
  it("marks the selected tab accessibly and calls onChange", () => {
    const onChange = vi.fn();
    render(<SegmentedTabs ariaLabel="资产分类" items={items} value="vehicle" onChange={onChange} />);

    expect(screen.getByRole("tab", { name: "车辆 2" })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("tab", { name: "施工机械 4" }));
    expect(onChange).toHaveBeenCalledWith("equipment");
  });
});
```

- [ ] **Step 5: Run tests and verify expected failures**

Run:

```bash
cd frontend && npm run test -- --run src/styles/design-system-contract.test.ts src/components/ui/ClayButton.test.tsx src/components/ui/EmptyState.test.tsx src/components/ui/SegmentedTabs.test.tsx
```

Expected: FAIL because the new components and CSS contracts are not implemented yet.

## Task 2: Strengthen shared UI primitives

**Files:**
- Modify: `frontend/src/components/ui/ClayButton.tsx`
- Modify: `frontend/src/components/ui/Badge.tsx`
- Create: `frontend/src/components/ui/EmptyState.tsx`
- Create: `frontend/src/components/ui/LoadingState.tsx`
- Create: `frontend/src/components/ui/SegmentedTabs.tsx`
- Create: `frontend/src/components/ui/Toolbar.tsx`

- [ ] **Step 1: Implement loading-aware ClayButton**

Replace `frontend/src/components/ui/ClayButton.tsx` with:

```tsx
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "ghost" | "outline" | "danger" | "secondary";
type Size = "sm" | "md" | "lg";

interface ClayButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  children: ReactNode;
}

export function ClayButton({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  className = "",
  children,
  ...rest
}: ClayButtonProps) {
  const normalizedVariant = variant === "secondary" ? "outline" : variant;
  const cls = [
    "clay-btn",
    `clay-btn--${normalizedVariant}`,
    size !== "md" ? `clay-btn--${size}` : "",
    loading ? "is-loading" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button className={cls} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading && <span className="clay-btn__spinner" aria-hidden="true" />}
      <span className="clay-btn__label">{loading ? "保存中" : children}</span>
    </button>
  );
}
```

- [ ] **Step 2: Extend Badge without breaking existing calls**

Replace `frontend/src/components/ui/Badge.tsx` with:

```tsx
import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

type BadgeVariant = "default" | "primary" | "success" | "warning" | "danger" | "info";
type BadgeSize = "sm" | "md";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  tone?: BadgeVariant;
  size?: BadgeSize;
  children: ReactNode;
  style?: CSSProperties;
}

export function Badge({ variant = "default", tone, size = "md", children, style, className = "", ...rest }: BadgeProps) {
  const resolvedVariant = tone ?? variant;
  return (
    <span
      className={`clay-badge clay-badge--${resolvedVariant} clay-badge--${size} ${className}`.trim()}
      style={style}
      {...rest}
    >
      {children}
    </span>
  );
}
```

- [ ] **Step 3: Add EmptyState component**

Create `frontend/src/components/ui/EmptyState.tsx`:

```tsx
import type { ReactNode } from "react";

type EmptyStateTone = "default" | "info" | "warning" | "danger" | "success";

interface EmptyStateProps {
  icon?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  tone?: EmptyStateTone;
  spacious?: boolean;
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  tone = "default",
  spacious = false,
  className = "",
}: EmptyStateProps) {
  const cls = ["empty-state", `empty-state--${tone}`, spacious ? "empty-state--spacious" : "", className]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={cls}>
      {icon && <span className="empty-state__icon">{icon}</span>}
      <p className="empty-state__title">{title}</p>
      {description && <p className="empty-state__description">{description}</p>}
      {action && <div className="empty-state__action">{action}</div>}
    </div>
  );
}
```

- [ ] **Step 4: Add LoadingState component**

Create `frontend/src/components/ui/LoadingState.tsx`:

```tsx
interface LoadingStateProps {
  label: string;
  rows?: number;
  compact?: boolean;
}

export function LoadingState({ label, rows = 2, compact = false }: LoadingStateProps) {
  return (
    <div className={`skeleton-stack ${compact ? "skeleton-stack--compact" : ""}`} aria-label={label}>
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className={index === 0 ? "skeleton-card" : "skeleton-line"} />
      ))}
    </div>
  );
}
```

- [ ] **Step 5: Add SegmentedTabs component**

Create `frontend/src/components/ui/SegmentedTabs.tsx`:

```tsx
import { Badge } from "./Badge";

export interface SegmentedTabItem<T extends string> {
  id: T;
  label: string;
  count?: number;
  disabled?: boolean;
}

interface SegmentedTabsProps<T extends string> {
  ariaLabel: string;
  items: SegmentedTabItem<T>[];
  value: T;
  onChange: (value: T) => void;
  compact?: boolean;
  className?: string;
}

export function SegmentedTabs<T extends string>({
  ariaLabel,
  items,
  value,
  onChange,
  compact = false,
  className = "",
}: SegmentedTabsProps<T>) {
  return (
    <div className={`segmented-tabs ${compact ? "segmented-tabs--compact" : ""} ${className}`.trim()} role="tablist" aria-label={ariaLabel}>
      {items.map((item) => {
        const active = item.id === value;
        const label = item.count == null ? item.label : `${item.label} ${item.count}`;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={active}
            aria-label={label}
            disabled={item.disabled}
            className={`segmented-tab ${active ? "is-active" : ""}`}
            onClick={() => onChange(item.id)}
          >
            <span>{item.label}</span>
            {item.count != null && <Badge size="sm" variant={active ? "primary" : "default"}>{item.count}</Badge>}
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 6: Add Toolbar component**

Create `frontend/src/components/ui/Toolbar.tsx`:

```tsx
import type { ReactNode } from "react";

interface ToolbarProps {
  children: ReactNode;
  align?: "start" | "between" | "end";
  className?: string;
}

export function Toolbar({ children, align = "between", className = "" }: ToolbarProps) {
  return <div className={`toolbar-row toolbar-row--${align} ${className}`.trim()}>{children}</div>;
}
```

- [ ] **Step 7: Run component tests**

Run:

```bash
cd frontend && npm run test -- --run src/components/ui/ClayButton.test.tsx src/components/ui/EmptyState.test.tsx src/components/ui/SegmentedTabs.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit shared primitives**

Run:

```bash
git add frontend/src/components/ui frontend/src/styles/design-system-contract.test.ts
git commit -m "feat: strengthen shared frontend UI primitives"
```

## Task 3: Normalize CSS tokens, controls, tables, tabs, and states

**Files:**
- Modify: `frontend/src/styles/tokens.css`
- Modify: `frontend/src/styles/buttons.css`
- Modify: `frontend/src/styles/tables.css`
- Modify: `frontend/src/styles/forms.css`
- Modify: `frontend/src/styles/tabs.css`
- Modify: `frontend/src/styles/utilities.css`

- [ ] **Step 1: Add component-level tokens**

In `frontend/src/styles/tokens.css`, inside `:root` after layout tokens, add:

```css
  /* Component sizing */
  --control-height-sm: 30px;
  --control-height-md: 36px;
  --control-height-lg: 42px;
  --control-padding-x-sm: var(--space-3);
  --control-padding-x-md: var(--space-4);
  --control-padding-x-lg: var(--space-6);
  --toolbar-gap: var(--space-3);
  --table-row-height: 44px;
  --table-cell-padding-y: 10px;
  --table-cell-padding-x: var(--space-4);
  --state-icon-size: 38px;
```

- [ ] **Step 2: Update button CSS for loading and token sizing**

In `frontend/src/styles/buttons.css`, change `.clay-btn` sizing to use component tokens and append spinner rules:

```css
.clay-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: 0 var(--control-padding-x-md);
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  font-weight: 650;
  white-space: nowrap;
  min-height: var(--control-height-md);
  line-height: 1;
  letter-spacing: 0;
  cursor: pointer;
  transition:
    background var(--transition-fast),
    border-color var(--transition-fast),
    color var(--transition-fast),
    box-shadow var(--transition-fast),
    transform var(--transition-fast);
}

.clay-btn--sm {
  min-width: 56px;
  min-height: var(--control-height-sm);
  padding: 0 var(--control-padding-x-sm);
  font-size: var(--text-xs);
  border-radius: var(--radius-xs);
}

.clay-btn--lg {
  padding: 0 var(--control-padding-x-lg);
  font-size: var(--text-base);
  min-height: var(--control-height-lg);
}

.clay-btn__spinner {
  width: 12px;
  height: 12px;
  border: 2px solid color-mix(in srgb, currentColor 30%, transparent);
  border-top-color: currentColor;
  border-radius: var(--radius-full);
  animation: clay-spin 0.8s linear infinite;
}

@keyframes clay-spin {
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .clay-btn,
  .clay-btn__spinner {
    transition: none;
    animation: none;
  }
}
```

Keep existing variant rules below this block.

- [ ] **Step 3: Replace table CSS with shared base selectors**

Replace `frontend/src/styles/tables.css` with:

```css
/* ── Data Tables ── */
.table-scroll,
.asset-table-wrap,
.company-contract-table-wrap,
.standard-viewer-modal__table-wrap,
.source-viewer__table-wrap,
.ai-extraction-panel__table-wrap,
.document-upload-ledger__table-wrap,
.personnel-table-wrap {
  width: 100%;
  overflow-x: auto;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  background: var(--color-surface);
}

:where(.data-table, .asset-table, .source-viewer__table, .ai-extraction-panel__table) {
  width: 100%;
  border-collapse: collapse;
  min-width: 720px;
}

:where(.data-table, .asset-table, .source-viewer__table, .ai-extraction-panel__table) th,
:where(.data-table, .asset-table, .source-viewer__table, .ai-extraction-panel__table) td {
  min-height: var(--table-row-height);
  padding: var(--table-cell-padding-y) var(--table-cell-padding-x);
  text-align: left;
  border-bottom: 1px solid var(--color-border-light);
  font-size: var(--text-sm);
  line-height: 1.55;
  vertical-align: top;
}

:where(.data-table, .asset-table, .source-viewer__table, .ai-extraction-panel__table) th {
  color: var(--color-text-secondary);
  font-weight: 700;
  font-size: var(--text-xs);
  text-transform: none;
  letter-spacing: 0.03em;
  background: var(--color-subtle-translucent);
}

:where(.data-table, .asset-table, .source-viewer__table, .ai-extraction-panel__table) tr:last-child td {
  border-bottom: none;
}

:where(.data-table, .asset-table, .source-viewer__table, .ai-extraction-panel__table) tbody tr:hover td {
  background: color-mix(in srgb, var(--color-primary-light) 68%, transparent);
}

.table-actions,
.asset-table__actions,
.standards-table-card__actions,
.company-contract-table__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: var(--space-2);
}
```

- [ ] **Step 4: Append unified segmented tab and chip CSS**

Append to `frontend/src/styles/tabs.css`:

```css
.segmented-tabs {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-1);
  padding: var(--space-1);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  background: var(--color-subtle-translucent);
}

.segmented-tabs--compact {
  border-radius: var(--radius-sm);
}

.segmented-tab,
.filter-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  min-height: var(--control-height-sm);
  padding: 0 var(--space-3);
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: 650;
  cursor: pointer;
  transition:
    color var(--transition-fast),
    background var(--transition-fast),
    border-color var(--transition-fast),
    box-shadow var(--transition-fast);
}

.segmented-tab:hover,
.filter-chip:hover {
  color: var(--color-text);
  background: var(--color-surface-translucent-strong);
}

.segmented-tab.is-active,
.filter-chip.active,
.filter-chip[aria-pressed="true"] {
  color: var(--color-primary);
  border-color: var(--color-primary-hairline);
  background: var(--color-primary-light);
  box-shadow: var(--shadow-clay);
}

.segmented-tab:focus-visible,
.filter-chip:focus-visible,
.tab-item:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}
```

- [ ] **Step 5: Update forms and utilities for states**

Append to `frontend/src/styles/forms.css`:

```css
.field-help {
  margin-top: var(--space-1);
  color: var(--color-text-muted);
  font-size: var(--text-xs);
  line-height: 1.5;
}

.field-error {
  margin-top: var(--space-1);
  color: var(--color-danger);
  font-size: var(--text-xs);
  line-height: 1.5;
}

.clay-input[aria-invalid="true"],
.clay-textarea[aria-invalid="true"] {
  border-color: var(--color-danger);
  box-shadow: 0 0 0 3px var(--color-danger-bg);
}

select.clay-input {
  appearance: none;
  padding-right: var(--space-8);
}
```

Append to `frontend/src/styles/utilities.css`:

```css
.empty-state__action {
  margin-top: var(--space-4);
  display: flex;
  justify-content: center;
  gap: var(--space-2);
}

.empty-state--info .empty-state__icon { color: var(--color-info); background: var(--color-info-bg); }
.empty-state--warning .empty-state__icon { color: var(--color-warning); background: var(--color-warning-bg); }
.empty-state--danger .empty-state__icon { color: var(--color-danger); background: var(--color-danger-bg); }
.empty-state--success .empty-state__icon { color: var(--color-success); background: var(--color-success-bg); }

.skeleton-stack--compact {
  gap: var(--space-2);
}

.toolbar-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--toolbar-gap);
}

.toolbar-row--start { justify-content: flex-start; }
.toolbar-row--end { justify-content: flex-end; }
.toolbar-row--between { justify-content: space-between; }

.attachment-link,
.asset-table__attachment-link,
.asset-drawer__attachment-link {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 var(--space-2);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-xs);
  background: var(--color-surface-translucent-strong);
  color: var(--color-primary);
  font-size: var(--text-xs);
  font-weight: 650;
  text-decoration: none;
  cursor: pointer;
}
```

- [ ] **Step 6: Run CSS contract test and build**

Run:

```bash
cd frontend && npm run test -- --run src/styles/design-system-contract.test.ts && npm run build
```

Expected: PASS.

- [ ] **Step 7: Commit CSS normalization**

Run:

```bash
git add frontend/src/styles
git commit -m "style: normalize frontend design-system CSS"
```

## Task 4: Flagship Requirements workbench pass

**Files:**
- Modify: `frontend/src/modules/authoring/RequirementsContent.tsx`

- [ ] **Step 1: Import shared primitives**

Add imports near existing UI imports:

```tsx
import { EmptyState } from "../../components/ui/EmptyState";
import { LoadingState } from "../../components/ui/LoadingState";
import { SegmentedTabs } from "../../components/ui/SegmentedTabs";
import { Toolbar } from "../../components/ui/Toolbar";
```

- [ ] **Step 2: Replace no-project empty state**

Replace the no-project block with:

```tsx
  if (!projectId) {
    return (
      <EmptyState
        icon="项"
        title="先选择投标项目"
        description="选择项目后，可核对废标红线、资格商务硬条件和递交清单。"
        spacious
      />
    );
  }
```

- [ ] **Step 3: Remove inline toolbar style**

Find:

```tsx
<div className="toolbar-row" style={{ margin: 0 }}>
```

Replace with:

```tsx
<Toolbar className="toolbar-row--flush">
```

Replace its matching closing `</div>` with `</Toolbar>`.

- [ ] **Step 4: Replace lane filter chips with SegmentedTabs**

Replace the whole `requirement-workbench__tabs` block with:

```tsx
      <div className="requirement-workbench__tabs">
        <SegmentedTabs
          ariaLabel="要求确认筛选"
          value={activeLane}
          onChange={setActiveLane}
          items={[
            { id: "all", label: "全部工作项", count: workbench?.packages.length ?? 0 },
            ...laneTabs.map((lane) => ({ id: lane.id, label: lane.label, count: lane.packages.length })),
          ]}
        />
      </div>
```

- [ ] **Step 5: Replace loading and empty states**

Replace loading skeleton block with:

```tsx
      {isLoading && <LoadingState label="关键条款加载中" rows={3} />}
```

Replace empty parsed requirements block with:

```tsx
      {!isLoading && workbench?.packages.length === 0 && (
        <EmptyState
          icon="条"
          title="暂无解析条款"
          description="上传并解析招标文件后，系统会先合并相似条款，再生成关键确认队列。"
          tone="info"
        />
      )}
```

Replace trace-panel empty block with:

```tsx
              <EmptyState
                title="选择一个条款包"
                description="右侧会显示原文、来源页码、冲突字段和处理记录。"
                icon="源"
              />
```

- [ ] **Step 6: Run focused tests and build**

Run:

```bash
cd frontend && npm run test -- --run src/modules/authoring/ParseContent.test.tsx src/modules/authoring/UploadContent.test.tsx && npm run build
```

Expected: PASS.

- [ ] **Step 7: Commit requirements pass**

Run:

```bash
git add frontend/src/modules/authoring/RequirementsContent.tsx
git commit -m "style: normalize requirements workbench UI"
```

## Task 5: Normalize local tabs and tables in asset/personnel/equipment flows

**Files:**
- Modify: `frontend/src/modules/database/components/CompanyAssetSection.tsx`
- Modify: `frontend/src/modules/authoring/EquipmentSelectionWorkbench.tsx`
- Modify: `frontend/src/modules/database/components/asset/AssetTable.tsx`
- Modify: `frontend/src/modules/database/components/asset/AssetFormDrawer.tsx`
- Modify: `frontend/src/modules/database/components/PersonnelLibraryWorkbench.tsx`

- [ ] **Step 1: Replace CompanyAssetSection local tabs**

In `CompanyAssetSection.tsx`, add:

```tsx
import { SegmentedTabs } from "../../../components/ui/SegmentedTabs";
```

Replace the `.asset-tabs` block with:

```tsx
        <SegmentedTabs
          ariaLabel="资产分类"
          value={activeType}
          onChange={setActiveType}
          items={ASSET_TABS.map((type) => ({
            id: type,
            label: ASSET_TYPE_SCHEMAS[type].label,
            count: counts[type],
          }))}
        />
```

- [ ] **Step 2: Replace EquipmentSelectionWorkbench local tabs**

In `EquipmentSelectionWorkbench.tsx`, add:

```tsx
import { SegmentedTabs } from "../../components/ui/SegmentedTabs";
```

Replace the `.asset-tabs` block with:

```tsx
        <SegmentedTabs
          ariaLabel="设备分类"
          value={assetType}
          onChange={setAssetType}
          items={ASSET_TYPE_TABS.map((tab) => ({
            id: tab.key,
            label: tab.label,
            count: groupedAssets[tab.key]?.length ?? 0,
          }))}
        />
```

If the file uses a different tab array name, keep the existing array and map its `key`/`label` fields exactly as shown.

- [ ] **Step 3: Use shared EmptyState in AssetTable**

In `AssetTable.tsx`, add:

```tsx
import { EmptyState } from "../../../../components/ui/EmptyState";
```

Replace:

```tsx
return <div className="template-strip-empty">当前分类还没有资产记录。</div>;
```

With:

```tsx
return <EmptyState icon="资" title="当前分类还没有资产记录" description="新增资产后，会在这里展示规格、附件、有效期和状态。" />;
```

- [ ] **Step 4: Normalize AssetFormDrawer notes textarea**

In `AssetFormDrawer.tsx`, replace:

```tsx
<textarea className="clay-input asset-drawer__notes" aria-label="备注" placeholder="备注" value={form.notes} onChange={(event) => updateField("notes", event.target.value)} />
```

With:

```tsx
<textarea className="clay-textarea asset-drawer__notes" aria-label="备注" placeholder="备注" value={form.notes} onChange={(event) => updateField("notes", event.target.value)} />
```

- [ ] **Step 5: Normalize personnel attachment buttons**

In `PersonnelLibraryWorkbench.tsx`, change attachment buttons from only `asset-table__attachment-link` to include shared class:

```tsx
className="attachment-link asset-table__attachment-link"
```

Do the same for drawer attachment buttons:

```tsx
className="attachment-link asset-drawer__attachment-link"
```

- [ ] **Step 6: Run database and asset tests/build**

Run:

```bash
cd frontend && npm run test -- --run src/modules/database/components/CompanyLibraryWorkbench.test.tsx src/modules/database/components/StandardSearchCard.test.tsx && npm run build
```

Expected: PASS.

- [ ] **Step 7: Commit asset/personnel normalization**

Run:

```bash
git add frontend/src/modules/database/components/CompanyAssetSection.tsx frontend/src/modules/authoring/EquipmentSelectionWorkbench.tsx frontend/src/modules/database/components/asset/AssetTable.tsx frontend/src/modules/database/components/asset/AssetFormDrawer.tsx frontend/src/modules/database/components/PersonnelLibraryWorkbench.tsx
git commit -m "style: normalize asset and personnel workbench UI"
```

## Task 6: Normalize editor, projects, review/export, and settings states

**Files:**
- Modify: `frontend/src/modules/authoring/EditorContent.tsx`
- Modify: `frontend/src/modules/projects/ProjectsModule.tsx`
- Modify: `frontend/src/modules/review/ReviewIssuesContent.tsx`
- Modify: `frontend/src/modules/review/ComplianceContent.tsx`
- Modify: `frontend/src/modules/export/ExportGateContent.tsx`
- Modify: `frontend/src/modules/export/ExportHistoryContent.tsx`
- Modify: `frontend/src/modules/settings/SettingsModule.tsx`

- [ ] **Step 1: Use shared EmptyState/LoadingState in EditorContent**

Add imports:

```tsx
import { EmptyState } from "../../components/ui/EmptyState";
import { LoadingState } from "../../components/ui/LoadingState";
```

Replace no-project and no-draft empty state blocks with `EmptyState` equivalents using the same Chinese text. Replace the drafts loading skeleton with:

```tsx
<LoadingState label="章节草稿加载中" rows={3} compact />
```

- [ ] **Step 2: Use shared EmptyState in ProjectsModule**

Add import:

```tsx
import { EmptyState } from "../../components/ui/EmptyState";
```

Replace:

```tsx
<p className="empty-state">暂无项目，请点击"新建项目"开始</p>
```

With:

```tsx
<EmptyState
  icon="项"
  title="暂无项目"
  description="点击新建项目后，可上传招标文件并启动解析。"
  action={<ClayButton type="button" onClick={() => setShowForm(true)}>新建项目</ClayButton>}
/>
```

- [ ] **Step 3: Normalize review/export plain empty paragraphs**

In `ReviewIssuesContent.tsx`, `ComplianceContent.tsx`, `ExportGateContent.tsx`, and `ExportHistoryContent.tsx`, add `EmptyState` imports and replace plain `<p className="empty-state">...` returns with structured `EmptyState` components. Use these mappings:

```tsx
<EmptyState icon="项" title="请先选择投标项目" description="选择项目后，可查看审校、合规或导出状态。" />
<EmptyState icon="审" title="暂无审校问题" description="完成审校后，问题会按风险等级显示在这里。" tone="success" />
<EmptyState icon="矩" title="暂无响应矩阵数据" description="生成响应矩阵后，可在这里核对条款响应状态。" />
<EmptyState icon="包" title="暂无交付包" description="满足导出门禁后，可生成投标交付包。" />
<EmptyState icon="导" title="暂无导出记录" description="导出完成后会在这里保留历史记录。" />
```

- [ ] **Step 4: Remove SettingsModule layout inline styles**

In `SettingsModule.tsx`, replace inline avatar sizing:

```tsx
<div className="avatar-circle" style={{ width: 36, height: 36 }}>
```

With:

```tsx
<div className="avatar-circle avatar-circle--md">
```

Replace inline font weight block:

```tsx
<div style={{ fontWeight: 600 }}>{user.display_name}</div>
```

With:

```tsx
<div className="font-semibold">{user.display_name}</div>
```

Replace:

```tsx
<div className="empty-state" style={{ padding: "var(--space-12)" }}>
```

With:

```tsx
<div className="empty-state empty-state--spacious">
```

- [ ] **Step 5: Add utility classes for settings replacements**

Append to `frontend/src/styles/utilities.css`:

```css
.avatar-circle--md {
  width: 36px;
  height: 36px;
}

.font-semibold {
  font-weight: 650;
}
```

- [ ] **Step 6: Run tests/build**

Run:

```bash
cd frontend && npm run test -- --run src/modules/export/ExportGateContent.test.tsx src/modules/review/ReviewIssuesContent.test.tsx && npm run build
```

Expected: PASS.

- [ ] **Step 7: Commit page state normalization**

Run:

```bash
git add frontend/src/modules/authoring/EditorContent.tsx frontend/src/modules/projects/ProjectsModule.tsx frontend/src/modules/review frontend/src/modules/export frontend/src/modules/settings/SettingsModule.tsx frontend/src/styles/utilities.css
git commit -m "style: normalize page states across frontend modules"
```

## Task 7: Clean up remaining local visual drift

**Files:**
- Modify: `frontend/src/modules/database/components/CompanyLibraryWorkbench.tsx`
- Modify: `frontend/src/modules/database/components/TemplateFieldWorkbench.tsx`
- Modify: `frontend/src/modules/database/components/StandardClauseTree.tsx`
- Modify: `frontend/src/modules/database/components/StandardSearchCard.tsx`
- Modify: CSS under `frontend/src/styles/utilities.css` if needed.

- [ ] **Step 1: Normalize summary pills with semantic class only**

In `CompanyLibraryWorkbench.tsx` and `TemplateFieldWorkbench.tsx`, keep `template-summary__pill` markup but ensure each pill is inside `summary-pill-row`. Do not add page-specific colors. If a pill needs emphasis, add `template-summary__pill--primary` only for the current selected or most important value.

- [ ] **Step 2: Normalize template preview tabs class**

In `TemplateFieldWorkbench.tsx`, change the preview container from:

```tsx
<div className="template-preview-tabs">
```

To:

```tsx
<div className="template-preview-tabs segmented-tabs">
```

For each child preview block, add `segmented-tab` if it is clickable. If the preview blocks are not clickable, keep them as `template-preview-block` and rely on CSS only for layout.

- [ ] **Step 3: Replace StandardClauseTree plain empty state**

In `StandardClauseTree.tsx`, add `EmptyState` import and replace:

```tsx
return <div className="empty-state">暂无可展示条款</div>;
```

With:

```tsx
return <EmptyState icon="条" title="暂无可展示条款" description="规范解析完成后，条款树会显示在这里。" />;
```

- [ ] **Step 4: Run drift search**

Run:

```bash
grep -RIn "style=\{\{" frontend/src --include='*.tsx'
grep -RIn "<p className=\"empty-state\"" frontend/src --include='*.tsx'
grep -RIn "className=\"[^\"]*asset-tab" frontend/src --include='*.tsx'
```

Expected: no matches for the second and third commands. The first command may still show intentional dynamic CSS variable styles such as progress percentages or clause indentation; inspect each remaining match and only keep dynamic CSS-variable cases.

- [ ] **Step 5: Run full frontend verification**

Run:

```bash
cd frontend && npm run test -- --run && npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit drift cleanup**

Run:

```bash
git add frontend/src/modules/database/components frontend/src/styles/utilities.css
git commit -m "style: clean up remaining frontend visual drift"
```

## Task 8: Final verification and report

**Files:**
- Create: `docs/superpowers/reports/2026-05-12-frontend-flagship-ui-unification-verification.md`

- [ ] **Step 1: Run full verification commands**

Run:

```bash
cd frontend && npm run test -- --run && npm run build
```

Expected: both commands PASS.

- [ ] **Step 2: Run consistency searches**

Run:

```bash
grep -RIn "<p className=\"empty-state\"" frontend/src --include='*.tsx' || true
grep -RIn "className=\"[^\"]*asset-tab" frontend/src --include='*.tsx' || true
grep -RIn "style=\{\{" frontend/src --include='*.tsx' || true
```

Expected: no plain empty paragraphs and no `asset-tab` JSX usage. Remaining `style={{ ... }}` entries must be documented as dynamic CSS variable or measured layout cases.

- [ ] **Step 3: Write verification report**

Create `docs/superpowers/reports/2026-05-12-frontend-flagship-ui-unification-verification.md`:

```md
# Frontend Flagship UI Unification Verification

**Date:** 2026-05-12

## Commands

- `cd frontend && npm run test -- --run`
- `cd frontend && npm run build`
- `grep -RIn "<p className=\"empty-state\"" frontend/src --include='*.tsx' || true`
- `grep -RIn "className=\"[^\"]*asset-tab" frontend/src --include='*.tsx' || true`
- `grep -RIn "style=\{\{" frontend/src --include='*.tsx' || true`

## Result

- Tests: PASS
- Build: PASS
- Plain empty-state paragraphs: none
- Local asset-tab JSX: none
- Remaining inline styles: only dynamic CSS-variable or measured layout cases

## Notes

The frontend now uses shared primitives for buttons, badges, segmented local tabs, empty states, loading states, toolbars, and core table density. The highest-drift asset/personnel/requirements/editor flows were normalized without changing backend API semantics.
```

- [ ] **Step 4: Commit verification report**

Run:

```bash
git add docs/superpowers/reports/2026-05-12-frontend-flagship-ui-unification-verification.md
git commit -m "docs: verify frontend flagship UI unification"
```

## Self-Review

- Spec coverage: design context, token normalization, shared Button/Badge/Tab/Table/Form/State rules, P1/P2/P3 page passes, accessibility/focus/reduced motion, and verification are all covered by Tasks 1–8.
- Placeholder scan: no TBD/TODO placeholders. Steps include exact files, code, commands, and expected results.
- Type consistency: `ClayButton.loading`, `Badge.size/tone`, `EmptyState`, `LoadingState`, `SegmentedTabs`, and `Toolbar` are defined before being used.
