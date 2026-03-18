# Frontend Workbench Refactor Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `frontend/` 现有分散流程页重构为统一的浅色极简工作台，满足侧栏导航、模块标签、卡片化工作区、顶部滚动提示和隐藏式 `Copilot` 助手等设计要求。

**Architecture:** 先新增统一 `App Shell` 与设计 token，再把现有业务页改造成工作区内容片段并接入模块/标签导航。保持现有 React Query 请求与接口语义不变，优先替换布局与样式层，避免一次性重写业务逻辑。

**Tech Stack:** React 18、TypeScript、Vite、TanStack Query、CSS（token 化 + 分层样式）、可选 Vitest + Testing Library（最小 UI 回归保障）。

---

## File Map

- Modify: `frontend/src/App.tsx` — 从简单路径判断升级为工作台入口编排
- Modify: `frontend/src/main.tsx` — 挂载全局快捷键、查询客户端保持不变
- Modify: `frontend/src/styles.css` — 拆出/迁移为全局 token 与基础样式
- Modify: `frontend/src/pages/project-list.tsx` — 迁入项目总览工作区
- Modify: `frontend/src/pages/upload.tsx` — 迁入资料库工作区内容
- Modify: `frontend/src/pages/parse-results.tsx` — 迁入资料库工作区内容
- Modify: `frontend/src/pages/requirements-confirmation.tsx` — 迁入要求确认工作区
- Modify: `frontend/src/pages/chapter-editor.tsx` — 迁入章节编辑工作区
- Modify: `frontend/src/pages/review-results.tsx` — 迁入审校导出工作区
- Modify: `frontend/src/pages/export.tsx` — 迁入审校导出工作区
- Create: `frontend/src/layouts/workbench-shell.tsx` — 左右结构壳层
- Create: `frontend/src/components/ui/app-button.tsx` — 统一按钮
- Create: `frontend/src/components/ui/app-card.tsx` — 统一卡片
- Create: `frontend/src/components/ui/status-badge.tsx` — 统一状态徽标
- Create: `frontend/src/components/ui/marquee-banner.tsx` — 顶部横向滚动提示
- Create: `frontend/src/components/ui/tab-strip.tsx` — 模块内标签导航
- Create: `frontend/src/components/ui/copilot-panel.tsx` — 右上隐藏式助手
- Create: `frontend/src/components/navigation/sidebar.tsx` — 左侧导航
- Create: `frontend/src/components/navigation/sidebar-user.tsx` — 底部用户区
- Create: `frontend/src/components/workspace/workspace-header.tsx` — 工作区头部
- Create: `frontend/src/components/workspace/empty-state-card.tsx` — 空状态卡
- Create: `frontend/src/components/workspace/stat-card.tsx` — 统计卡
- Create: `frontend/src/lib/navigation.ts` — 模块、标签与路由映射
- Create: `frontend/src/lib/ui-state.ts` — 侧栏、Copilot、banner 的 UI 状态工具
- Create: `frontend/src/styles/tokens.css` — 颜色、阴影、圆角、间距 token
- Create: `frontend/src/styles/layout.css` — 壳层与布局样式
- Create: `frontend/src/styles/components.css` — 通用组件样式
- Create: `frontend/src/styles/modules.css` — 模块级样式
- Optional Create: `frontend/src/test/setup.ts` — UI 测试初始化
- Optional Create: `frontend/src/layouts/workbench-shell.test.tsx` — 壳层 smoke test

## Chunk 1: Establish UI Baseline

### Task 1: Add minimal UI verification harness

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/test/setup.ts`
- Test: `frontend/src/layouts/workbench-shell.test.tsx`

- [ ] **Step 1: Add the failing test harness configuration**

Add `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, and `jsdom` as dev dependencies in `frontend/package.json`. Create `frontend/vitest.config.ts` and `frontend/src/test/setup.ts`.

Expected: test command exists but fails because target shell component is not implemented yet.

- [ ] **Step 2: Run config smoke check**

Run: `cd frontend && npm install && npm run test -- --run`

Expected: test runner starts and reports missing test target/component rather than config failure.

- [ ] **Step 3: Commit baseline test harness**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vitest.config.ts frontend/src/test/setup.ts
git commit -m "test: add frontend UI verification baseline"
```

### Task 2: Define design tokens and style layers

**Files:**
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/styles.css`
- Create: `frontend/src/styles/tokens.css`
- Create: `frontend/src/styles/layout.css`
- Create: `frontend/src/styles/components.css`
- Create: `frontend/src/styles/modules.css`

- [ ] **Step 1: Write the failing style integration expectation**

Add a shell-level test asserting the app root exposes sidebar and workspace landmarks with token-driven classes.

Expected: FAIL because shell styles and structure do not exist.

- [ ] **Step 2: Import token/style layers**

Refactor `frontend/src/styles.css` into an import hub or minimal reset layer, then add token, layout, component, and module CSS files with semantic variables for:

- sidebar/background contrast
- button height/radius/border/shadow
- card radius/border/shadow
- marquee status colors
- clay-like pressed state
- spacing and typography scale

Expected: buildable style foundation with no component usage yet.

- [ ] **Step 3: Run focused verification**

Run: `cd frontend && npm run build`

Expected: PASS and CSS assets compile cleanly.

- [ ] **Step 4: Commit token layer**

```bash
git add frontend/src/main.tsx frontend/src/styles.css frontend/src/styles
git commit -m "feat: add workbench design tokens and style layers"
```

## Chunk 2: Build the shared shell

### Task 3: Introduce navigation and shell state model

**Files:**
- Create: `frontend/src/lib/navigation.ts`
- Create: `frontend/src/lib/ui-state.ts`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Write the failing navigation model test**

Add a test asserting module definitions include:

- `项目总览`
- `投标资料库`
- `要求确认`
- `章节编辑`
- `审校导出`
- `设置`

and that `投标资料库` contains the five approved tabs.

Expected: FAIL because navigation registry does not exist.

- [ ] **Step 2: Implement module and tab registry**

Create route-to-module mapping and tab metadata in `frontend/src/lib/navigation.ts`. Add helpers for current module, current tab, and fallback states. Add local UI state helpers for sidebar collapse and `Copilot` visibility.

Expected: route parsing logic moves out of `App.tsx`.

- [ ] **Step 3: Re-run tests**

Run: `cd frontend && npm run test -- --run`

Expected: PASS for navigation model coverage.

- [ ] **Step 4: Commit navigation registry**

```bash
git add frontend/src/lib/navigation.ts frontend/src/lib/ui-state.ts frontend/src/App.tsx frontend/src/layouts/workbench-shell.test.tsx
git commit -m "feat: add workbench navigation registry"
```

### Task 4: Build shared UI primitives

**Files:**
- Create: `frontend/src/components/ui/app-button.tsx`
- Create: `frontend/src/components/ui/app-card.tsx`
- Create: `frontend/src/components/ui/status-badge.tsx`
- Create: `frontend/src/components/ui/marquee-banner.tsx`
- Create: `frontend/src/components/ui/tab-strip.tsx`
- Create: `frontend/src/components/workspace/empty-state-card.tsx`
- Create: `frontend/src/components/workspace/stat-card.tsx`

- [ ] **Step 1: Write failing primitive smoke tests**

Add tests for:

- button variants share identical sizing tokens
- cards render consistent container classes
- tab strip marks selected tab accessibly
- marquee banner renders a single text lane

Expected: FAIL until primitives are implemented.

- [ ] **Step 2: Implement primitives**

Use a single prop-driven button component and card wrapper so every workspace action inherits the same visual system. Ensure icon-only or compact variants keep the same token family, not separate visual logic.

Expected: reusable primitives replace ad-hoc button/card markup.

- [ ] **Step 3: Run focused tests**

Run: `cd frontend && npm run test -- --run`

Expected: PASS for primitive component smoke tests.

- [ ] **Step 4: Commit primitives**

```bash
git add frontend/src/components/ui frontend/src/components/workspace frontend/src/layouts/workbench-shell.test.tsx
git commit -m "feat: add shared workbench UI primitives"
```

### Task 5: Build the workbench shell

**Files:**
- Create: `frontend/src/layouts/workbench-shell.tsx`
- Create: `frontend/src/components/navigation/sidebar.tsx`
- Create: `frontend/src/components/navigation/sidebar-user.tsx`
- Create: `frontend/src/components/workspace/workspace-header.tsx`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/layouts/workbench-shell.test.tsx`

- [ ] **Step 1: Write the failing shell test**

Add a smoke test asserting:

- sidebar exists
- collapse button exists
- username area exists at bottom
- workspace exists
- `Copilot` trigger exists but panel is collapsed by default

Expected: FAIL because shell is not wired.

- [ ] **Step 2: Implement the shell**

Create the two-column layout with:

- darker left sidebar
- brighter right workspace
- collapsible sidebar
- bottom user block and round management button
- top marquee slot
- top-right hidden `Copilot` anchor

Expected: every route renders inside a single persistent shell.

- [ ] **Step 3: Run tests and build**

Run: `cd frontend && npm run test -- --run && npm run build`

Expected: PASS for shell smoke tests and production build.

- [ ] **Step 4: Commit shell**

```bash
git add frontend/src/App.tsx frontend/src/layouts/workbench-shell.tsx frontend/src/components/navigation frontend/src/components/workspace/workspace-header.tsx frontend/src/layouts/workbench-shell.test.tsx
git commit -m "feat: add persistent frontend workbench shell"
```

## Chunk 3: Migrate modules into the shell

### Task 6: Migrate 项目总览 and 资料库 tabs

**Files:**
- Modify: `frontend/src/pages/project-list.tsx`
- Modify: `frontend/src/pages/upload.tsx`
- Modify: `frontend/src/pages/parse-results.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Write the failing integration test**

Add a route-level test asserting `投标资料库` renders the approved five-tab strip and card-based content containers.

Expected: FAIL because pages still render standalone page headers and tables.

- [ ] **Step 2: Refactor project overview**

Transform `project-list.tsx` into the overview workspace:

- remove standalone page header
- use shared header slot
- convert “新建项目” area into card + unified buttons
- ensure project items render as workbench cards

Expected: overview no longer looks like a separate landing page.

- [ ] **Step 3: Refactor 资料库 content**

Map current upload and parse data into tabbed card content:

- `历史投标文件` uses uploaded file cards
- `规范规程` can reuse parse/file status cards
- remaining tabs use prepared empty-state cards until data is wired

Expected: upload and parse pages visually align with the new workspace.

- [ ] **Step 4: Run verification**

Run: `cd frontend && npm run test -- --run && npm run build`

Expected: PASS and no standalone legacy header remains in these routes.

- [ ] **Step 5: Commit module migration**

```bash
git add frontend/src/pages/project-list.tsx frontend/src/pages/upload.tsx frontend/src/pages/parse-results.tsx frontend/src/App.tsx
git commit -m "feat: migrate overview and repository modules into workbench"
```

### Task 7: Migrate 要求确认 and 章节编辑

**Files:**
- Modify: `frontend/src/pages/requirements-confirmation.tsx`
- Modify: `frontend/src/pages/chapter-editor.tsx`

- [ ] **Step 1: Write the failing route behavior test**

Add tests asserting:

- top blocking warnings surface through marquee/banner data
- requirement items render as uniform cards
- chapter editor uses a card-based outline pane and editor pane

Expected: FAIL because pages still use page-local layouts and inline styles.

- [ ] **Step 2: Refactor 要求确认**

Move veto warnings into the banner/message model. Convert filters and confirmation actions to shared button styles. Render requirement entries as cards with status badges and compact metadata.

Expected: warnings are globally visible and content density improves.

- [ ] **Step 3: Refactor 章节编辑**

Move the outline list and edit area into shell-compatible cards. Replace ad-hoc toolbar/button styling with shared primitives. Keep editor behavior unchanged.

Expected: editor visually aligns with the rest of the workspace while preserving save flow.

- [ ] **Step 4: Run verification**

Run: `cd frontend && npm run test -- --run && npm run build`

Expected: PASS for confirmation/editor smoke coverage and build.

- [ ] **Step 5: Commit migration**

```bash
git add frontend/src/pages/requirements-confirmation.tsx frontend/src/pages/chapter-editor.tsx
git commit -m "feat: migrate confirmation and editor modules into workbench"
```

### Task 8: Migrate 审校导出 and unify status cards

**Files:**
- Modify: `frontend/src/pages/review-results.tsx`
- Modify: `frontend/src/pages/export.tsx`

- [ ] **Step 1: Write the failing status card test**

Add a test asserting review issues and export gates share the same card, badge, and button primitives.

Expected: FAIL because current pages still mix inline styles and emoji-like status rendering.

- [ ] **Step 2: Refactor 审校与导出**

Convert blocking alerts to banner feed inputs. Replace gate indicators and issue blocks with consistent cards and status badges. Remove inline color objects in favor of semantic severity tokens.

Expected: review/export pages become visually consistent and shell-native.

- [ ] **Step 3: Run verification**

Run: `cd frontend && npm run test -- --run && npm run build`

Expected: PASS and no inline style severity system remains in these modules.

- [ ] **Step 4: Commit migration**

```bash
git add frontend/src/pages/review-results.tsx frontend/src/pages/export.tsx
git commit -m "feat: migrate review and export modules into workbench"
```

## Chunk 4: Settings, Copilot, and polish

### Task 9: Implement 设置 module for AI API configuration

**Files:**
- Create: `frontend/src/pages/settings.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/lib/navigation.ts`

- [ ] **Step 1: Write the failing settings test**

Add a test asserting the settings module renders:

- provider card
- API key input
- base URL input
- model name input
- save action using shared button styles

Expected: FAIL because settings page does not exist.

- [ ] **Step 2: Implement settings workspace**

Create card-based settings content for AI model/API entry. Store values locally first unless an existing backend endpoint is available. Provide connection status placeholders without inventing new backend contracts.

Expected: settings fulfills the approved UI role without backend dependency creep.

- [ ] **Step 3: Run verification**

Run: `cd frontend && npm run test -- --run && npm run build`

Expected: PASS for settings smoke test and build.

- [ ] **Step 4: Commit settings**

```bash
git add frontend/src/pages/settings.tsx frontend/src/App.tsx frontend/src/lib/navigation.ts
git commit -m "feat: add AI model settings workspace"
```

### Task 10: Add hidden Copilot panel and keyboard interactions

**Files:**
- Create: `frontend/src/components/ui/copilot-panel.tsx`
- Modify: `frontend/src/layouts/workbench-shell.tsx`
- Modify: `frontend/src/lib/ui-state.ts`
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: Write the failing interaction test**

Add a test asserting:

- `Copilot` remains collapsed by default
- hover or explicit state opens it
- `Ctrl/Cmd + K` toggles it

Expected: FAIL because no panel or shortcut exists.

- [ ] **Step 2: Implement `Copilot` interaction**

Add a right-edge assistant trigger that expands on hover/focus and toggles on keyboard shortcut. Keep it lightweight and non-blocking; use placeholder collaboration content unless an existing data source is available.

Expected: approved hidden-assistant interaction works without disturbing primary workflows.

- [ ] **Step 3: Run verification**

Run: `cd frontend && npm run test -- --run && npm run build`

Expected: PASS for interaction smoke test and build.

- [ ] **Step 4: Commit `Copilot`**

```bash
git add frontend/src/components/ui/copilot-panel.tsx frontend/src/layouts/workbench-shell.tsx frontend/src/lib/ui-state.ts frontend/src/main.tsx
git commit -m "feat: add hidden copilot assistant interactions"
```

### Task 11: Final visual consistency and responsive pass

**Files:**
- Modify: `frontend/src/styles/tokens.css`
- Modify: `frontend/src/styles/layout.css`
- Modify: `frontend/src/styles/components.css`
- Modify: `frontend/src/styles/modules.css`
- Modify: any touched UI component/page files as needed

- [ ] **Step 1: Run visual checklist pass**

Verify and adjust:

- sidebar darker than workspace
- all workspace buttons same size and border/shadow system
- sidebar press state has subtle clay feel
- no unnecessary descriptive text blocks
- cards are the dominant content container
- collapsed sidebar still usable

Expected: any inconsistencies are identified before final polish.

- [ ] **Step 2: Implement final polish**

Tune spacing, focus states, marquee motion, card density, responsive breakpoints, and reduced-motion handling. Remove leftover inline styles and duplicated button classes.

Expected: interface feels cohesive across all modules.

- [ ] **Step 3: Run full verification**

Run: `cd frontend && npm run test -- --run && npm run build`

Expected: PASS for all UI tests and production build.

- [ ] **Step 4: Manual QA checklist**

Manually verify in browser:

- sidebar expand/collapse
- module switching
- repository tabs
- banner visibility on warning states
- settings input behavior
- `Ctrl/Cmd + K` for `Copilot`
- medium-width screen layout

Expected: approved interaction model matches design intent.

- [ ] **Step 5: Commit final polish**

```bash
git add frontend/src
git commit -m "feat: finalize unified frontend workbench redesign"
```

---

## Verification Commands

- `cd frontend && npm run test -- --run`
- `cd frontend && npm run build`

## Delivery Notes

- Keep existing backend API contracts unchanged during the refactor.
- Prefer semantic tokens over inline colors or style objects.
- Do not reintroduce standalone page headers once the shell is in place.
- If testing infrastructure proves too expensive, keep the shell smoke tests and build verification at minimum; do not skip final `npm run build`.

Plan complete and saved to `docs/superpowers/plans/2026-03-17-frontend-workbench-refactor.md`. Ready to execute?
